"""
Display Sistemi Endpointleri
Büyük ekran, kart okuyucu, self-service terminal için açık endpointler.
"""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from sqlalchemy import select, func, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import Player, Ticket, DrawSchedule, DrawResult, PrizeWin, DrawStatus
from ..schemas import LeaderboardEntry
from ..core.config import settings
from ..services.draw_engine import get_player_eligibility_status

router = APIRouter(prefix="/display", tags=["Display"])


def today_casino():
    return datetime.now(ZoneInfo(settings.CASINO_TIMEZONE)).date()


# ── LEADERBOARD (N+1 fix) ─────────────────────────────────────────────────────

@router.get("/leaderboard", response_model=list[LeaderboardEntry])
async def leaderboard(limit: int = 50, db: AsyncSession = Depends(get_db)):
    """Bilet sıralaması. Büyük ekran + admin panel için."""
    year  = settings.CAMPAIGN_YEAR
    today = today_casino()

    # 1 query: toplam aktif bilet sayısı kart bazında
    total_q = await db.execute(
        select(Ticket.card_id, func.count(Ticket.id).label("total"))
        .where(and_(Ticket.campaign_year == year, Ticket.is_active == True))
        .group_by(Ticket.card_id)
    )
    total_map = {r.card_id: r.total for r in total_q}

    # 1 query: bugün kazanılan biletler
    today_q = await db.execute(
        select(Ticket.card_id, func.count(Ticket.id).label("cnt"))
        .where(and_(Ticket.campaign_year == year, Ticket.earned_date == today))
        .group_by(Ticket.card_id)
    )
    today_map = {r.card_id: r.cnt for r in today_q}

    # 1 query: kazanan kart ID'leri
    wins_q = await db.execute(
        select(PrizeWin.card_id, PrizeWin.draw_tier)
        .where(PrizeWin.campaign_year == year)
        .distinct(PrizeWin.card_id)
    )
    wins_map = {r.card_id: r.draw_tier.value for r in wins_q}

    # 1 query: aktif oyuncular
    players_q = await db.execute(select(Player).where(Player.is_active == True))
    players   = players_q.scalars().all()

    entries = [
        LeaderboardEntry(
            rank=0,
            card_id=p.card_id,
            name=p.name,
            total_tickets=total_map.get(p.card_id, 0),
            tickets_today=today_map.get(p.card_id, 0),
            has_won=p.card_id in wins_map,
            won_tier=wins_map.get(p.card_id),
        )
        for p in players
        if total_map.get(p.card_id, 0) > 0
    ]

    entries.sort(key=lambda x: x.total_tickets, reverse=True)
    for i, e in enumerate(entries[:limit]):
        e.rank = i + 1
    return entries[:limit]


# ── NEXT DRAW ─────────────────────────────────────────────────────────────────

@router.get("/next-draw")
async def next_draw(db: AsyncSession = Depends(get_db)):
    """Bir sonraki planlanmış çekiliş. Display ekranı geri sayım için kullanır."""
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(DrawSchedule)
        .where(and_(
            DrawSchedule.status == DrawStatus.SCHEDULED,
            DrawSchedule.scheduled_at >= now,
        ))
        .order_by(DrawSchedule.scheduled_at.asc())
        .limit(1)
    )
    s = result.scalar_one_or_none()
    if not s:
        return {"next_draw": None}

    return {"next_draw": {
        "id": str(s.id),
        "name": s.name,
        "tier": s.draw_tier.value,
        "scheduled_at": s.scheduled_at.isoformat(),
        "prize_amount": str(s.prize_amount),
        "prize_currency": s.prize_currency,
        "prize_description": s.prize_description,
        "tax_cleared": s.tax_cleared,
    }}


# ── LAST RESULT ───────────────────────────────────────────────────────────────

