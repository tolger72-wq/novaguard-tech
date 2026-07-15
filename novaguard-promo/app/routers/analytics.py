"""
NovaGuard Analytics — ROI & Retention Modülü
==============================================
Casino yönetimine "Bu sistem ne işe yaradı?" sorusunun cevabını verir.

Temel fikir:
  Sistem devreye girmeden önce casino'nun oyuncu ziyaret verisi yoktu.
  Sistem devreye girdikten sonra her oturum kaydediliyor.
  Bu sayede haftalık/aylık trend karşılaştırması yapılabiliyor.

  Ek olarak: bilet sahibi oyuncular (sisteme katılanlar) ile
  bileti olmayan oyuncuları (sisteme katılmayanlar) karşılaştırıyoruz.
  Bu A/B testi gibi çalışır — farkı sistem yarattı.
"""
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from sqlalchemy import select, func, and_, distinct, case
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import Player, GameSession, Ticket, PrizeWin, SessionStatus
from ..core.config import settings
from ..core.security import require_admin

router = APIRouter(prefix="/analytics", tags=["Analytics"])


def now_casino():
    return datetime.now(ZoneInfo(settings.CASINO_TIMEZONE))

def today_casino():
    return now_casino().date()


# ── GENEL ÖZET ────────────────────────────────────────────────────────────────

@router.get("/summary")
async def analytics_summary(
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_admin),
):
    """
    Tek bakışta tüm KPI'lar.
    Casino yöneticisi bu ekranı sabah toplantıda gösterir.
    """
    today    = today_casino()
    year     = settings.CAMPAIGN_YEAR
    wk_start = today - timedelta(days=today.weekday())       # Bu hafta Pzt
    mo_start = today.replace(day=1)                          # Bu ay 1
    lst_mo_e = mo_start - timedelta(days=1)                  # Geçen ay sonu
    lst_mo_s = lst_mo_e.replace(day=1)                       # Geçen ay başı

    # Toplam kayıtlı oyuncu
    total_players = (await db.execute(
        select(func.count(Player.id)).where(Player.is_active == True)
    )).scalar_one() or 0

    # Bu hafta aktif oyuncu (en az 1 oturum)
    active_this_week = (await db.execute(
        select(func.count(distinct(GameSession.card_id))).where(
            and_(
                GameSession.status == SessionStatus.ENDED,
                func.date(GameSession.started_at) >= wk_start,
            )
        )
    )).scalar_one() or 0

    # Bu ay aktif oyuncu
    active_this_month = (await db.execute(
        select(func.count(distinct(GameSession.card_id))).where(
            and_(
                GameSession.status == SessionStatus.ENDED,
                func.date(GameSession.started_at) >= mo_start,
            )
        )
    )).scalar_one() or 0

    # Geçen ay aktif oyuncu
    active_last_month = (await db.execute(
        select(func.count(distinct(GameSession.card_id))).where(
            and_(
                GameSession.status == SessionStatus.ENDED,
                func.date(GameSession.started_at) >= lst_mo_s,
                func.date(GameSession.started_at) <= lst_mo_e,
            )
        )
    )).scalar_one() or 0

    # Retention: geçen ay gelenlerin bu ay da gelme oranı
    last_month_players = (await db.execute(
        select(distinct(GameSession.card_id)).where(
            and_(
                GameSession.status == SessionStatus.ENDED,
                func.date(GameSession.started_at) >= lst_mo_s,
                func.date(GameSession.started_at) <= lst_mo_e,
            )
        )
    )).scalars().all()

    retained = 0
    if last_month_players:
        retained = (await db.execute(
            select(func.count(distinct(GameSession.card_id))).where(
                and_(
                    GameSession.card_id.in_(last_month_players),
                    GameSession.status == SessionStatus.ENDED,
                    func.date(GameSession.started_at) >= mo_start,
                )
            )
        )).scalar_one() or 0

    retention_rate = round(retained / len(last_month_players) * 100, 1) if last_month_players else 0

    # Bu ay ortalama oturum süresi (dakika)
    avg_session = (await db.execute(
        select(func.avg(GameSession.duration_minutes)).where(
            and_(
                GameSession.status == SessionStatus.ENDED,
                GameSession.duration_minutes > 0,
                func.date(GameSession.started_at) >= mo_start,
            )
        )
    )).scalar_one()
    avg_session = round(float(avg_session), 1) if avg_session else 0

    # Bilet sahibi oyuncu sayısı (sisteme entegre)
    engaged_players = (await db.execute(
        select(func.count(distinct(Ticket.card_id))).where(
            and_(
                Ticket.campaign_year == year,
                Ticket.is_active == True,
            )
        )
    )).scalar_one() or 0

    engagement_rate = round(engaged_players / total_players * 100, 1) if total_players else 0

    # Bu haftaki ortalama günlük ziyaret (oturum/gün)
    days_this_week = max(1, (today - wk_start).days + 1)
    sessions_this_week = (await db.execute(
        select(func.count(GameSession.id)).where(
            and_(
                GameSession.status == SessionStatus.ENDED,
                func.date(GameSession.started_at) >= wk_start,
            )
        )
    )).scalar_one() or 0
    daily_sessions_avg = round(sessions_this_week / days_this_week, 1)

    return {
        "period": {"week_start": wk_start.isoformat(), "month_start": mo_start.isoformat()},
        "players": {
            "total_registered": total_players,
            "active_this_week": active_this_week,
            "active_this_month": active_this_month,
            "active_last_month": active_last_month,
            "engaged_with_tickets": engaged_players,
            "engagement_rate_pct": engagement_rate,
        },
        "retention": {
            "last_month_players": len(last_month_players),
            "retained_this_month": retained,
            "retention_rate_pct": retention_rate,
            "interpretation": (
                "Mükemmel" if retention_rate >= 70 else
                "İyi" if retention_rate >= 50 else
                "Geliştirilmeli"
            ),
        },
        "sessions": {
            "avg_duration_minutes": avg_session,
            "daily_sessions_avg_this_week": daily_sessions_avg,
        },
    }


