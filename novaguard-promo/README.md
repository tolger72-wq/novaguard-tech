# NovaGuard Promo Engine

Casino promosyon çekiliş sistemi. **CRM bağımsız, platform bağımsız.**

---

## Temel Felsefe

Biz sadece üç şey istiyoruz:

| Veri | Neden |
|------|-------|
| Kart numarası | Oyuncuyu tanımlamak için |
| Oturum süresi | Kaç bilet kazanacağını hesaplamak için |
| Ciro miktarı | Kaç bilet kazanacağını hesaplamak için |

**Görmek istemediklerimiz:** Oyuncu adı, kayıp/kazanç, kişisel bilgi, bakiye.

Nexio, Caleo, CasinoAssist veya kendi yazılımınız — fark etmez. Casino
sistemi ne kullanıyorsa, oturum başında ve bitişinde iki HTTP isteği atar. Hepsi bu.

---

## Hızlı Başlangıç

```bash
cp .env.example .env
./quickstart.sh
```

API     → http://localhost:8000
Docs    → http://localhost:8000/docs
Admin   → admin.html dosyasını tarayıcıda aç

---

## Casino Entegrasyonu — 2 Endpoint

### 1. Oturum Başladı
```http
POST /api/v1/sessions/push
X-CRM-Key: {crm_api_key}

{
  "external_session_id": "casino-kendi-id-001",
  "card_id": "KRT-001",
  "game_type": "live",
  "started_at": "2025-06-14T20:00:00Z",
  "turnover_amount": 0,
  "currency": "GEL"
}
```

### 2. Oturum Bitti (biletler burada hesaplanır)
```http
PATCH /api/v1/sessions/by-external/casino-kendi-id-001/end
X-CRM-Key: {crm_api_key}

{
  "ended_at": "2025-06-14T22:30:00Z",
  "final_turnover_amount": 3500.00
}
```

Cevap: `{ "tickets_earned": 7 }` → 7 benzersiz bilet karta yüklendi.

Hazır entegrasyon örneği: `scripts/casino_sync_example.py`

---

## Bilet Kazanım Formülü

Admin panelinden ayarlanır. Örnek (varsayılan):

| Parametre | Değer | Açıklama |
|-----------|-------|----------|
| Live — Saatte Bilet | 1.0 | 1 saat live = 1 bilet |
| Live — Ciro / Bilet | 500 | 500 GEL ciro = 1 bilet |
| Slot — Saatte Bilet | 0.5 | 2 saat slot = 1 bilet |
| Slot — Ciro / Bilet | 1000 | 1000 GEL ciro = 1 bilet |
| Günlük Maksimum | 10 | Oyuncu günde en fazla 10 bilet |

---

## Çekiliş Seviyeleri ve Dışlama Kuralı

```
Günlük  → Haftalık  → Aylık  → 3 Aylık  → Yıllık Final (13 Ocak)
```

**Kural:** Bir seviyeden ödül kazanan, o dönem için diğer ödüllerden çıkar.
Aylık / 3 aylık / final hakları ayrı dönemlere aittir — etkilenmez.
**Final her zaman herkese açık.**

---

## Vergi Beyanı (RS.GE — Gürcistan)

RS.GE'ye vergi beyanı Casino'nun kendi iç muhasebe/hukuki prosedürüdür — NovaGuard bu süreci
yürütmez veya zorunlu kılmaz. Sistem yalnızca kayıt tutma (record-keeping) amacıyla, isteğe
bağlı olarak beyan bilgisini saklar ve sertifikada gösterir:

```http
PATCH /api/v1/draws/{id}/tax-declaration
X-Admin-Key: {admin_key}

{
  "tax_declaration_ref": "RS-GE-2025-0614-3391",
  "tax_amount_paid": 980.00,
  "declared_by": "Muhasebe Yetkilisi"
}
```

Bu bilgi girilmese de çekiliş normal şekilde yürütülür. Vergi uyumluluğunun takibi
Casino'nun sorumluluğundadır.

---

## Çekiliş Sertifikası (PDF)

```
GET /api/v1/draws/{id}/certificate
```

Her tamamlanmış çekiliş için otomatik üretilir. İçerik:
- Kazanan + bilet numarası
- Havuz şeffaflığı (toplam bilet, oyuncu sayısı)
- RS.GE vergi beyan numarası
- SHA-256 doğrulama hash'i
- İmza alanı

---

## API Anahtarları

```
ADMIN_API_KEY  →  X-Admin-Key header   (çekiliş yönetimi, admin panel)
CRM_API_KEY    →  X-CRM-Key header     (casino sistemi veri push'u)
```

.env.example dosyasını kopyalayıp değerleri değiştirin.

---

## Servisler

| Servis | Teknoloji | Görev |
|--------|-----------|-------|
| API | FastAPI + Python | İş mantığı, endpointler |
| Veritabanı | PostgreSQL | Kalıcı veri |
| Cache/Queue | Redis | Celery kuyruk |
| Worker | Celery | Zamanlanmış çekilişler |

```bash
docker compose up -d      # başlat
docker compose down       # durdur
docker compose logs api   # loglar
```
