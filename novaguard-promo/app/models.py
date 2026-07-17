"""
NovaGuard Promo Engine — Database Models
=========================================
Tüm tablolar burada tanımlanmıştır.
"""
import uuid
from datetime import datetime, date
from decimal import Decimal
from enum import Enum as PyEnum
from typing import Optional

from sqlalchemy import (
    String, Integer, Numeric, Boolean, DateTime, Date, Text,
    ForeignKey, Enum, JSON, UniqueConstraint, Index, func
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


# ── ENUMS ─────────────────────────────────────────────────────────────────────

class GameType(str, PyEnum):
    LIVE   = "live"
    SLOT   = "slot"

class DrawTier(str, PyEnum):
    DAILY     = "daily"
    WEEKLY    = "weekly"
    MONTHLY   = "monthly"
    QUARTERLY = "quarterly"
    ANNUAL    = "annual"       # Grand Final — herkes her zaman dahil
    MINI      = "mini"         # Aktif Oyuncu Mini Bonusu — her 30 dk'da bir küçük ödül

class DrawStatus(str, PyEnum):
    SCHEDULED  = "scheduled"
    IN_PROGRESS = "in_progress"
    COMPLETED  = "completed"
    CANCELLED  = "cancelled"

class SessionStatus(str, PyEnum):
    ACTIVE   = "active"
    ENDED    = "ended"


# ── PLAYER ────────────────────────────────────────────────────────────────────

class Player(Base):
    """
    Casino CRM'den gelen oyuncu kaydı.
    card_id: CRM'den alınan benzersiz kart numarası.
    """
    __tablename__ = "players"

    id:          Mapped[uuid.UUID]        = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    card_id:     Mapped[str]              = mapped_column(String(64), unique=True, nullable=False, index=True)
    name:        Mapped[str]              = mapped_column(String(256), nullable=False)
    email:       Mapped[Optional[str]]    = mapped_column(String(256), nullable=True)
    phone:       Mapped[Optional[str]]    = mapped_column(String(32), nullable=True)
    crm_data:    Mapped[Optional[dict]]   = mapped_column(JSON, nullable=True)   # CRM'den gelen ek veriler
    is_active:   Mapped[bool]             = mapped_column(Boolean, default=True)
    registered_at: Mapped[datetime]       = mapped_column(DateTime(timezone=True), default=func.now())
    updated_at:  Mapped[datetime]         = mapped_column(DateTime(timezone=True), default=func.now(), onupdate=func.now())

    # İlişkiler
    sessions:    Mapped[list["GameSession"]] = relationship(back_populates="player", lazy="dynamic")
    tickets:     Mapped[list["Ticket"]]      = relationship(back_populates="player", lazy="dynamic")
    prize_wins:  Mapped[list["PrizeWin"]]    = relationship(back_populates="player", lazy="dynamic")


# ── TICKET FORMULA ────────────────────────────────────────────────────────────

class TicketFormula(Base):
    """
    Admin tarafından yapılandırılabilen bilet kazanım formülü.
    Live game ve slot için ayrı katsayılar.
    """
    __tablename__ = "ticket_formulas"

    id:                        Mapped[int]     = mapped_column(Integer, primary_key=True, autoincrement=True)
    name:                      Mapped[str]     = mapped_column(String(128), default="Varsayılan Formül")
    is_active:                 Mapped[bool]    = mapped_column(Boolean, default=True)

    # Live game
    live_tickets_per_hour:     Mapped[Decimal] = mapped_column(Numeric(8, 2), default=Decimal("1.0"))
    live_turnover_per_ticket:  Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("500.0"))
    live_min_session_minutes:  Mapped[int]     = mapped_column(Integer, default=15)
    live_rounds_per_hour:      Mapped[int]     = mapped_column(Integer, default=30)   # FIX 11

    # Slot
    slot_tickets_per_hour:     Mapped[Decimal] = mapped_column(Numeric(8, 2), default=Decimal("0.5"))
    slot_turnover_per_ticket:  Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("1000.0"))
    slot_min_session_minutes:  Mapped[int]     = mapped_column(Integer, default=15)
    slot_rounds_per_hour:      Mapped[int]     = mapped_column(Integer, default=300)  # FIX 11

    # Günlük limitler
    max_tickets_per_day:       Mapped[int]     = mapped_column(Integer, default=10)
    max_tickets_per_session:   Mapped[int]     = mapped_column(Integer, default=5)

    # Küçük oyuncu koruması — havuzda maksimum bilet (fairness cap)
    # Büyük oyuncu max bu kadar biletini havuza sokabilir. 0 = sınırsız.
    max_pool_tickets:          Mapped[int]     = mapped_column(Integer, default=20)

    # Ardışık gün bonusu (ör: 3 gün üst üste gelen +1 bonus bilet)
    consecutive_day_bonus_days:    Mapped[int] = mapped_column(Integer, default=3)
    consecutive_day_bonus_tickets: Mapped[int] = mapped_column(Integer, default=1)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now())
    updated_by: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)