# ── HAFTALIK TREND ────────────────────────────────────────────────────────────

@router.get("/weekly-trend")
async def weekly_trend(
    weeks: int = 12,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_admin),
):
    """
    Son N haftanın karşılaştırmalı verisi.
    Grafik için: Sistem devreye girdikten sonra eğri yukarı gidiyorsa işe yarıyor.
    """
    today = today_casino()
    result = []

    for i in range(weeks - 1, -1, -1):
        wk_end   = today - timedelta(days=today.weekday()) + timedelta(days=6) - timedelta(weeks=i)
        wk_start = wk_end - timedelta(days=6)

        # O haftaki unique oyuncu
        unique = (await db.execute(
            select(func.count(distinct(GameSession.card_id))).where(
                and_(
                    GameSession.status == SessionStatus.ENDED,
                    func.date(GameSession.started_at) >= wk_start,
                    func.date(GameSession.started_at) <= wk_end,
                )
            )
        )).scalar_one() or 0

        # O haftaki toplam oturum
        sessions = (await db.execute(
            select(func.count(GameSession.id)).where(
                and_(
                    GameSession.status == SessionStatus.ENDED,
                    func.date(GameSession.started_at) >= wk_start,
                    func.date(GameSession.started_at) <= wk_end,
                )
            )
        )).scalar_one() or 0

        # O haftaki ortalama süre
        avg_dur = (await db.execute(
            select(func.avg(GameSession.duration_minutes)).where(
                and_(
                    GameSession.status == SessionStatus.ENDED,
                    GameSession.duration_minutes > 0,
                    func.date(GameSession.started_at) >= wk_start,
                    func.date(GameSession.started_at) <= wk_end,
                )
            )
        )).scalar_one()

        result.append({
            "week_label": f"Hf {wk_start.strftime('%d.%m')}",
            "week_start": wk_start.isoformat(),
            "unique_players": unique,
            "total_sessions": sessions,
            "avg_session_min": round(float(avg_dur), 1) if avg_dur else 0,
            "visits_per_player": round(sessions / unique, 2) if unique else 0,
        })

    return {"weeks": result, "period_count": weeks}


# ── ENGAGED vs NON-ENGAGED KARŞILAŞTIRMASI ────────────────────────────────────

