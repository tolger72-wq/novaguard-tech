"""
NovaGuard Çekiliş Sertifikası Üretici
=======================================
Her çekiliş sonrası otomatik PDF sertifika üretir.

Amaç: "Bu çekiliş hileli mi?" sorusuna fiziksel/dijital kanıtla cevap.
İçerik: kazanan, havuz şeffaflığı, kriptografik RNG kanıtı, doğrulama hash'i.

Büyük ödüllerde bu sertifika aynı zamanda kazanılan paranın/ödülün DEKLARASYONU
niteliğindedir (misafire ve — vergi beyanı girildiyse — muhasebeye kanıt) —
bu yüzden üç dilde (Türkçe / İngilizce / Gürcüce) basılır: casino personeli,
uluslararası misafir ve yerel (Gürcü) makam/misafir aynı belgeyi okuyabilsin.

Yazı tipi: standart PDF-14 fontları (Helvetica vb.) Gürcüce'yi (Mkhedruli)
hiç, Türkçe'nin bazı harflerini (ı, İ, ş, ğ) ise kısmen desteklemez — bu
harfler kare olarak basılırdı. Bunun yerine DejaVu Sans gömülüyor: tek bir
font dosyasıyla Türkçe + Gürcüce + İngilizce/Latin tam kapsanıyor (bkz.
app/services/fonts/LICENSE.txt). Font dosyaları pakete dahildir — internet
bağlantısı gerektirmez (offline casino kurulumlarında da çalışır).

Bu sertifika:
  - Casino duvarına asılabilir (görsel güven unsuru)
  - Yasal denetimde ibraz edilebilir
  - Oyunculara e-posta ile gönderilebilir (bkz. app/services/mailer.py,
    POST /api/v1/draws/{id}/certificate/email)
"""
import hashlib
import os
from datetime import datetime
from decimal import Decimal
from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)

# ── GÖMÜLÜ YAZI TİPİ (Türkçe + Gürcüce + İngilizce tek fontta) ─────────────────
_FONT_DIR = os.path.join(os.path.dirname(__file__), "fonts")
FONT_REGULAR = "DejaVuSans"
FONT_BOLD    = "DejaVuSans-Bold"
FONT_MONO    = "DejaVuSansMono"

if FONT_REGULAR not in pdfmetrics.getRegisteredFontNames():
    pdfmetrics.registerFont(TTFont(FONT_REGULAR, os.path.join(_FONT_DIR, "DejaVuSans.ttf")))
    pdfmetrics.registerFont(TTFont(FONT_BOLD, os.path.join(_FONT_DIR, "DejaVuSans-Bold.ttf")))
    pdfmetrics.registerFont(TTFont(FONT_MONO, os.path.join(_FONT_DIR, "DejaVuSansMono.ttf")))
    pdfmetrics.registerFontFamily(FONT_REGULAR, normal=FONT_REGULAR, bold=FONT_BOLD)

# ── NOVAGUARD RENK PALETİ ──────────────────────────────────────────────────────
GOLD      = HexColor("#8b6d1a")
GOLD_DARK = HexColor("#5c4810")
INK       = HexColor("#1a1a1a")
DIM       = HexColor("#6a6058")
LINE      = HexColor("#d4af37")


# ── ÜÇ DİLLİ ETİKETLER (TR / EN / KA) ──────────────────────────────────────────
# Sertifika büyük ödüllerde ödülün deklarasyonu yerine geçtiği için üç dilde basılır.
L = {
    "draw_name":    ("ÇEKİLİŞ ADI", "DRAW NAME", "გათამაშების დასახელება"),
    "draw_type":    ("ÇEKİLİŞ TÜRÜ", "DRAW TYPE", "გათამაშების ტიპი"),
    "prize":        ("ÖDÜL", "PRIZE", "პრიზი"),
    "datetime":     ("TARİH / SAAT", "DATE / TIME", "თარიღი / დრო"),
    "winner":       ("KAZANAN", "WINNER", "გამარჯვებული"),
    "card_no":      ("Kart No", "Card No", "ბარათის №"),
    "winning_ticket": ("Kazanan Bilet", "Winning Ticket", "გამარჯვებული ბილეთი"),
    "pool_transparency": ("HAVUZ ŞEFFAFLIĞI", "POOL TRANSPARENCY", "პულის გამჭვირვალობა"),
    "total_pool_tickets": ("Toplam Katılımcı Bilet", "Total Tickets in Pool", "პულში სულ ბილეთი"),
    "total_pool_players": ("Toplam Uygun Oyuncu", "Total Eligible Players", "უფლებამოსილი მოთამაშეები"),
    "rng_method":   ("RNG Yöntemi", "RNG Method", "შემთხვევითობის მეთოდი"),
    "tax_section":  ("VERGİ BEYANI", "TAX DECLARATION", "საგადასახადო დეკლარაცია"),
    "tax_ref":      ("RS.GE Beyan No", "RS.GE Declaration No", "RS.GE დეკლარაციის №"),
    "tax_paid":     ("Yatırılan Vergi", "Tax Paid", "გადახდილი გადასახადი"),
    "tax_date":     ("Ödeme Tarihi", "Payment Date", "გადახდის თარიღი"),
    "verification": ("DOĞRULAMA KODU", "VERIFICATION HASH", "დამოწმების კოდი"),
    "cert_no":      ("Sertifika No", "Certificate No", "სერტიფიკატის №"),
    "sig_operator": ("Casino Yetkilisi", "Casino Operator", "კაზინოს წარმომადგენელი"),
    "sig_date":     ("Tarih", "Date", "თარიღი"),
}

