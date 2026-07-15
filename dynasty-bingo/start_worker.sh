#!/bin/bash
# ============================================================
# DYNASTY BINGO — Otomatik Çekiliş Robotunu Başlat (Linux / Mac)
# Terminalde: chmod +x start_worker.sh && ./start_worker.sh
# ============================================================

export DYNASTY_MASTER_SECRET="BURAYA-KENDI-GIZLI-SIFRENIZI-YAZIN"
export DYNASTY_LICENSE_KEY="BURAYA-generate_license.py-CIKTISINI-YAZIN"
export DYNASTY_INTERNAL_KEY="BURAYA-UZUN-RASTGELE-ADMIN-ANAHTARI-YAZIN"

echo ""
echo "Otomatik çekiliş robotu başlatılıyor... (Bu terminali kapatmayın)"
echo ""

python3 worker.py
