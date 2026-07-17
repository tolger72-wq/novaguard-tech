"""
Draw Engine — Dışlama Mantığı Testleri v2.0

Kesinleşmiş kurallar:
  GÜNLÜK  : Bugün ödül kazandıysan → bugünkü diğer günlük çekilişlere giremezsin
             Yarın sıfır. Haftalık/aylık/final etkilenmez.
  HAFTALIK: Geçen hafta haftalık kazandıysan → bu haftanın haftalık çekilişine giremezsin
             İki hafta sonra tekrar giriyorsun. Diğer tier'lar etkilenmez.
  AYLIK   : Geçen ay aylık kazandıysan → bu ayın aylık çekilişine giremezsin
  ÇEYREK  : Geçen çeyrek kazandıysan → bu çeyreğe giremezsin
  FİNAL   : Asla dışlanma yok
"""
import pytest
from datetime import datetime, timedelta, timezone, date
from unittest.mock import AsyncMock, MagicMock
from app.models import DrawTier, PrizeWin
from app.services.draw_engine import (
    is_excluded, _prev_week, _prev_month, _prev_quarter,
    _week_bounds, _month_bounds, _quarter_bounds,
)


# ── YARDIMCI ─────────────────────────────────────────────────────────────────

def mock_db(win_count: int):
    """Belirli sayıda kazanım dönen sahte DB."""
    scalar = MagicMock()
    scalar.scalar_one.return_value = win_count
    db = AsyncMock()
    db.execute = AsyncMock(return_value=scalar)
    return db


TODAY = date(2025, 6, 14)   # Cumartesi


# ── DÖNEM HESAPLAMA ───────────────────────────────────────────────────────────

def test_week_bounds():
    """14 Haziran 2025 (Cumartesi) → hafta Pazartesi 9 Haz başlar."""
    mon, sun = _week_bounds(TODAY)
    assert mon == date(2025, 6, 9)
    assert sun == date(2025, 6, 15)


def test_prev_week():
    """Geçen hafta: 2-8 Haziran."""
    start, end = _prev_week(TODAY)
    assert start == date(2025, 6, 2)
    assert end   == date(2025, 6, 8)


def test_prev_month():
    """Haziran 2025 → Mayıs 2025."""
    start, end = _prev_month(TODAY)
    assert start == date(2025, 5, 1)
    assert end   == date(2025, 5, 31)


def test_quarter_bounds():
    """Q2 2025: Nisan-Haziran."""
    start, end = _quarter_bounds(TODAY)
    assert start == date(2025, 4, 1)
    assert end   == date(2025, 6, 30)


def test_prev_quarter():
    """Q1 2025: Ocak-Mart."""
    start, end = _prev_quarter(TODAY)
    assert start == date(2025, 1, 1)
    assert end   == date(2025, 3, 31)


# ── FİNAL: ASLA DIŞLANMA ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_annual_never_excluded():
    """Final çekilişinden asla dışlanılmaz — ne kadar kazanmış olursa olsun."""
    db = mock_db(999)
    assert await is_excluded("KRT-001", DrawTier.ANNUAL, db, TODAY) is False


# ── GÜNLÜK: BUGÜN SINIRI ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_daily_excluded_if_won_today():
    """Bugün ödül kazandıysan günlük çekilişe giremezsin."""
    assert await is_excluded("KRT-001", DrawTier.DAILY, mock_db(1), TODAY) is True


@pytest.mark.asyncio
async def test_daily_eligible_if_no_win_today():
    """Bugün kazanmadıysan günlük çekilişe girebilirsin."""
    assert await is_excluded("KRT-001", DrawTier.DAILY, mock_db(0), TODAY) is False


@pytest.mark.asyncio
async def test_daily_does_not_affect_weekly():
    """Bugün günlük kazanmak haftalık çekilişi etkilemez."""
    # Günlük: bugün kazandı (1) → dışlanır
    daily_excluded = await is_excluded("KRT-001", DrawTier.DAILY, mock_db(1), TODAY)
    assert daily_excluded is True

    # Haftalık: geçen hafta haftalık kazanmadı (0) → dışlanmaz
    weekly_excluded = await is_excluded("KRT-001", DrawTier.WEEKLY, mock_db(0), TODAY)
    assert weekly_excluded is False


# ── HAFTALIK: GEÇEN HAFTA SINIRI ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_weekly_excluded_if_won_last_week():
    """Geçen hafta haftalık kazandıysan bu haftanın haftalık çekilişine giremezsin."""
    assert await is_excluded("KRT-001", DrawTier.WEEKLY, mock_db(1), TODAY) is True


@pytest.mark.asyncio
async def test_weekly_eligible_if_not_won_last_week():
    """Geçen hafta haftalık kazanmadıysan bu haftanın haftalık çekilişine girebilirsin."""
    assert await is_excluded("KRT-001", DrawTier.WEEKLY, mock_db(0), TODAY) is False