TIER_LABEL = {
    "daily":     ("GÜNLÜK ÇEKİLİŞ",   "DAILY DRAW",           "დღიური გათამაშება"),
    "weekly":    ("HAFTALIK ÇEKİLİŞ", "WEEKLY DRAW",          "კვირეული გათამაშება"),
    "monthly":   ("AYLIK ÇEKİLİŞ",    "MONTHLY DRAW",         "თვიური გათამაშება"),
    "quarterly": ("3 AYLIK ÇEKİLİŞ",  "QUARTERLY DRAW",       "კვარტალური გათამაშება"),
    "annual":    ("YILLIK BÜYÜK FİNAL", "ANNUAL GRAND FINAL", "წლიური დიდი ფინალი"),
}


def _tri(key: str, sep: str = "  ·  ") -> str:
    """Üç dilli etiket satırı üretir: 'TR  ·  EN  ·  KA'."""
    tr, en, ka = L[key]
    return f"{tr}{sep}{en}{sep}{ka}"


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
    her durumda PDF bytes döner (API'den direkt stream edilebilir veya
    e-posta eki olarak gönderilebilir).
    """
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        topMargin=22*mm, bottomMargin=22*mm,
        leftMargin=24*mm, rightMargin=24*mm,
    )

    styles = getSampleStyleSheet()
    brand_style = ParagraphStyle("Brand", parent=styles["Normal"],
        fontName=FONT_BOLD, fontSize=10, textColor=GOLD_DARK,
        alignment=TA_CENTER, characterSpacing=3)
    title_style = ParagraphStyle("Title", parent=styles["Title"],
        fontName=FONT_BOLD, fontSize=22, leading=27, textColor=INK,
        alignment=TA_CENTER, spaceAfter=2)
    subtitle_style = ParagraphStyle("Subtitle", parent=styles["Normal"],
        fontName=FONT_REGULAR, fontSize=9.5, textColor=DIM,
        alignment=TA_CENTER, spaceAfter=2, leading=13)
    tricap_style = ParagraphStyle("TriCap", parent=styles["Normal"],
        fontName=FONT_REGULAR, fontSize=7.5, textColor=DIM, leading=10)
    label_style = ParagraphStyle("Label", parent=styles["Normal"],
        fontName=FONT_REGULAR, fontSize=7.5, textColor=DIM, leading=10)
    value_style = ParagraphStyle("Value", parent=styles["Normal"],
        fontName=FONT_BOLD, fontSize=12, textColor=INK, leading=15)
    winner_name_style = ParagraphStyle("WinnerName", parent=styles["Normal"],
        fontName=FONT_BOLD, fontSize=25, leading=32, textColor=GOLD_DARK,
        alignment=TA_CENTER, spaceAfter=8)
    footer_style = ParagraphStyle("Footer", parent=styles["Normal"],
        fontName=FONT_REGULAR, fontSize=7, textColor=DIM, leading=10)
    mono_style = ParagraphStyle("Mono", parent=styles["Normal"],
        fontName=FONT_MONO, fontSize=8, textColor=INK, leading=11)

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
    story.append(Paragraph("DRAW CERTIFICATE &nbsp;·&nbsp; გათამაშების სერტიფიკატი", subtitle_style))
    story.append(Paragraph(casino_name, subtitle_style))
    story.append(Spacer(1, 12))
    story.append(HRFlowable(width="100%", thickness=1.2, color=LINE, spaceAfter=20))

    # ── ÇEKİLİŞ BİLGİSİ ─────────────────────────────────────────────────────
    tier_tr, tier_en, tier_ka = TIER_LABEL.get(draw_tier, (draw_tier.upper(), draw_tier.upper(), draw_tier.upper()))

    info_table = Table([
        [Paragraph(_tri("draw_name"), label_style), Paragraph(draw_name, value_style)],
        [Paragraph(_tri("draw_type"), label_style), Paragraph(f"{tier_tr} / {tier_en} / {tier_ka}", value_style)],
        [Paragraph(_tri("prize"), label_style), Paragraph(prize_description, value_style)],
        [Paragraph(_tri("datetime"), label_style), Paragraph(
            executed_at.strftime("%d.%m.%Y &nbsp;·&nbsp; %H:%M"), value_style)],
    ], colWidths=[52*mm, 103*mm])
    info_table.setStyle(TableStyle([
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("BOTTOMPADDING", (0,0), (-1,-1), 10),
        ("TOPPADDING", (0,0), (-1,-1), 2),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 8))
    story.append(HRFlowable(width="100%", thickness=.5, color=DIM, spaceAfter=22))

    # ── KAZANAN ─────────────────────────────────────────────────────────────
    story.append(Paragraph(_tri("winner"), ParagraphStyle(
        "WinnerLabel", parent=tricap_style, alignment=TA_CENTER,
        fontSize=8.5, textColor=GOLD_DARK, spaceAfter=10)))
    story.append(Paragraph(winner_name, winner_name_style))
    story.append(Spacer(1, 10))

    label_center_style = ParagraphStyle("LabelCenter", parent=label_style, alignment=TA_CENTER)
    value_center_style = ParagraphStyle("ValueCenter", parent=value_style, alignment=TA_CENTER, fontSize=11)
    winner_id_table = Table([
        [Paragraph(_tri("card_no"), label_center_style), Paragraph(_tri("winning_ticket"), label_center_style)],
        [Paragraph(winner_card_id, value_center_style), Paragraph(winning_ticket, value_center_style)],
    ], colWidths=[77.5*mm, 77.5*mm])
    winner_id_table.setStyle(TableStyle([
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("TOPPADDING", (0,1), (-1,1), 4),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
    ]))
    story.append(winner_id_table)
    story.append(Spacer(1, 18))
    story.append(HRFlowable(width="100%", thickness=.5, color=DIM, spaceAfter=20))

    # ── ŞEFFAFLIK / HAVUZ İSTATİSTİKLERİ ──────────────────────────────────────
    story.append(Paragraph(_tri("pool_transparency"),
        ParagraphStyle("SectionLabel", parent=tricap_style, fontSize=7.5,
                       textColor=GOLD_DARK, spaceAfter=10)))

    pool_table = Table([
        [Paragraph(_tri("total_pool_tickets"), label_style),
         Paragraph(_tri("total_pool_players"), label_style),
         Paragraph(_tri("rng_method"), label_style)],
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
    # Bilgi amaçlı kayıt — vergi beyanı bu sistemde çekilişin yürütülmesi için
    # zorunlu değildir (bkz. draw_engine.execute_draw); Casino'nun kendi iç
    # muhasebe/hukuki sürecinin belgesidir, girildiyse sertifikaya eklenir.
    if tax_declaration_ref:
        story.append(Paragraph(_tri("tax_section") + " (RS.GE)",
            ParagraphStyle("TaxLabel", parent=tricap_style, fontSize=7.5,
                           textColor=GOLD_DARK, spaceAfter=10)))
        tax_table = Table([
            [Paragraph(_tri("tax_ref"), label_style),
             Paragraph(_tri("tax_paid"), label_style),
             Paragraph(_tri("tax_date"), label_style)],
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
        story.append(Paragraph(
            "This prize was declared to the Georgian Revenue Service (RS.GE) "
            "and its tax paid prior to distribution, per Casino procedure.",
            ParagraphStyle("TaxNoteEn", parent=footer_style, fontSize=7.5)))
        story.append(Paragraph(
            "ეს პრიზი გაცემამდე სათანადოდ იქნა დეკლარირებული საქართველოს "
            "შემოსავლების სამსახურში (RS.GE) და გადასახადი გადახდილია.",
            ParagraphStyle("TaxNoteKa", parent=footer_style, fontSize=7.5)))
        story.append(Spacer(1, 20))
        story.append(HRFlowable(width="100%", thickness=.5, color=DIM, spaceAfter=20))

    # ── DOĞRULAMA ───────────────────────────────────────────────────────────
    story.append(Paragraph(_tri("verification"),
        ParagraphStyle("SectionLabel2", parent=tricap_style, fontSize=7.5,
                       textColor=GOLD_DARK, spaceAfter=8)))
    story.append(Paragraph(cert_hash, mono_style))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        f"{_tri('cert_no', sep='/')}: {cert_no}",
        ParagraphStyle("CertNo", parent=label_style, fontSize=7.5)))
    story.append(Spacer(1, 30))

    # ── İMZA ALANI ──────────────────────────────────────────────────────────
    sig_table = Table([
        ["_" * 32, "_" * 32],
        [Paragraph(_tri("sig_operator", sep=" / "), footer_style),
         Paragraph(_tri("sig_date", sep=" / "), footer_style)],
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
    story.append(Paragraph(
        "ეს სერტიფიკატი ავტომატურად გენერირებულია NovaGuard Promo Engine-ის მიერ. "
        "დამოწმების კოდი გამომდინარეობს გათამაშების ID-დან, გამარჯვებულიდან, "
        "გამარჯვებული ბილეთის ნომრიდან და პულის საერთო ზომიდან — ნებისმიერი "
        "ცვლილება გააუქმებს კოდს.",
        footer_style))

    doc.build(story)
    pdf_bytes = buf.getvalue()
    buf.close()

    if output_path:
        with open(output_path, "wb") as f:
            f.write(pdf_bytes)

    return pdf_bytes
