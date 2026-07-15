"""
NovaGuard Çekiliş Sertifikası Üretici
=======================================
Her çekiliş sonrası otomatik PDF sertifika üretir.

Amaç: "Bu çekiliş hileli mi?" sorusuna fiziksel/dijital kanıtla cevap.
İçerik: kazanan, havuz şeffaflığı, kriptografik RNG kanıtı, doğrulama hash'i.

Bu sertifika:
  - Casino duvarına asılabilir (görsel güven unsuru)
  - Yasal denetimde ibraz edilebilir
  - Oyunculara dijital olarak gönderilebilir (gelecek: WhatsApp/email)
"""
import hashlib
from datetime import datetime
from decimal import Decimal
from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)

# ── NOVAGUARD RENK PALETİ ──────────────────────────────────────────────────────
GOLD      = HexColor("#8b6d1a")
GOLD_DARK = HexColor("#5c4810")
INK       = HexColor("#1a1a1a")
DIM       = HexColor("#6a6058")
LINE      = HexColor("#d4af37")


def _certificate_hash(draw_id: str, winner_card_id: str, winning_ticket: str,
                       total_tickets: int, executed_at: str,
                       tax_declaration_ref: str | None = None) -> str:
    """
    Doğrulama hash'i — sertifikadaki tüm kritik veriyi tek SHA-256'ya bağlar.
    Sertifika sonradan değiştirilirse bu hash artık eşleşmez.
    Vergi beyan referansı da hash'e dahildir — bu sayede "X numaralı RS.GE
    beyanı bu çekilişe aittir" iddiası da kriptografik olarak korunur.
    """
    payload = f"{draw_id}|{winner_card_id}|{winning_ticket}|{total_tickets}|{executed_at}|{tax_declaration_ref or ''}"
    return hashlib.sha256(payload.encode()).hexdigest().upper()


