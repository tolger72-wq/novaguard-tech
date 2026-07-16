"""
Mini Bonus Servisi — "Aktif Oyuncu Mini Bonusu"
==================================================

Bu özellik NE YAPAR?
  Belirlenen saat aralığında (örn: 14:00 - 06:00), düzenli aralıklarla
  (örn: her 30 dakikada bir) o anda AKTİF OLARAK OYNAYAN bir oyuncuya
  küçük bir hediye (örn: 100 GEL) verir.

  Bilet sistemi ile karışmaz — bu tamamen ayrı, basit bir mekanizmadır.
  "Şu an masada/makinede oturan biri" havuzdan rastgele seçilir.

Bu dosyadaki fonksiyonlar tek tek, adım adım anlaşılır olacak şekilde yazıldı.
"""

import secrets
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import settings
# Not: bu dosya app/services/ altında olacağı için modelleri iki üst klasörden alıyoruz
from ..models import Player, GameSession, SessionStatus, DrawTier, DrawResult, PrizeWin, MiniBonusConfig


# ── ADIM 1: Şu an casino saatiyle kaç olduğunu bulmak ─────────────────────────

def get_casino_now() -> datetime:
    """
    Casino'nun bulunduğu şehre göre şu anki zamanı döner.
    Örnek: Gürcistan saatine göre "şimdi" ne zaman.
    """
    return datetime.now(ZoneInfo(settings.CASINO_TIMEZONE))


# ── ADIM 2: Şu an mini bonus penceresinin içinde miyiz? ───────────────────────

def is_within_window(now: datetime, start_hour: int, end_hour: int) -> bool:
    """
    Verilen saat (now), start_hour ile end_hour arasında mı diye bakar.

    ÖNEMLİ DETAY: Pencere gece yarısını geçebilir!
    Örnek: start_hour=14, end_hour=6 demek:
        14:00'ten gece yarısına (24:00) kadar VE
        gece yarısından sabah 06:00'ya kadar
    yani "14:00 - 06:00 arası" demektir, "14:00'ten 6:00'ya normal aralık" değil.

    Basit örnekler:
        saat 15:00 iken pencere içinde miyiz? → Evet (14 ile 24 arası)
        saat 03:00 iken pencere içinde miyiz? → Evet (0 ile 6 arası)
        saat 10:00 iken pencere içinde miyiz? → Hayır
    """
    current_hour = now.hour

    if start_hour <= end_hour:
        # Normal durum: örneğin 09:00 - 17:00 (gece yarısını geçmiyor)
        return start_hour <= current_hour < end_hour
    else:
        # Gece yarısını geçen durum: örneğin 14:00 - 06:00
        return current_hour >= start_hour or current_hour < end_hour


# ── ADIM 3: Günde kaç çekiliş oluyor, maliyeti ne? (hesap makinesi) ───────────

def calculate_daily_draw_count(interval_minutes: int, start_hour: int, end_hour: int) -> int:
    """
    Pencere kaç saat sürüyor, o sürede kaç kere çekiliş yapılıyor hesaplar.

    Örnek: start_hour=14, end_hour=6, interval_minutes=30
        14:00'ten 06:00'ya kadar = 16 saat = 960 dakika
        960 / 30 = 32 çekiliş
    """
    if start_hour <= end_hour:
        window_hours = end_hour - start_hour
    else:
        # Gece yarısını geçiyor: örn 14'ten 24'e (10 saat) + 0'dan 6'ya (6 saat) = 16 saat
        window_hours = (24 - start_hour) + end_hour

    window_minutes = window_hours * 60
    draw_count = window_minutes // interval_minutes
    return draw_count


def calculate_daily_cost(prize_amount: Decimal, interval_minutes: int,
                          start_hour: int, end_hour: int) -> Decimal:
    """Günlük toplam maliyeti hesaplar: (kaç çekiliş) x (ödül miktarı)."""
    count = calculate_daily_draw_count(interval_minutes, start_hour, end_hour)
    return prize_amount * count