# ── GAME SESSION ──────────────────────────────────────────────────────────────

class GameSession(Base):
    """
    Casino sisteminin gerçek zamanlı push ettiği oyun oturumu.
    Her oturum kapandığında bilet hesabı yapılır.
    """
    __tablename__ = "game_sessions"

    id:               Mapped[uuid.UUID]        = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    external_session_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, unique=True, index=True)
    card_id:          Mapped[str]              = mapped_column(String(64), ForeignKey("players.card_id"), nullable=False, index=True)
    game_type:        Mapped[GameType]         = mapped_column(Enum(GameType), nullable=False)
    game_name:        Mapped[Optional[str]]    = mapped_column(String(128), nullable=True)
    table_id:         Mapped[Optional[str]]    = mapped_column(String(64), nullable=True)

    started_at:       Mapped[datetime]         = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at:         Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_minutes: Mapped[Optional[int]]    = mapped_column(Integer, nullable=True)

    turnover_amount:  Mapped[Decimal]          = mapped_column(Numeric(14, 2), default=Decimal("0.0"))
    average_bet:      Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    currency:         Mapped[str]              = mapped_column(String(8), default="GEL")

    tickets_earned:   Mapped[int]              = mapped_column(Integer, default=0)
    status:           Mapped[SessionStatus]    = mapped_column(Enum(SessionStatus), default=SessionStatus.ACTIVE)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now())

    player: Mapped["Player"] = relationship(back_populates="sessions", foreign_keys=[card_id])
    tickets: Mapped[list["Ticket"]] = relationship(back_populates="session", lazy="dynamic")

    __table_args__ = (
        Index("ix_sessions_card_started", "card_id", "started_at"),
    )


# ── TICKET ────────────────────────────────────────────────────────────────────

class Ticket(Base):
    """
    Her bir dijital bilet. Benzersiz numaralı, karta yüklü.
    Bir bilet birden fazla çekilişte geçerli olabilir (tier bazlı).
    """
    __tablename__ = "tickets"

    id:             Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Benzersiz bilet numarası — örn: NVG-2025-A3F7B2C1
    ticket_number:  Mapped[str]       = mapped_column(String(32), unique=True, nullable=False, index=True)

    card_id:        Mapped[str]       = mapped_column(String(64), ForeignKey("players.card_id"), nullable=False, index=True)
    session_id:     Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("game_sessions.id"), nullable=True)

    # Hangi çekiliş döneminde kazanıldı
    campaign_year:  Mapped[int]       = mapped_column(Integer, nullable=False)
    earned_date:    Mapped[date]      = mapped_column(Date, nullable=False, default=date.today)

    # Bu bilet hangi çekilişler için geçerli (JSON list: ["daily","weekly","monthly","quarterly","annual"])
    valid_for_tiers: Mapped[list]     = mapped_column(JSON, default=list)

    is_active:      Mapped[bool]      = mapped_column(Boolean, default=True)
    used_in_draw_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("draw_results.id"), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now())

    player:  Mapped["Player"]           = relationship(back_populates="tickets", foreign_keys=[card_id])
    session: Mapped[Optional["GameSession"]] = relationship(back_populates="tickets")

    __table_args__ = (
        Index("ix_tickets_card_campaign", "card_id", "campaign_year"),
        Index("ix_tickets_active_tier", "is_active", "campaign_year"),
    )