@router.get("/engagement-comparison")
async def engagement_comparison(
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_admin),
):
    """
    BİLET SAHİBİ vs BİLET SAHİBİ OLMAYAN oyuncu karşılaştırması.

    Bu, sistemin değerini kanıtlayan en güçlü metrik:
    "Çekilişe katılan oyuncular daha sık geliyor ve daha uzun kalıyor."

    Eğer bu fark büyükse = sistem çalışıyor.
    Eğer fark yoksa = dışlama kuralları veya ödül büyüklüğü gözden geçirilmeli.
    """
    year     = settings.CAMPAIGN_YEAR
    mo_start = today_casino().replace(day=1)

    # Bilet sahibi oyuncular
    engaged_ids = (await db.execute(
        select(distinct(Ticket.card_id)).where(
            and_(Ticket.campaign_year == year, Ticket.is_active == True)
        )
    )).scalars().all()

    engaged_ids = list(engaged_ids)

    async def get_metrics(card_ids: list, label: str) -> dict:
        if not card_ids:
            return {"group": label, "players": 0, "avg_sessions_per_week": 0, "avg_duration_min": 0}

        # Bu aydaki oturumlar
        sessions_q = await db.execute(
            select(
                func.count(GameSession.id).label("total"),
                func.count(distinct(GameSession.card_id)).label("unique"),
                func.avg(GameSession.duration_minutes).label("avg_dur"),
            ).where(
                and_(
                    GameSession.card_id.in_(card_ids),
                    GameSession.status == SessionStatus.ENDED,
                    func.date(GameSession.started_at) >= mo_start,
                )
            )
        )
        row = sessions_q.one()
        total    = row.total or 0
        unique   = row.unique or 0
        avg_dur  = float(row.avg_dur) if row.avg_dur else 0
        weeks_in_month = 4.3

        return {
            "group": label,
            "players": len(card_ids),
            "total_sessions_this_month": total,
            "avg_sessions_per_player_per_week": round(total / max(unique, 1) / weeks_in_month, 2),
            "avg_duration_min": round(avg_dur, 1),
        }

    # Bilet sahibi OLMAYAN oyuncular
    all_ids = (await db.execute(select(Player.card_id).where(Player.is_active == True))).scalars().all()
    non_engaged = [cid for cid in all_ids if cid not in set(engaged_ids)]

    engaged_metrics     = await get_metrics(engaged_ids, "Çekilişe Katılan (Bilet Sahibi)")
    non_engaged_metrics = await get_metrics(non_engaged, "Çekilişe Katılmayan")

    # Fark hesapla
    e_sess = engaged_metrics["avg_sessions_per_player_per_week"]
    n_sess = non_engaged_metrics["avg_sessions_per_player_per_week"]
    e_dur  = engaged_metrics["avg_duration_min"]
    n_dur  = non_engaged_metrics["avg_duration_min"]

    return {
        "engaged":     engaged_metrics,
        "non_engaged": non_engaged_metrics,
        "difference": {
            "visit_frequency_uplift_pct": round((e_sess - n_sess) / max(n_sess, 0.01) * 100, 1),
            "session_duration_uplift_pct": round((e_dur - n_dur) / max(n_dur, 0.01) * 100, 1),
            "interpretation": (
                "Sistem etkili — katılanlar daha sık ve uzun geliyor"
                if e_sess > n_sess else
                "Sistem henüz etki göstermiyor — kural/ödül gözden geçir"
            ),
        },
    }


# ── OYUNCU BAZLI DETAY ────────────────────────────────────────────────────────

@router.get("/player/{card_id}")
async def player_analytics(
    card_id: str,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_admin),
):
    """Tek oyuncunun zaman içindeki davranış değişimi."""
    today    = today_casino()
    year     = settings.CAMPAIGN_YEAR

    # Son 8 hafta haftalık oturum sayısı
    weekly = []
    for i in range(7, -1, -1):
        wk_end   = today - timedelta(days=today.weekday()) + timedelta(days=6) - timedelta(weeks=i)
        wk_start = wk_end - timedelta(days=6)
        sessions = (await db.execute(
            select(func.count(GameSession.id)).where(
                and_(
                    GameSession.card_id == card_id,
                    GameSession.status == SessionStatus.ENDED,
                    func.date(GameSession.started_at) >= wk_start,
                    func.date(GameSession.started_at) <= wk_end,
                )
            )
        )).scalar_one() or 0
        weekly.append({"week": wk_start.strftime("%d.%m"), "sessions": sessions})

    # Toplam bilet
    total_tickets = (await db.execute(
        select(func.count(Ticket.id)).where(
            and_(Ticket.card_id == card_id, Ticket.campaign_year == year, Ticket.is_active == True)
        )
    )).scalar_one() or 0

    # Kazanımlar
    wins = (await db.execute(
        select(PrizeWin).where(
            and_(PrizeWin.card_id == card_id, PrizeWin.campaign_year == year)
        ).order_by(PrizeWin.won_at)
    )).scalars().all()

    return {
        "card_id": card_id,
        "total_tickets": total_tickets,
        "weekly_sessions": weekly,
        "wins": [{"tier": w.draw_tier.value, "prize": w.prize_description, "date": w.won_at.isoformat()} for w in wins],
    }
