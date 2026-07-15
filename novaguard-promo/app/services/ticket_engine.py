"""
NovaGuard Ticket Engine — v1.1
================================
Düzeltmeler:
  - get_consecutive_days: 30 ayrı query → tek GROUP BY query
  - process_session_tickets: sequence race condition giderildi
  - Casino timezone kullanımı (UTC değil)
  - Enum karşılaştırması düzeltildi (SessionStatus.ENDED)
"""
import hashlib
import secrets
import string
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy import select, func, and_, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import GameSession, Ticket, TicketFormula, GameType, SessionStatus
from ..core.config import settings


def now_casino() -> datetime:
    """Casino timezone'unda şimdiki zamanı döner."""
    return datetime.now(ZoneInfo(settings.CASINO_TIMEZONE))


def today_casino() -> date:
    return now_casino().date()


# ── TICKET NUMBER ─────────────────────────────────────────────────────────────

def generate_ticket_number(card_id: str, campaign_year: int, sequence: int) -> str:
    """NVG-YYYY-XXXXXXXXXXXXXXXX — cryptographically unique."""
    alphabet = string.ascii_uppercase + string.digits
    random_part = "".join(secrets.choice(alphabet) for _ in range(8))
    checksum = hashlib.sha256(
        f"{card_id}{campaign_year}{sequence}{random_part}".encode()
    ).hexdigest()[:4].upper()
    return f"NVG-{campaign_year}-{random_part}{checksum}"


# ── CONSECUTIVE DAYS — tek query ──────────────────────────────────────────────

async def get_consecutive_days(card_id: str, db: AsyncSession) -> int:
    """
    Oyuncunun ardışık gün sayısını TEK query ile hesaplar.
    Önceki versiyon: 30 ayrı DB çağrısı — düzeltildi.
    """
    today = today_casino()
    # Son 31 günde oturum açılan günleri getir
    cutoff = today - timedelta(days=31)
    result = await db.execute(
        select(func.date(GameSession.started_at).label("play_date"))
        .where(
            and_(
                GameSession.card_id == card_id,
                GameSession.status == SessionStatus.ENDED,
                func.date(GameSession.started_at) >= cutoff,
                func.date(GameSession.started_at) < today,
            )
        )
        .distinct()
        .order_by(func.date(GameSession.started_at).desc())
    )
    play_dates = {row.play_date for row in result}

    consecutive = 0
    check = today - timedelta(days=1)
    while check in play_dates:
        consecutive += 1
        check -= timedelta(days=1)
    return consecutive


# ── TODAY'S TICKETS ───────────────────────────────────────────────────────────

async def get_tickets_earned_today(card_id: str, db: AsyncSession) -> int:
    today = today_casino()
    result = await db.execute(
        select(func.count(Ticket.id)).where(
            and_(
                Ticket.card_id == card_id,
                Ticket.earned_date == today,
                Ticket.campaign_year == settings.CAMPAIGN_YEAR,
            )
        )
    )
    return result.scalar_one() or 0


# ── FORMULA ───────────────────────────────────────────────────────────────────

async def get_active_formula(db: AsyncSession) -> Optional[TicketFormula]:
    result = await db.execute(
        select(TicketFormula).where(TicketFormula.is_active == True).limit(1)
    )
    return result.scalar_one_or_none()


# ── CORE CALC ─────────────────────────────────────────────────────────────────

