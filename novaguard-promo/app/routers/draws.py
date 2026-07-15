"""
Çekiliş Yönetimi + WebSocket (real-time) + Campaign Reset
"""
from datetime import datetime, timezone
from uuid import UUID
import json

from fastapi import APIRouter, Depends, HTTPException, status, WebSocket, WebSocketDisconnect
from sqlalchemy import select, desc, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import DrawSchedule, DrawResult, DrawTier, DrawStatus, PrizeWin, Ticket
from ..schemas import DrawScheduleCreate, DrawScheduleOut, DrawResultOut, PoolStats, TaxDeclarationInput
from ..core.security import require_admin
from ..core.config import settings
from ..services.draw_engine import execute_draw, get_pool_stats, get_draw_history

router = APIRouter(prefix="/draws", tags=["Çekilişler"])

# ── WebSocket bağlantı yöneticisi ──────────────────────────────────────────────
class ConnectionManager:
    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket):
        self.active.remove(ws)

    async def broadcast(self, data: dict):
        for ws in self.active[:]:
            try:
                await ws.send_json(data)
            except Exception:
                self.active.remove(ws)

manager = ConnectionManager()


# ── WebSocket — display ekranı real-time güncellemeler ────────────────────────
@router.websocket("/ws")
async def draw_websocket(websocket: WebSocket, db: AsyncSession = Depends(get_db)):
    """
    Display ekranı buraya bağlanır.
    Admin çekiliş yürütünce tüm bağlı ekranlara push edilir.
    """
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()  # ping/pong
    except WebSocketDisconnect:
        manager.disconnect(websocket)


# ── Çekiliş Programla ─────────────────────────────────────────────────────────
@router.post("/schedule", response_model=DrawScheduleOut, status_code=status.HTTP_201_CREATED)
async def schedule_draw(
    data: DrawScheduleCreate,
    db: AsyncSession = Depends(get_db),
    admin: str = Depends(require_admin),
):
    """
    Yeni çekiliş programlar.
    Aynı tier için aynı günde sadece 1 çekiliş olabilir.
    """
    draw_date = data.scheduled_at.date()
    conflict = await db.execute(
        select(DrawSchedule).where(
            and_(
                DrawSchedule.draw_tier == DrawTier(data.draw_tier),
                DrawSchedule.status == DrawStatus.SCHEDULED,
                func.date(DrawSchedule.scheduled_at) == draw_date,
            )
        )
    )
    if conflict.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail=f"{data.draw_tier} çekilişi {draw_date} için zaten programlanmış"
        )

    schedule = DrawSchedule(
        draw_tier=DrawTier(data.draw_tier),
        name=data.name,
        description=data.description,
        scheduled_at=data.scheduled_at,
        prize_amount=data.prize_amount,
        prize_currency=data.prize_currency,
        prize_description=data.prize_description,
        annual_prize_options=data.annual_prize_options,
        tax_declaration_required=data.tax_declaration_required,
        campaign_year=settings.CAMPAIGN_YEAR,   # hardcode fix
        created_by=admin,
    )
    db.add(schedule)
    await db.commit()
    await db.refresh(schedule)
    return schedule


# ── Liste ──────────────────────────────────────────────────────────────────────
@router.get("/", response_model=list[DrawScheduleOut])
async def list_draws(
    tier: str = None,
    status_filter: str = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_admin),
):
    query = select(DrawSchedule).order_by(desc(DrawSchedule.scheduled_at)).limit(limit)
    if tier:
        query = query.where(DrawSchedule.draw_tier == DrawTier(tier))
    if status_filter:
        query = query.where(DrawSchedule.status == DrawStatus(status_filter))
    result = await db.execute(query)
    return result.scalars().all()


# ── Havuz önizle ──────────────────────────────────────────────────────────────
@router.get("/{schedule_id}/pool", response_model=PoolStats)
async def get_draw_pool(
    schedule_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_admin),
):
    result = await db.execute(select(DrawSchedule).where(DrawSchedule.id == schedule_id))
    schedule = result.scalar_one_or_none()
    if not schedule:
        raise HTTPException(status_code=404, detail="Çekiliş bulunamadı")
    return await get_pool_stats(schedule.draw_tier, db)


