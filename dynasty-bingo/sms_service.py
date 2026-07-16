"""
sms_service.py — SMS gönderme servisi.

Bu dosya, misafire kart linkini SMS ile göndermek için kullanılır.

Gerçek SMS göndermek için Twilio (dünyada en yaygın kullanılan SMS servisi)
hesabı açman gerekir: https://www.twilio.com — hesap açınca 3 bilgi verir:
  1. Account SID
  2. Auth Token
  3. Senin adına SMS gönderecek bir telefon numarası

Bu 3 bilgiyi ortam değişkeni olarak ayarlarsın (aşağıda), bu dosya otomatik kullanır.

🧪 SANDBOX MODU: Henüz Twilio hesabın yoksa (test/deneme aşamasındaysan),
sistem SMS'i GERÇEKTEN göndermez — sadece sunucu ekranına yazdırır. Böylece
kodun geri kalanını test edebilirsin, gerçek SMS istediğinde sadece ortam
değişkenlerini eklemen yeterli, kodda hiçbir değişiklik gerekmez.
"""

import os

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_FROM_NUMBER = os.getenv("TWILIO_FROM_NUMBER")


def send_sms(to_number: str, message: str) -> bool:
    """
    Verilen telefon numarasına SMS gönderir.

    to_number: Alıcının telefon numarası, ülke koduyla, örn. "+905551234567"
    message: Gönderilecek metin

    Dönüş değeri: True (başarılı veya sandbox modu) / False (gerçek hata oluştu)
    """
    # 1. Twilio bilgileri ayarlanmamışsa -> SANDBOX MODU (sadece ekrana yazdır)
    if not (TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_FROM_NUMBER):
        print("=" * 60)
        print(f"[SANDBOX SMS] Alıcı: {to_number}")
        print(f"[SANDBOX SMS] Mesaj: {message}")
        print("NOT: Bu gerçek bir SMS DEĞİL. Gerçek SMS göndermek için şu ortam")
        print("değişkenlerini ayarla: TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER")
        print("=" * 60)
        return True

    # 2. Twilio bilgileri varsa -> GERÇEK SMS gönder
    try:
        from twilio.rest import Client  # Bu satır, sadece gerçekten göndermek gerektiğinde çalışır
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        client.messages.create(body=message, from_=TWILIO_FROM_NUMBER, to=to_number)
        print(f"SMS gönderildi: {to_number}")
        return True
    except Exception as e:
        print(f"SMS GÖNDERME HATASI: {e}")
        return False