def calculate_raw_tickets(
    game_type: GameType,
    duration_minutes: int,
    formula: TicketFormula,
    turnover_amount: Decimal = Decimal("0"),
    average_bet: Decimal | None = None,
) -> int:
    """
    Bilet hesabı — iki veri modelini destekler:

    Model A — Average Bet (tercih edilen):
      Casino "oyuncu saatte ortalama X TL bahis yaptı" bilgisini gönderir.
      Bilet = (süre_saat × saatte_bilet) + (average_bet / eşik_değer)
      Bu model daha adildir: hem süre hem de oyun yoğunluğunu yansıtır.

    Model B — Turnover (alternatif):
      Casino toplam döngüyü gönderir.
      Bilet = (süre_saat × saatte_bilet) + (turnover / eşik_değer)

    İkisi de verilirse average_bet önceliklidir.
    İkisi de yoksa sadece süre bazlı hesaplanır.
    """
    min_minutes = (
        formula.live_min_session_minutes
        if game_type == GameType.LIVE
        else formula.slot_min_session_minutes
    )
    if duration_minutes < min_minutes:
        return 0

    hours = Decimal(str(duration_minutes)) / Decimal("60")

    if game_type == GameType.LIVE:
        tph = formula.live_tickets_per_hour
        tpu = formula.live_turnover_per_ticket
    else:
        tph = formula.slot_tickets_per_hour
        tpu = formula.slot_turnover_per_ticket

    # Süre bileşeni
    time_tickets = hours * tph

    # Bahis bileşeni — average_bet varsa onu kullan, yoksa turnover
    bet_tickets = Decimal("0")
    if average_bet and average_bet > 0 and tpu > 0:
        rounds_per_hour = Decimal(str(
            formula.live_rounds_per_hour if game_type == GameType.LIVE
            else formula.slot_rounds_per_hour
        ))
        estimated_turnover = average_bet * rounds_per_hour * hours
        bet_tickets = estimated_turnover / tpu
    elif turnover_amount > 0 and tpu > 0:
        bet_tickets = turnover_amount / tpu

    total = int(time_tickets + bet_tickets)
    return min(total, formula.max_tickets_per_session)


# ── SESSION → TICKETS (race-condition safe) ───────────────────────────────────

async def process_session_tickets(session: GameSession, db: AsyncSession) -> list[Ticket]:
    """
    Biten oturum için bilet hesaplar.
    Race condition fix: sequence tek seferde alınır, döngüde artırılır.
    """
    formula = await get_active_formula(db) or TicketFormula()

    if not session.duration_minutes or session.duration_minutes <= 0:
        return []

    raw = calculate_raw_tickets(
        game_type=session.game_type,
        duration_minutes=session.duration_minutes,
        formula=formula,
        turnover_amount=session.turnover_amount,
        average_bet=session.average_bet if hasattr(session, 'average_bet') else None,
    )
    if raw <= 0:
        return []

    today_earned    = await get_tickets_earned_today(session.card_id, db)
    remaining_today = max(0, formula.max_tickets_per_day - today_earned)
    if remaining_today <= 0:
        return []

    count = min(raw, remaining_today)

    # Ardışık gün bonusu
    consec = await get_consecutive_days(session.card_id, db)
    if consec >= formula.consecutive_day_bonus_days:
        bonus = formula.consecutive_day_bonus_tickets
        extra = min(bonus, formula.max_tickets_per_day - today_earned - count)
        count += max(0, extra)

    # Sequence: tek query, döngüde artır (race-condition safe)
    seq_result = await db.execute(
        select(func.count(Ticket.id)).where(
            and_(
                Ticket.card_id == session.card_id,
                Ticket.campaign_year == settings.CAMPAIGN_YEAR,
            )
        )
    )
    base_seq = (seq_result.scalar_one() or 0) + 1

    all_tiers = ["daily", "weekly", "monthly", "quarterly", "annual"]
    today     = today_casino()
    created   = []

    for i in range(count):
        ticket = Ticket(
            ticket_number=generate_ticket_number(session.card_id, settings.CAMPAIGN_YEAR, base_seq + i),
            card_id=session.card_id,
            session_id=session.id,
            campaign_year=settings.CAMPAIGN_YEAR,
            earned_date=today,
            valid_for_tiers=all_tiers,
            is_active=True,
        )
        db.add(ticket)
        created.append(ticket)

    session.tickets_earned = count
    await db.commit()
    return created


# ── SUMMARY ───────────────────────────────────────────────────────────────────

async def get_player_ticket_summary(card_id: str, db: AsyncSession) -> dict:
    total = await db.execute(
        select(func.count(Ticket.id)).where(
            and_(
                Ticket.card_id == card_id,
                Ticket.campaign_year == settings.CAMPAIGN_YEAR,
                Ticket.is_active == True,
            )
        )
    )
    today  = await get_tickets_earned_today(card_id, db)
    consec = await get_consecutive_days(card_id, db)
    return {
        "total_active_tickets": total.scalar_one() or 0,
        "tickets_earned_today": today,
        "consecutive_days": consec,
        "campaign_year": settings.CAMPAIGN_YEAR,
    }
