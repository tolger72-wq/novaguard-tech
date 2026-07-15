"""
app.py — TEK CASİNO sürümü.

Fark: Her endpoint'te '/tenant/{tenant_id}/...' yerine artık sadece
'/...' var. Çünkü tek casino olduğu için "hangi casino?" sorusuna
hiç gerek yok — hep aynı casino.
"""

import csv
import hmac
import io
import os
import secrets
from fastapi import FastAPI, Depends, File, Header, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Optional

import royal_math  # Kara Kutu Motoru
from database import SessionLocal, init_db, Card, GameState, Winners, GameConfig, LoyaltyPoints, get_or_create_config, get_or_create_state
from integrations import CasinoSystem
from card_generator import generate_cards
from sms_service import send_sms

# --- I. SABİTLER ---
LICENSE_KEY = os.getenv("DYNASTY_LICENSE_KEY", "KEY-GIRINIZ")
INTERNAL_KEY = os.getenv("DYNASTY_INTERNAL_KEY", "DYNASTY_SECRET_KEY")
MIN_WEEKLY_PRIZE_POOL_USD = 10000
WEEKLY_COMMISSION_RATE = 0.20
DAILY_BALL_LIMIT = 15
MIN_DRAW_INTERVAL_MINUTES = 15

PRIZE_SPLIT = {
    "c1": 0.10,      # 1. Çinko
    "c2": 0.15,      # 2. Çinko
    "t": 0.50,       # Tombala
    "amorti": 0.25,  # Amorti
}

try:
    engine_instance = royal_math.RoyalEngine(LICENSE_KEY)
except Exception as e:
    engine_instance = None
    print(f"HATA: Royal Engine başlatılamadı: {e}")

init_db()

# game_config/game_state singleton satırlarını (id=1) sunucu daha hiç istek
# almadan ÖNCE burada oluşturuyoruz. Sebep: get_or_create_config/state,
# satır yoksa "SELECT sonra INSERT" yapıyor — iki istek TAM AYNI ANDA gelip
# ikisi de "satır yok" görürse, ikisi de INSERT etmeye çalışır ve ikincisi
# "UNIQUE constraint failed" ile 500 döner. Bu durum tam olarak /bigscreen ve
# /admin sayfalarının kendi Promise.all([...]) ile /state, /prizes, /winners'ı
# AYNI ANDA çağırdığı ilk sayfa yüklemesinde (henüz hiçbir satır yokken) oluşur.
# Satırları burada, tek seferde ve daha rekabet yokken yaratmak sorunu kökten çözer.
with SessionLocal() as _startup_db:
    get_or_create_config(_startup_db)
    get_or_create_state(_startup_db)

app = FastAPI(title="Dynasty Bingo — Tek Casino", version="1.0-single")

# 🧪 SİMÜLASYON MODU UYARISI — CasinoSystem (integrations.py) henüz gerçek bir
# casino CMS/CRM'sine bağlı değil, sadakat puanları hash tabanlı UYDURMA veridir.
# Bu veri, ödül paylaşımı (kimin kazanacağı, Amorti dağılımı) kararlarını
# etkiliyor — gerçek casino verisine bağlanana kadar bunu açıkça göstermeliyiz.
print("=" * 60)
print("🧪 SİMÜLASYON MODU: Sadakat puanları gerçek CMS'e bağlı değil,")
print("   integrations.py içinde hash tabanlı uydurma veri kullanılıyor.")
print("   Ödül paylaşım kararları (kim kazanır, Amorti dağılımı) bu")
print("   sahte veriyle yapılıyor. Gerçek casino verisine bağlanmadan")
print("   canlıya (gerçek ödülle) ALINMAMALI.")
print("=" * 60)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def verify_internal_key(x_internal_key: str = Header(...)):
    """
    Hem yönetici işlemlerini (start-week, draw) hem de kart/SMS üreten
    personel işlemlerini (cards, reception/register) korur — hepsi aynı
    paylaşılan iç anahtarı kullanır. hmac.compare_digest kullanıyoruz
    çünkü normal '==' karşılaştırması zamanlama saldırısına açık olurdu.
    """
    if not hmac.compare_digest(x_internal_key, INTERNAL_KEY):
        raise HTTPException(status_code=401, detail="Geçersiz internal key.")
    return True


# --- II. PYDANTIC MODELLERİ ---

class StartWeekInput(BaseModel):
    declared_weekly_pool_usd: int = Field(..., ge=MIN_WEEKLY_PRIZE_POOL_USD)
    # 🆕 Casino bu sayıları isterse değiştirebilir, vermezse varsayılanlar kullanılır.
    max_winners_c1: int = Field(default=4, ge=1, description="1.Çinko'yu en fazla kaç kişi paylaşabilir")
    max_winners_c2: int = Field(default=4, ge=1, description="2.Çinko'yu en fazla kaç kişi paylaşabilir")
    max_winners_t: int = Field(default=2, ge=1, description="Tombala'yı en fazla kaç kişi paylaşabilir")
    amorti_top_n: int = Field(default=5, ge=1, description="Amorti'yi en fazla kaç kişi paylaşabilir")


class BuyCardsInput(BaseModel):
    # NOT: "Buy" ismi tarihi nedenlerle kaldı ama kartlar ÜCRETSİZ —
    # casino bunu bir eğlence/atraksiyon olarak sunuyor, para alınmıyor.
    # Oyuncu başına en fazla 1 kart kuralı var (bkz. buy_cards) — bu yüzden
    # "count" alanı kasıtlı olarak kaldırıldı, her çağrı tam olarak 1 kart üretir.
    owner_id: str


class ReceptionRegisterInput(BaseModel):
    """Resepsiyonda misafir giriş yaptığında doldurulacak bilgiler."""
    guest_name: str = Field(..., description="Misafirin adı veya üyelik ID'si")
    phone_number: str = Field(..., description="SMS gönderilecek telefon numarası, örn. +905551234567")
    # NOT: "card_count" kasıtlı olarak kaldırıldı — oyuncu başına en fazla 1 kart var.


class ManualDrawInput(BaseModel):
    force: bool = False
    is_panic_mode: bool = False


class CardStatusOutput(BaseModel):
    id: int
    owner_id: str
    grid: List[List[Optional[int]]]
    marked_count: int
    score: int


class GameStateOutput(BaseModel):
    drawn_numbers: List[int]
    flags: Dict[str, bool]
    daily_draw_count: int
    is_paid_for_current_week: bool
    current_week_start_date: Optional[date]


class WinnerOutput(BaseModel):
    id: int
    type: str
    users: List[str]
    prize_details: Dict[str, Any]
    draw_time: datetime


class PublicPrizesOutput(BaseModel):
    """
    🔒 GÜVENLİK NOTU: Bu, halka açık (public) bir çıktı. Bilerek SADECE toplam
    ödül miktarlarını içeriyor. 'max_winners_c1' gibi 'kaç kişiye bölünecek'
    ayarlarını buraya HİÇ EKLEMİYORUZ — o bilgi yalnızca yöneticide kalmalı,
    yoksa müşteri önceden "bu ödülü en fazla 2 kişi alacak" diye öğrenip
    oyunun sürprizini/adalet algısını bozabilir.
    """
    prize_c1_usd: int
    prize_c2_usd: int
    prize_t_usd: int
    prize_amorti_usd: int


class LoyaltyPushItem(BaseModel):
    owner_id: str
    points: int = Field(..., ge=0)


class LoyaltyPushInput(BaseModel):
    """
    Casino'nun CMS/CRM'i, oyuncuların sadakat puanlarını buraya toplu halde
    gönderir (biz CMS'e bağlanmıyoruz, CMS bize bağlanıyor — bkz. README).
    """
    records: List[LoyaltyPushItem]


# --- III. ANA ÇEKİLİŞ MANTIĞI ---

def resolve_loyalty_points(db: Session, owner_id: str) -> int:
    """
    Önce gerçek casino verisini arar (CMS'ten /integrations/loyalty-points ile
    PUSH edilmiş ya da /integrations/loyalty-csv ile yüklenmiş). Bulamazsa
    integrations.py'deki CasinoSystem simülasyon değerine düşer — böylece
    entegrasyon henüz kurulmamış bir casino'da sistem yine de çalışmaya devam
    eder, sadece o oyuncu için puan gerçek değil uydurma olur.
    """
    real = db.query(LoyaltyPoints).filter(LoyaltyPoints.owner_id == owner_id).first()
    if real:
        return real.points
    return CasinoSystem.get_loyalty_points(owner_id)


