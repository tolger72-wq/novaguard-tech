"""
generate_license.py — SADECE SİZİN İÇİN (satıcı için), MÜŞTERİYE GÖNDERİLMEZ.

Bu script'i kendi bilgisayarınızda çalıştırıp, her müşteri (casino) için
özel bir lisans anahtarı üretirsiniz. Ürettiğiniz anahtarı müşteriye
verirsiniz, o da bunu DYNASTY_LICENSE_KEY ortam değişkenine koyar.

KULLANIM (terminalde):
    python generate_license.py casino_batumi 2026-12-31

Bu, 31 Aralık 2026'ya kadar geçerli, "casino_batumi" için özel bir
anahtar üretir. Başka hiçbir casino bu anahtarı kullanamaz (tenant_id
anahtarın içine gömülü ve imzayla korunuyor).

ÖNEMLİ: DYNASTY_MASTER_SECRET ortam değişkeni burada ve app.py'nin
çalıştığı sunucuda AYNI olmalı. Bu şifreyi kimseyle paylaşmayın.
"""

import sys
from datetime import datetime

from royal_math import generate_license_key


def main():
    if len(sys.argv) != 3:
        print("Kullanım: python generate_license.py <tenant_id> <YYYY-MM-DD>")
        print("Örnek:   python generate_license.py casino_batumi 2026-12-31")
        sys.exit(1)

    tenant_id = sys.argv[1]
    try:
        expiry_date = datetime.strptime(sys.argv[2], "%Y-%m-%d").date()
    except ValueError:
        print("Tarih formatı yanlış. YYYY-MM-DD şeklinde yazın, örn: 2026-12-31")
        sys.exit(1)

    key = generate_license_key(tenant_id, expiry_date)
    print()
    print(f"Casino:          {tenant_id}")
    print(f"Son kullanma:    {expiry_date}")
    print(f"LİSANS ANAHTARI: {key}")
    print()
    print("Müşteriye bu anahtarı verin, o da şu şekilde kullansın:")
    print(f'  export DYNASTY_LICENSE_KEY="{key}"')


if __name__ == "__main__":
    main()
