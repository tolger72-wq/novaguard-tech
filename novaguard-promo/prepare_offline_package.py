#!/usr/bin/env python3
"""
NovaGuard — Offline Paket Hazırlama Scripti
==============================================

NE İŞE YARAR?
  Bu scripti SADECE BİR KERE, internetli bir bilgisayarda çalıştırırsın.
  Docker'ın ihtiyaç duyduğu tüm parçaları (image denir) indirir ve
  "docker-images" klasörüne .tar dosyaları olarak kaydeder.

  Bu klasör USB'ye kopyalandıktan sonra, artık İNTERNET OLMADAN
  herhangi bir bilgisayarda (Docker kuruluysa) tüm sistem çalışabilir.

NASIL ÇALIŞTIRILIR?
  1. Bu dosyanın olduğu klasörde bir terminal aç
  2. Şunu yaz ve Enter'a bas:

       python3 prepare_offline_package.py

  3. Birkaç dakika sürer (indirme boyutuna göre değişir, ~500 MB - 1 GB)
  4. Bittiğinde "docker-images" adında bir klasör oluşur
  5. O klasörü ve tüm proje klasörünü USB'ye kopyala

GEREKSİNİM:
  - Bu bilgisayarda Docker kurulu ve internet olmalı (sadece bu adım için)
  - Python 3 kurulu olmalı (çoğu bilgisayarda zaten var)
"""

import subprocess
import sys
import os

# Projede kullanılan Docker image'ları — docker-compose.yml dosyasından alındı.
# Bunlar internetten indirilecek "hazır paketler" gibi düşünülebilir.
IMAGES_TO_DOWNLOAD = [
    "postgres:16-alpine",   # Veritabanı
    "redis:7-alpine",       # Ön bellek / kuyruk sistemi
    "python:3.11-slim",     # NovaGuard'ın kendi kodu bunun üzerine kurulu
]

# İndirilen image'ların kaydedileceği klasör
OUTPUT_FOLDER = "docker-images"


def run_command(command_list):
    """
    Bir terminal komutunu çalıştırır ve sonucunu ekrana yazar.
    command_list bir liste olmalı, örnek: ["docker", "pull", "redis:7-alpine"]
    """
    print(f"\n→ Çalıştırılıyor: {' '.join(command_list)}")
    result = subprocess.run(command_list, capture_output=False)
    if result.returncode != 0:
        print(f"✗ HATA: Komut başarısız oldu: {' '.join(command_list)}")
        return False
    return True


def check_docker_installed():
    """Docker'ın bu bilgisayarda kurulu olup olmadığını kontrol eder."""
    try:
        subprocess.run(["docker", "--version"], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def main():
    print("=" * 60)
    print("  NOVAGUARD — OFFLINE PAKET HAZIRLAMA")
    print("=" * 60)

    # ADIM 1: Docker kurulu mu kontrol et
    if not check_docker_installed():
        print("\n✗ Docker bulunamadı!")
        print("  Önce Docker Desktop kurmalısın: https://docker.com/products/docker-desktop")
        sys.exit(1)

    print("\n✓ Docker bulundu, devam ediliyor...")

    # ADIM 2: Çıktı klasörünü oluştur
    if not os.path.exists(OUTPUT_FOLDER):
        os.makedirs(OUTPUT_FOLDER)
        print(f"✓ '{OUTPUT_FOLDER}' klasörü oluşturuldu")

    # ADIM 3: NovaGuard'ın kendi imajını inşa et (build)
    print("\n--- NovaGuard uygulaması derleniyor ---")
    if not run_command(["docker", "compose", "build"]):
        print("✗ Derleme başarısız. .env dosyasının var olduğundan emin ol.")
        sys.exit(1)

    # ADIM 4: Her image'ı internetten indir (varsa zaten indirilmişse atlar)
    print("\n--- Gerekli parçalar indiriliyor ---")
    for image in IMAGES_TO_DOWNLOAD:
        run_command(["docker", "pull", image])

    # ADIM 5: Tüm image'ları .tar dosyaları olarak diske kaydet
    print("\n--- İndirilenler USB için paketleniyor ---")

    # Önce docker-compose ile inşa edilen kendi uygulama imajımızı kaydet.
    # 'docker compose images' ile hangi isimle kaydedildiğini buluyoruz.
    result = subprocess.run(
        ["docker", "images", "--format", "{{.Repository}}:{{.Tag}}"],
        capture_output=True, text=True
    )
    all_local_images = result.stdout.strip().split("\n")

    # NovaGuard'ın kendi image'ını bul (genelde klasör adıyla başlar, örn: novaguard-promo-api)
    novaguard_images = [img for img in all_local_images if "novaguard" in img.lower()]

    images_to_save = IMAGES_TO_DOWNLOAD + novaguard_images

    for image in images_to_save:
        # Dosya adında ":" karakteri olamaz, "_" ile değiştiriyoruz
        safe_filename = image.replace(":", "_").replace("/", "_") + ".tar"
        output_path = os.path.join(OUTPUT_FOLDER, safe_filename)

        print(f"\n→ Kaydediliyor: {image} → {output_path}")
        success = run_command(["docker", "save", "-o", output_path, image])
        if success:
            size_mb = os.path.getsize(output_path) / (1024 * 1024)
            print(f"  ✓ Tamamlandı ({size_mb:.0f} MB)")

    print("\n" + "=" * 60)
    print("  HAZIR!")
    print("=" * 60)
    print(f"""
'{OUTPUT_FOLDER}' klasörü artık USB'ye kopyalanmaya hazır.

ŞİMDİ NE YAPMALISIN:
  1. Tüm 'novaguard-promo' klasörünü (bu '{OUTPUT_FOLDER}' klasörü dahil) USB'ye kopyala
  2. USB'yi hedef bilgisayara (casino sunucusu) tak
  3. Orada 'load_offline_images.py' scriptini çalıştır
     (bu script otomatik olarak sistemi ayağa kaldırır — internet gerekmez)
""")


if __name__ == "__main__":
    main()
