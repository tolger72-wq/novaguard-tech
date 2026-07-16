#!/bin/bash
# ============================================================
# DYNASTY BINGO — Sunucuyu Başlat (Linux / Mac)
# Terminalde: chmod +x start_sunucu.sh && ./start_sunucu.sh
# ============================================================

export DYNASTY_MASTER_SECRET="BURAYA-KENDI-GIZLI-SIFRENIZI-YAZIN"
export DYNASTY_LICENSE_KEY="BURAYA-generate_license.py-CIKTISINI-YAZIN"
export DYNASTY_INTERNAL_KEY="BURAYA-UZUN-RASTGELE-ADMIN-ANAHTARI-YAZIN"

# Gerçek SMS göndermek için (Twilio hesabı açtıktan sonra) aşağıdaki 3 satırı
# doldurup başındaki "# " kısmını silin. Doldurmazsanız SMS sadece ekrana yazılır.
# export TWILIO_ACCOUNT_SID="..."
# export TWILIO_AUTH_TOKEN="..."
# export TWILIO_FROM_NUMBER="+1..."

echo ""
echo "Dynasty Bingo sunucusu başlatılıyor..."
echo "Bu bilgisayarın ağ adresini öğrenmek için: ip addr (Linux) veya ifconfig (Mac)"
echo "Müşteriler http://BU-BILGISAYARIN-IP-ADRESI:8000/view/KART_NO adresinden kartlarını görebilir."
echo ""

# --host 0.0.0.0 ÖNEMLİ: aynı WiFi'daki telefonların erişebilmesi için gerekli.
python3 -m uvicorn app:app --host 0.0.0.0 --port 8000
