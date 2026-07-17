#!/usr/bin/env python3
"""
NovaGuard — Offline Yükleme ve Başlatma Scripti
===================================================

NE İŞE YARAR?
  USB'den kopyaladığın "docker-images" klasöründeki hazır parçaları
  bu bilgisayara yükler ve sistemi başlatır.

  İNTERNET GEREKMEZ — çünkü her şey zaten USB'de hazır geldi.

NASIL ÇALIŞTIRILIR?
  1. USB'den tüm "novaguard-promo" klasörünü bilgisayara kopyala
     (masaüstüne veya istediğin bir yere)
  2. O klasörün içinde bir terminal aç
  3. Şunu yaz ve Enter'a bas:

       python3 load_offline_images.py

GEREKSİNİM:
  - Bu bilgisayarda Docker kurulu olmalı (Docker Desktop)
  - "docker-images" klasörü, bu scriptle aynı yerde olmalı
"""

import subprocess
import sys
import os

IMAGES_FOLDER = "docker-images"


def run_command(command_list):
    """Bir terminal komutunu çalıştırır, sonucu ekrana yazar."""
    print(f"\n→ Çalıştırılıyor: {' '.join(command_list)}")
    result = subprocess.run(command_list, capture_output=False)
    return result.returncode == 0


def check_docker_installed():
    """Docker'ın bu bilgisayarda kurulu olup olmadığını kontrol eder."""
    try:
        subprocess.run(["docker", "--version"], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def main():
    print("=" * 60)
    print("  NOVAGUARD — OFFLINE YÜKLEME")
    print("=" * 60)

    # ADIM 1: Docker kurulu mu?
    if not check_docker_installed():
        print("\n✗ Bu bilgisayarda Docker kurulu değil!")
        print("  Docker Desktop'ı kurman gerekiyor: https://docker.com/products/docker-desktop")
        print("  (Bu kurulum için internet lazım, ama kurulumdan SONRA")
        print("   NovaGuard'ın kendisi internet olmadan çalışacak.)")
        sys.exit(1)

    print("\n✓ Docker bulundu")

    # ADIM 2: docker-images klasörü var mı?
    if not os.path.exists(IMAGES_FOLDER):
        print(f"\n✗ '{IMAGES_FOLDER}' klasörü bulunamadı!")
        print("  USB'deki tüm 'novaguard-promo' klasörünü eksiksiz kopyaladığından emin ol.")
        sys.exit(1)

    # ADIM 3: Klasördeki her .tar dosyasını Docker'a yükle
    tar_files = [f for f in os.listdir(IMAGES_FOLDER) if f.endswith(".tar")]

    if not tar_files:
        print(f"\n✗ '{IMAGES_FOLDER}' klasöründe hiç .tar dosyası yok!")
        sys.exit(1)

    print(f"\n{len(tar_files)} adet paket bulundu, yükleniyor...")

    for tar_file in tar_files:
        tar_path = os.path.join(IMAGES_FOLDER, tar_file)
        print(f"\n→ Yükleniyor: {tar_file}")
        success = run_command(["docker", "load", "-i", tar_path])
        if success:
            print(f"  ✓ Tamamlandı")
        else:
            print(f"  ✗ Bu dosya yüklenemedi: {tar_file}")

    # ADIM 4: .env dosyası yoksa örnekten oluştur
    if not os.path.exists(".env"):
        if os.path.exists(".env.example"):
            with open(".env.example", "r", encoding="utf-8") as src:
                content = src.read()
            with open(".env", "w", encoding="utf-8") as dst:
                dst.write(content)
            print("\n✓ .env dosyası oluşturuldu (.env.example'dan kopyalandı)")
        else:
            print("\n⚠ .env dosyası yok ve .env.example de bulunamadı.")
            print("  Sistemi başlatmadan önce .env dosyasını elle oluşturman gerekebilir.")

    # ADIM 5: Sistemi başlat — artık internet gerekmez, her şey local'de hazır
    print("\n" + "=" * 60)
    print("  SİSTEM BAŞLATILIYOR")
    print("=" * 60)

    success = run_command(["docker", "compose", "up", "-d"])

    if success:
        print("""

✓ HAZIR! Sistem çalışıyor.

  API           → http://localhost:8000
  API Docs      → http://localhost:8000/docs
  Admin Panel   → admin.html dosyasını tarayıcıda aç
  Büyük Ekran   → display/display.html dosyasını aç

  Durdurmak için: docker compose down
""")
    else:
        print("\n✗ Sistem başlatılamadı. Yukarıdaki hata mesajlarına bak.")


if __name__ == "__main__":
    main()