# ── DRAW SCHEDULE ─────────────────────────────────────────────────────────────

class DrawSchedule(Base):
    """
    Casino tarafından yapılandırılan çekiliş programı.
    Günlük çekilişler saati, miktarı ve para birimi ile ayarlanabilir.

    VERGİ BEYANI KAYDI (Gürcistan — RS.GE):
      Gürcistan'da çekiliş ödülü dağıtılmadan önce Revenue Service'e (RS.GE)
      beyan yapılıp vergisi yatırılması Casino'nun kendi iç muhasebe/hukuki
      sorumluluğudur. Bu alanlar sadece o sürecin kaydını tutmak içindir —
      NovaGuard bu beyanı zorunlu kılmaz veya çekilişin yürütülmesini buna
      bağlamaz (bkz. draw_engine.execute_draw).
    """
    __tablename__ = "draw_schedules"

    id:               Mapped[uuid.UUID]  = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    draw_tier:        Mapped[DrawTier]   = mapped_column(Enum(DrawTier), nullable=False, index=True)
    name:             Mapped[str]        = mapped_column(String(256), nullable=False)
    description:      Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    scheduled_at:     Mapped[datetime]   = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    campaign_year:    Mapped[int]        = mapped_column(Integer, nullable=False)

    # Ödül
    prize_amount:     Mapped[Decimal]    = mapped_column(Numeric(14, 2), nullable=False)
    prize_currency:   Mapped[str]        = mapped_column(String(8), default="TRY")
    prize_description: Mapped[str]       = mapped_column(String(512), nullable=False)

    # Özel: yıllık final için ödül türü çekilişi
    annual_prize_options: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)

    status:           Mapped[DrawStatus] = mapped_column(Enum(DrawStatus), default=DrawStatus.SCHEDULED)
    created_by:       Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    created_at:       Mapped[datetime]   = mapped_column(DateTime(timezone=True), default=func.now())

    # ── Vergi Beyanı (RS.GE) ────────────────────────────────────────────────
    # Casino politikasına göre: çok küçük günlük ödüllerde muhasebe toplu
    # beyan tercih edebilir — bu yüzden zorunluluk per-draw ayarlanabilir.
    tax_declaration_required: Mapped[bool] = mapped_column(Boolean, default=True)
    tax_declaration_ref:  Mapped[Optional[str]]   = mapped_column(String(128), nullable=True)   # RS.GE beyan no
    tax_amount_paid:      Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2), nullable=True)
    tax_paid_at:           Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    tax_declared_by:       Mapped[Optional[str]]   = mapped_column(String(128), nullable=True)   # muhasebe yetkilisi

    result: Mapped[Optional["DrawResult"]] = relationship(back_populates="schedule", uselist=False)

    @property
    def tax_cleared(self) -> bool:
        """Bilgi amaçlı: vergi beyanı kaydı tamamlanmış mı? (çekilişi engellemez)"""
        if not self.tax_declaration_required:
            return True
        return self.tax_paid_at is not None and bool(self.tax_declaration_ref)


# ── DRAW RESULT ───────────────────────────────────────────────────────────────