def automatic_draw_process(db: Session, force: bool = False, is_panic_mode: bool = False):
    """Tek casino için otomatik top çekme işlemi. Worker her tetiklediğinde bunu çağırır."""
    if not engine_instance or engine_instance.locked:
        print("Royal Engine kilitli veya başlatılamadı. Çekiliş yapılmadı.")
        return

    config = get_or_create_config(db)
    state = get_or_create_state(db)

    if state.flags.get("over", False):
        print("OYUN BİTMİŞ. Çekiliş yapılmadı.")
        return

    now = datetime.now()
    today = now.date()

    # A. Haftalık süre kontrolü: 7 gün dolduysa ve tombala vurulmadıysa oyunu kapat
    if config.current_week_start_date and today >= config.current_week_start_date + timedelta(days=7):
        state.flags["over"] = True
        config.is_paid_for_current_week = False
        db.commit()
        print("HAFTA SÜRESİ DOLDU. Oyun otomatik kapatıldı.")
        return

    # B. Günlük top limiti
    if state.last_session_date != today:
        state.daily_draw_count = 0
        state.last_session_date = today

    if not force and state.daily_draw_count >= DAILY_BALL_LIMIT:
        print(f"GÜNLÜK LİMİT AŞILDI ({DAILY_BALL_LIMIT} top). Bekleniyor.")
        return

    # C. Çekimler arası minimum süre
    if not force and state.last_draw_time and now < state.last_draw_time + timedelta(minutes=MIN_DRAW_INTERVAL_MINUTES):
        print(f"SÜRE KONTROLÜ. {MIN_DRAW_INTERVAL_MINUTES}dk dolmadı. Bekleniyor.")
        return

    # D. Kara Kutu'dan güvenli top iste
    time_since_start = now - state.start_date
    day_index = time_since_start.days

    active_cards = db.query(Card.grid).all()
    card_grids = [{"grid": card[0]} for card in active_cards]

    new_ball = engine_instance.get_safe_number(
        remaining=list(set(range(1, 91)) - set(state.drawn_numbers)),
        drawn=state.drawn_numbers,
        active_cards=card_grids,
        day_index=day_index,
        flags=state.flags,
        is_panic_mode=is_panic_mode,
    )

    if new_ball is None:
        print("Top kalmadı veya kilitli motor. Çekiliş durduruldu.")
        return

    state.drawn_numbers.append(new_ball)
    state.daily_draw_count += 1
    state.last_draw_time = now

    print(f"ÇEKİLİŞ BAŞARILI. Top: {new_ball} | Güncel Top Sayısı: {len(state.drawn_numbers)}")

    # E. Kazanan kontrolü — HER ödül türü kendi anında, çoklu kazananla işlenir.
    # Önce her kartın şu anki durumunu (kaç çinko yaptı, kaç sayısı işaretli) hesaplıyoruz.
    drawn_set = set(state.drawn_numbers)
    card_scores = []
    for card in db.query(Card).all():
        score = engine_instance._analyze(card.grid, drawn_set)
        marked = sum(len([n for n in row if n in drawn_set]) for row in card.grid)
        card_scores.append((card, score, marked))

    def _unique_by_owner(cards):
        """
        owner_id başına en fazla 1 kart kuralı /cards ve /reception/register'da
        zaten uygulanıyor, yani normal koşullarda burada hiç tekrar olmaz. Yine de
        aynı kişi iki kez listede görünürse (örn. eski/bozuk bir veritabanı kaydı)
        ödül parasının kişi başına değil kart başına hesaplanıp yanlışlıkla
        ikiye/üçe bölünmesini önlemek için savunma amaçlı tekilleştiriyoruz.
        """
        seen = set()
        unique = []
        for c in cards:
            if c.owner_id not in seen:
                seen.add(c.owner_id)
                unique.append(c)
        return unique

    def pick_winners(qualifying_cards, max_count):
        """
        Bir ödülü hak eden kartlar listesi verilir. Eğer sayı, izin verilen
        maksimum kazanan sayısından FAZLAYSA, sadakat puanı en yüksek olanlar
        seçilir (herkes değil, sadece en sadık N kişi ödülü alır).
        """
        qualifying_cards = _unique_by_owner(qualifying_cards)
        if len(qualifying_cards) <= max_count:
            return qualifying_cards
        ranked = sorted(qualifying_cards, key=lambda c: resolve_loyalty_points(db, c.owner_id), reverse=True)
        return ranked[:max_count]

    # --- 1. ÇİNKO (score >= 1) ---
    if not state.flags.get("c1", False):
        qualifiers = [card for card, score, marked in card_scores if score >= 1]
        if qualifiers:
            winners = pick_winners(qualifiers, config.max_winners_c1)
            per_winner = round(config.prize_c1_usd / len(winners), 2)
            db.add(Winners(
                type="cinko1",
                users=[w.owner_id for w in winners],
                prize_details={"per_winner_usd": per_winner, "total_usd": config.prize_c1_usd},
                week_start_date=state.start_date,
            ))
            state.flags["c1"] = True
            print(f"1. ÇİNKO! {[w.owner_id for w in winners]} paylaştı (kişi başı ${per_winner}).")

    # --- 2. ÇİNKO (score >= 2) ---
    if not state.flags.get("c2", False):
        qualifiers = [card for card, score, marked in card_scores if score >= 2]
        if qualifiers:
            winners = pick_winners(qualifiers, config.max_winners_c2)
            per_winner = round(config.prize_c2_usd / len(winners), 2)
            db.add(Winners(
                type="cinko2",
                users=[w.owner_id for w in winners],
                prize_details={"per_winner_usd": per_winner, "total_usd": config.prize_c2_usd},
                week_start_date=state.start_date,
            ))
            state.flags["c2"] = True
            print(f"2. ÇİNKO! {[w.owner_id for w in winners]} paylaştı (kişi başı ${per_winner}).")

    # --- TOMBALA (score == 3) ---
    if not state.flags.get("t", False):
        qualifiers = [card for card, score, marked in card_scores if score == 3]
        if qualifiers:
            winners = pick_winners(qualifiers, config.max_winners_t)
            per_winner = round(config.prize_t_usd / len(winners), 2)
            db.add(Winners(
                type="tombala",
                users=[w.owner_id for w in winners],
                prize_details={"per_winner_usd": per_winner, "total_usd": config.prize_t_usd},
                week_start_date=state.start_date,
            ))
            print(f"🏆 TOMBALA! {[w.owner_id for w in winners]} paylaştı (kişi başı ${per_winner}).")

            # --- AMORTİ --- (tombala vurulduğunda, tombalaya 1 sayı kalanlar arasından)
            # NOT: eskiden 'top_n' kart bazlıydı ve aynı kişinin birden fazla
            # kartı olursa payouts sözlüğünde o kişinin payı sessizce üzerine
            # yazılıp gerçek toplamın altında bir tutar kaydediliyordu
            # (kişi başı değil kart başı hesaplanıp owner_id anahtarlı bir
            # sözlüğe yazıldığı için). _unique_by_owner ile bunu önlüyoruz.
            eligible = _unique_by_owner([card for card, score, marked in card_scores if marked == 14])
            if config.prize_amorti_usd > 0 and eligible:
                ranked = sorted(eligible, key=lambda c: resolve_loyalty_points(db, c.owner_id), reverse=True)
                top_n = ranked[:config.amorti_top_n]
                total_points = sum(resolve_loyalty_points(db, c.owner_id) for c in top_n)
                if total_points > 0:
                    payouts = {c.owner_id: round((resolve_loyalty_points(db, c.owner_id) / total_points) * config.prize_amorti_usd, 2) for c in top_n}
                    db.add(Winners(type="amorti", users=[c.owner_id for c in top_n], prize_details={"payouts": payouts}, week_start_date=state.start_date))
                    print(f"ÖDÜL: En yüksek puana sahip {len(top_n)} kişiye Amorti dağıtıldı.")

            state.flags["t"] = True
            state.flags["over"] = True

    db.commit()
    print("İşlem tamamlandı.")


# =====================================================================
# IV. API UÇLARI
# =====================================================================

