#!/usr/bin/env python3
"""
NovaGuard Promo Engine — Casino Entegrasyon Örneği
====================================================
Bu script casino IT ekibine verilir.
"Sisteminizi NovaGuard'a nasıl bağlarsınız" sorusunun cevabıdır.

Standart Python kütüphanesiyle yazılmıştır — ek kurulum gerekmez.
Herhangi bir casino sisteminden çağrılabilir.

AKIŞ:
  1. Oyuncu masaya/makineye oturur
     → push_session_start() çağrılır

  2. Oyuncu kalkar
     → push_session_end() çağrılır
     → NovaGuard biletleri otomatik hesaplar

GEREKLİ VERİ:
  • Kart numarası (casino'nun kendi formatı — değiştirmiyoruz)
  • Oyun süresi (başlangıç / bitiş zamanı)
  • Ortalama bahis — SADECE BU KADAR

GÖNDERMEMEK GEREKEN VERİ:
  × Oyuncu adı / kişisel bilgi
  × Kazanç veya kayıp
  × Bakiye
"""
import json
import urllib.request
import urllib.error
from datetime import datetime, timezone

# ── BAĞLANTI AYARLARI (casino IT doldurur) ────────────────────────────────────
NOVAGUARD_URL = "http://NOVAGUARD-SUNUCU-ADRESI:8000"
API_KEY       = "size-verilen-crm-api-key"


def push_session_start(
    card_id: str,
    session_id: str,
    game_type: str,         # "live" veya "slot"
    started_at: datetime,
    game_name: str = None,
) -> bool:
    """
    Oyuncu masaya/makineye oturduğunda çağrılır.
    game_type: "live" (blackjack, rulet, bakara, poker)
               "slot" (slot makinesi)
    """
    payload = {
        "external_session_id": session_id,
        "card_id": card_id,
        "game_type": game_type,
        "started_at": _iso(started_at),
        "currency": "GEL",
    }
    if game_name:
        payload["game_name"] = game_name

    return _post("/api/v1/sessions/push", payload)


def push_session_end(
    session_id: str,
    ended_at: datetime,
    average_bet: float,     # oyuncunun o oturumdaki ortalama bahisi
) -> bool:
    """
    Oyuncu kalktığında çağrılır.
    average_bet: ortalama bahis miktarı (GEL cinsinden)
                 Örn: oyuncu 2 saat blackjack oynadı, elle ortalama 50 GEL koydu → average_bet=50

    Bu noktada NovaGuard otomatik olarak:
      - Süre + ortalama bahis → bilet sayısı hesaplar
      - Benzersiz numaralı biletleri karta yükler
      - Çekiliş havuzunu günceller
    """
    payload = {
        "ended_at": _iso(ended_at),
        "final_average_bet": average_bet,
    }
    return _patch(f"/api/v1/sessions/by-external/{session_id}/end", payload)


def sync_player_name(card_id: str, name: str) -> bool:
    """
    Opsiyonel: oyuncunun adını senkronize eder.
    Display ekranında "Tebrikler Hasan Koç!" göstermek için kullanılır.
    Gönderilmezse sistem kart numarasıyla devam eder.
    Kişisel veri politikanıza göre göndermeyebilirsiniz.
    """
    return _post("/api/v1/sessions/players/sync", {
        "card_id": card_id,
        "name": name,
    })


# ── ALT YAPI ──────────────────────────────────────────────────────────────────

def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _post(path: str, data: dict) -> bool:
    return _request("POST", path, data)


def _patch(path: str, data: dict) -> bool:
    return _request("PATCH", path, data)


def _request(method: str, path: str, data: dict) -> bool:
    try:
        body = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(
            f"{NOVAGUARD_URL}{path}",
            data=body,
            headers={
                "Content-Type": "application/json",
                "X-CRM-Key": API_KEY,
            },
            method=method,
        )
        urllib.request.urlopen(req, timeout=10)
        return True
    except urllib.error.HTTPError as e:
        print(f"NovaGuard hata {e.code}: {e.read().decode()[:300]}")
        return False
    except Exception as e:
        print(f"NovaGuard bağlantı hatası: {e}")
        return False


# ── KULLANIM ÖRNEĞİ ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Casino IT'si bunu kendi akışına entegre eder.
    # Bu blok sadece test amaçlıdır.

    now = datetime.now(timezone.utc)

    print("Test: Oturum başlatılıyor...")
    push_session_start(
        card_id="KRT-007",
        session_id="TEST-001",
        game_type="live",
        game_name="Blackjack #3",
        started_at=now,
    )

    import time; time.sleep(1)

    print("Test: Oturum kapatılıyor (ortalama bahis: 50 GEL)...")
    from datetime import timedelta
    push_session_end(
        session_id="TEST-001",
        ended_at=now + timedelta(hours=2),
        average_bet=50.0,
    )

    print("Tamam. NovaGuard biletleri hesapladı.")
    print(f"Kontrol: {NOVAGUARD_URL}/docs")