# ── Vergi Beyanı (RS.GE) ──────────────────────────────────────────────────────
@router.patch("/{schedule_id}/tax-declaration", response_model=DrawScheduleOut)
async def declare_tax(
    schedule_id: UUID,
    data: TaxDeclarationInput,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_admin),
):
    """
    RS.GE vergi beyanını ve ödemesini kayıt amacıyla sisteme işler.
    Bu, Casino'nun kendi iç muhasebe/hukuki sürecinin bir kaydıdır —
    NovaGuard bu adımı çekilişin yürütülmesi için zorunlu kılmaz
    (execute_draw bu alana bakmaz).

    Akış: Muhasebe RS.GE'ye beyan yapar → onay alır → vergiyi yatırır →
    bu endpoint'e referans numarasını ve ödenen tutarı girer →
    bilgi sertifikada ve raporlarda görünür.
    """
    result = await db.execute(select(DrawSchedule).where(DrawSchedule.id == schedule_id))
    schedule = result.scalar_one_or_none()
    if not schedule:
        raise HTTPException(status_code=404, detail="Çekiliş bulunamadı")

    if schedule.status != DrawStatus.SCHEDULED:
        raise HTTPException(status_code=400, detail="Sadece planlanmış çekilişler için vergi beyanı işlenebilir")

    schedule.tax_declaration_ref = data.tax_declaration_ref
    schedule.tax_amount_paid     = data.tax_amount_paid
    schedule.tax_declared_by     = data.declared_by
    schedule.tax_paid_at         = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(schedule)
    return schedule


@router.get("/{schedule_id}/tax-status")
async def get_tax_status(
    schedule_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_admin),
):
    """Çekilişin vergi beyanı kaydının durumunu hızlıca kontrol et (bilgi amaçlı — yürütmeyi etkilemez)."""
    result = await db.execute(select(DrawSchedule).where(DrawSchedule.id == schedule_id))
    schedule = result.scalar_one_or_none()
    if not schedule:
        raise HTTPException(status_code=404, detail="Çekiliş bulunamadı")

    return {
        "schedule_id": str(schedule_id),
        "tax_declaration_required": schedule.tax_declaration_required,
        "tax_cleared": schedule.tax_cleared,
        "tax_declaration_ref": schedule.tax_declaration_ref,
        "tax_amount_paid": str(schedule.tax_amount_paid) if schedule.tax_amount_paid else None,
        "tax_paid_at": schedule.tax_paid_at.isoformat() if schedule.tax_paid_at else None,
        # Yürütülebilirlik yalnızca durum'a bağlıdır — vergi beyanı bir kapı değildir.
        "can_execute": schedule.status == DrawStatus.SCHEDULED,
    }


# ── Çekilişi yürüt ───────────────────────────────────────────────────────────
@router.post("/{schedule_id}/execute", response_model=DrawResultOut)
async def run_draw(
    schedule_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin: str = Depends(require_admin),
):
    """
    Çekilişi yürütür. Row-lock ile eş zamanlı çalıştırma önlenir.
    Tamamlanınca WebSocket üzerinden tüm display ekranlarına push edilir.
    """
    result = await db.execute(select(DrawSchedule).where(DrawSchedule.id == schedule_id))
    schedule = result.scalar_one_or_none()
    if not schedule:
        raise HTTPException(status_code=404, detail="Çekiliş bulunamadı")

    try:
        schedule._executed_by = admin   # draw_engine'e geçir
        draw_result = await execute_draw(schedule, db)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # WebSocket push
    await manager.broadcast({
        "event": "draw_completed",
        "draw_id": str(draw_result.id),
        "tier": schedule.draw_tier.value,
        "winner_card_id": draw_result.winner_card_id,
        "winning_ticket": draw_result.winning_ticket_number,
        "prize": schedule.prize_description,
        "prize_amount": str(schedule.prize_amount),
        "prize_currency": schedule.prize_currency,
        "executed_at": draw_result.executed_at.isoformat(),
        "executed_by": admin,
    })

    return draw_result