@app.get("/health")
def health_check(db: Session = Depends(get_db)):
    real_count = db.query(LoyaltyPoints).count()
    return {
        "status": "ok",
        "engine_locked": engine_instance.locked if engine_instance else True,
        # 🧪 real_loyalty_records=0 ise HİÇBİR oyuncu için gerçek sadakat verisi
        # push/upload edilmemiş demektir — tüm ödül paylaşım kararları
        # integrations.py'deki uydurma veriyle veriliyor. >0 ise o kadar oyuncu
        # için gerçek veri var, geri kalanlar hâlâ simülasyona düşüyor (karışık
        # durum normaldir — entegrasyon aşamalı da kurulabilir).
        "loyalty_data_source": "simulation" if real_count == 0 else "mixed",
        "real_loyalty_records": real_count,
    }


# --- ADMIN UÇLARI ---

@app.post("/admin/start-week", dependencies=[Depends(verify_internal_key)])
def start_week(payload: StartWeekInput, db: Session = Depends(get_db)):
    """Haftalık ödemeyi işler, komisyonu keser, ödülleri böler, oyunu sıfırlar."""
    config = get_or_create_config(db)
    state = get_or_create_state(db)

    declared = payload.declared_weekly_pool_usd
    commission = declared * WEEKLY_COMMISSION_RATE
    net_pool = declared - commission

    config.declared_weekly_pool_usd = declared
    config.prize_c1_usd = round(net_pool * PRIZE_SPLIT["c1"], 2)
    config.prize_c2_usd = round(net_pool * PRIZE_SPLIT["c2"], 2)
    config.prize_t_usd = round(net_pool * PRIZE_SPLIT["t"], 2)
    config.prize_amorti_usd = round(net_pool * PRIZE_SPLIT["amorti"], 2)
    config.current_week_start_date = date.today()
    config.is_paid_for_current_week = True

    # 🆕 Kaç kişinin paylaşacağı ayarlarını kaydet
    config.max_winners_c1 = payload.max_winners_c1
    config.max_winners_c2 = payload.max_winners_c2
    config.max_winners_t = payload.max_winners_t
    config.amorti_top_n = payload.amorti_top_n

    state.start_date = datetime.now()
    state.drawn_numbers = []
    state.flags = {"c1": False, "c2": False, "t": False, "over": False}
    state.daily_draw_count = 0
    state.last_session_date = None
    state.last_draw_time = None

    db.query(Card).delete()  # Yeni hafta = yeni kartlar

    db.commit()
    return {
        "message": "Hafta başlatıldı.",
        "declared_weekly_pool_usd": declared,
        "commission_usd": round(commission, 2),
        "net_pool_usd": round(net_pool, 2),
        "prizes": {
            "c1": config.prize_c1_usd,
            "c2": config.prize_c2_usd,
            "t": config.prize_t_usd,
            "amorti": config.prize_amorti_usd,
        },
        "max_winners": {
            "c1": config.max_winners_c1,
            "c2": config.max_winners_c2,
            "t": config.max_winners_t,
            "amorti": config.amorti_top_n,
        },
    }


@app.post("/admin/draw", dependencies=[Depends(verify_internal_key)])
def manual_draw(payload: ManualDrawInput, db: Session = Depends(get_db)):
    state_before = get_or_create_state(db)
    before_count = len(state_before.drawn_numbers)

    automatic_draw_process(db, force=payload.force, is_panic_mode=payload.is_panic_mode)

    state = get_or_create_state(db)
    return {
        "drew_new_ball": len(state.drawn_numbers) > before_count,
        "drawn_numbers": state.drawn_numbers,
        "flags": state.flags,
    }