def cost_estimate(config: MiniBonusConfig) -> dict:
    """
    Admin panelinde göstermek için hazır bir özet döner.
    Günlük, haftalık ve aylık maliyeti de hesaplar — casino bütçe planlaması yapabilsin.
    """
    daily_count = calculate_daily_draw_count(
        config.interval_minutes, config.window_start_hour, config.window_end_hour
    )
    daily_cost = config.prize_amount * daily_count

    return {
        "draws_per_day": daily_count,
        "daily_cost": str(daily_cost),
        "weekly_cost": str(daily_cost * 7),
        "monthly_cost": str(daily_cost * 30),
        "prize_amount": str(config.prize_amount),
        "prize_currency": config.prize_currency,
        "interval_minutes": config.interval_minutes,
        "window_start_hour": config.window_start_hour,
        "window_end_hour": config.window_end_hour,
    }


# ── ADIM 4: Şu an aktif oynayan oyuncuları bulmak ─────────────────────────────

async def get_active_players(db: AsyncSession) -> list[Player]:
    """
    "Aktif oyuncu" demek: oturumu hâlâ açık olan (henüz kalkmamış) oyuncu demek.
    GameSession tablosunda status = ACTIVE olan kayıtları buluyoruz.
    """
    result = await db.execute(
        select(Player)
        .join(GameSession, GameSession.card_id == Player.card_id)
        .where(GameSession.status == SessionStatus.ACTIVE)
        .where(Player.is_active == True)
        .distinct()
    )
    players = result.scalars().all()
    return list(players)


# ── ADIM 5: Mini bonus çekilişini yürütmek ────────────────────────────────────

async def execute_mini_bonus(config: MiniBonusConfig, db: AsyncSession) -> DrawResult | None:
    """
    Şu an aktif oynayan oyunculardan birini rastgele seçer, ona ödül verir.

    Eğer şu an oynayan kimse yoksa None döner (çekiliş yapılamaz, hiç sorun değil,
    bir sonraki 30 dakikada tekrar denenir).
    """
    active_players = await get_active_players(db)

    if not active_players:
        return None

    # Kriptografik olarak güvenli rastgele seçim (secrets modülü — normal random değil)
    winner = secrets.choice(active_players)

    now = get_casino_now()

    # DrawResult tablosuna kaydediyoruz (aynı tablo, farklı draw_tier ile)
    result = DrawResult(
        schedule_id=None,  # Mini bonus'un ayrı bir DrawSchedule kaydı yok, direkt yürütülüyor
        winner_card_id=winner.card_id,
        winning_ticket_number=f"MINI-{now.strftime('%Y%m%d-%H%M')}",
        total_tickets_in_pool=len(active_players),   # burada "bilet" değil "aktif oyuncu sayısı"
        total_players_in_pool=len(active_players),
        executed_at=now,
        executed_by="auto-mini-bonus",
        draw_metadata={
            "draw_tier": "mini",
            "prize_amount": str(config.prize_amount),
            "prize_currency": config.prize_currency,
            "rng": "secrets.choice",
            "note": "Aktif Oyuncu Mini Bonusu — otomatik çekiliş",
        },
    )
    db.add(result)
    await db.flush()

    # Kazanım kaydı (PrizeWin) — istatistik ve raporlama için
    prize_win = PrizeWin(
        card_id=winner.card_id,
        draw_tier=DrawTier.MINI,
        draw_result_id=result.id,
        prize_amount=config.prize_amount,
        prize_currency=config.prize_currency,
        prize_description=f"Aktif Oyuncu Mini Bonusu — {config.prize_amount} {config.prize_currency}",
        campaign_year=settings.CAMPAIGN_YEAR,
    )
    db.add(prize_win)

    await db.commit()
    await db.refresh(result)
    return result


# ── ADIM 6: Ayarları okumak / oluşturmak ──────────────────────────────────────

async def get_or_create_config(db: AsyncSession) -> MiniBonusConfig:
    """
    Mini bonus ayarları veritabanında yoksa varsayılan değerlerle oluşturur.
    Varsayılan: 100 GEL, her 30 dakikada bir, 14:00 - 06:00 arası, kapalı (is_active=False).
    """
    result = await db.execute(select(MiniBonusConfig).where(MiniBonusConfig.id == 1))
    config = result.scalar_one_or_none()

    if config is None:
        config = MiniBonusConfig(
            id=1,
            is_active=False,
            prize_amount=Decimal("100.00"),
            prize_currency="GEL",
            interval_minutes=30,
            window_start_hour=14,
            window_end_hour=6,
        )
        db.add(config)
        await db.commit()
        await db.refresh(config)

    return config
