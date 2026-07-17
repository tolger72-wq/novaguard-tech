"""
NovaGuard Draw Engine — v2.0
==============================

DIŞLAMA KURALI (kesinleşmiş versiyon):

  GÜNLÜK:
    Bugün herhangi bir ödül kazandıysan → bugünkü diğer günlük çekilişlere giremezsin.
    Yarın sıfırdan başlarsın. Haftalık/aylık/final ETKİLENMEZ.

  HAFTALIK:
    Bu haftanın haftalık çekilişini kazandıysan → SADECE BİR SONRAKI haftanın
    haftalık çekilişine giremezsin. İki hafta sonra tekrar giriyorsun.
    Günlük/aylık/final ETKİLENMEZ.

  AYLIK:
    Bu ayın aylık çekilişini kazandıysan → sadece bir sonraki ayın aylık çekilişine
    giremezsin. Diğer tierlar ETKİLENMEZ.

  ÇEYREK:
    Bu çeyreğin çekiliş kazananı → sadece bir sonraki çeyreğe giremez.
    Diğer tierlar ETKİLENMEZ.

  FİNAL:
    HERKES HER ZAMAN. Ne kadar ödül kazanmış olursa olsun. İstisna yok.

KÜÇÜK OYUNCU KORUMASI (fairness cap):
    Her oyuncunun havuzdaki bilet sayısı formula.max_pool_tickets ile sınırlıdır.
    Büyük oyuncunun avantajı var ama sınırsız değil — küçük oyuncunun gerçek şansı var.
"""
import secrets
from calendar import monthrange
from datetime import datetime, timedelta, date
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy import select, and_, func, cast, Date
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Player, Ticket, DrawSchedule, DrawResult, PrizeWin, DrawTier, DrawStatus
from ..core.config import settings

_rng = secrets.SystemRandom()


def now_casino() -> datetime:
    return datetime.now(ZoneInfo(settings.CASINO_TIMEZONE))


def today_casino() -> date:
    return now_casino().date()


# ── DÖNEM HESAPLAMA ───────────────────────────────────────────────────────────

def _week_bounds(ref: date) -> tuple[date, date]:
    """Pazartesi-Pazar sınırları."""
    monday = ref - timedelta(days=ref.weekday())
    return monday, monday + timedelta(days=6)


def _month_bounds(ref: date) -> tuple[date, date]:
    start = ref.replace(day=1)
    _, days = monthrange(ref.year, ref.month)
    return start, start + timedelta(days=days - 1)