class DrawResult(Base):
    """
    Tamamlanmış çekilişin sonucu.
    executed_by: Çekilişi yürüten yetkili (admin key sahibi).
    prize_distributed: Ödül fiziksel olarak teslim edildi mi?
    """
    __tablename__ = "draw_results"

    id:               Mapped[uuid.UUID]  = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # nullable=True: Mini bonus çekilişlerinin ayrı bir DrawSchedule kaydı yoktur,
    # doğrudan yürütülür. Normal çekilişlerde (haftalık/aylık/vs) bu alan dolu olur.
    schedule_id:      Mapped[Optional[uuid.UUID]]  = mapped_column(UUID(as_uuid=True), ForeignKey("draw_schedules.id"), nullable=True, unique=True)
    winner_card_id:   Mapped[str]        = mapped_column(String(64), ForeignKey("players.card_id"), nullable=False)
    winning_ticket_number: Mapped[str]   = mapped_column(String(32), nullable=False)

    total_tickets_in_pool: Mapped[int]   = mapped_column(Integer, nullable=False)
    total_players_in_pool: Mapped[int]   = mapped_column(Integer, nullable=False)

    executed_at:      Mapped[datetime]   = mapped_column(DateTime(timezone=True), default=func.now())
    executed_by:      Mapped[Optional[str]] = mapped_column(String(128), nullable=True)   # Kim yaptı
    draw_metadata:    Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Ödül teslim takibi
    prize_distributed:    Mapped[bool]           = mapped_column(Boolean, default=False)
    prize_distributed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    prize_distributed_by: Mapped[Optional[str]]  = mapped_column(String(128), nullable=True)
    prize_notes:          Mapped[Optional[str]]  = mapped_column(Text, nullable=True)

    schedule: Mapped["DrawSchedule"]     = relationship(back_populates="result")
    winner:   Mapped["Player"]           = relationship(foreign_keys=[winner_card_id])


# ── PRIZE WIN ─────────────────────────────────────────────────────────────────

class PrizeWin(Base):
    """
    Oyuncunun kazandığı ödül kaydı.
    Bu tablo dışlama (exclusion) mantığı için kritiktir.
    Bir oyuncu yıllık finale kadar sadece 1 adet
    {daily|weekly|monthly|quarterly} ödülü kazanabilir.
    """
    __tablename__ = "prize_wins"

    id:           Mapped[uuid.UUID]  = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    card_id:      Mapped[str]        = mapped_column(String(64), ForeignKey("players.card_id"), nullable=False, index=True)
    draw_tier:    Mapped[DrawTier]   = mapped_column(Enum(DrawTier), nullable=False)
    draw_result_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("draw_results.id"), nullable=False)

    prize_amount:   Mapped[Decimal]  = mapped_column(Numeric(14, 2), nullable=False)
    prize_currency: Mapped[str]      = mapped_column(String(8), default="TRY")
    prize_description: Mapped[str]   = mapped_column(String(512), nullable=False)
    campaign_year:  Mapped[int]      = mapped_column(Integer, nullable=False)

    won_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now())

    player: Mapped["Player"] = relationship(back_populates="prize_wins", foreign_keys=[card_id])

    __table_args__ = (
        Index("ix_prize_wins_card_year", "card_id", "campaign_year"),
    )


# ── MİNİ BONUS AYARLARI ─────────────────────────────────────────────────────
# "Aktif Oyuncu Mini Bonusu": belirli bir saat aralığında, düzenli aralıklarla
# o an oynayan bir oyuncuya küçük bir ödül verir. Casino bu ayarları
# admin panelinden değiştirebilir — kod değişmez.

class MiniBonusConfig(Base):
    """
    Mini bonus özelliğinin ayarları. Tek satır olarak tutulur (id=1 gibi).
    """
    __tablename__ = "mini_bonus_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=False)

    prize_amount:   Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("100.00"))
    prize_currency: Mapped[str]     = mapped_column(String(8), default="GEL")

    # Kaç dakikada bir çekiliş yapılacak
    interval_minutes: Mapped[int] = mapped_column(Integer, default=30)

    # Başlangıç ve bitiş saati (0-23 arası, casino saatine göre)
    # Örnek: start=14, end=6 demek "14:00'ten ertesi gün 06:00'ya kadar" demektir.
    window_start_hour: Mapped[int] = mapped_column(Integer, default=14)
    window_end_hour:   Mapped[int] = mapped_column(Integer, default=6)

    updated_by: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now(), onupdate=func.now())
