"""
Celery Worker — Zamanlanmış görevler.
  1. Zamanı gelen çekilişleri otomatik yürütür.
  2. Mini bonus penceresinde ise, düzenli aralıklarla mini bonus çekilişi yapar.

Senkronizasyon casino sisteminin kendi script'i ile yapılır
(bkz. scripts/casino_sync_example.py).
"""
from celery import Celery
from .core.config import settings

celery = Celery("novaguard_promo", broker=settings.REDIS_URL, backend=settings.REDIS_URL)
celery.conf.timezone = settings.CASINO_TIMEZONE

celery.conf.beat_schedule = {
    "check-scheduled-draws": {
        "task": "app.worker.check_scheduled_draws",
        "schedule": 60.0,   # her dakika kontrol et
    },
    "check-mini-bonus": {
        "task": "app.worker.check_mini_bonus",
        "schedule": 60.0,   # her dakika kontrol et — ayarlanan aralığa göre kendi karar verir
    },
}


@celery.task
def check_scheduled_draws():
    """Zamanı gelen çekilişleri otomatik yürüt."""
    import asyncio
    from datetime import datetime

    async def _run():
        from sqlalchemy import select, and_
        from .database import AsyncSessionLocal
        from .models import DrawSchedule, DrawStatus
        from .services.draw_engine import execute_draw

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(DrawSchedule).where(
                    and_(
                        DrawSchedule.status == DrawStatus.SCHEDULED,
                        DrawSchedule.scheduled_at <= datetime.utcnow(),
                    )
                )
            )
            for schedule in result.scalars().all():
                # Vergi beyanı Casino'nun kendi iç prosedürü — sistemimiz bunu
                # yürütmeyi engelleyen bir kapı olarak kullanmaz (bkz. draw_engine.execute_draw).
                try:
                    await execute_draw(schedule, db)
                    print(f"✓ Otomatik çekiliş: {schedule.name}")
                except Exception as e:
                    print(f"✗ Çekiliş hatası {schedule.id}: {e}")

    asyncio.run(_run())


@celery.task
def check_mini_bonus():
    """
    Her dakika çalışır ama sadece şu şartlar sağlanınca gerçekten çekiliş yapar:
      1. Mini bonus özelliği açık mı (is_active)
      2. Şu an belirlenen saat penceresinde miyiz (örn: 14:00-06:00)
      3. Son çekilişten bu yana yeterli süre geçti mi (interval_minutes)

    Bu üç kontrol de "hayır" değilse çekiliş yapılır.
    """
    import asyncio
    from datetime import datetime, timedelta

    async def _run():
        from sqlalchemy import select, desc
        from .database import AsyncSessionLocal
        from .models import DrawResult
        from .services import mini_bonus as mini_bonus_service

        async with AsyncSessionLocal() as db:
            config = await mini_bonus_service.get_or_create_config(db)

            # 1. Özellik kapalıysa hiçbir şey yapma
            if not config.is_active:
                return

            now = mini_bonus_service.get_casino_now()

            # 2. Saat penceresinin dışındaysak hiçbir şey yapma
            if not mini_bonus_service.is_within_window(now, config.window_start_hour, config.window_end_hour):
                return

            # 3. Son mini bonus ne zaman yapıldı, ona bak
            last_result = await db.execute(
                select(DrawResult)
                .where(DrawResult.executed_by == "auto-mini-bonus")
                .order_by(desc(DrawResult.executed_at))
                .limit(1)
            )
            last = last_result.scalar_one_or_none()

            if last is not None:
                minutes_since_last = (now - last.executed_at).total_seconds() / 60
                if minutes_since_last < config.interval_minutes:
                    return  # Henüz zamanı gelmedi

            # Her şey uygun — çekilişi yap
            try:
                result = await mini_bonus_service.execute_mini_bonus(config, db)
                if result:
                    print(f"✓ Mini bonus verildi: {result.winner_card_id}")
                else:
                    print("Mini bonus: şu an aktif oyuncu yok, atlandı")
            except Exception as e:
                print(f"✗ Mini bonus hatası: {e}")

    asyncio.run(_run())
