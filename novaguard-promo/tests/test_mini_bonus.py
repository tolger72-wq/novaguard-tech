"""
Mini Bonus Testleri
======================
Bu testler basit hesap fonksiyonlarını kontrol eder:
  - Pencere içinde miyiz kontrolü (gece yarısını geçen saatler dahil)
  - Günde kaç çekiliş oluyor hesabı
  - Günlük/haftalık/aylık maliyet hesabı
"""
from datetime import datetime
from decimal import Decimal

from app.services.mini_bonus import (
    is_within_window,
    calculate_daily_draw_count,
    calculate_daily_cost,
)


# ── PENCERE KONTROLÜ (14:00 - 06:00 gibi gece yarısını geçen durumlar) ────────

def test_within_window_afternoon():
    """Saat 15:00 iken, 14:00-06:00 penceresinin İÇİNDE olmalıyız."""
    now = datetime(2025, 6, 1, 15, 0)  # saat 15:00
    assert is_within_window(now, start_hour=14, end_hour=6) is True


def test_within_window_early_morning():
    """Saat 03:00 iken (gece yarısından sonra), hâlâ pencerenin İÇİNDE olmalıyız."""
    now = datetime(2025, 6, 1, 3, 0)  # saat 03:00
    assert is_within_window(now, start_hour=14, end_hour=6) is True


def test_outside_window_midday():
    """Saat 10:00 iken, 14:00-06:00 penceresinin DIŞINDA olmalıyız."""
    now = datetime(2025, 6, 1, 10, 0)  # saat 10:00
    assert is_within_window(now, start_hour=14, end_hour=6) is False


def test_exactly_at_start_hour():
    """Saat tam 14:00 olunca pencere BAŞLAMALI (içeride sayılmalı)."""
    now = datetime(2025, 6, 1, 14, 0)
    assert is_within_window(now, start_hour=14, end_hour=6) is True


def test_exactly_at_end_hour():
    """Saat tam 06:00 olunca pencere BİTMİŞ olmalı (dışarıda sayılmalı)."""
    now = datetime(2025, 6, 1, 6, 0)
    assert is_within_window(now, start_hour=14, end_hour=6) is False


def test_normal_window_no_midnight_cross():
    """Gece yarısını geçmeyen normal bir pencere de doğru çalışmalı: 09:00-17:00."""
    assert is_within_window(datetime(2025, 6, 1, 12, 0), 9, 17) is True   # öğlen, içeride
    assert is_within_window(datetime(2025, 6, 1, 20, 0), 9, 17) is False  # akşam, dışarıda


# ── GÜNLÜK ÇEKİLİŞ SAYISI HESABI ──────────────────────────────────────────────

def test_daily_draw_count_matches_expected():
    """
    Kullanıcının istediği senaryo: 14:00 - 06:00 arası, her 30 dakikada bir.
    16 saat = 960 dakika. 960 / 30 = 32 çekiliş olmalı.
    """
    count = calculate_daily_draw_count(interval_minutes=30, start_hour=14, end_hour=6)
    assert count == 32


def test_daily_draw_count_shorter_window():
    """Örnek: 10:00-14:00 (4 saat = 240 dakika), her 60 dakikada bir → 4 çekiliş."""
    count = calculate_daily_draw_count(interval_minutes=60, start_hour=10, end_hour=14)
    assert count == 4


def test_daily_draw_count_full_day():
    """7/24 çalışsa (00:00-00:00 yani start=end=0 varsayımı yerine 0-24 gibi düşünmeyelim,
    farklı bir tam gün senaryosu test edelim: 0'dan 12'ye, her 30 dakikada bir → 24 çekiliş."""
    count = calculate_daily_draw_count(interval_minutes=30, start_hour=0, end_hour=12)
    assert count == 24


# ── MALİYET HESABI ────────────────────────────────────────────────────────────

def test_daily_cost_matches_expected():
    """
    32 çekiliş x 100 GEL = 3200 GEL/gün olmalı.
    Bu, kullanıcının sorduğu asıl soru.
    """
    cost = calculate_daily_cost(
        prize_amount=Decimal("100.00"),
        interval_minutes=30,
        start_hour=14,
        end_hour=6,
    )
    assert cost == Decimal("3200.00")


def test_daily_cost_scales_with_prize_amount():
    """Ödül miktarı 50 GEL olsaydı, maliyet yarıya inmeli: 32 x 50 = 1600 GEL."""
    cost = calculate_daily_cost(
        prize_amount=Decimal("50.00"),
        interval_minutes=30,
        start_hour=14,
        end_hour=6,
    )
    assert cost == Decimal("1600.00")


def test_daily_cost_scales_with_interval():
    """Aralık 60 dakika olsaydı (yarısı kadar çekiliş), maliyet yarıya inmeli: 16 x 100 = 1600 GEL."""
    cost = calculate_daily_cost(
        prize_amount=Decimal("100.00"),
        interval_minutes=60,
        start_hour=14,
        end_hour=6,
    )
    assert cost == Decimal("1600.00")