@app.get("/admin", response_class=HTMLResponse)
def admin_page():
    """
    Yönetici paneli: hafta başlatma ve manuel çekiliş, tarayıcıdan tıklanarak
    yapılabilsin diye. Bundan önce bu iki işlem SADECE ham HTTP isteğiyle
    (curl/Postman) yapılabiliyordu — casino personelinin kullanabileceği bir
    ekran yoktu. /reception ile aynı desende: sayfa herkese açık, ama gerçek
    işlemler (start-week, draw) sunucu tarafında zaten x-internal-key ile
    korunuyor; anahtar tarayıcıda sadece bir kez girilip sessionStorage'da
    tutulur (reception ile aynı anahtarı paylaşır).
    """
    html = """
<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Yönetici Paneli — Dynasty Bingo</title>
<style>
  body { margin:0; padding:24px; background:#0A1120; color:#E7ECF3; font-family:-apple-system,sans-serif; max-width:720px; margin-left:auto; margin-right:auto; }
  h1 { font-size:22px; margin-bottom:4px; }
  h2 { font-size:15px; color:#8593AC; font-weight:600; margin:0 0 14px; text-transform:uppercase; letter-spacing:.04em; }
  .sub { font-size:13px; color:#8593AC; margin-bottom:20px; }
  section { background:#121B2E; border:1px solid #223049; border-radius:12px; padding:20px; margin-bottom:16px; }
  label { display:block; font-size:13px; color:#8593AC; margin-top:14px; margin-bottom:6px; }
  input[type=text], input[type=password], input[type=number], input[type=file] {
    width:100%; padding:12px; font-size:16px; border-radius:8px; border:1px solid #223049;
    background:#16213A; color:#E7ECF3; box-sizing:border-box;
  }
  code { background:#16213A; border:1px solid #223049; border-radius:4px; padding:1px 6px; font-size:12px; }
  .row { display:grid; grid-template-columns:1fr 1fr; gap:12px; }
  .checkline { display:flex; align-items:flex-start; gap:10px; margin-top:14px; }
  .checkline input { margin-top:3px; }
  .checkline .txt { font-size:13px; color:#B7C0D6; line-height:1.5; }
  .checkline.danger .txt { color:#E8B94D; }
  .checkline.danger .txt b { color:#E85D5D; }
  button { margin-top:18px; width:100%; padding:14px; font-size:16px; font-weight:700; border-radius:8px; border:none; background:#2DD4E8; color:#06222B; cursor:pointer; }
  button.warn { background:#E8B94D; }
  button:disabled { opacity:0.5; }
  .result { margin-top:14px; padding:14px; border-radius:8px; font-size:13px; line-height:1.5; white-space:pre-wrap; }
  .result.ok { background:rgba(45,212,232,0.1); border:1px solid rgba(45,212,232,0.3); color:#2DD4E8; }
  .result.err { background:rgba(232,93,93,0.1); border:1px solid rgba(232,93,93,0.3); color:#E85D5D; }

  .statgrid { display:grid; grid-template-columns:repeat(auto-fit,minmax(140px,1fr)); gap:10px; margin-bottom:14px; }
  .stat { background:#16213A; border:1px solid #223049; border-radius:8px; padding:12px; }
  .stat .label { font-size:11px; color:#8593AC; margin-bottom:4px; text-transform:uppercase; letter-spacing:.03em; }
  .stat .value { font-size:18px; font-weight:700; }
  .pill { display:inline-block; padding:3px 9px; border-radius:999px; font-size:11px; font-weight:700; }
  .pill.open { background:rgba(45,212,232,0.15); color:#2DD4E8; }
  .pill.locked { background:rgba(133,147,172,0.15); color:#8593AC; }
  .pill.paid { background:rgba(45,212,232,0.15); color:#2DD4E8; }
  .pill.unpaid { background:rgba(232,93,93,0.15); color:#E85D5D; }

  .winner-row { display:flex; justify-content:space-between; padding:10px 0; border-bottom:1px solid #223049; font-size:13px; }
  .winner-row:last-child { border-bottom:none; }
  .winner-type { color:#E8B94D; font-weight:700; }
  .empty { color:#8593AC; font-size:13px; }
</style>
</head>
<body>
  <h1>🎛️ Yönetici Paneli</h1>
  <div class="sub">Hafta başlatma ve manuel çekiliş buradan yapılır. Diğer tüm ekranlar (resepsiyon, büyük ekran, oyuncu kartı) bu panelden bağımsız çalışmaya devam eder.</div>

  <section>
    <h2>Yönetici Anahtarı</h2>
    <input id="staffKey" type="password" placeholder="x-internal-key değeri">
  </section>

  <section>
    <h2>Canlı Durum</h2>
    <div class="statgrid" id="statgrid"><div class="empty">Yükleniyor...</div></div>
    <div id="winnersBox"><div class="empty">Yükleniyor...</div></div>
  </section>

  <section>
    <h2>Haftayı Başlat</h2>
    <div class="sub" style="margin-top:-8px;">⚠️ Bu, bu haftaki TÜM kartları siler ve oyunu sıfırdan başlatır. Sadece yeni bir hafta başlarken kullanın.</div>

    <label>Haftalık İlan Edilen Ödül Havuzu (USD, komisyon öncesi, en az 10.000)</label>
    <input id="poolInput" type="number" min="10000" step="100" placeholder="örn: 20000">

    <div class="row">
      <div>
        <label>1.Çinko en fazla kaç kişi paylaşır</label>
        <input id="maxC1Input" type="number" min="1" value="4">
      </div>
      <div>
        <label>2.Çinko en fazla kaç kişi paylaşır</label>
        <input id="maxC2Input" type="number" min="1" value="4">
      </div>
      <div>
        <label>Tombala en fazla kaç kişi paylaşır</label>
        <input id="maxTInput" type="number" min="1" value="2">
      </div>
      <div>
        <label>Amorti en fazla kaç kişiye dağılır</label>
        <input id="amortiInput" type="number" min="1" value="5">
      </div>
    </div>

    <button id="startWeekBtn" onclick="startWeek()">Haftayı Başlat</button>
    <div id="startWeekResult"></div>
  </section>

  <section>
    <h2>Manuel Çekiliş</h2>

    <div class="checkline">
      <input id="forceCheck" type="checkbox">
      <div class="txt">Günlük top limitini (15) ve çekimler arası 15dk bekleme süresini yok say.</div>
    </div>
    <div class="checkline danger">
      <input id="panicCheck" type="checkbox">
      <div class="txt"><b>PANİK MODU</b> — 1./2./3. gün kimse kazanamasın kuralını (gün kilitlerini) TAMAMEN kapatır. Sadece haftayı acilen bitirmeniz gerektiğinde kullanın; normal oyunda İŞARETLEMEYİN, yoksa ödüller günlere yayılmadan hemen dağılabilir.</div>
    </div>

    <button class="warn" id="drawBtn" onclick="manualDraw()">Top Çek</button>
    <div id="drawResult"></div>
  </section>

  <section>
    <h2>Sadakat Verisi</h2>
    <div class="sub" style="margin-top:-8px;">Kazanan seçimi ve Amorti dağılımı sadakat puanına göre yapılır. Gerçek veri
    olmayan oyuncular için sistem otomatik olarak simülasyon değeri kullanır (bkz. <code>/health</code>).
    Casino'nun CMS'i <code>/integrations/loyalty-points</code>'e API ile puan gönderebilir; API'ye bağlanacak
    IT kapasitesi yoksa aşağıdan CSV de yüklenebilir (iki sütun: <code>owner_id,points</code>).</div>

    <label>CSV Dosyası</label>
    <input id="csvFile" type="file" accept=".csv,text/csv">

    <button id="csvBtn" onclick="uploadCsv()">CSV Yükle</button>
    <div id="csvResult"></div>
  </section>

<script>
const staffKeyInput = document.getElementById('staffKey');
staffKeyInput.value = sessionStorage.getItem('dynastyStaffKey') || '';
staffKeyInput.addEventListener('input', () => sessionStorage.setItem('dynastyStaffKey', staffKeyInput.value.trim()));

function fmt(n) { return "$" + Number(n).toLocaleString("en-US"); }

async function refreshStatus() {
  try {
    const [stateRes, prizesRes, winnersRes, healthRes] = await Promise.all([
      fetch('/state'), fetch('/prizes'), fetch('/winners'), fetch('/health')
    ]);
    const state = await stateRes.json();
    const prizes = await prizesRes.json();
    const winners = await winnersRes.json();
    const health = await healthRes.json();

    const paidPill = state.is_paid_for_current_week
      ? '<span class="pill paid">Ödendi</span>' : '<span class="pill unpaid">Ödenmedi</span>';
    const lockPill = (open) => open ? '<span class="pill open">Açık</span>' : '<span class="pill locked">Kilitli</span>';
    const loyaltyPill = health.real_loyalty_records > 0
      ? `<span class="pill paid">${health.real_loyalty_records} gerçek</span>`
      : '<span class="pill unpaid">Simülasyon</span>';

    document.getElementById('statgrid').innerHTML = `
      <div class="stat"><div class="label">Hafta</div><div class="value">${paidPill}</div></div>
      <div class="stat"><div class="label">Çekilen Top</div><div class="value">${state.drawn_numbers.length} / 90</div></div>
      <div class="stat"><div class="label">Bugünkü Çekim</div><div class="value">${state.daily_draw_count} / 15</div></div>
      <div class="stat"><div class="label">1.Çinko</div><div class="value">${lockPill(state.flags.c1)}</div></div>
      <div class="stat"><div class="label">2.Çinko</div><div class="value">${lockPill(state.flags.c2)}</div></div>
      <div class="stat"><div class="label">Tombala</div><div class="value">${lockPill(state.flags.t)}</div></div>
      <div class="stat"><div class="label">1.Çinko Ödülü</div><div class="value">${fmt(prizes.prize_c1_usd)}</div></div>
      <div class="stat"><div class="label">2.Çinko Ödülü</div><div class="value">${fmt(prizes.prize_c2_usd)}</div></div>
      <div class="stat"><div class="label">Tombala Ödülü</div><div class="value">${fmt(prizes.prize_t_usd)}</div></div>
      <div class="stat"><div class="label">Amorti Ödülü</div><div class="value">${fmt(prizes.prize_amorti_usd)}</div></div>
      <div class="stat"><div class="label">Sadakat Verisi</div><div class="value">${loyaltyPill}</div></div>
    `;

    const winnersBox = document.getElementById('winnersBox');
    if (winners.length === 0) {
      winnersBox.innerHTML = '<div class="empty">Bu hafta henüz kazanan yok.</div>';
    } else {
      winnersBox.innerHTML = winners.map(w => {
        const names = w.users.join(', ');
        const amount = w.prize_details.per_winner_usd
          ? `${fmt(w.prize_details.per_winner_usd)} / kişi` : 'Detaylar için /winners bakın';
        return `<div class="winner-row"><span><span class="winner-type">${w.type.toUpperCase()}</span> — ${names}</span><span>${amount}</span></div>`;
      }).join('');
    }
  } catch (e) {
    document.getElementById('statgrid').innerHTML = '<div class="empty">Durum alınamadı, tekrar deneniyor...</div>';
  }
}

async function startWeek() {
  const staffKey = staffKeyInput.value.trim();
  const resultBox = document.getElementById('startWeekResult');
  const btn = document.getElementById('startWeekBtn');

  if (!staffKey) { resultBox.className = 'result err'; resultBox.textContent = 'Yönetici anahtarını girin.'; return; }

  const pool = parseInt(document.getElementById('poolInput').value, 10);
  if (!pool || pool < 10000) { resultBox.className = 'result err'; resultBox.textContent = 'Ödül havuzu en az 10.000 USD olmalı.'; return; }

  if (!confirm('Yeni hafta başlatılacak. Bu haftaki TÜM kartlar silinecek. Emin misiniz?')) return;

  btn.disabled = true; btn.textContent = 'Başlatılıyor...';
  try {
    const res = await fetch('/admin/start-week', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'x-internal-key': staffKey },
      body: JSON.stringify({
        declared_weekly_pool_usd: pool,
        max_winners_c1: parseInt(document.getElementById('maxC1Input').value, 10) || 4,
        max_winners_c2: parseInt(document.getElementById('maxC2Input').value, 10) || 4,
        max_winners_t: parseInt(document.getElementById('maxTInput').value, 10) || 2,
        amorti_top_n: parseInt(document.getElementById('amortiInput').value, 10) || 5,
      })
    });
    const data = await res.json();
    if (res.ok) {
      resultBox.className = 'result ok';
      resultBox.textContent = `✅ ${data.message}\nNet havuz: ${fmt(data.net_pool_usd)} (komisyon: ${fmt(data.commission_usd)})\n1.Çinko: ${fmt(data.prizes.c1)} · 2.Çinko: ${fmt(data.prizes.c2)} · Tombala: ${fmt(data.prizes.t)} · Amorti: ${fmt(data.prizes.amorti)}`;
      refreshStatus();
    } else {
      resultBox.className = 'result err';
      resultBox.textContent = `Hata: ${data.detail || 'Bilinmeyen hata'}`;
    }
  } catch (e) {
    resultBox.className = 'result err'; resultBox.textContent = 'Bağlantı hatası, tekrar deneyin.';
  }
  btn.disabled = false; btn.textContent = 'Haftayı Başlat';
}

async function manualDraw() {
  const staffKey = staffKeyInput.value.trim();
  const resultBox = document.getElementById('drawResult');
  const btn = document.getElementById('drawBtn');

  if (!staffKey) { resultBox.className = 'result err'; resultBox.textContent = 'Yönetici anahtarını girin.'; return; }

  const panicMode = document.getElementById('panicCheck').checked;
  if (panicMode && !confirm('PANİK MODU açık: gün kilitleri tamamen kapanacak. Emin misiniz?')) return;

  btn.disabled = true; btn.textContent = 'Çekiliyor...';
  try {
    const res = await fetch('/admin/draw', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'x-internal-key': staffKey },
      body: JSON.stringify({
        force: document.getElementById('forceCheck').checked,
        is_panic_mode: panicMode,
      })
    });
    const data = await res.json();
    if (res.ok) {
      resultBox.className = 'result ok';
      const lastBall = data.drawn_numbers.length ? data.drawn_numbers[data.drawn_numbers.length - 1] : '—';
      resultBox.textContent = data.drew_new_ball
        ? `✅ Top çekildi: ${lastBall} (toplam ${data.drawn_numbers.length})`
        : 'Top çekilmedi (limit/süre kontrolüne takıldı veya oyun bitti — force işaretleyin ya da bekleyin).';
      refreshStatus();
    } else {
      resultBox.className = 'result err';
      resultBox.textContent = `Hata: ${data.detail || 'Bilinmeyen hata'}`;
    }
  } catch (e) {
    resultBox.className = 'result err'; resultBox.textContent = 'Bağlantı hatası, tekrar deneyin.';
  }
  btn.disabled = false; btn.textContent = 'Top Çek';
}

async function uploadCsv() {
  const staffKey = staffKeyInput.value.trim();
  const resultBox = document.getElementById('csvResult');
  const btn = document.getElementById('csvBtn');
  const fileInput = document.getElementById('csvFile');

  if (!staffKey) { resultBox.className = 'result err'; resultBox.textContent = 'Yönetici anahtarını girin.'; return; }
  if (!fileInput.files.length) { resultBox.className = 'result err'; resultBox.textContent = 'Bir CSV dosyası seçin.'; return; }

  btn.disabled = true; btn.textContent = 'Yükleniyor...';
  try {
    const formData = new FormData();
    formData.append('file', fileInput.files[0]);
    const res = await fetch('/integrations/loyalty-csv', {
      method: 'POST',
      headers: { 'x-internal-key': staffKey },
      body: formData,
    });
    const data = await res.json();
    if (res.ok) {
      resultBox.className = 'result ok';
      resultBox.textContent = `✅ ${data.message}`;
      fileInput.value = '';
      refreshStatus();
    } else {
      resultBox.className = 'result err';
      resultBox.textContent = `Hata: ${data.detail || 'Bilinmeyen hata'}`;
    }
  } catch (e) {
    resultBox.className = 'result err'; resultBox.textContent = 'Bağlantı hatası, tekrar deneyin.';
  }
  btn.disabled = false; btn.textContent = 'CSV Yükle';
}

refreshStatus();
setInterval(refreshStatus, 4000);
</script>
</body>
</html>
"""
    return HTMLResponse(html)


