"""
NovaGuard Promo Engine — API Şemaları
"""
from datetime import datetime, date
from decimal import Decimal
from typing import Optional, Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


# ── PLAYER ────────────────────────────────────────────────────────────────────

class PlayerCreate(BaseModel):
    card_id: str = Field(..., description="CRM'den gelen kart numarası")
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    crm_data: Optional[dict] = None


class PlayerUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    crm_data: Optional[dict] = None
    is_active: Optional[bool] = None


class PlayerOut(BaseModel):
    id: UUID
    card_id: str
    name: str
    email: Optional[str]
    is_active: bool
    registered_at: datetime

    class Config:
        from_attributes = True


# ── SESSION ───────────────────────────────────────────────────────────────────

class SessionPush(BaseModel):
    """
    Casino sisteminin NovaGuard'a push ettiği oturum verisi.

    Biz casino sisteminden VERİ ÇEKMIYORUZ.
    Casino IT'si, oyuncu masaya/makineye oturduğunda bu endpoint'i çağırır.
    API key'i biz veriyoruz, onlar bağlanıyor.

    Zorunlu:
      card_id    — oyuncu kart numarası (casino'nun kendi formatı, değiştirmiyoruz)
      game_type  — "live" veya "slot"
      started_at — oturum başlangıç zamanı

    Bilet hesabı için (ikisinden biri yeterli):
      average_bet     — oyuncunun o oturumdaki ortalama bahis miktarı  ← TERCİH EDİLEN
      turnover_amount — toplam döngü (casino sistemi bunu veriyorsa kullanılır)

    Opsiyonel:
      external_session_id — casino'nun kendi ID'si (idempotency için önerilir)
      game_name           — masa/makine adı (display ekranı için)
      currency            — TRY, GEL, EUR, USD (varsayılan: GEL)
    """
    external_session_id: Optional[str] = Field(None, description="Casino sisteminin oturum ID'si")
    card_id:    str      = Field(..., description="Oyuncu kart numarası")
    game_type:  str      = Field(..., description="live veya slot")
    game_name:  Optional[str] = None
    table_id:   Optional[str] = None
    started_at: datetime

    # Bilet hesabı için — ikisinden biri gönderilir
    average_bet:     Optional[Decimal] = Field(None, ge=0, description="Ortalama bahis miktarı (tercih edilen)")
    turnover_amount: Decimal           = Field(default=Decimal("0"), ge=0, description="Toplam döngü (alternatif)")

    currency: str = Field(default="GEL", max_length=8)

    @field_validator("game_type")
    @classmethod
    def validate_game_type(cls, v):
        if v not in ("live", "slot"):
            raise ValueError("game_type 'live' veya 'slot' olmalıdır")
        return v


class SessionEnd(BaseModel):
    """
    Oturum kapanış verisi — biletler burada hesaplanır.
    Casino IT'si, oyuncu kalktığında bu endpoint'i çağırır.
    """
    ended_at: datetime
    final_average_bet:     Optional[Decimal] = Field(None, ge=0, description="Final ortalama bahis")
    final_turnover_amount: Optional[Decimal] = Field(None, ge=0, description="Final toplam döngü (alternatif)")


class SessionOut(BaseModel):
    id: UUID
    card_id: str
    game_type: str
    duration_minutes: Optional[int]
    turnover_amount: Decimal
    currency: str
    tickets_earned: int
    status: str
    started_at: datetime
    ended_at: Optional[datetime]

    class Config:
        from_attributes = True


# ── TICKET ────────────────────────────────────────────────────────────────────

class TicketOut(BaseModel):
    id: UUID
    ticket_number: str
    card_id: str
    earned_date: date
    valid_for_tiers: list[str]
    is_active: bool
    campaign_year: int
    created_at: datetime

    class Config:
        from_attributes = True


class PlayerTicketSummary(BaseModel):
    card_id: str
    name: str
    total_active_tickets: int
    tickets_earned_today: int
    consecutive_days: int
    campaign_year: int
    sample_tickets: list[TicketOut] = []


# ── TICKET FORMULA ────────────────────────────────────────────────────────────

class FormulaUpdate(BaseModel):
    """Admin tarafından güncellenebilen bilet formülü."""
    name: Optional[str] = None

    live_tickets_per_hour: Optional[Decimal]    = Field(None, gt=0)
    live_turnover_per_ticket: Optional[Decimal] = Field(None, gt=0)
    live_min_session_minutes: Optional[int]     = Field(None, ge=1)
    live_rounds_per_hour: Optional[int]         = Field(None, ge=1, description="Saatte kaç el/tur (average_bet hesabı için)")

    slot_tickets_per_hour: Optional[Decimal]    = Field(None, gt=0)
    slot_turnover_per_ticket: Optional[Decimal] = Field(None, gt=0)
    slot_min_session_minutes: Optional[int]     = Field(None, ge=1)
    slot_rounds_per_hour: Optional[int]         = Field(None, ge=1, description="Saatte kaç spin (average_bet hesabı için)")

    max_tickets_per_day: Optional[int]          = Field(None, ge=1)
    max_tickets_per_session: Optional[int]      = Field(None, ge=1)
    max_pool_tickets: Optional[int]             = Field(None, ge=0, description="Havuzda oyuncu başına max bilet. 0=sınırsız. Küçük oyuncu koruması.")

    consecutive_day_bonus_days: Optional[int]    = Field(None, ge=1)
    consecutive_day_bonus_tickets: Optional[int] = Field(None, ge=0)


