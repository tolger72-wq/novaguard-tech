#!/usr/bin/env bash
# ════════════════════════════════════════════════════════════════════════════
# NovaGuard Promo Engine — Tek Komutla Demo
# Casino sahibine 5 dakikada tam sistemi gösterir. IT gerekmez.
# ════════════════════════════════════════════════════════════════════════════
set -e

echo "╔══════════════════════════════════════════╗"
echo "║   NOVAGUARD PROMO ENGINE — HIZLI BAŞLAT   ║"
echo "╚══════════════════════════════════════════╝"
echo ""

if [ ! -f .env ]; then
  cp .env.example .env
  echo "✓ .env oluşturuldu"
fi

echo "→ Servisler başlatılıyor (ilk seferde ~2 dk sürebilir)..."
docker compose up -d --build

echo "→ Veritabanı bekleniyor..."
until docker compose exec -T db pg_isready -U promo > /dev/null 2>&1; do
  sleep 1
done
echo "✓ Veritabanı hazır"

echo "→ API bekleniyor..."
until curl -sf http://localhost:8000/health > /dev/null 2>&1; do
  sleep 1
done
echo "✓ API hazır"

echo "→ Demo oyuncular ve çekilişler yükleniyor..."
python3 scripts/seed_demo.py

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║              SİSTEM HAZIR ✓               ║"
echo "╚══════════════════════════════════════════╝"
echo ""
echo "  Admin Panel  →  admin.html dosyasını çift tıkla"
echo "  API Docs     →  http://localhost:8000/docs"
echo "  Admin Key    →  casino-admin-key-change-me"
echo ""
echo "  Durdurmak için: docker compose down"
echo ""

if command -v open &> /dev/null; then
  open admin.html
elif command -v xdg-open &> /dev/null; then
  xdg-open admin.html
fi