# =====================================================================
# VIII. ENTEGRASYON UÇLARI — Gerçek sadakat verisi
# 🔌 Casino'nun CMS/CRM'i BİZE bağlanır (biz CMS'e bağlanmıyoruz). Sebep: çoğu
# casino ağında dışarıdan içeri bağlantıya (bize erişim) izin vermek IT için
# zor onaylanır; dışarıya bağlantı açmaya (CMS'ten bize) izin vermek çok daha
# kolaydır. CMS'in API çağırma kapasitesi yoksa /integrations/loyalty-csv
# yedek yolu var — iki sütunlu bir CSV (owner_id,points) yeterli.
# =====================================================================

@app.post("/integrations/loyalty-points", dependencies=[Depends(verify_internal_key)])
def push_loyalty_points(payload: LoyaltyPushInput, db: Session = Depends(get_db)):
    """
    Casino'nun CMS'i, güncel sadakat puanlarını burada toplu olarak gönderir
    (örn. her gece bir zamanlanmış görevle). Aynı owner_id tekrar gönderilirse
    üzerine yazılır (upsert) — CMS her seferinde TÜM güncel listeyi
    gönderebilir, eski/silinen oyuncuları burada ayrıca silmemize gerek yok.
    """
    updated = 0
    for item in payload.records:
        existing = db.query(LoyaltyPoints).filter(LoyaltyPoints.owner_id == item.owner_id).first()
        if existing:
            existing.points = item.points
        else:
            db.add(LoyaltyPoints(owner_id=item.owner_id, points=item.points))
        updated += 1
    db.commit()
    return {"message": f"{updated} oyuncunun sadakat puanı güncellendi.", "updated": updated}


@app.post("/integrations/loyalty-csv", dependencies=[Depends(verify_internal_key)])
async def upload_loyalty_csv(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """
    📄 YEDEK YOL — CMS'in API çağırma kapasitesi yoksa (küçük casino'larda IT
    ekibi olmayabilir), puanlar basit bir CSV dosyası olarak buraya
    yüklenebilir. Beklenen format, başlık satırı dahil ya da hariç iki sütun:
        owner_id,points
        Ahmet Kaya,4200
        Tamar Gelashvili,7800
    Aynı owner_id birden fazla satırda geçerse son satır geçerli olur.
    """
    content = (await file.read()).decode("utf-8-sig")
    reader = csv.reader(content.splitlines())
    updated = 0
    for row in reader:
        if len(row) < 2:
            continue
        owner_id, points_str = row[0].strip(), row[1].strip()
        if not owner_id or owner_id.lower() == "owner_id":  # başlık satırını atla
            continue
        try:
            points = int(points_str)
        except ValueError:
            continue
        existing = db.query(LoyaltyPoints).filter(LoyaltyPoints.owner_id == owner_id).first()
        if existing:
            existing.points = points
        else:
            db.add(LoyaltyPoints(owner_id=owner_id, points=points))
        updated += 1
    db.commit()
    return {"message": f"{updated} satır işlendi.", "updated": updated}


# --- OYUNCU / GENEL UÇLAR ---

@app.post("/cards", dependencies=[Depends(verify_internal_key)])
def buy_cards(payload: BuyCardsInput, db: Session = Depends(get_db)):
    """
    Oyuncu başına en fazla 1 kart hakkı var — bu yüzden önce aynı owner_id
    için bu hafta zaten bir kart oluşturulmuş mu diye bakıyoruz. Bu kontrol
    olmadan (a) aynı kişi/isim adına defalarca kart üretilebilir, hem
    adaleti bozar hem de kazanan/Amorti hesaplarını (owner_id başına tek
    kayıt varsayan) bozar. Sadece güvenilir/iç sistemler çağırabilsin diye
    x-internal-key ile korunuyor — halka açık, kimliksiz bir uç nokta değil.
    """
    config = get_or_create_config(db)
    state = get_or_create_state(db)

    if not config.is_paid_for_current_week:
        raise HTTPException(status_code=400, detail="Bu hafta için ödeme yapılmamış, kart satışı kapalı.")
    if state.flags.get("over", False):
        raise HTTPException(status_code=400, detail="Bu haftanın oyunu bitti, yeni hafta başlamadan kart satılamaz.")

    existing = db.query(Card).filter(Card.owner_id == payload.owner_id).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"'{payload.owner_id}' için bu hafta zaten bir kart var (Kart No: {existing.id}). Oyuncu başına en fazla 1 kart hakkı var.",
        )

    grid = generate_cards(1)[0]
    new_card = Card(owner_id=payload.owner_id, grid=grid, token=secrets.token_urlsafe(16))
    db.add(new_card)
    db.commit()
    db.refresh(new_card)

    return {"message": "1 kart oluşturuldu.", "card_id": new_card.id, "token": new_card.token}