# ── Ödül Teslim Takibi ────────────────────────────────────────────────────────
@router.patch("/{schedule_id}/prize-distributed")
async def mark_prize_distributed(
    schedule_id: UUID,
    notes: str = "",
    db: AsyncSession = Depends(get_db),
    admin: str = Depends(require_admin),
):
    """
    Ödülün fiziksel olarak kazanana teslim edildiğini işaretler.
    Casino operatörü parayı / ödülü verdikten sonra bu endpoint'i çağırır.
    Audit trail için zorunlu — sertifikaya da yansır.
    """
    result = await db.execute(select(DrawResult).where(DrawResult.schedule_id == schedule_id))
    draw_result = result.scalar_one_or_none()
    if not draw_result:
        raise HTTPException(status_code=404, detail="Çekiliş sonucu bulunamadı")
    if draw_result.prize_distributed:
        return {"already_distributed": True, "distributed_at": draw_result.prize_distributed_at.isoformat()}

    draw_result.prize_distributed    = True
    draw_result.prize_distributed_at = datetime.now(timezone.utc)
    draw_result.prize_distributed_by = admin
    draw_result.prize_notes          = notes or None
    await db.commit()

    return {
        "distributed": True,
        "winner_card_id": draw_result.winner_card_id,
        "distributed_at": draw_result.prize_distributed_at.isoformat(),
        "distributed_by": admin,
    }
    # WebSocket push — tüm display ekranlarına anlık bildir
    await manager.broadcast({
        "event": "draw_completed",
        "draw_id": str(draw_result.id),
        "tier": schedule.draw_tier.value,
        "winner_card_id": draw_result.winner_card_id,
        "winning_ticket": draw_result.winning_ticket_number,
        "prize": schedule.prize_description,
        "prize_amount": str(schedule.prize_amount),
        "prize_currency": schedule.prize_currency,
        "executed_at": draw_result.executed_at.isoformat(),
        "executed_by": admin,
    })

    return draw_result


# ── Sonuç geçmişi ─────────────────────────────────────────────────────────────
@router.get("/results/history", response_model=list[DrawResultOut])
async def draw_history(
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_admin),
):
    return await get_draw_history(db, limit)


@router.get("/{schedule_id}/result", response_model=DrawResultOut)
async def get_draw_result(
    schedule_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_admin),
):
    result = await db.execute(select(DrawResult).where(DrawResult.schedule_id == schedule_id))
    draw_result = result.scalar_one_or_none()
    if not draw_result:
        raise HTTPException(status_code=404, detail="Sonuç bulunamadı")
    return draw_result


# ── Dışa aktarım — audit log ──────────────────────────────────────────────────
@router.get("/{schedule_id}/export")
async def export_draw_audit(
    schedule_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_admin),
):
    """
    Çekiliş audit logu — havuz, kazanan, bilet detayları.
    Yasal uyumluluk / denetim için.
    """
    result = await db.execute(select(DrawSchedule).where(DrawSchedule.id == schedule_id))
    schedule = result.scalar_one_or_none()
    if not schedule:
        raise HTTPException(status_code=404, detail="Çekiliş bulunamadı")

    draw_result_q = await db.execute(select(DrawResult).where(DrawResult.schedule_id == schedule_id))
    draw_result = draw_result_q.scalar_one_or_none()

    return {
        "audit": {
            "schedule_id": str(schedule_id),
            "draw_name": schedule.name,
            "draw_tier": schedule.draw_tier.value,
            "scheduled_at": schedule.scheduled_at.isoformat(),
            "prize_amount": str(schedule.prize_amount),
            "prize_currency": schedule.prize_currency,
            "prize_description": schedule.prize_description,
            "campaign_year": schedule.campaign_year,
            "created_by": schedule.created_by,
        },
        "result": {
            "winner_card_id": draw_result.winner_card_id if draw_result else None,
            "winning_ticket": draw_result.winning_ticket_number if draw_result else None,
            "total_tickets_in_pool": draw_result.total_tickets_in_pool if draw_result else None,
            "total_players_in_pool": draw_result.total_players_in_pool if draw_result else None,
            "executed_at": draw_result.executed_at.isoformat() if draw_result else None,
            "rng_method": draw_result.draw_metadata.get("rng") if draw_result else None,
        } if draw_result else None,
    }


