# Display Screen (CasinoCampaign.jsx)

Bu klasör, casino büyük ekranı için React display uygulamasını içerir.

## Kurulum

```bash
# Vite ile yeni proje oluştur
npm create vite@latest casino-display -- --template react
cd casino-display
npm install
# CasinoCampaign.jsx dosyasını src/ klasörüne kopyala
# App.jsx içinde import et
npm run dev
```

## Backend Bağlantısı

Operatör panelini aç → "Canlı API" modunu seç → API adresini ve Admin Key'i gir → BAĞLAN.

Bağlantı kurulduktan sonra:
- Oyuncular `/api/v1/display/leaderboard` den gelir
- Bilet ağırlıkları gerçek veriden hesaplanır
- Çekiliş yürütme backend'e `/api/v1/draws/{id}/execute` isteği gönderir
- Otomatik 15 saniyede bir güncelleme