@app.post("/reception/register", dependencies=[Depends(verify_internal_key)])
def reception_register(payload: ReceptionRegisterInput, request: Request, db: Session = Depends(get_db)):
    """
    🏨 RESEPSİYON AKIŞI — misafir giriş yaptığında personel bu formu doldurur.
    1. Misafire otomatik ücretsiz TEK kart atanır (satış YOK, casino'nun hediyesi;
       oyuncu başına en fazla 1 kart kuralı burada da geçerli)
    2. Kart linki SMS ile otomatik telefonuna gönderilir — kağıt/QR yazdırmaya gerek kalmaz

    x-internal-key ile korunuyor çünkü bu, gerçek SMS gönderiyor (ücretli) ve
    ücretsiz kart üretiyor — sadece resepsiyon personeli/casino sistemi
    tetikleyebilmeli, herkese açık internet erişimi değil.
    """
    config = get_or_create_config(db)
    state = get_or_create_state(db)

    if not config.is_paid_for_current_week:
        raise HTTPException(status_code=400, detail="Bu hafta için oyun henüz başlatılmadı.")
    if state.flags.get("over", False):
        raise HTTPException(status_code=400, detail="Bu haftanın oyunu bitti.")

    existing = db.query(Card).filter(Card.owner_id == payload.guest_name).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"'{payload.guest_name}' için bu hafta zaten bir kart var (Kart No: {existing.id}). Oyuncu başına en fazla 1 kart hakkı var.",
        )

    grid = generate_cards(1)[0]
    new_card = Card(owner_id=payload.guest_name, grid=grid, token=secrets.token_urlsafe(16))
    db.add(new_card)
    db.commit()
    db.refresh(new_card)

    link = f"{request.base_url}view/{new_card.token}"
    message = f"Hoş geldiniz {payload.guest_name}! Dynasty Bingo kartınız hazır.\n{link}"
    sms_sent = send_sms(payload.phone_number, message)

    return {
        "message": f"1 kart oluşturuldu, SMS {'gönderildi' if sms_sent else 'gönderilemedi'}.",
        "card_id": new_card.id,
        "token": new_card.token,
        "sms_sent": sms_sent,
    }


@app.get("/reception", response_class=HTMLResponse)
def reception_page():
    """
    Resepsiyon personelinin kullanacağı basit form. API'yle uğraşmasına gerek yok —
    misafirin adını ve telefon numarasını yazıp butona basması yeterli.
    """
    html = """
<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Resepsiyon — Misafir Kaydı</title>
<style>
  body { margin:0; padding:24px; background:#0A1120; color:#E7ECF3; font-family:-apple-system,sans-serif; max-width:420px; }
  h1 { font-size:20px; margin-bottom:4px; }
  .sub { font-size:13px; color:#8593AC; margin-bottom:20px; }
  label { display:block; font-size:13px; color:#8593AC; margin-top:14px; margin-bottom:6px; }
  input { width:100%; padding:12px; font-size:16px; border-radius:8px; border:1px solid #223049; background:#16213A; color:#E7ECF3; box-sizing:border-box; }
  button { margin-top:20px; width:100%; padding:14px; font-size:16px; font-weight:700; border-radius:8px; border:none; background:#2DD4E8; color:#06222B; cursor:pointer; }
  button:disabled { opacity:0.5; }
  .result { margin-top:16px; padding:14px; border-radius:8px; font-size:13px; line-height:1.5; }
  .result.ok { background:rgba(45,212,232,0.1); border:1px solid rgba(45,212,232,0.3); color:#2DD4E8; }
  .result.err { background:rgba(232,93,93,0.1); border:1px solid rgba(232,93,93,0.3); color:#E85D5D; }
</style>
</head>
<body>
  <h1>🎟️ Dynasty Bingo — Misafir Kaydı</h1>
  <div class="sub">Misafir giriş yaptı mı? Adını ve telefon numarasını gir, kartı otomatik oluşup SMS ile gönderilsin. Ücretsizdir. Oyuncu başına en fazla 1 kart hakkı var.</div>

  <label>Personel Anahtarı (bir kez girin, tarayıcı hatırlar)</label>
  <input id="staffKey" type="password" placeholder="x-internal-key değeri">

  <label>Misafir Adı</label>
  <input id="guestName" placeholder="Örn: Ahmet Kaya">

  <label>Telefon Numarası</label>
  <input id="phoneNumber" placeholder="+905551234567">

  <button id="submitBtn" onclick="register()">Kart Oluştur ve SMS Gönder</button>

  <div id="result"></div>

<script>
const staffKeyInput = document.getElementById('staffKey');
staffKeyInput.value = sessionStorage.getItem('dynastyStaffKey') || '';

async function register() {
  const staffKey = staffKeyInput.value.trim();
  const guestName = document.getElementById('guestName').value.trim();
  const phoneNumber = document.getElementById('phoneNumber').value.trim();
  const resultBox = document.getElementById('result');
  const btn = document.getElementById('submitBtn');

  if (!staffKey) {
    resultBox.className = 'result err';
    resultBox.textContent = 'Personel anahtarını girin.';
    return;
  }
  if (!guestName || !phoneNumber) {
    resultBox.className = 'result err';
    resultBox.textContent = 'Lütfen ad ve telefon numarası girin.';
    return;
  }

  btn.disabled = true;
  btn.textContent = 'Gönderiliyor...';

  try {
    const res = await fetch('/reception/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'x-internal-key': staffKey },
      body: JSON.stringify({ guest_name: guestName, phone_number: phoneNumber })
    });
    const data = await res.json();

    if (res.ok) {
      sessionStorage.setItem('dynastyStaffKey', staffKey);
      resultBox.className = 'result ok';
      resultBox.textContent = `✅ ${data.message} Kart No: ${data.card_id}`;
      document.getElementById('guestName').value = '';
      document.getElementById('phoneNumber').value = '';
    } else {
      resultBox.className = 'result err';
      resultBox.textContent = `Hata: ${data.detail || 'Bilinmeyen hata'}`;
    }
  } catch (e) {
    resultBox.className = 'result err';
    resultBox.textContent = 'Bağlantı hatası, tekrar deneyin.';
  }

  btn.disabled = false;
  btn.textContent = 'Kart Oluştur ve SMS Gönder';
}
</script>
</body>
</html>
"""
    return HTMLResponse(html)


@app.get("/state", response_model=GameStateOutput)
def get_state(db: Session = Depends(get_db)):
    config = get_or_create_config(db)
    state = get_or_create_state(db)
    return GameStateOutput(
        drawn_numbers=state.drawn_numbers,
        flags=state.flags,
        daily_draw_count=state.daily_draw_count,
        is_paid_for_current_week=config.is_paid_for_current_week,
        current_week_start_date=config.current_week_start_date,
    )


@app.get("/card/{token}", response_model=CardStatusOutput)
def get_card_status(token: str, db: Session = Depends(get_db)):
    """
    🔒 'token' (tahmin edilemez rastgele değer) ile aranır, sıralı 'id' ile
    DEĞİL — yoksa /card/1, /card/2 diye sayarak herkesin kartı görülebilirdi.
    """
    card = db.query(Card).filter(Card.token == token).first()
    if not card:
        raise HTTPException(status_code=404, detail="Kart bulunamadı.")
    state = get_or_create_state(db)
    drawn_set = set(state.drawn_numbers)

    marked_count = sum(len([n for n in row if n in drawn_set]) for row in card.grid)
    score = engine_instance._analyze(card.grid, drawn_set) if engine_instance else 0

    return CardStatusOutput(id=card.id, owner_id=card.owner_id, grid=card.grid, marked_count=marked_count, score=score)


@app.get("/owner/{owner_id}/cards")
def list_owner_cards(owner_id: str, db: Session = Depends(get_db)):
    """
    /myview (QR kaybolduğunda isimle kart bulma) tarafından kullanılır.
    NOT: Bu uç nokta, tam olarak bilinen bir ismi arayan birinin o kişinin
    kartını bulmasına izin verir — bu, özelliğin amacı (QR'sız kurtarma).
    Kapattığımız risk, sıralı ID'leri sayarak TÜM kartları taramaktı; onu
    /view ve /card artık token istediği için kapattık. İsimle hedefli arama
    riski, bu kurulumun sadece casino'nun kendi WiFi'ında çalışması ile
    sınırlı kalıyor (bkz. README).
    """
    cards = db.query(Card).filter(Card.owner_id == owner_id).all()
    return {"cards": [{"id": c.id, "token": c.token} for c in cards]}