# ── Kampanya yılı sıfırlama ───────────────────────────────────────────────────
@router.post("/campaign/reset")
async def reset_campaign(
    new_year: int,
    confirm: str,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_admin),
):
    """
    Yeni kampanya yılı başlatır.
    Tüm biletler ve kazanımlar arşivlenir (silinmez).
    confirm parametresi "RESET-{new_year}" olmalı.
    """
    if confirm != f"RESET-{new_year}":
        raise HTTPException(status_code=400, detail=f"confirm parametresi 'RESET-{new_year}' olmalı")

    # Eski yılın biletlerini pasifleştir
    await db.execute(
        Ticket.__table__.update()
        .where(Ticket.campaign_year == settings.CAMPAIGN_YEAR)
        .values(is_active=False)
    )
    await db.commit()

    return {
        "message": f"Kampanya {new_year} için sıfırlandı",
        "old_year": settings.CAMPAIGN_YEAR,
        "note": "CAMPAIGN_YEAR değerini .env dosyasında güncelleyin",
    }


# ── ÇEKİLİŞ SERTİFİKASI (PDF) ─────────────────────────────────────────────────
from fastapi.responses import Response
from pydantic import BaseModel as _BaseModel
from starlette.concurrency import run_in_threadpool
from ..services.certificate import generate_draw_certificate
from ..services.mailer import send_certificate_email, MailerNotConfigured
from ..models import Player as _Player


async def _load_certificate_context(schedule_id: UUID, db: AsyncSession):
    """GET (indirme) ve POST (e-posta) sertifika endpointlerinin ortak veri yükleme adımı."""
    sched_res = await db.execute(select(DrawSchedule).where(DrawSchedule.id == schedule_id))
    schedule = sched_res.scalar_one_or_none()
    if not schedule:
        raise HTTPException(status_code=404, detail="Çekiliş bulunamadı")

    result_res = await db.execute(select(DrawResult).where(DrawResult.schedule_id == schedule_id))
    draw_result = result_res.scalar_one_or_none()
    if not draw_result:
        raise HTTPException(status_code=400, detail="Bu çekiliş henüz yürütülmedi")

    winner_res = await db.execute(select(_Player).where(_Player.card_id == draw_result.winner_card_id))
    winner = winner_res.scalar_one_or_none()
    winner_name = winner.name if winner else draw_result.winner_card_id

    return schedule, draw_result, winner, winner_name


def _build_certificate_pdf(schedule, draw_result, winner_name) -> bytes:
    return generate_draw_certificate(
        draw_id=str(schedule.id),
        draw_name=schedule.name,
        draw_tier=schedule.draw_tier.value,
        prize_description=schedule.prize_description,
        prize_amount=schedule.prize_amount,
        prize_currency=schedule.prize_currency,
        winner_name=winner_name,
        winner_card_id=draw_result.winner_card_id,
        winning_ticket=draw_result.winning_ticket_number,
        total_tickets_in_pool=draw_result.total_tickets_in_pool,
        total_players_in_pool=draw_result.total_players_in_pool,
        executed_at=draw_result.executed_at,
        rng_method=draw_result.draw_metadata.get("rng", "secrets.SystemRandom") if draw_result.draw_metadata else "secrets.SystemRandom",
        tax_declaration_ref=schedule.tax_declaration_ref,
        tax_amount_paid=schedule.tax_amount_paid,
        tax_paid_at=schedule.tax_paid_at,
    )


@router.get("/{schedule_id}/certificate")
async def get_draw_certificate(
    schedule_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_admin),
):
    """
    Çekiliş sertifikasını PDF olarak üretir (Türkçe / İngilizce / Gürcüce).
    "Bu çekiliş hileli mi?" sorusuna kanıtla cevap — büyük ödüllerde aynı
    zamanda kazanılan paranın deklarasyonu niteliğindedir. Duvara asılabilir,
    oyuncuya gönderilebilir, denetimde ibraz edilebilir.
    """
    schedule, draw_result, _winner, winner_name = await _load_certificate_context(schedule_id, db)
    pdf_bytes = _build_certificate_pdf(schedule, draw_result, winner_name)

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="cekilis-sertifikasi-{schedule.id}.pdf"'
        },
    )


