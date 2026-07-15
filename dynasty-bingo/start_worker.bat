@echo off
REM ============================================================
REM  DYNASTY BINGO — Otomatik Çekiliş Robotunu Başlat (Windows)
REM  Bu, arka planda çalışıp zamanı geldiğinde otomatik top çeker.
REM  start_sunucu.bat'ı kapatmadan, AYRI bir pencerede bunu da açık tutun.
REM ============================================================

set DYNASTY_MASTER_SECRET=BURAYA-KENDI-GIZLI-SIFRENIZI-YAZIN
set DYNASTY_LICENSE_KEY=BURAYA-generate_license.py-CIKTISINI-YAZIN
set DYNASTY_INTERNAL_KEY=BURAYA-UZUN-RASTGELE-ADMIN-ANAHTARI-YAZIN

echo.
echo Otomatik cekilis robotu baslatiliyor... (Bu pencereyi kapatmayin)
echo.

python worker.py

pause