@app.get("/winners", response_model=List[WinnerOutput])
def get_winners(db: Session = Depends(get_db)):
    """Sadece MEVCUT haftanın kazananlarını döner — eski haftalar veritabanında
    kalır (kayıt/rapor için) ama burada, dolayısıyla büyük ekranda, hiç
    gösterilmez. Bundan önce eski haftaların kazananları sonsuza kadar
    listede kalıp yeni haftayla karışıyordu.

    NOT: Karşılaştırma için state.start_date (saniye hassasiyetli DateTime)
    kullanılıyor, config.current_week_start_date (sadece gün hassasiyetli
    Date) değil — çünkü aynı takvim gününde hafta iki kez başlatılırsa
    (örn. yanlışlıkla) Date bazlı bir karşılaştırma iki haftayı ayırt edemez.
    """
    state = get_or_create_state(db)
    query = db.query(Winners).order_by(Winners.draw_time.desc())
    if state.start_date:
        query = query.filter(Winners.week_start_date == state.start_date)
    return query.all()


@app.get("/prizes", response_model=PublicPrizesOutput)
def get_public_prizes(db: Session = Depends(get_db)):
    """
    🔒 Büyük ekran ve müşteri sayfaları SADECE bu uç noktayı kullanmalı.
    /admin/start-week yanıtındaki max_winners bilgisi buraya kasıtlı olarak
    hiç dahil edilmedi.
    """
    config = get_or_create_config(db)
    return PublicPrizesOutput(
        prize_c1_usd=config.prize_c1_usd,
        prize_c2_usd=config.prize_c2_usd,
        prize_t_usd=config.prize_t_usd,
        prize_amorti_usd=config.prize_amorti_usd,
    )


# =====================================================================
# V. MÜŞTERİ EKRANI — Oyuncular kendi kartlarını burada canlı görür
# =====================================================================

@app.get("/view/{token}", response_class=HTMLResponse)
def view_card_page(token: str, db: Session = Depends(get_db)):
    """
    Müşterinin telefonunda açacağı sayfa. QR kod okutunca buraya düşer.
    Sayfa kendi kendine her 3 saniyede bir /card/{token} ve /state'i sorup
    ekranı günceller — müşteri elle yenilemek zorunda kalmaz.

    🔒 'token' rastgele/tahmin edilemez — sıralı bir 'id' olsaydı, /view/1,
    /view/2 diye sayarak başkalarının kartı görülebilirdi.
    """
    card = db.query(Card).filter(Card.token == token).first()
    if not card:
        return HTMLResponse("<h1>Kart bulunamadı.</h1>", status_code=404)
    card_id = card.id  # sadece ekranda gösterilecek insan-dostu numara

    # NOT: Basit olsun diye HTML'i doğrudan Python içinde yazıyoruz (f-string).
    # Gerçek veriler sayfa açıldıktan SONRA tarayıcıda JavaScript ile
    # /card/{token} adresinden çekilir — böylece sayfa her zaman güncel kalır.
    html = f"""
<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Kartım — #{card_id}</title>
<style>
  body {{
    margin: 0; padding: 20px;
    background: #0A1120; color: #E7ECF3;
    font-family: -apple-system, sans-serif;
    display: flex; flex-direction: column; align-items: center;
  }}
  h1 {{ font-size: 18px; color: #8593AC; font-weight: 500; margin: 6px 0 2px; }}
  .status {{ font-size: 14px; color: #2DD4E8; margin-bottom: 16px; }}
  .status.win {{ color: #E8B94D; font-weight: 700; font-size: 18px; }}
  .ticket {{
    display: grid; grid-template-columns: repeat(9, 1fr); gap: 5px;
    width: 100%; max-width: 420px;
  }}
  .cell {{
    aspect-ratio: 1; display: flex; align-items: center; justify-content: center;
    font-size: 16px; font-weight: 700; border-radius: 6px;
    background: #16213A; color: #8593AC;
  }}
  .cell.empty {{ background: transparent; }}
  .cell.marked {{ background: rgba(45,212,232,0.18); color: #2DD4E8; border: 1px solid rgba(45,212,232,0.4); }}
  .footer {{ margin-top: 18px; font-size: 12px; color: #4A5876; }}
</style>
</head>
<body>
  <h1>Kart No: #{card_id} — <span id="ownerName"></span></h1>
  <div class="status" id="statusLine">Yükleniyor...</div>
  <div class="ticket" id="ticket"></div>
  <div class="footer">Sayfa otomatik yenilenir, elle yenilemene gerek yok.</div>

<script>
async function refresh() {{
  try {{
    const res = await fetch('/card/{token}');
    if (!res.ok) {{ document.getElementById('statusLine').textContent = 'Kart bulunamadı.'; return; }}
    const data = await res.json();

    document.getElementById('ownerName').textContent = data.owner_id;

    const statusEl = document.getElementById('statusLine');
    if (data.score === 3) {{
      statusEl.textContent = '🏆 TOMBALA YAPTINIZ!';
      statusEl.className = 'status win';
    }} else if (data.score === 2) {{
      statusEl.textContent = '2. Çinko yapıldı — Tombala\\'ya devam!';
      statusEl.className = 'status';
    }} else if (data.score === 1) {{
      statusEl.textContent = '1. Çinko yapıldı — devam ediyor!';
      statusEl.className = 'status';
    }} else {{
      statusEl.textContent = `İşaretli: ${{data.marked_count}} / 15`;
      statusEl.className = 'status';
    }}

    const ticket = document.getElementById('ticket');
    ticket.innerHTML = '';
    // Hangi sayıların çekildiğini öğrenmek için ayrıca /state'e bakıyoruz
    const stateRes = await fetch('/state');
    const stateData = await stateRes.json();
    const drawnSet = new Set(stateData.drawn_numbers);

    data.grid.forEach(row => {{
      row.forEach(n => {{
        const cell = document.createElement('div');
        if (n === null) {{
          cell.className = 'cell empty';
        }} else {{
          cell.className = 'cell' + (drawnSet.has(n) ? ' marked' : '');
          cell.textContent = n;
        }}
        ticket.appendChild(cell);
      }});
    }});
  }} catch (e) {{
    document.getElementById('statusLine').textContent = 'Bağlantı hatası, tekrar deneniyor...';
  }}
}}
refresh();
setInterval(refresh, 3000); // Her 3 saniyede bir otomatik güncelle
</script>
</body>
</html>
"""
    return HTMLResponse(html)


@app.get("/card/{token}/qrcode")
def get_card_qrcode(token: str, request: Request, db: Session = Depends(get_db)):
    """
    Bu kartın müşteri ekranına (/view/{token}) giden bir QR kod resmi üretir.
    Kart satıldığında bu resmi yazdırıp müşteriye verebilir veya ekranda gösterebilirsin.
    Müşteri telefon kamerasıyla okutunca direkt kendi kartını görür.
    """
    import qrcode

    card = db.query(Card).filter(Card.token == token).first()
    if not card:
        raise HTTPException(status_code=404, detail="Kart bulunamadı.")

    # request.base_url otomatik olarak "http://şu-anki-sunucu-adresi:port/" verir.
    # Böylece QR kod, sunucu hangi IP'de çalışıyorsa ona göre doğru linki içerir.
    view_url = f"{request.base_url}view/{card.token}"

    qr_img = qrcode.make(view_url)
    buffer = io.BytesIO()
    qr_img.save(buffer, format="PNG")
    buffer.seek(0)
    return StreamingResponse(buffer, media_type="image/png")