@router.get("/last-result")
async def last_result(db: AsyncSession = Depends(get_db)):
    """Son tamamlanmış çekiliş sonucu. Display ekranı kazananı göstermek için."""
    r = await db.execute(
        select(DrawResult).order_by(desc(DrawResult.executed_at)).limit(1)
    )
    dr = r.scalar_one_or_none()
    if not dr:
        return {"last_result": None}

    player   = (await db.execute(select(Player).where(Player.card_id == dr.winner_card_id))).scalar_one_or_none()
    schedule = (await db.execute(select(DrawSchedule).where(DrawSchedule.id == dr.schedule_id))).scalar_one_or_none()

    return {"last_result": {
        "winner_name":    player.name if player else dr.winner_card_id,
        "winner_card_id": dr.winner_card_id,
        "winning_ticket": dr.winning_ticket_number,
        "prize":          schedule.prize_description if schedule else "",
        "prize_amount":   str(schedule.prize_amount) if schedule else "",
        "prize_currency": schedule.prize_currency if schedule else "",
        "tier":           schedule.draw_tier.value if schedule else "",
        "executed_at":    dr.executed_at.isoformat(),
    }}


# ── CARD STATUS ───────────────────────────────────────────────────────────────

@router.get("/card/{card_id}/status")
async def card_status(card_id: str, db: AsyncSession = Depends(get_db)):
    """Kart okuyucu için — kaç bilet, hangi çekilişlere uygun."""
    player = (await db.execute(
        select(Player).where(Player.card_id == card_id)
    )).scalar_one_or_none()

    if not player:
        return {"found": False, "card_id": card_id}

    eligibility = await get_player_eligibility_status(card_id, db)
    return {"found": True, "card_id": card_id, "name": player.name, "eligibility": eligibility}


# ── BRANDING ──────────────────────────────────────────────────────────────────
import json, os

@router.get("/branding")
async def get_branding():
    """
    Display ekranı için marka yapılandırması.
    branding.json varsa okur, yoksa varsayılan NovaGuard markasını döner.
    """
    branding_path = os.path.join(os.path.dirname(__file__), "../../branding.json")
    try:
        with open(branding_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            # _comment ve _ ile başlayan notları temizle
            data.pop("_comment", None)
            return data
    except FileNotFoundError:
        return {
            "casino": {
                "name": "NOVAGUARD",
                "tagline": "Çekiliş Sistemi",
                "city": "",
                "logo_url": "",
            },
            "theme": {"preset": "dark_gold"},
            "display": {
                "show_leaderboard": True,
                "show_countdown": True,
                "lang_auto_rotate": True,
                "lang_rotate_interval_sec": 4,
                "languages": ["tr", "en", "ru", "ka"],
            },
        }


# ── MİNİ BONUS — SON KAZANAN ────────────────────────────────────────────────
# Büyük ekran (display.html) bu endpoint'i düzenli aralıklarla kontrol eder.
# "Yeni bir mini bonus kazananı var mı?" diye sorar, varsa küçük bir bildirim gösterir.

@router.get("/last-mini-bonus")
async def get_last_mini_bonus(db: AsyncSession = Depends(get_db)):
    """
    En son verilen mini bonus ödülünü döner.

    Mini bonus arka planda (Celery worker'da) otomatik çalıştığı için,
    büyük ekranın anında haberi olmuyor — bu yüzden ekran bu endpoint'i
    her birkaç saniyede bir soruyor (polling denir bu yönteme).
    """
    # executed_by="auto-mini-bonus" olan en son DrawResult kaydını bul.
    # Bu, mini bonus çekilişlerini normal haftalık/aylık çekilişlerden ayırt eden işarettir.
    result = await db.execute(
        select(DrawResult)
        .where(DrawResult.executed_by == "auto-mini-bonus")
        .order_by(desc(DrawResult.executed_at))
        .limit(1)
    )
    last = result.scalar_one_or_none()

    if last is None:
        return {"found": False}

    # Kazananın adını da bulalım (varsa) — ekranda kart numarası yerine isim gösterelim
    player_result = await db.execute(
        select(Player).where(Player.card_id == last.winner_card_id)
    )
    player = player_result.scalar_one_or_none()
    winner_name = player.name if player else last.winner_card_id

    # draw_metadata içinde ödül miktarı/para birimi saklanmıştı (mini_bonus.py'de)
    meta = last.draw_metadata or {}

    return {
        "found": True,
        "result_id": str(last.id),          # ekran bu ID'yi hatırlayıp "bunu daha önce gösterdim mi" diye bakacak
        "winner_name": winner_name,
        "winner_card_id": last.winner_card_id,
        "prize_amount": meta.get("prize_amount", "100"),
        "prize_currency": meta.get("prize_currency", "GEL"),
        "executed_at": last.executed_at.isoformat(),
    }