class CertificateEmailInput(_BaseModel):
    """Boş bırakılırsa oyuncunun kayıtlı e-postası (Player.email) kullanılır."""
    to_email: str | None = None


@router.post("/{schedule_id}/certificate/email")
async def email_draw_certificate(
    schedule_id: UUID,
    data: CertificateEmailInput = CertificateEmailInput(),
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_admin),
):
    """Sertifikayı PDF olarak üretip misafirin (veya belirtilen adresin) e-postasına gönderir."""
    schedule, draw_result, winner, winner_name = await _load_certificate_context(schedule_id, db)

    recipient = data.to_email or (winner.email if winner else None)
    if not recipient:
        raise HTTPException(
            status_code=400,
            detail="Oyuncunun kayıtlı e-postası yok — bir e-posta adresi belirtin (to_email)",
        )

    pdf_bytes = _build_certificate_pdf(schedule, draw_result, winner_name)
    filename = f"cekilis-sertifikasi-{schedule.id}.pdf"
    subject = f"NovaGuard — {schedule.name} / Draw Certificate / გათამაშების სერტიფიკატი"
    body = (
        f"{winner_name},\n\n"
        f"\"{schedule.name}\" çekilişini kazandınız — sertifikanız ektedir.\n"
        f"Congratulations — you won \"{schedule.name}\". Your certificate is attached.\n"
        f"თქვენ მოიგეთ \"{schedule.name}\" — სერტიფიკატი თანდართულია.\n\n"
        f"— {schedule.name} · NovaGuard"
    )

    try:
        await run_in_threadpool(
            send_certificate_email,
            to_email=recipient,
            subject=subject,
            body_text=body,
            pdf_bytes=pdf_bytes,
            attachment_filename=filename,
        )
    except MailerNotConfigured as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"E-posta gönderilemedi: {e}")

    return {"sent": True, "to": recipient}


# ── Çekiliş İptal ─────────────────────────────────────────────────────────────
@router.patch("/{schedule_id}/cancel")
async def cancel_draw(
    schedule_id: UUID,
    reason: str = "Manuel iptal",
    db: AsyncSession = Depends(get_db),
    admin: str = Depends(require_admin),
):
    """Planlanmış bir çekiliş iptal edilir. Tamamlanmış çekilişler iptal edilemez."""
    result = await db.execute(select(DrawSchedule).where(DrawSchedule.id == schedule_id))
    schedule = result.scalar_one_or_none()
    if not schedule:
        raise HTTPException(status_code=404, detail="Çekiliş bulunamadı")
    if schedule.status == DrawStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="Tamamlanmış çekiliş iptal edilemez")
    if schedule.status == DrawStatus.CANCELLED:
        raise HTTPException(status_code=400, detail="Zaten iptal edilmiş")

    schedule.status = DrawStatus.CANCELLED
    await db.commit()
    return {"cancelled": True, "schedule_id": str(schedule_id), "reason": reason}


# ── Ödül Teslim (result ID ile) ───────────────────────────────────────────────
@router.patch("/result/{result_id}/prize-distributed")
async def mark_prize_distributed_by_result(
    result_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin: str = Depends(require_admin),
):
    """Admin panelinin 'Teslim Et' butonu bu endpoint'i kullanır."""
    result = await db.execute(select(DrawResult).where(DrawResult.id == result_id))
    draw_result = result.scalar_one_or_none()
    if not draw_result:
        raise HTTPException(status_code=404, detail="Çekiliş sonucu bulunamadı")

    draw_result.prize_distributed    = True
    draw_result.prize_distributed_at = datetime.now(timezone.utc)
    draw_result.prize_distributed_by = admin
    await db.commit()
    return {"distributed": True, "winner_card_id": draw_result.winner_card_id}