@app.get("/myview", response_class=HTMLResponse)
def find_my_cards_page():
    """
    Müşteri QR kodu kaybettiyse veya elle bakmak isterse, ismini/ID'sini
    yazıp kendi kartlarını bulabileceği basit bir arama sayfası.
    """
    html = """
<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Kartımı Bul</title>
<style>
  body { margin:0; padding: 24px; background:#0A1120; color:#E7ECF3; font-family:-apple-system,sans-serif; }
  h1 { font-size: 18px; }
  input { width:100%; padding:12px; font-size:16px; border-radius:8px; border:1px solid #223049; background:#16213A; color:#E7ECF3; box-sizing:border-box; }
  button { margin-top:10px; width:100%; padding:12px; font-size:16px; font-weight:600; border-radius:8px; border:none; background:#2DD4E8; color:#06222B; }
  .card-link { display:block; margin-top:10px; padding:14px; background:#121B2E; border:1px solid #223049; border-radius:8px; color:#2DD4E8; text-decoration:none; }
  .empty { color:#8593AC; margin-top:14px; }
</style>
</head>
<body>
  <h1>Kartlarımı bul</h1>
  <input id="ownerInput" placeholder="Adınızı/Üyelik ID'nizi girin" />
  <button onclick="search()">Kartlarımı Göster</button>
  <div id="results"></div>

<script>
async function search() {
  const ownerId = document.getElementById('ownerInput').value.trim();
  if (!ownerId) return;
  const res = await fetch(`/owner/${encodeURIComponent(ownerId)}/cards`);
  const data = await res.json();
  const results = document.getElementById('results');
  results.innerHTML = '';
  if (data.cards.length === 0) {
    results.innerHTML = '<div class="empty">Bu isimle kayıtlı kart bulunamadı.</div>';
    return;
  }
  data.cards.forEach(c => {
    const a = document.createElement('a');
    a.className = 'card-link';
    a.href = `/view/${c.token}`;
    a.textContent = `Kart #${c.id} — Görüntüle`;
    results.appendChild(a);
  });
}
</script>
</body>
</html>
"""
    return HTMLResponse(html)


# =====================================================================
# VI. BÜYÜK EKRAN — Salon projeksiyonu / TV için. Herkes görür.
# 🔒 Bu sayfa asla max_winners (kaç kişiye bölünecek) bilgisini göstermez.
# Sadece /state, /prizes, /winners uç noktalarını kullanır (hepsi genel/public).
# =====================================================================

@app.get("/bigscreen", response_class=HTMLResponse)
def big_screen_page():
    """Salondaki büyük TV/projeksiyona bu adres açılır: http://sunucu:8000/bigscreen"""
    html = """
<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Dynasty Bingo — Canlı Çekiliş</title>
<style>
  body {
    margin:0; padding:40px; background:#0A1120; color:#E7ECF3;
    font-family:-apple-system,sans-serif; min-height:100vh; box-sizing:border-box;
  }
  .wrap { max-width: 1100px; margin: 0 auto; }
  h1 { font-size: 28px; margin-bottom: 30px; }
  h1 span { color:#2DD4E8; }
  .row { display:flex; gap:40px; align-items:center; margin-bottom:40px; flex-wrap:wrap; }
  .ball {
    width:200px; height:200px; border-radius:50%;
    background: radial-gradient(circle at 32% 28%, #1B2A45, #0D1526 70%);
    border:3px solid #2DD4E8;
    display:flex; align-items:center; justify-content:center;
    font-size:80px; font-weight:700;
  }
  .chips { display:flex; flex-wrap:wrap; gap:10px; max-width:700px; }
  .chip {
    width:50px; height:50px; border-radius:50%; background:#16213A;
    display:flex; align-items:center; justify-content:center;
    font-size:18px; font-weight:600; color:#8593AC; border:1px solid #223049;
  }
  .chip.recent { color:#2DD4E8; border-color:#2DD4E8; }
  .prizes { display:grid; grid-template-columns:repeat(4,1fr); gap:16px; margin-bottom:30px; }
  .prize-box { background:#121B2E; border:1px solid #223049; border-radius:12px; padding:20px; text-align:center; }
  .prize-box .label { font-size:14px; color:#8593AC; margin-bottom:6px; }
  .prize-box .amount { font-size:24px; font-weight:700; color:#2DD4E8; }
  .prize-box.t .amount { color:#E8B94D; }
  .winners { background:#121B2E; border:1px solid #223049; border-radius:12px; padding:10px 24px; }
  .winner-row { display:flex; justify-content:space-between; padding:14px 0; border-bottom:1px solid #223049; font-size:16px; }
  .winner-row:last-child { border-bottom:none; }
  .winner-type { color:#E8B94D; font-weight:700; }
  .empty { color:#8593AC; padding:16px 0; }
</style>
</head>
<body>
<div class="wrap">
  <h1>DYNASTY <span>BINGO</span> — Canlı Çekiliş</h1>

  <div class="row">
    <div class="ball" id="ball">—</div>
    <div class="chips" id="chips"></div>
  </div>

  <div class="prizes" id="prizes"></div>

  <div class="winners" id="winners">
    <div class="empty">Henüz kazanan yok</div>
  </div>
</div>

<script>
function fmt(n) { return "$" + Number(n).toLocaleString("en-US"); }

async function refresh() {
  const [stateRes, prizesRes, winnersRes] = await Promise.all([
    fetch('/state'), fetch('/prizes'), fetch('/winners')
  ]);
  const state = await stateRes.json();
  const prizes = await prizesRes.json();
  const winners = await winnersRes.json();

  const drawn = state.drawn_numbers;
  document.getElementById('ball').textContent = drawn.length ? drawn[drawn.length-1] : '—';

  const chips = document.getElementById('chips');
  chips.innerHTML = '';
  drawn.slice().reverse().slice(0, 20).forEach((n, i) => {
    const el = document.createElement('div');
    el.className = 'chip' + (i === 0 ? ' recent' : '');
    el.textContent = n;
    chips.appendChild(el);
  });

  document.getElementById('prizes').innerHTML = `
    <div class="prize-box"><div class="label">1. Çinko</div><div class="amount">${fmt(prizes.prize_c1_usd)}</div></div>
    <div class="prize-box"><div class="label">2. Çinko</div><div class="amount">${fmt(prizes.prize_c2_usd)}</div></div>
    <div class="prize-box t"><div class="label">Tombala</div><div class="amount">${fmt(prizes.prize_t_usd)}</div></div>
    <div class="prize-box"><div class="label">Amorti</div><div class="amount">${fmt(prizes.prize_amorti_usd)}</div></div>
  `;

  const winBox = document.getElementById('winners');
  if (winners.length === 0) {
    winBox.innerHTML = '<div class="empty">Henüz kazanan yok</div>';
  } else {
    winBox.innerHTML = winners.map(w => {
      const names = w.users.join(', ');
      const amount = w.prize_details.per_winner_usd
        ? `${fmt(w.prize_details.per_winner_usd)} / kişi`
        : 'Detay için yönetici paneline bakın';
      return `<div class="winner-row"><span><span class="winner-type">${w.type.toUpperCase()}</span> — ${names}</span><span>${amount}</span></div>`;
    }).join('');
  }
}

refresh();
setInterval(refresh, 2000);
</script>
</body>
</html>
"""
    return HTMLResponse(html)


# =====================================================================
# VII. KASA FİŞİ — Kart satıldığında yazdırılacak QR'lı fiş.
# =====================================================================

@app.get("/card/{token}/receipt", response_class=HTMLResponse)
def card_receipt_page(token: str, request: Request, db: Session = Depends(get_db)):
    """
    Kasadaki personel, kart satışından hemen sonra bu sayfayı açıp
    (Ctrl+P ile) yazdırır ve müşteriye kağıt fiş olarak verir.
    Fiş üzerinde QR kod + kart numarası + kısa talimat var.
    """
    card = db.query(Card).filter(Card.token == token).first()
    if not card:
        return HTMLResponse("<h1>Kart bulunamadı.</h1>", status_code=404)
    card_id = card.id  # sadece ekranda gösterilecek insan-dostu numara

    qr_url = f"/card/{card.token}/qrcode"
    view_url = f"{request.base_url}view/{card.token}"

    html = f"""
<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<title>Fiş — Kart #{card_id}</title>
<style>
  body {{ font-family: -apple-system, sans-serif; text-align:center; padding:20px; width: 280px; margin:0 auto; }}
  h2 {{ margin-bottom:4px; }}
  .card-no {{ font-size:20px; font-weight:700; margin-bottom:14px; }}
  img {{ width:200px; height:200px; }}
  .instructions {{ font-size:12px; color:#333; margin-top:14px; line-height:1.5; }}
  .url {{ font-size:10px; color:#666; word-break:break-all; margin-top:8px; }}
  @media print {{ .no-print {{ display:none; }} }}
</style>
</head>
<body>
  <h2>DYNASTY BINGO</h2>
  <div class="card-no">Kart No: #{card_id}</div>
  <img src="{qr_url}" alt="QR Kod">
  <div class="instructions">
    Kartınızı canlı takip etmek için telefonunuzla<br>yukarıdaki QR kodu okutun.
  </div>
  <div class="url">{view_url}</div>
  <button class="no-print" onclick="window.print()" style="margin-top:16px;padding:10px 20px;">Yazdır</button>
</body>
</html>
"""
    return HTMLResponse(html)
