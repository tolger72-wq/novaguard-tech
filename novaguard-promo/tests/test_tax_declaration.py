"""
Vergi Beyanı — Kayıt Testleri

Vergi beyanı artık ZORUNLU KAPI değil, opsiyonel kayıttır.
tax_cleared property hâlâ çalışır (bilgi amaçlı), ama execute_draw bunu kontrol etmez.
Casino kendi sürecinde RS.GE beyanını yapar, sistemde belgeleyebilir.
"""
from decimal import Decimal
from datetime import datetime, timezone
from app.models import DrawSchedule, DrawTier, DrawStatus


def make_schedule(**overrides) -> DrawSchedule:
    defaults = dict(
        draw_tier=DrawTier.WEEKLY,
        name="Test Çekiliş",
        scheduled_at=datetime.now(timezone.utc),
        prize_amount=Decimal("1000"),
        prize_currency="GEL",
        prize_description="Test ödülü",
        campaign_year=2025,
        status=DrawStatus.SCHEDULED,
        tax_declaration_required=True,
    )
    defaults.update(overrides)
    return DrawSchedule(**defaults)


def test_tax_cleared_false_when_not_declared():
    """Beyan yapılmamışsa tax_cleared False — kayıt amaçlı bilgi."""
    s = make_schedule()
    assert s.tax_cleared is False


def test_tax_cleared_true_when_fully_declared():
    """Referans + ödeme tarihi varsa tax_cleared True."""
    s = make_schedule(
        tax_declaration_ref="RS-GE-2025-001",
        tax_amount_paid=Decimal("180"),
        tax_paid_at=datetime.now(timezone.utc),
    )
    assert s.tax_cleared is True


def test_tax_not_required_is_always_cleared():
    """tax_declaration_required=False ise her zaman temiz sayılır."""
    s = make_schedule(tax_declaration_required=False)
    assert s.tax_cleared is True


def test_tax_cleared_false_with_empty_ref():
    """Boş string referans dolu sayılmaz."""
    s = make_schedule(
        tax_declaration_ref="",
        tax_paid_at=datetime.now(timezone.utc),
    )
    assert s.tax_cleared is False


def test_tax_gate_is_removed():
    """
    Vergi beyanı artık çekilişi BLOKLAMAMAKTADIR.
    Bu test draw_engine'in tax_cleared kontrolü yapmadığını belgeler.
    """
    import inspect
    from app.services import draw_engine
    src = inspect.getsource(draw_engine.execute_draw)
    assert "tax_cleared" not in src, (
        "execute_draw içinde tax_cleared kontrolü bulundu — "
        "vergi beyanı zorunlu kapı olmamalı."
    )


def test_scheduled_draw_worker_does_not_gate_on_tax():
    """
    Otomatik çekiliş görevi (Celery worker) de vergi beyanına bakarak
    çekilişi atlamamalı — manuel yürütme ile tutarlı davranmalı.
    """
    import inspect
    from app import worker
    src = inspect.getsource(worker.check_scheduled_draws)
    assert "tax_cleared" not in src, (
        "check_scheduled_draws içinde tax_cleared kontrolü bulundu — "
        "otomatik çekiliş vergi beyanına göre atlanmamalı."
    )