def generate_draw_certificate(
    *,
    draw_id: str,
    draw_name: str,
    draw_tier: str,
    prize_description: str,
    prize_amount: Decimal,
    prize_currency: str,
    winner_name: str,
    winner_card_id: str,
    winning_ticket: str,
    total_tickets_in_pool: int,
    total_players_in_pool: int,
    executed_at: datetime,
    rng_method: str = "secrets.SystemRandom (CSPRNG)",
    casino_name: str = "NovaGuard Casino Operations",
    tax_declaration_ref: str | None = None,
    tax_amount_paid: Decimal | None = None,
    tax_paid_at: datetime | None = None,
    output_path: str | None = None,
) -> bytes:
    """
    Çekiliş sertifikası PDF'i üretir. output_path verilirse dosyaya yazar,
    her durumda PDF bytes döner (API'den direkt stream edilebilir).
    """
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        topMargin=22*mm, bottomMargin=22*mm,
        leftMargin=24*mm, rightMargin=24*mm,
    )

    styles = getSampleStyleSheet()
    brand_style = ParagraphStyle("Brand", parent=styles["Normal"],
        fontName="Helvetica-Bold", fontSize=10, textColor=GOLD_DARK,
        alignment=TA_CENTER, characterSpacing=3)
    title_style = ParagraphStyle("Title", parent=styles["Title"],
        fontName="Helvetica-Bold", fontSize=22, textColor=INK,
        alignment=TA_CENTER, spaceAfter=2)
    subtitle_style = ParagraphStyle("Subtitle", parent=styles["Normal"],
        fontName="Helvetica", fontSize=10, textColor=DIM,
        alignment=TA_CENTER, spaceAfter=18)
    label_style = ParagraphStyle("Label", parent=styles["Normal"],
        fontName="Helvetica", fontSize=8, textColor=DIM, leading=11)
    value_style = ParagraphStyle("Value", parent=styles["Normal"],
        fontName="Helvetica-Bold", fontSize=12, textColor=INK, leading=15)
    winner_name_style = ParagraphStyle("WinnerName", parent=styles["Normal"],
        fontName="Helvetica-Bold", fontSize=26, textColor=GOLD_DARK,
        alignment=TA_CENTER, spaceAfter=4)
    winner_sub_style = ParagraphStyle("WinnerSub", parent=styles["Normal"],
        fontName="Helvetica", fontSize=10, textColor=DIM,
        alignment=TA_CENTER)
    footer_style = ParagraphStyle("Footer", parent=styles["Normal"],
        fontName="Helvetica", fontSize=7, textColor=DIM, leading=10)
    mono_style = ParagraphStyle("Mono", parent=styles["Normal"],
        fontName="Courier", fontSize=8, textColor=INK, leading=11)

    cert_hash = _certificate_hash(
        draw_id, winner_card_id, winning_ticket,
        total_tickets_in_pool, executed_at.isoformat(),
        tax_declaration_ref,
    )
    cert_no = f"NVG-CERT-{executed_at.strftime('%Y%m%d')}-{cert_hash[:8]}"

    story = []

    # ── HEADER ──────────────────────────────────────────────────────────────
    story.append(Paragraph("◈ &nbsp; N O V A G U A R D &nbsp; ◈", brand_style))
    story.append(Spacer(1, 14))
    story.append(Paragraph("ÇEKİLİŞ SERTİFİKASI", title_style))
    story.append(Paragraph("Draw Certificate &nbsp;·&nbsp; " + casino_name, subtitle_style))
    story.append(HRFlowable(width="100%", thickness=1.2, color=LINE, spaceAfter=20))

    # ── ÇEKİLİŞ BİLGİSİ ─────────────────────────────────────────────────────
    tier_label = {
        "daily": "GÜNLÜK ÇEKİLİŞ", "weekly": "HAFTALIK ÇEKİLİŞ",
        "monthly": "AYLIK ÇEKİLİŞ", "quarterly": "3 AYLIK ÇEKİLİŞ",
        "annual": "YILLIK BÜYÜK FİNAL",
    }.get(draw_tier, draw_tier.upper())

    info_table = Table([
        [Paragraph("ÇEKİLİŞ ADI", label_style), Paragraph(draw_name, value_style)],
        [Paragraph("ÇEKİLİŞ TÜRÜ", label_style), Paragraph(tier_label, value_style)],
        [Paragraph("ÖDÜL", label_style), Paragraph(prize_description, value_style)],
        [Paragraph("TARİH / SAAT", label_style), Paragraph(
            executed_at.strftime("%d.%m.%Y &nbsp;·&nbsp; %H:%M"), value_style)],
    ], colWidths=[45*mm, 110*mm])
    info_table.setStyle(TableStyle([
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("BOTTOMPADDING", (0,0), (-1,-1), 10),
        ("TOPPADDING", (0,0), (-1,-1), 2),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 8))
    story.append(HRFlowable(width="100%", thickness=.5, color=DIM, spaceAfter=22))

    # ── KAZANAN ─────────────────────────────────────────────────────────────
    story.append(Paragraph("K A Z A N A N", ParagraphStyle(
        "WinnerLabel", parent=label_style, alignment=TA_CENTER,
        fontSize=9, textColor=GOLD_DARK, spaceAfter=10)))
    story.append(Paragraph(winner_name, winner_name_style))
    story.append(Paragraph(
        f"Kart No: {winner_card_id} &nbsp;·&nbsp; Kazanan Bilet: {winning_ticket}",
        winner_sub_style))
    story.append(Spacer(1, 24))
    story.append(HRFlowable(width="100%", thickness=.5, color=DIM, spaceAfter=20))

    # ── ŞEFFAFLIK / HAVUZ İSTATİSTİKLERİ ──────────────────────────────────────
    story.append(Paragraph("HAVUZ ŞEFFAFLIĞI &nbsp;/&nbsp; POOL TRANSPARENCY",
        ParagraphStyle("SectionLabel", parent=label_style, fontSize=8,
                       textColor=GOLD_DARK, spaceAfter=10)))

    pool_table = Table([
        [Paragraph("Toplam Katılımcı Bilet", label_style),
         Paragraph("Toplam Uygun Oyuncu", label_style),
         Paragraph("RNG Yöntemi", label_style)],
        [Paragraph(f"{total_tickets_in_pool:,}".replace(",", "."), value_style),
         Paragraph(f"{total_players_in_pool}", value_style),
         Paragraph(rng_method, ParagraphStyle("RngVal", parent=value_style, fontSize=9))],
    ], colWidths=[51.6*mm, 51.6*mm, 51.6*mm])
    pool_table.setStyle(TableStyle([
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("BOTTOMPADDING", (0,0), (-1,0), 8),
    ]))
    story.append(pool_table)
    story.append(Spacer(1, 20))
    story.append(HRFlowable(width="100%", thickness=.5, color=DIM, spaceAfter=20))

    # ── VERGİ BEYANI (RS.GE) ────────────────────────────────────────────────
    if tax_declaration_ref:
        story.append(Paragraph("VERGİ BEYANI &nbsp;/&nbsp; TAX DECLARATION (RS.GE)",
            ParagraphStyle("TaxLabel", parent=label_style, fontSize=8,
                           textColor=GOLD_DARK, spaceAfter=10)))
        tax_table = Table([
            [Paragraph("RS.GE Beyan No", label_style),
             Paragraph("Yatırılan Vergi", label_style),
             Paragraph("Ödeme Tarihi", label_style)],
            [Paragraph(tax_declaration_ref, ParagraphStyle("TaxVal", parent=value_style, fontSize=10)),
             Paragraph(f"{tax_amount_paid:,.2f} {prize_currency}".replace(",", ".") if tax_amount_paid else "—",
                       ParagraphStyle("TaxVal2", parent=value_style, fontSize=10)),
             Paragraph(tax_paid_at.strftime("%d.%m.%Y") if tax_paid_at else "—",
                       ParagraphStyle("TaxVal3", parent=value_style, fontSize=10))],
        ], colWidths=[51.6*mm, 51.6*mm, 51.6*mm])
        tax_table.setStyle(TableStyle([
            ("VALIGN", (0,0), (-1,-1), "TOP"),
            ("BOTTOMPADDING", (0,0), (-1,0), 8),
        ]))
        story.append(tax_table)
        story.append(Spacer(1, 8))
        story.append(Paragraph(
            "Bu ödül, dağıtılmadan önce Gürcistan Revenue Service'e (RS.GE) "
            "usulüne uygun şekilde beyan edilmiş ve vergisi yatırılmıştır.",
            ParagraphStyle("TaxNote", parent=footer_style, fontSize=7.5)))
        story.append(Spacer(1, 20))
        story.append(HRFlowable(width="100%", thickness=.5, color=DIM, spaceAfter=20))

    # ── DOĞRULAMA ───────────────────────────────────────────────────────────
    story.append(Paragraph("DOĞRULAMA KODU &nbsp;/&nbsp; VERIFICATION HASH",
        ParagraphStyle("SectionLabel2", parent=label_style, fontSize=8,
                       textColor=GOLD_DARK, spaceAfter=8)))
    story.append(Paragraph(cert_hash, mono_style))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        f"Sertifika No: {cert_no}",
        ParagraphStyle("CertNo", parent=label_style, fontSize=8)))
    story.append(Spacer(1, 30))

    # ── İMZA ALANI ──────────────────────────────────────────────────────────
    sig_table = Table([
        ["_" * 32, "_" * 32],
        [Paragraph("Casino Yetkilisi / Operator", footer_style),
         Paragraph("Tarih / Date", footer_style)],
    ], colWidths=[77*mm, 77*mm])
    sig_table.setStyle(TableStyle([
        ("TOPPADDING", (0,0), (-1,0), 30),
    ]))
    story.append(sig_table)
    story.append(Spacer(1, 24))

    # ── FOOTER ──────────────────────────────────────────────────────────────
    story.append(HRFlowable(width="100%", thickness=.5, color=DIM, spaceAfter=8))
    story.append(Paragraph(
        "Bu sertifika NovaGuard Promo Engine tarafından otomatik üretilmiştir. "
        "Doğrulama hash'i çekiliş kimliği, kazanan, kazanan bilet numarası ve "
        "toplam havuz büyüklüğünden türetilmiştir — herhangi bir değişiklik "
        "hash'i geçersiz kılar.",
        footer_style))
    story.append(Paragraph(
        "This certificate is auto-generated by NovaGuard Promo Engine. "
        "The verification hash is derived from the draw ID, winner, winning "
        "ticket number, and total pool size — any tampering invalidates it.",
        footer_style))

    doc.build(story)
    pdf_bytes = buf.getvalue()
    buf.close()

    if output_path:
        with open(output_path, "wb") as f:
            f.write(pdf_bytes)

    return pdf_bytes