class FormulaOut(BaseModel):
    id: int
    name: str
    is_active: bool
    live_tickets_per_hour: Decimal
    live_turnover_per_ticket: Decimal
    live_min_session_minutes: int
    live_rounds_per_hour: int
    slot_tickets_per_hour: Decimal
    slot_turnover_per_ticket: Decimal
    slot_min_session_minutes: int
    slot_rounds_per_hour: int
    max_tickets_per_day: int
    max_tickets_per_session: int
    max_pool_tickets: int
    consecutive_day_bonus_days: int
    consecutive_day_bonus_tickets: int
    updated_by: Optional[str]

    class Config:
        from_attributes = True


# ── BULK IMPORT ───────────────────────────────────────────────────────────────

class BulkPlayerEntry(BaseModel):
    card_id: str
    name: Optional[str] = None


class BulkPlayerImport(BaseModel):
    """Toplu oyuncu import — casino'nun oyuncu listesini tek seferde yüklemek için."""
    players: list[BulkPlayerEntry] = Field(..., min_length=1, max_length=2000)


# ── DRAW SCHEDULE ─────────────────────────────────────────────────────────────

class DrawScheduleCreate(BaseModel):
    draw_tier: str = Field(..., description="daily | weekly | monthly | quarterly | annual")
    name: str
    description: Optional[str] = None
    scheduled_at: datetime
    prize_amount: Decimal = Field(..., gt=0)
    prize_currency: str = Field(default="TRY", max_length=8)
    prize_description: str
    annual_prize_options: Optional[list[str]] = None  # Yıllık için seçenekler
    tax_declaration_required: bool = Field(default=True, description="RS.GE beyanı zorunlu mu")

    @field_validator("draw_tier")
    @classmethod
    def validate_tier(cls, v):
        valid = {"daily", "weekly", "monthly", "quarterly", "annual"}
        if v not in valid:
            raise ValueError(f"draw_tier şunlardan biri olmalıdır: {valid}")
        return v


class TaxDeclarationInput(BaseModel):
    """RS.GE vergi beyanı kaydı — çekiliş yürütülmeden önce girilmeli."""
    tax_declaration_ref: str = Field(..., description="RS.GE beyan referans numarası")
    tax_amount_paid: Decimal = Field(..., ge=0, description="Yatırılan vergi tutarı")
    declared_by: str = Field(..., description="Beyanı yapan muhasebe yetkilisi")


class DrawScheduleOut(BaseModel):
    id: UUID
    draw_tier: str
    name: str
    description: Optional[str]
    scheduled_at: datetime
    prize_amount: Decimal
    prize_currency: str
    prize_description: str
    status: str
    created_at: datetime

    # Vergi beyanı durumu
    tax_declaration_required: bool
    tax_declaration_ref: Optional[str] = None
    tax_amount_paid: Optional[Decimal] = None
    tax_paid_at: Optional[datetime] = None
    tax_declared_by: Optional[str] = None
    tax_cleared: bool = False

    class Config:
        from_attributes = True


# ── DRAW RESULT ───────────────────────────────────────────────────────────────

class DrawResultOut(BaseModel):
    id: UUID
    winner_card_id: str
    winning_ticket_number: str
    total_tickets_in_pool: int
    total_players_in_pool: int
    executed_at: datetime
    executed_by: Optional[str] = None
    draw_metadata: Optional[dict] = None

    # Ödül teslim durumu
    prize_distributed:    bool = False
    prize_distributed_at: Optional[datetime] = None
    prize_distributed_by: Optional[str] = None
    prize_notes:          Optional[str] = None

    class Config:
        from_attributes = True


# ── ELIGIBILITY ───────────────────────────────────────────────────────────────

class PlayerEligibility(BaseModel):
    card_id: str
    eligible_for_exclusive_draws: bool
    eligible_for_annual_final: bool
    won_this_year: Optional[dict]
    ticket_summary: dict
    eligible_tiers: list[str]


# ── POOL STATS ────────────────────────────────────────────────────────────────

class PoolStats(BaseModel):
    draw_tier: str
    eligible_players: int
    total_tickets: int
    players: list[dict]


# ── DISPLAY ───────────────────────────────────────────────────────────────────

class DisplayDraw(BaseModel):
    """Display ekranı için aktif çekiliş bilgisi."""
    schedule: Optional[DrawScheduleOut]
    pool_stats: Optional[PoolStats]
    last_result: Optional[DrawResultOut]
    campaign_year: int


class LeaderboardEntry(BaseModel):
    rank: int
    card_id: str
    name: str
    total_tickets: int
    tickets_today: int
    has_won: bool
    won_tier: Optional[str]
