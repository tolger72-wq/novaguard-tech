# Nova IQ (Nans_Core)

Merkezi karar/otomasyon + lisans/süre/ödeme takip servisi. `dynasty-bingo`,
`novaguard-promo` ve `casino_ops.py` gibi ürünlerin ortak arka planı olarak
tasarlanmıştır — her ürün kendi `product_id`'siyle kayıt olur, kendi API
anahtarıyla lisanslarını (süre, cihaz sayısı, ödeme geçmişi) buradan yönetir.

## Kurulum

```bash
pip install -r requirements.txt
python main.py
```

`NANS_MASTER_KEY` ortam değişkenini prodüksiyonda mutlaka ayarlayın —
ayarlanmazsa `nans_data/_master_key.txt` içinde kalıcı bir geçici anahtar
otomatik üretilir (restart'ta sıfırlanmaz, ama tercih edilen yol değildir).

## Test

```bash
pip install pytest
pytest tests/ -v
```

## Kod incelemesi sırasında düzeltilenler

- **Lisans taraması artık tek bozuk kayıtla çökmüyor** — `expires_at`/
  `new_expires_at` artık `datetime` tipiyle API sınırında doğrulanıyor
  (bkz. `LicenseCreateRequest`, `LicenseRenewRequest`), ayrıca
  `sweep_expiries()` ve `_daily_license_sweep()` her lisansı/ürünü ayrı
  try/except içinde işliyor — biri bozuksa diğerleri etkilenmiyor.
- **Cihaz takibi artık "şu an aktif" ölçüyor, "bugüne dek görülen tümü" değil**
  (`License.active_device_ids`, 30 günlük pencere) — normal cihaz değişimi
  (yeni bilgisayar, format) artık sadık bir müşteriyi kalıcı olarak
  otomatik askıya almıyor. Anında düzeltme için `DELETE
  /v1/{product_id}/licenses/{license_key}/devices/{device_id}` eklendi.
- **API anahtarı karşılaştırmaları artık sabit zamanlı** (`secrets.compare_digest`)
  — timing attack'e karşı.
- **`NANS_MASTER_KEY` ayarlanmamışsa artık her restart'ta rastgele değişmiyor**
  — diskte kalıcı olarak saklanıyor, çökme sonrası admin kilitlenmiyor.
- **Veri dosyaları artık atomik yazılıyor** (geçici dosya + rename) — yazma
  sırasında çökme, o ürünün tüm lisans/ödeme geçmişini bozmuyor.
- **`/renew` artık tutar bildirmeden geçmiyor** (`amount` zorunlu) — ödeme
  tahsilatı bu serviste yapılmaz (çağıran taraf doğrular), ama en azından
  denetim/mutabakat kaydı boş kalmıyor.
