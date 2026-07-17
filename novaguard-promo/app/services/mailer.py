"""
NovaGuard E-Posta Servisi
============================
Çekiliş sertifikasını (PDF) misafire doğrudan e-posta ile gönderir —
duvara asmak veya elden vermek yerine, uluslararası/uzaktaki misafirlere
de büyük ödül deklarasyonunu ulaştırmanın bir yolu.

Standart kütüphane (smtplib) kullanılır — yeni bir bağımlılık eklemez,
herhangi bir SMTP sağlayıcısıyla (kurumsal mail sunucusu, Gmail SMTP,
SendGrid/Mailgun SMTP arayüzü vb.) çalışır. Ayarlar .env dosyasındadır
(bkz. .env.example → SMTP_*).
"""
import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from ..core.config import settings


class MailerNotConfigured(RuntimeError):
    """SMTP ayarları .env dosyasında girilmemiş."""


def send_certificate_email(
    *,
    to_email: str,
    subject: str,
    body_text: str,
    pdf_bytes: bytes,
    attachment_filename: str,
) -> None:
    """
    Senkron (bloklayan) SMTP gönderimi — çağıran taraf async bir endpoint'teyse
    starlette.concurrency.run_in_threadpool ile thread'e alınmalı (bkz.
    app/routers/draws.py: email_draw_certificate).
    """
    if not settings.SMTP_HOST:
        raise MailerNotConfigured(
            "SMTP yapılandırılmamış — .env dosyasında SMTP_HOST, SMTP_USER, "
            "SMTP_PASSWORD ayarlarını girin (bkz. .env.example)."
        )

    msg = MIMEMultipart()
    msg["From"] = settings.SMTP_FROM or settings.SMTP_USER
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body_text, "plain", "utf-8"))

    part = MIMEApplication(pdf_bytes, _subtype="pdf")
    part.add_header("Content-Disposition", "attachment", filename=attachment_filename)
    msg.attach(part)

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20) as server:
        if settings.SMTP_USE_TLS:
            server.starttls()
        if settings.SMTP_USER:
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD or "")
        server.send_message(msg)
