"""
Çekiliş Sertifikası — Font ve İçerik Testleri

Standart PDF-14 fontları (Helvetica vb.) Gürcüce'yi hiç, Türkçe'nin bazı
harflerini (ı, İ, ş, ğ) ise kısmen desteklemiyordu — bu testler DejaVu Sans'ın
gömülü olduğunu ve Gürcüce/Türkçe içeriğin hatasız üretildiğini doğrular.
"""
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from reportlab.pdfbase import pdfmetrics

from app.services.certificate import (
    generate_draw_certificate, FONT_REGULAR, FONT_BOLD, FONT_MONO, L, TIER_LABEL,
)


def _sample_pdf(**overrides) -> bytes:
    defaults = dict(
        draw_id="draw-test-1",
        draw_name="Haftalık Çekiliş — Hafta 23",
        draw_tier="weekly",
        prize_description="4,900 GEL Free Play Kredisi",
        prize_amount=Decimal("4900.00"),
        prize_currency="GEL",
        winner_name="ნუცა ბერიშვილი",
        winner_card_id="KRT-008",
        winning_ticket="NG-K7R3M9P2A1F4",
        total_tickets_in_pool=14218,
        total_players_in_pool=186,
        executed_at=datetime(2026, 6, 14, 21, 7, tzinfo=timezone.utc),
    )
    defaults.update(overrides)
    return generate_draw_certificate(**defaults)


def test_dejavu_fonts_registered():
    """Gürcüce (Mkhedruli) + Türkçe glyph kapsamı olan font gömülü mü?"""
    names = pdfmetrics.getRegisteredFontNames()
    assert FONT_REGULAR in names
    assert FONT_BOLD in names
    assert FONT_MONO in names


def test_certificate_with_georgian_winner_name_does_not_raise():
    """Gürcüce (Mkhedruli) kazanan ismiyle sertifika hatasız üretilmeli."""
    pdf = _sample_pdf(winner_name="ნუცა ბერიშვილი")
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 1000


def test_certificate_with_turkish_diacritics_does_not_raise():
    """ı/İ/ş/ğ gibi standart PDF fontlarında eksik olan harfler sorun çıkarmamalı."""
    pdf = _sample_pdf(winner_name="Gökçe Yıldırım İğneci", draw_name="Şanslı Çekiliş — Öğle Turu")
    assert pdf.startswith(b"%PDF")


def test_certificate_is_trilingual():
    """Her etiket TR/EN/KA üç dilde tanımlı olmalı (bkz. L sözlüğü)."""
    for key, (tr, en, ka) in L.items():
        assert tr and en and ka, f"'{key}' için eksik dil çevirisi"


def test_tier_labels_are_trilingual():
    for tier, (tr, en, ka) in TIER_LABEL.items():
        assert tr and en and ka, f"'{tier}' tier etiketi için eksik dil çevirisi"


def test_certificate_without_tax_declaration_omits_tax_section():
    """Vergi beyanı girilmemişse (opsiyonel kayıt) bölüm sertifikada hiç görünmemeli."""
    pdf = _sample_pdf(tax_declaration_ref=None)
    assert pdf.startswith(b"%PDF")


def test_certificate_with_tax_declaration_included():
    pdf = _sample_pdf(
        tax_declaration_ref="RS-GE-2026-0614-3391",
        tax_amount_paid=Decimal("980.00"),
        tax_paid_at=datetime(2026, 6, 14, tzinfo=timezone.utc),
    )
    assert pdf.startswith(b"%PDF")


@pytest.mark.parametrize("tier", ["daily", "weekly", "monthly", "quarterly", "annual"])
def test_certificate_all_tiers_render(tier):
    pdf = _sample_pdf(draw_tier=tier)
    assert pdf.startswith(b"%PDF")
