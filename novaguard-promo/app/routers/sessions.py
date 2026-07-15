"""
Casino Entegrasyon Endpointleri
Casino sistemi gerçek zamanlı olarak oturum verisi push eder.
Biz casino sisteminden veri çekmiyoruz — onlar bize bağlanıyor.
"""
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import GameSession, Player, GameType, SessionStatus
from ..schemas import SessionPush, SessionEnd, SessionOut, PlayerCreate, PlayerOut
from ..core.security import require_crm, require_admin
from ..services.ticket_engine import process_session_tickets

router = APIRouter(prefix="/sessions", tags=["Casino — Oturumlar"])


# ── PLAYER SYNC ───────────────────────────────────────────────────────────────

@router.post("/players/sync", response_model=PlayerOut, status_code=status.HTTP_200_OK)
async def sync_player(
    data: PlayerCreate,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_crm),
):
    """
    Oyuncu kaydı veya güncellemesi.
    İsim senkronizasyonu için — kişisel veri göndermek opsiyoneldir.
    Gönderilmezse sistem kart numarasıyla devam eder.
    """
    result = await db.execute(select(Player).where(Player.card_id == data.card_id))
    player = result.scalar_one_or_none()

    if player:
        player.name = data.name
    else:
        player = Player(card_id=data.card_id, name=data.name)
        db.add(player)

    await db.commit()
    await db.refresh(player)
    return player


# ── SESSION PUSH ──────────────────────────────────────────────────────────────

@router.post("/push", response_model=SessionOut, status_code=status.HTTP_201_CREATED)
async def push_session(
    data: SessionPush,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_crm),
):
    """
    Oyuncu masaya/makineye oturduğunda casino sistemi bu endpoint'i çağırır.
    Oyuncu kayıtlı değilse otomatik oluşturulur.
    """
    # Oyuncu otomatik kayıt
    result = await db.execute(select(Player).where(Player.card_id == data.card_id))
    if not result.scalar_one_or_none():
        db.add(Player(card_id=data.card_id, name=f"Oyuncu {data.card_id}"))
        await db.flush()

    # Idempotency — aynı external_session_id tekrar gelirse güncelle
    if data.external_session_id:
        existing = await db.execute(
            select(GameSession).where(
                GameSession.external_session_id == data.external_session_id
            )
        )
        session = existing.scalar_one_or_none()
        if session:
            if data.average_bet is not None:
                session.average_bet = data.average_bet
            if data.turnover_amount:
                session.turnover_amount = data.turnover_amount
            await db.commit()
            await db.refresh(session)
            return session

    session = GameSession(
        external_session_id=data.external_session_id,
        card_id=data.card_id,
        game_type=GameType(data.game_type),
        game_name=data.game_name,
        table_id=data.table_id,
        started_at=data.started_at,
        turnover_amount=data.turnover_amount,
        average_bet=data.average_bet,          # FIX 1 — average_bet kaydediliyor
        currency=data.currency,
        status=SessionStatus.ACTIVE,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


# ── SESSION END ───────────────────────────────────────────────────────────────

def _close_session(session: GameSession, data: SessionEnd) -> None:
    """Oturum kapatma mantığı — iki endpoint'te de aynı."""
    session.ended_at = data.ended_at
    # average_bet varsa güncelle (FIX 2)
    if data.final_average_bet is not None:
        session.average_bet = data.final_average_bet
    elif data.final_turnover_amount is not None:
        session.turnover_amount = data.final_turnover_amount
    session.duration_minutes = max(
        0, int((data.ended_at - session.started_at).total_seconds() / 60)
    )
    session.status = SessionStatus.ENDED


@router.patch("/{session_id}/end", response_model=SessionOut)
async def end_session(
    session_id: UUID,
    data: SessionEnd,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_crm),
):
    """NovaGuard session ID ile oturum kapatır. Biletler hesaplanır."""
    result = await db.execute(select(GameSession).where(GameSession.id == session_id))
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Oturum bulunamadı")
    if session.status == SessionStatus.ENDED:
        raise HTTPException(status_code=400, detail="Oturum zaten kapatılmış")

    _close_session(session, data)
    await db.flush()
    await process_session_tickets(session, db)
    return session


@router.patch("/by-external/{external_id}/end", response_model=SessionOut)
async def end_session_by_external(
    external_id: str,
    data: SessionEnd,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_crm),
):
    """Casino'nun kendi session ID'si ile oturum kapatır (tercih edilen yol)."""
    result = await db.execute(
        select(GameSession).where(GameSession.external_session_id == external_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Oturum bulunamadı")
    if session.status == SessionStatus.ENDED:
        return session  # Idempotent — tekrar gelirse sessizce dön

    _close_session(session, data)
    await db.flush()
    await process_session_tickets(session, db)
    return session


@router.get("/{card_id}/history", response_model=list[SessionOut])
async def session_history(
    card_id: str,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_admin),
):
    result = await db.execute(
        select(GameSession)
        .where(GameSession.card_id == card_id)
        .order_by(GameSession.started_at.desc())
        .limit(limit)
    )
    return result.scalars().all()