def _quarter_bounds(ref: date) -> tuple[date, date]:
    q_start_month = ((ref.month - 1) // 3) * 3 + 1
    start = ref.replace(month=q_start_month, day=1)
    end_month = q_start_month + 3
    if end_month > 12:
        end = date(ref.year + 1, end_month - 12, 1) - timedelta(days=1)
    else:
        end = date(ref.year, end_month, 1) - timedelta(days=1)
    return start, end


def _prev_week(ref: date) -> tuple[date, date]:
    monday, _ = _week_bounds(ref)
    prev_monday = monday - timedelta(weeks=1)
    return prev_monday, monday - timedelta(days=1)


def _prev_month(ref: date) -> tuple[date, date]:
    this_start = ref.replace(day=1)
    prev_end = this_start - timedelta(days=1)
    return prev_end.replace(day=1), prev_end


def _prev_quarter(ref: date) -> tuple[date, date]:
    q_start, _ = _quarter_bounds(ref)
    prev_end = q_start - timedelta(days=1)
    return _quarter_bounds(prev_end)


# ── DIŞLAMA KONTROLÜ — TEK OYUNCU ─────────────────────────────────────────────

async def is_excluded(card_id: str, draw_tier: DrawTier, db: AsyncSession,
                       ref_date: date | None = None) -> bool:
    """
    Oyuncu bu çekilişten dışlanmış mı?

    GÜNLÜK  → bugün herhangi bir ödül kazandı mı?
    HAFTALIK → GEÇEN HAFTA haftalık ödül kazandı mı?
    AYLIK   → GEÇEN AY aylık ödül kazandı mı?
    ÇEYREK  → GEÇEN ÇEYREKTE çeyrek ödül kazandı mı?
    FİNAL   → Asla hayır.
    """
    if draw_tier == DrawTier.ANNUAL:
        return False

    if ref_date is None:
        ref_date = today_casino()

    year = settings.CAMPAIGN_YEAR

    if draw_tier == DrawTier.DAILY:
        # Bugün herhangi bir ödül kazandı mı?
        q = select(func.count(PrizeWin.id)).where(
            and_(
                PrizeWin.card_id == card_id,
                PrizeWin.campaign_year == year,
                cast(PrizeWin.won_at, Date) == ref_date,
            )
        )

    elif draw_tier == DrawTier.WEEKLY:
        # Geçen hafta (Pzt-Paz) haftalık ödül kazandı mı?
        prev_start, prev_end = _prev_week(ref_date)
        q = select(func.count(PrizeWin.id)).where(
            and_(
                PrizeWin.card_id == card_id,
                PrizeWin.campaign_year == year,
                PrizeWin.draw_tier == DrawTier.WEEKLY,
                cast(PrizeWin.won_at, Date) >= prev_start,
                cast(PrizeWin.won_at, Date) <= prev_end,
            )
        )

    elif draw_tier == DrawTier.MONTHLY:
        # Geçen ay aylık ödül kazandı mı?
        prev_start, prev_end = _prev_month(ref_date)
        q = select(func.count(PrizeWin.id)).where(
            and_(
                PrizeWin.card_id == card_id,
                PrizeWin.campaign_year == year,
                PrizeWin.draw_tier == DrawTier.MONTHLY,
                cast(PrizeWin.won_at, Date) >= prev_start,
                cast(PrizeWin.won_at, Date) <= prev_end,
            )
        )

    elif draw_tier == DrawTier.QUARTERLY:
        # Geçen çeyrekte çeyrek ödül kazandı mı?
        prev_start, prev_end = _prev_quarter(ref_date)
        q = select(func.count(PrizeWin.id)).where(
            and_(
                PrizeWin.card_id == card_id,
                PrizeWin.campaign_year == year,
                PrizeWin.draw_tier == DrawTier.QUARTERLY,
                cast(PrizeWin.won_at, Date) >= prev_start,
                cast(PrizeWin.won_at, Date) <= prev_end,
            )
        )
    else:
        return False

    result = await db.execute(q)
    return (result.scalar_one() or 0) > 0


# ── ELİGİBLE POOL — toplu query + fairness cap ────────────────────────────────

async def get_eligible_players(
    draw_tier: DrawTier,
    db: AsyncSession,
    ref_date: date | None = None,
) -> list[tuple[Player, list[Ticket]]]:
    """
    Bu çekilişe katılabilecek oyuncu + bilet listesi.

    N+1 fix: Her tier için tek bir batch query ile dışlanan kart ID'leri bulunur.
    Fairness cap: Her oyuncunun havuzdaki maksimum bilet sayısı sınırlıdır.
    """
    if ref_date is None:
        ref_date = today_casino()

    year = settings.CAMPAIGN_YEAR

    # ── 1. Tüm aktif oyuncular ────────────────────────────────────────────────
    players_res = await db.execute(select(Player).where(Player.is_active == True))
    all_players = players_res.scalars().all()
    if not all_players:
        return []

    # ── 2. Dışlanan card_id'leri BATCH query ile al ────────────────────────────
    excluded_ids: set[str] = set()

    if draw_tier != DrawTier.ANNUAL:
        if draw_tier == DrawTier.DAILY:
            excl_q = select(PrizeWin.card_id).where(
                and_(
                    PrizeWin.campaign_year == year,
                    cast(PrizeWin.won_at, Date) == ref_date,
                )
            ).distinct()

        elif draw_tier == DrawTier.WEEKLY:
            prev_start, prev_end = _prev_week(ref_date)
            excl_q = select(PrizeWin.card_id).where(
                and_(
                    PrizeWin.campaign_year == year,
                    PrizeWin.draw_tier == DrawTier.WEEKLY,
                    cast(PrizeWin.won_at, Date) >= prev_start,
                    cast(PrizeWin.won_at, Date) <= prev_end,
                )
            ).distinct()

        elif draw_tier == DrawTier.MONTHLY:
            prev_start, prev_end = _prev_month(ref_date)
            excl_q = select(PrizeWin.card_id).where(
                and_(
                    PrizeWin.campaign_year == year,
                    PrizeWin.draw_tier == DrawTier.MONTHLY,
                    cast(PrizeWin.won_at, Date) >= prev_start,
                    cast(PrizeWin.won_at, Date) <= prev_end,
                )
            ).distinct()

        elif draw_tier == DrawTier.QUARTERLY:
            prev_start, prev_end = _prev_quarter(ref_date)
            excl_q = select(PrizeWin.card_id).where(
                and_(
                    PrizeWin.campaign_year == year,
                    PrizeWin.draw_tier == DrawTier.QUARTERLY,
                    cast(PrizeWin.won_at, Date) >= prev_start,
                    cast(PrizeWin.won_at, Date) <= prev_end,
                )
            ).distinct()

        excl_res = await db.execute(excl_q)
        excluded_ids = {row[0] for row in excl_res}

    eligible = [p for p in all_players if p.card_id not in excluded_ids]
    if not eligible:
        return []

    # ── 3. Tüm aktif biletleri tek query ──────────────────────────────────────
    card_ids = [p.card_id for p in eligible]
    tickets_res = await db.execute(
        select(Ticket).where(
            and_(
                Ticket.card_id.in_(card_ids),
                Ticket.campaign_year == year,
                Ticket.is_active == True,
                Ticket.used_in_draw_id == None,
            )
        )
    )
    all_tickets = tickets_res.scalars().all()

    ticket_map: dict[str, list[Ticket]] = {}
    for t in all_tickets:
        ticket_map.setdefault(t.card_id, []).append(t)

    # ── 4. Fairness cap — küçük oyuncu koruması ───────────────────────────────
    # Bilet sayısı formüldeki max_pool_tickets ile sınırlıdır.
    # Büyük oyuncunun avantajı var ama sınırsız değil.
    from ..services.ticket_engine import get_active_formula
    formula = await get_active_formula(db)
    cap = formula.max_pool_tickets if formula and hasattr(formula, 'max_pool_tickets') else 20

    result = []
    for p in eligible:
        raw_tickets = ticket_map.get(p.card_id, [])
        if not raw_tickets:
            continue
        # Cap uygula — en eski biletler önce gelir (daha adil sıralama)
        capped = raw_tickets[:cap]
        result.append((p, capped))

    return result


async def get_pool_stats(draw_tier: DrawTier, db: AsyncSession) -> dict:
    ref = today_casino()
    eligible = await get_eligible_players(draw_tier, db, ref)
    total_tickets = sum(len(t) for _, t in eligible)
    return {
        "draw_tier": draw_tier.value,
        "ref_date": ref.isoformat(),
        "eligible_players": len(eligible),
        "total_tickets": total_tickets,
        "players": [
            {"card_id": p.card_id, "name": p.name, "ticket_count": len(t)}
            for p, t in eligible
        ],
    }


# ── ÇEKİLİŞ YÜRÜTME ──────────────────────────────────────────────────────────

async def execute_draw(schedule: DrawSchedule, db: AsyncSession) -> DrawResult:
    """
    Casino-grade çekiliş yürütme:
      - secrets.SystemRandom (kriptografik RNG)
      - SELECT FOR UPDATE (eş zamanlı çalıştırma kilidi)
      - Vergi beyanı artık zorunlu kapı değil — opsiyonel kayıt
    """
    locked = await db.execute(
        select(DrawSchedule).where(DrawSchedule.id == schedule.id).with_for_update()
    )
    schedule = locked.scalar_one()

    if schedule.status != DrawStatus.SCHEDULED:
        raise ValueError(f"Bu çekiliş zaten {schedule.status.value} durumunda.")

    schedule.status = DrawStatus.IN_PROGRESS
    await db.flush()

    draw_date = schedule.scheduled_at.date() if schedule.scheduled_at else today_casino()
    eligible = await get_eligible_players(schedule.draw_tier, db, draw_date)

    if not eligible:
        schedule.status = DrawStatus.SCHEDULED
        await db.commit()
        raise ValueError("Çekilişe katılabilecek uygun oyuncu bulunamadı.")

    pool: list[tuple[Player, Ticket]] = [
        (player, ticket)
        for player, tickets in eligible
        for ticket in tickets
    ]

    winner_player, winning_ticket = _rng.choice(pool)

    schedule.status = DrawStatus.COMPLETED

    result = DrawResult(
        schedule_id=schedule.id,
        winner_card_id=winner_player.card_id,
        winning_ticket_number=winning_ticket.ticket_number,
        total_tickets_in_pool=len(pool),
        total_players_in_pool=len(eligible),
        executed_at=now_casino(),
        executed_by=getattr(schedule, '_executed_by', None),
        draw_metadata={
            "draw_tier": schedule.draw_tier.value,
            "prize_amount": str(schedule.prize_amount),
            "prize_currency": schedule.prize_currency,
            "rng": "secrets.SystemRandom",
            "ref_date": draw_date.isoformat(),
        },
    )
    db.add(result)
    await db.flush()

    winning_ticket.used_in_draw_id = result.id

    prize_win = PrizeWin(
        card_id=winner_player.card_id,
        draw_tier=schedule.draw_tier,
        draw_result_id=result.id,
        prize_amount=schedule.prize_amount,
        prize_currency=schedule.prize_currency,
        prize_description=schedule.prize_description,
        campaign_year=settings.CAMPAIGN_YEAR,
    )
    db.add(prize_win)
    await db.commit()
    await db.refresh(result)
    return result


# ── ELİGİBİLİTY DURUMU ───────────────────────────────────────────────────────

async def get_player_eligibility_status(card_id: str, db: AsyncSession) -> dict:
    today = today_casino()
    tiers = [DrawTier.DAILY, DrawTier.WEEKLY, DrawTier.MONTHLY, DrawTier.QUARTERLY, DrawTier.ANNUAL]

    eligibility = {}
    for tier in tiers:
        excluded = await is_excluded(card_id, tier, db, today)
        eligibility[tier.value] = {"eligible": not excluded}

    wins_res = await db.execute(
        select(PrizeWin)
        .where(and_(PrizeWin.card_id == card_id, PrizeWin.campaign_year == settings.CAMPAIGN_YEAR))
        .order_by(PrizeWin.won_at.desc())
        .limit(10)
    )
    wins = wins_res.scalars().all()

    from ..services.ticket_engine import get_player_ticket_summary
    ticket_summary = await get_player_ticket_summary(card_id, db)

    return {
        "card_id": card_id,
        "eligibility_by_tier": eligibility,
        "wins_this_year": [
            {"tier": w.draw_tier.value, "prize": w.prize_description,
             "amount": str(w.prize_amount), "currency": w.prize_currency,
             "won_at": w.won_at.isoformat()}
            for w in wins
        ],
        "ticket_summary": ticket_summary,
    }


async def get_draw_history(db: AsyncSession, limit: int = 20) -> list[DrawResult]:
    result = await db.execute(
        select(DrawResult).order_by(DrawResult.executed_at.desc()).limit(limit)
    )
    return result.scalars().all()