@pytest.mark.asyncio
async def test_weekly_does_not_affect_daily():
    """Haftalık kazanmak günlük çekilişleri etkilemez."""
    # Haftalık: geçen hafta kazandı → dışlanır
    weekly_excl = await is_excluded("KRT-001", DrawTier.WEEKLY, mock_db(1), TODAY)
    assert weekly_excl is True

    # Günlük: bugün kazanmadı → dışlanmaz
    daily_excl = await is_excluded("KRT-001", DrawTier.DAILY, mock_db(0), TODAY)
    assert daily_excl is False


@pytest.mark.asyncio
async def test_weekly_does_not_affect_monthly():
    """Geçen hafta haftalık kazanmak aylık çekilişi etkilemez."""
    weekly_excl = await is_excluded("KRT-001", DrawTier.WEEKLY, mock_db(1), TODAY)
    assert weekly_excl is True

    monthly_excl = await is_excluded("KRT-001", DrawTier.MONTHLY, mock_db(0), TODAY)
    assert monthly_excl is False


# ── AYLIK: GEÇEN AY SINIRI ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_monthly_excluded_if_won_last_month():
    """Geçen ay aylık kazandıysan bu ayın aylık çekilişine giremezsin."""
    assert await is_excluded("KRT-001", DrawTier.MONTHLY, mock_db(1), TODAY) is True


@pytest.mark.asyncio
async def test_monthly_eligible_if_not_won_last_month():
    assert await is_excluded("KRT-001", DrawTier.MONTHLY, mock_db(0), TODAY) is False


@pytest.mark.asyncio
async def test_monthly_does_not_affect_quarterly():
    """Geçen ay aylık kazanmak çeyrek çekilişi etkilemez."""
    monthly_excl = await is_excluded("KRT-001", DrawTier.MONTHLY, mock_db(1), TODAY)
    assert monthly_excl is True

    quarterly_excl = await is_excluded("KRT-001", DrawTier.QUARTERLY, mock_db(0), TODAY)
    assert quarterly_excl is False


# ── ÇEYREK: GEÇEN ÇEYREK SINIRI ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_quarterly_excluded_if_won_last_quarter():
    """Geçen çeyrekte çeyrek kazandıysan bu çeyreğin çekiliişine giremezsin."""
    assert await is_excluded("KRT-001", DrawTier.QUARTERLY, mock_db(1), TODAY) is True


@pytest.mark.asyncio
async def test_quarterly_eligible_if_not_won_last_quarter():
    assert await is_excluded("KRT-001", DrawTier.QUARTERLY, mock_db(0), TODAY) is False


@pytest.mark.asyncio
async def test_quarterly_does_not_affect_annual():
    """Geçen çeyrekte kazanmak final çekilişini etkilemez."""
    quarterly_excl = await is_excluded("KRT-001", DrawTier.QUARTERLY, mock_db(1), TODAY)
    assert quarterly_excl is True

    annual_excl = await is_excluded("KRT-001", DrawTier.ANNUAL, mock_db(999), TODAY)
    assert annual_excl is False


# ── ÇAPRAZ SENARYOLAR ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_all_wins_never_affect_annual():
    """Tüm tier'lardan ödül kazanmak final hakkını etkilemez."""
    annual_excl = await is_excluded("KRT-001", DrawTier.ANNUAL, mock_db(100), TODAY)
    assert annual_excl is False


@pytest.mark.asyncio
async def test_daily_win_allows_weekly_participation():
    """
    Bugün günlük kazandım → günlük dışındayım.
    Ama haftalık çekilişe GİREBİLİRİM (geçen hafta haftalık kazanmadım).
    """
    daily_excl   = await is_excluded("KRT-001", DrawTier.DAILY,  mock_db(1), TODAY)
    weekly_excl  = await is_excluded("KRT-001", DrawTier.WEEKLY, mock_db(0), TODAY)
    monthly_excl = await is_excluded("KRT-001", DrawTier.MONTHLY, mock_db(0), TODAY)
    annual_excl  = await is_excluded("KRT-001", DrawTier.ANNUAL, mock_db(0), TODAY)

    assert daily_excl   is True   # günlük: bugün kazandım → dışındayım
    assert weekly_excl  is False  # haftalık: geçen hafta kazanmadım → girerim
    assert monthly_excl is False  # aylık: geçen ay kazanmadım → girerim
    assert annual_excl  is False  # final: asla dışlanma


@pytest.mark.asyncio
async def test_weekly_winner_skip_one_week():
    """
    Haftalık kazananı sadece BİR sonraki hafta dışlar.
    İki hafta sonra (bu hafta için geçen hafta kazanmadı) → tekrar girer.
    """
    # Bu hafta: geçen hafta kazandı → dışlanır
    next_week_ref = TODAY + timedelta(weeks=1)
    excl_next = await is_excluded("KRT-001", DrawTier.WEEKLY, mock_db(1), next_week_ref)
    assert excl_next is True

    # İki hafta sonra: "geçen hafta" = bu hafta, kazanmadı → girer
    week_after_ref = TODAY + timedelta(weeks=2)
    excl_after = await is_excluded("KRT-001", DrawTier.WEEKLY, mock_db(0), week_after_ref)
    assert excl_after is False
