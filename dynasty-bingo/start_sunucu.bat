@echo off
REM ============================================================
REM  DYNASTY BINGO — Sunucuyu Başlat (Windows)
REM  Bu dosyaya çift tıklayınca sunucu çalışmaya başlar.
REM  Kapatmak için bu pencereyi kapatman yeterli.
REM ============================================================

REM 🔑 Buraya kendi gizli anahtarlarınızı yazın (tırnak içinde, boşluk bırakmadan)
set DYNASTY_MASTER_SECRET=BURAYA-KENDI-GIZLI-SIFRENIZI-YAZIN
set DYNASTY_LICENSE_KEY=BURAYA-generate_license.py-CIKTISINI-YAZIN
set DYNASTY_INTERNAL_KEY=BURAYA-UZUN-RASTGELE-ADMIN-ANAHTARI-YAZIN

REM Gercek SMS gondermek icin (Twilio hesabi actiktan sonra) asagidaki 3 satiri
REM doldurup basindaki "REM " kismini silin. Doldurmazsaniz SMS sadece ekrana yazilir.
REM set TWILIO_ACCOUNT_SID=...
REM set TWILIO_AUTH_TOKEN=...
REM set TWILIO_FROM_NUMBER=+1...

echo.
echo Dynasty Bingo sunucusu baslatiliyor...
echo Bu bilgisayarin ag adresini ogrenmek icin ayri bir pencerede "ipconfig" yazabilirsiniz.
echo Musteriler telefonlarindan http://BU-BILGISAYARIN-IP-ADRESI:8000/view/KART_NO adresine giderek kartlarini gorebilir.
echo.

REM --host 0.0.0.0 ONEMLI: bu, ayni WiFi'daki telefonlarin sunucuya erisebilmesini saglar.
python -m uvicorn app:app --host 0.0.0.0 --port 8000

pause
