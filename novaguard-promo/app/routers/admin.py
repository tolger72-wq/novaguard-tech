"""
Admin Paneli Endpointleri
Oyuncu yönetimi, bilet formülü, çekiliş yapılandırması.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import Player, Ticket, TicketFormula, PrizeWin
from ..schemas import (
    PlayerCreate, PlayerUpdate, PlayerOut,
    FormulaUpdate, FormulaOut,
    PlayerTicketSummary, TicketOut, PlayerEligibility,
)
from ..core.security import require_admin
from ..core.config import settings
from ..services.ticket_engine import get_player_ticket_summary
from ..services.draw_engine import get_player_eligibility_status

router = APIRouter(prefix="/admin", tags=["Admin"])


# ── PLAYERS ───────────────────────────────────────────────────────────────────

@router.post("/players", response_model=PlayerOut, status_code=status.HTTP_201_CREATED)
async def create_player(
    data: PlayerCreate,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_admin),
):
    existing = await db.execute(select(Player).where(Player.card_id == data.card_id))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Bu kart ID zaten kayıtlı")

    player = Player(**data.model_dump())
    db.add(player)
    await db.commit()
    await db.refresh(player)
    return player


@router.get("/players", response_model=list[PlayerOut])
async def list_players(
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_admin),
):
    result = await db.execute(
        select(Player).where(Player.is_active == True)
        .order_by(Player.registered_at.desc())
        .limit(limit).offset(offset)
    )
    return result.scalars().all()


@router.get("/players/{card_id}", response_model=PlayerOut)
async def get_player(card_id: str, db: AsyncSession = Depends(get_db), _: str = Depends(require_admin)):
    result = await db.execute(select(Player).where(Player.card_id == card_id))
    player = result.scalar_one_or_none()
    if not player:
        raise HTTPException(status_code=404, detail="Oyuncu bulunamadı")
    return player


@router.patch("/players/{card_id}", response_model=PlayerOut)
async def update_player(
    card_id: str,
    data: PlayerUpdate,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_admin),
):
    result = await db.execute(select(Player).where(Player.card_id == card_id))
    player = result.scalar_one_or_none()
    if not player:
        raise HTTPException(status_code=404, detail="Oyuncu bulunamadı")

    for field, value in data.model_dump(exclude_none=True).items():
        setattr(player, field, value)

    await db.commit()
    await db.refresh(player)
    return player


# ── TICKETS ───────────────────────────────────────────────────────────────────

@router.get("/players/{card_id}/tickets", response_model=PlayerTicketSummary)
async def get_player_tickets(
    card_id: str,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_admin),
):
    result = await db.execute(select(Player).where(Player.card_id == card_id))
    player = result.scalar_one_or_none()
    if not player:
        raise HTTPException(status_code=404, detail="Oyuncu bulunamadı")

    summary = await get_player_ticket_summary(card_id, db)

    # Örnek biletler
    tickets_result = await db.execute(
        select(Ticket).where(
            and_(
                Ticket.card_id == card_id,
                Ticket.campaign_year == settings.CAMPAIGN_YEAR,
                Ticket.is_active == True,
            )
        ).order_by(Ticket.created_at.desc()).limit(10)
    )
    sample = tickets_result.scalars().all()

    return PlayerTicketSummary(
        card_id=card_id,
        name=player.name,
        **summary,
        sample_tickets=sample,
    )


@router.get("/players/{card_id}/eligibility", response_model=PlayerEligibility)
async def get_eligibility(
    card_id: str,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_admin),
):
    """Oyuncunun hangi çekilişlere katılabileceğini göster."""
    result = await db.execute(select(Player).where(Player.card_id == card_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Oyuncu bulunamadı")

    return await get_player_eligibility_status(card_id, db)


# ── FORMULA ───────────────────────────────────────────────────────────────────

@router.get("/formula", response_model=FormulaOut)
async def get_formula(db: AsyncSession = Depends(get_db), _: str = Depends(require_admin)):
    """Aktif bilet formülünü getir."""
    result = await db.execute(
        select(TicketFormula).where(TicketFormula.is_active == True).limit(1)
    )
    formula = result.scalar_one_or_none()
    if not formula:
        # Varsayılanı oluştur
        formula = TicketFormula(name="Varsayılan", is_active=True)
        db.add(formula)
        await db.commit()
        await db.refresh(formula)
    return formula


@router.put("/formula", response_model=FormulaOut)
async def update_formula(
    data: FormulaUpdate,
    updated_by: str = "admin",
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_admin),
):
    """Bilet formülünü güncelle. Tüm alanlar opsiyonel."""
    result = await db.execute(
        select(TicketFormula).where(TicketFormula.is_active == True).limit(1)
    )
    formula = result.scalar_one_or_none()
    if not formula:
        formula = TicketFormula(name="Varsayılan", is_active=True)
        db.add(formula)

    for field, value in data.model_dump(exclude_none=True).items():
        setattr(formula, field, value)

    formula.updated_by = updated_by
    await db.commit()
    await db.refresh(formula)
    return formula


# ── CAMPAIGN STATS ────────────────────────────────────────────────────────────

@router.get("/stats/campaign")
async def campaign_stats(
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_admin),
):
    """Kampanya özet istatistikleri."""
    year = settings.CAMPAIGN_YEAR

    total_players = (await db.execute(select(func.count(Player.id)).where(Player.is_active == True))).scalar_one()
    total_tickets = (await db.execute(select(func.count(Ticket.id)).where(and_(Ticket.campaign_year == year, Ticket.is_active == True)))).scalar_one()
    total_wins = (await db.execute(select(func.count(PrizeWin.id)).where(PrizeWin.campaign_year == year))).scalar_one()

    wins_by_tier = {}
    from ..models import DrawTier
    for tier in DrawTier:
        count = (await db.execute(
            select(func.count(PrizeWin.id)).where(
                and_(PrizeWin.campaign_year == year, PrizeWin.draw_tier == tier)
            )
        )).scalar_one()
        wins_by_tier[tier.value] = count

    return {
        "campaign_year": year,
        "total_active_players": total_players,
        "total_active_tickets": total_tickets,
        "total_prize_wins": total_wins,
        "wins_by_tier": wins_by_tier,
    }


# ── BULK IMPORT ───────────────────────────────────────────────────────────────

from ..schemas import BulkPlayerImport

@router.post("/players/bulk-import")
async def bulk_import_players(
    data: BulkPlayerImport,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_admin),
):
    """
    Toplu oyuncu kaydı. Casino'nun oyuncu listesini tek seferde yüklemek için.
    Mevcut oyuncular güncellenir, yeni oyuncular eklenir.
    Sadece kart ID zorunlu — isim bilinmiyorsa kart numarası kullanılır.
    """
    created, updated, skipped = 0, 0, 0

    for p in data.players:
        if not p.card_id or not p.card_id.strip():
            skipped += 1
            continue

        result = await db.execute(select(Player).where(Player.card_id == p.card_id))
        existing = result.scalar_one_or_none()

        if existing:
            existing.name = p.name or existing.name
            updated += 1
        else:
            db.add(Player(
                card_id=p.card_id.strip(),
                name=p.name or f"Oyuncu {p.card_id}",
            ))
            created += 1

    await db.commit()
    return {
        "total": len(data.players),
        "created": created,
        "updated": updated,
        "skipped": skipped,
    }


# ── CSV RAPOR EXPORT ───────────────────────────────────────────────────────────

from fastapi.responses import StreamingResponse
import csv, io
from sqlalchemy import select, desc
from ..models import DrawResult, DrawSchedule, PrizeWin, Player

@router.get("/reports/draws.csv")
async def export_draws_csv(
    year: int = None,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_admin),
):
    """Tüm çekiliş sonuçlarını CSV olarak indir."""
    from ..core.config import settings
    campaign_year = year or settings.CAMPAIGN_YEAR

    results = await db.execute(
        select(DrawResult, DrawSchedule)
        .join(DrawSchedule, DrawResult.schedule_id == DrawSchedule.id)
        .where(DrawSchedule.campaign_year == campaign_year)
        .order_by(desc(DrawResult.executed_at))
    )
    rows = results.all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Çekiliş Adı", "Tür", "Tarih", "Ödül", "Para Birimi",
        "Kazanan Kart", "Kazanan Bilet", "Havuz Bilet",
        "Havuz Oyuncu", "Kim Yaptı", "Teslim Edildi", "Teslim Tarihi"
    ])
    for dr, ds in rows:
        writer.writerow([
            ds.name, ds.draw_tier.value,
            dr.executed_at.strftime("%d.%m.%Y %H:%M"),
            str(ds.prize_amount), ds.prize_currency,
            dr.winner_card_id, dr.winning_ticket_number,
            dr.total_tickets_in_pool, dr.total_players_in_pool,
            dr.executed_by or "—",
            "Evet" if dr.prize_distributed else "Hayır",
            dr.prize_distributed_at.strftime("%d.%m.%Y") if dr.prize_distributed_at else "—",
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=cekilis-rapor-{campaign_year}.csv"}
    )


@router.get("/reports/players.csv")
async def export_players_csv(
    year: int = None,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_admin),
):
    """Tüm oyuncuları bilet sayılarıyla CSV olarak indir."""
    from ..core.config import settings
    from ..models import Ticket
    from sqlalchemy import func, and_
    campaign_year = year or settings.CAMPAIGN_YEAR

    results = await db.execute(
        select(Player, func.count(Ticket.id).label("tickets"))
        .outerjoin(Ticket, and_(
            Ticket.card_id == Player.card_id,
            Ticket.campaign_year == campaign_year,
            Ticket.is_active == True,
        ))
        .group_by(Player.id)
        .order_by(desc("tickets"))
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Kart No", "İsim", "Aktif Bilet", "Aktif"])
    for player, tickets in results:
        writer.writerow([player.card_id, player.name, tickets or 0, "Evet" if player.is_active else "Hayır"])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=oyuncular-{campaign_year}.csv"}
    )


# ── MİNİ BONUS (AKTİF OYUNCU BONUSU) ──────────────────────────────────────────
# Basit özellik: belirli saatler arası, düzenli aralıklarla, o an oynayan bir
# oyuncuya küçük bir hediye verir. Casino ayarları admin panelinden değiştirir.

from pydantic import BaseModel as _BaseModel
from decimal import Decimal as _Decimal
from ..services import mini_bonus as mini_bonus_service


class MiniBonusConfigInput(_BaseModel):
    """Admin panelinden gelen mini bonus ayar güncellemesi."""
    is_active: bool
    prize_amount: _Decimal
    prize_currency: str = "GEL"
    interval_minutes: int
    window_start_hour: int   # 0-23 arası
    window_end_hour: int     # 0-23 arası


@router.get("/mini-bonus/config")
async def get_mini_bonus_config(
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_admin),
):
    """Şu anki mini bonus ayarlarını döner."""
    config = await mini_bonus_service.get_or_create_config(db)
    return {
        "is_active": config.is_active,
        "prize_amount": str(config.prize_amount),
        "prize_currency": config.prize_currency,
        "interval_minutes": config.interval_minutes,
        "window_start_hour": config.window_start_hour,
        "window_end_hour": config.window_end_hour,
    }


@router.put("/mini-bonus/config")
async def update_mini_bonus_config(
    data: MiniBonusConfigInput,
    updated_by: str = "admin",
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_admin),
):
    """Mini bonus ayarlarını günceller (açık/kapalı, ödül miktarı, saatler)."""
    config = await mini_bonus_service.get_or_create_config(db)

    config.is_active          = data.is_active
    config.prize_amount       = data.prize_amount
    config.prize_currency     = data.prize_currency
    config.interval_minutes   = data.interval_minutes
    config.window_start_hour  = data.window_start_hour
    config.window_end_hour    = data.window_end_hour
    config.updated_by         = updated_by

    await db.commit()
    await db.refresh(config)

    return {"saved": True, "config": mini_bonus_service.cost_estimate(config)}


@router.get("/mini-bonus/cost-estimate")
async def get_mini_bonus_cost_estimate(
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_admin),
):
    """
    Şu anki ayarlara göre günde kaç çekiliş yapılacağını ve maliyetini gösterir.
    Casino bütçe planlaması yaparken kullanır.
    """
    config = await mini_bonus_service.get_or_create_config(db)
    return mini_bonus_service.cost_estimate(config)


@router.post("/mini-bonus/execute-now")
async def execute_mini_bonus_now(
    db: AsyncSession = Depends(get_db),
    admin: str = Depends(require_admin),
):
    """
    Mini bonusu HEMEN, manuel olarak yürütür (test için).
    Normalde bu otomatik olarak arka planda (Celery) çalışır.
    """
    config = await mini_bonus_service.get_or_create_config(db)
    result = await mini_bonus_service.execute_mini_bonus(config, db)

    if result is None:
        return {"executed": False, "reason": "Şu an aktif oynayan oyuncu yok"}

    return {
        "executed": True,
        "winner_card_id": result.winner_card_id,
        "prize_amount": str(config.prize_amount),
        "prize_currency": config.prize_currency,
        "active_players_in_pool": result.total_players_in_pool,
    }
