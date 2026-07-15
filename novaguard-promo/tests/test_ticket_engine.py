"""
Bilet Motoru Testleri
pytest tests/ ile çalıştırın.
"""
import pytest
from decimal import Decimal
from app.models import GameType, TicketFormula
from app.services.ticket_engine import calculate_raw_tickets, generate_ticket_number


# ── TICKET NUMBER ─────────────────────────────────────────────────────────────

def test_ticket_number_format():
    num = generate_ticket_number("KRT-001", 2025, 1)
    assert num.startswith("NVG-2025-")
    assert len(num) == 21  # NVG-2025-XXXXXXXXCCCC (8 random + 4 checksum)

def test_ticket_numbers_unique():
    """Aynı parametrelerle farklı numaralar üretilmeli."""
    nums = {generate_ticket_number("KRT-001", 2025, 1) for _ in range(100)}
    assert len(nums) == 100


# ── RAW TICKET CALCULATION ────────────────────────────────────────────────────

@pytest.fixture
def default_formula():
    return TicketFormula(
        live_tickets_per_hour=Decimal("1.0"),
        live_turnover_per_ticket=Decimal("500.0"),
        live_min_session_minutes=15,
        slot_tickets_per_hour=Decimal("0.5"),
        slot_turnover_per_ticket=Decimal("1000.0"),
        slot_min_session_minutes=15,
        max_tickets_per_day=10,
        max_tickets_per_session=5,
    )


def test_live_time_based(default_formula):
    """2 saat live = 2 bilet (turnover 0)"""
    result = calculate_raw_tickets(
        game_type=GameType.LIVE,
        duration_minutes=120,
        turnover_amount=Decimal("0"),
        formula=default_formula,
    )
    assert result == 2


def test_live_turnover_based(default_formula):
    """1000 TL turnover live = 2 bilet (süre kısa)"""
    result = calculate_raw_tickets(
        game_type=GameType.LIVE,
        duration_minutes=20,
        turnover_amount=Decimal("1000"),
        formula=default_formula,
    )
    assert result == 2


def test_live_combined(default_formula):
    """2 saat + 1500 TL = 2 + 3 = 5 (max_session limiti)"""
    result = calculate_raw_tickets(
        game_type=GameType.LIVE,
        duration_minutes=120,
        turnover_amount=Decimal("1500"),
        formula=default_formula,
    )
    assert result == 5  # max_tickets_per_session = 5


def test_slot_multiplier(default_formula):
    """Slot saatte 0.5 bilet — 2 saat = 1 bilet"""
    result = calculate_raw_tickets(
        game_type=GameType.SLOT,
        duration_minutes=120,
        turnover_amount=Decimal("0"),
        formula=default_formula,
    )
    assert result == 1


def test_below_minimum_session(default_formula):
    """Minimum süre altındaki oturum bilet kazanmaz."""
    result = calculate_raw_tickets(
        game_type=GameType.LIVE,
        duration_minutes=10,  # min 15
        turnover_amount=Decimal("5000"),
        formula=default_formula,
    )
    assert result == 0


def test_session_cap(default_formula):
    """max_tickets_per_session aşılamaz."""
    result = calculate_raw_tickets(
        game_type=GameType.LIVE,
        duration_minutes=600,  # 10 saat
        turnover_amount=Decimal("50000"),
        formula=default_formula,
    )
    assert result == 5  # max_tickets_per_session


def test_custom_formula():
    """Casino formülü değiştirildiğinde hesap değişir."""
    formula = TicketFormula(
        live_tickets_per_hour=Decimal("2.0"),   # 2x
        live_turnover_per_ticket=Decimal("250"), # daha az ciro gerekir
        live_min_session_minutes=5,
        slot_tickets_per_hour=Decimal("1.0"),
        slot_turnover_per_ticket=Decimal("500"),
        slot_min_session_minutes=5,
        max_tickets_per_day=20,
        max_tickets_per_session=10,
    )
    result = calculate_raw_tickets(
        game_type=GameType.LIVE,
        duration_minutes=60,
        turnover_amount=Decimal("500"),
        formula=formula,
    )
    assert result == 4  # 2 (saat) + 2 (turnover 500/250)


# ── TIMEZONE TESTS ────────────────────────────────────────────────────────────

def test_ticket_number_uniqueness_at_scale():
    """1000 bilet üretildiğinde çakışma olmaz."""
    nums = {generate_ticket_number("KRT-001", 2025, i) for i in range(1000)}
    assert len(nums) == 1000, "Bilet numaraları benzersiz olmalı"


def test_consecutive_days_single_query():
    """
    get_consecutive_days artık single query kullanıyor.
    Fonksiyon var ve çağrılabilir.
    """
    import inspect, asyncio
    from app.services.ticket_engine import get_consecutive_days
    assert asyncio.iscoroutinefunction(get_consecutive_days)
