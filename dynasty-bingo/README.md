# Dynasty Bingo — Tek Casino Sürümü

Bu, çoklu casino (multi-tenant) sürümünün basitleştirilmiş hali. Tek bir casino için
çalışacak şekilde düzenlendi — URL'lerde `tenant_id` yok, tüm veri zaten tek casino'ya ait.

**Kural: Oyuncu başına en fazla 1 kart.** `/cards` ve `/reception/register`, aynı
`owner_id`/isim için bu hafta zaten bir kart varsa 409 hatası döner.

🧪 **Simülasyon modu:** Bir oyuncu için gerçek sadakat puanı (bkz. aşağıdaki
"Gerçek Sadakat Verisi" bölümü) push/upload edilmediyse, `integrations.py` içindeki
`CasinoSystem` sınıfı o oyuncu için uydurma (hash tabanlı) bir puan üretir. Bu veri,
birden fazla kişi aynı ödülü hak ettiğinde kimin kazanacağını ve Amorti dağılımını
belirliyor. Hiç entegrasyon kurulmadan CANLIYA (gerçek ödülle) ALINMAMALI. Sunucu
başlarken ve `/health` içinde (`real_loyalty_records` alanı) bu açıkça görünür.

## Kurulum

```bash
pip install -r requirements.txt
```

## Ortam Değişkenleri

```bash
export DYNASTY_MASTER_SECRET="çok-uzun-rastgele-bir-şifre"
export DYNASTY_LICENSE_KEY="my_casino:20261231:abcd1234..."   # generate_license.py ile üretin
export DYNASTY_INTERNAL_KEY="uzun-rastgele-admin-anahtarı"
```

## Çalıştırma

```bash
uvicorn app:app --host 0.0.0.0 --port 8000
python worker.py   # ayrı terminalde
```

## 🎛️ Yönetici Paneli

`http://sunucu-adresi:8000/admin` — haftayı başlatmak ve manuel çekiliş yapmak artık
tarayıcıdan tıklanarak yapılır, ham HTTP isteği (curl/Postman) göndermeye gerek yok.
Sayfa açılınca yönetici anahtarını (`x-internal-key` değeri) bir kez girin; tarayıcı
bir sonraki ziyarete kadar hatırlar (resepsiyon sayfasıyla aynı anahtarı paylaşır).

Panelde dört bölüm var: **Canlı Durum** (kaç top çekildi, kilitler açık mı, ödül tutarları,
kazananlar, sadakat verisinin ne kadarı gerçek — 4 saniyede bir otomatik yenilenir),
**Haftayı Başlat** (ödül havuzu ve paylaşım ayarlarıyla yeni hafta açar — bu haftaki
tüm kartları siler, dikkatli kullanın), **Manuel Çekiliş** ve **Sadakat Verisi**
(CSV yükleme — bkz. aşağıdaki "Gerçek Sadakat Verisi" bölümü).

⚠️ **Panik modu** manuel çekilişte bir seçenek olarak var — ama bunu SADECE haftayı
acilen bitirmeniz gerektiğinde işaretleyin. Bu, "1./2./3. gün kimse kazanmasın" gün
kilidini tamamen kapatır; normal oynatışta işaretli bırakırsanız ödüller günlere
yayılmadan aynı gün içinde dağılabilir.

## 🔌 Gerçek Sadakat Verisi Nasıl Bağlanır?

Kazanan seçimi ve Amorti dağılımı sadakat puanına göre yapılır (bkz. yukarıdaki
simülasyon modu notu). Gerçek veriyi bağlamanın iki yolu var — **biz casino'nun
CMS'ine bağlanmıyoruz, CMS bize bağlanır.** Sebep: çoğu casino ağında dışarıdan
içeri (bize) bağlantıya izin vermek IT için zor onaylanır; dışarıya (CMS'ten bize)
bağlantı açmaya izin vermek çok daha kolaydır.

**1. API push (önerilen, CMS'in IT kapasitesi varsa):**

```bash
curl -X POST http://sunucu:8000/integrations/loyalty-points \
  -H "x-internal-key: ..." \
  -H "Content-Type: application/json" \
  -d '{"records": [
    {"owner_id": "Ahmet Kaya", "points": 4200},
    {"owner_id": "Tamar Gelashvili", "points": 7800}
  ]}'
```

CMS bunu örn. her gece zamanlanmış bir görevle çağırabilir. Aynı `owner_id` tekrar
gönderilirse üzerine yazılır (upsert) — her seferinde TÜM güncel listeyi göndermek
güvenlidir, eski oyuncuları ayrıca silmeye gerek yok.

**2. CSV yükleme (yedek yol, IT kapasitesi yoksa):** Yönetici panelindeki
**Sadakat Verisi** bölümünden, iki sütunlu bir CSV dosyası (`owner_id,points`)
yüklenebilir. Aynı API'yle aynı sonucu üretir.

**Nasıl çalışır:** Bir `owner_id` için gerçek veri varsa (push edilmiş ya da CSV ile
yüklenmiş), sistem SİMÜLASYONU bırakıp bu gerçek puanı kullanır. Veri olmayan
oyuncular için simülasyon devam eder — yani entegrasyon aşamalı da kurulabilir,
tüm oyuncuları aynı anda bağlamak zorunda değilsiniz. `/health` uç noktasındaki
`real_loyalty_records` alanı kaç oyuncu için gerçek veri olduğunu gösterir.

## 🖥️ Flash Diskle Casino'ya Kurulum (Adım Adım)

Bu proje "kurulum" gerektirmez — sadece dosyaları kopyalayıp çalıştırmak yeterli. Aşağıdaki
adımlar casino'daki bilgisayarda (Windows varsayıyoruz, Mac/Linux için `.sh` dosyaları da var):

1. **Python kurulu mu kontrol et.** Casino bilgisayarında Command Prompt (cmd) açıp `python --version`
   yaz. Yoksa [python.org](https://www.python.org/downloads/)'dan indir — kurulumda **"Add Python to PATH"**
   kutucuğunu işaretlemeyi unutma, bu önemli.
2. **Flash diskteki `dynasty-bingo-single` klasörünü** bilgisayara kopyala (örn. Masaüstü'ne).
3. O klasörde Command Prompt aç (klasöre sağ tık → "Terminali burada aç" veya klasör içinde
   adres çubuğuna `cmd` yazıp Enter'a bas) ve şunu çalıştır:
   ```
   pip install -r requirements.txt
   ```
4. **`start_sunucu.bat`** dosyasını metin editörüyle (Not Defteri) aç, en üstteki 3 satırı
   kendi gizli anahtarlarınla doldur (lisans anahtarını `generate_license.py` ile üretmiştin).
5. **`start_sunucu.bat`'a çift tıkla.** Bir pencere açılır ve sunucu çalışmaya başlar — bu
   pencereyi KAPATMA, oyun boyunca açık kalmalı.
6. Otomatik çekiliş istiyorsan **`start_worker.bat`'ı da** (ayrı bir pencerede, aynı şekilde
   anahtarları doldurduktan sonra) çalıştır. İstemezsen, admin panelinden manuel çekiliş de yapılabilir.
7. **Bilgisayarın ağ adresini öğren:** Command Prompt'ta `ipconfig` yaz, "IPv4 Address" yazan
   satıra bak (örn. `192.168.1.42`). Aynı WiFi'a bağlı telefonlar bu adresle sunucuya ulaşabilir:
   `http://192.168.1.42:8000`
8. Windows Güvenlik Duvarı ilk çalıştırmada "izin ver" diye sorabilir — **izin ver**'e bas,
   yoksa telefonlar bağlanamaz.

Mac/Linux'ta aynı adımlar geçerli, sadece `.bat` yerine `.sh` dosyalarını kullan
(`chmod +x start_sunucu.sh && ./start_sunucu.sh`).

⚠️ Bu kurulum aynı WiFi ağı içinde çalışır (casino'nun kendi WiFi'ı). İnternetten (WiFi dışından)
erişim istersen, bunun yerine Hetzner gibi bir bulut sunucuya kalıcı kurulum yapmak daha doğru olur
— flash disk kurulumu pilot/deneme için pratik bir çözüm.

## 📱 Müşteri Kendi Kartını Nasıl Görecek?

Her kart için bir **QR kod** var. Müşteri bunu telefonuyla okutunca kendi kartını canlı görür —
işaretlenen sayılar otomatik renklenir, sayfa kendi kendine 3 saniyede bir güncellenir.

**Akış:**
1. Müşteri kart alır → `/cards` uç noktası çağrılır (`x-internal-key` gerekir) → kart
   numarası VE gizli bir token döner (örn. `{"card_id": 5, "token": "aZ3f..."}`)
2. Sen (veya kasadaki personel) şu adrese gidip QR kodu görürsün/yazdırırsın:
   ```
   http://sunucu-adresi:8000/card/aZ3f.../qrcode
   ```
   Bu bir PNG resmi döner — ekrana koy, yazdır, veya müşteriye SMS ile linki gönder.
3. Müşteri QR'ı okutunca `http://sunucu-adresi:8000/view/aZ3f...` sayfası açılır — kendi
   kartını görür. 🔒 URL'lerde artık sıralı kart numarası değil, tahmin edilemez bir
   token kullanılıyor — yoksa `/view/1`, `/view/2` diye sayarak başkalarının kartı görülebilirdi.
4. QR kodu kaybolursa/silinirse, müşteri `http://sunucu-adresi:8000/myview` adresine gidip
   adını/üyelik numarasını yazarak kartını tekrar bulabilir.

**Pratik öneri:** Kart satışında, kağıt bir fiş üzerine QR kodu yazdırıp müşteriye verebilirsin
(fiş = kart numarası + QR kod). Bu, gerçek casino tombala kartı deneyimine en yakın yöntem.

## API Uçları (artık tenant_id yok, daha basit)

| Method | Yol | Açıklama |
|---|---|---|
| GET | `/health` | Sağlık kontrolü (simülasyon modu durumu dahil) |
| GET | `/admin` | 🎛️ Yönetici paneli — hafta başlatma ve manuel çekiliş tarayıcıdan yapılır (anahtar formda istenir) |
| POST | `/admin/start-week` | Hafta başlatır (`x-internal-key` header gerekir) |
| POST | `/admin/draw` | Manuel çekiliş (`x-internal-key` header gerekir) |
| POST | `/cards` | Kart oluşturur — oyuncu başına 1 kart (`x-internal-key` header gerekir) |
| GET | `/state` | Oyun durumu |
| GET | `/card/{token}` | Kart durumu (token ile, sıralı ID ile DEĞİL) |
| GET | `/owner/{owner_id}/cards` | Oyuncunun kartları (`id` + `token` döner) |
| GET | `/winners` | SADECE mevcut haftanın kazananları |
| GET | `/view/{token}` | 📱 Müşterinin canlı kart ekranı (tarayıcıda açılır) |
| GET | `/card/{token}/qrcode` | 📱 Bu karta giden QR kod resmi (PNG) |
| GET | `/card/{token}/receipt` | 🧾 Kasada yazdırılacak QR'lı fiş sayfası |
| GET | `/myview` | 📱 İsimle kart arama sayfası |
| GET | `/bigscreen` | 📺 Salon projeksiyonu/TV için genel ekran |
| GET | `/prizes` | 🔒 Sadece toplam ödül miktarları (max_winners YOK) |
| GET | `/reception` | 🏨 Resepsiyon personeli için misafir kayıt formu (personel anahtarı formda istenir) |
| POST | `/reception/register` | 🏨 Misafire ücretsiz kart atar + otomatik SMS gönderir (`x-internal-key` header gerekir) |
| POST | `/integrations/loyalty-points` | 🔌 Casino'nun CMS'i gerçek sadakat puanlarını buraya push eder (`x-internal-key` header gerekir) |
| POST | `/integrations/loyalty-csv` | 📄 CSV yükleyerek aynısını yapar — API'ye bağlanacak IT kapasitesi yoksa yedek yol (`x-internal-key` header gerekir) |

## 🆕 Kaç Kişi Paylaşabilir? (Yapılandırılabilir Kazanan Sayısı)

Artık her ödül kategorisi için "en fazla kaç kişi paylaşabilir" ayarını `start-week` çağrısında
belirleyebilirsin. Örnek:

```bash
curl -X POST http://sunucu/admin/start-week \
  -H "x-internal-key: ..." \
  -d '{
    "declared_weekly_pool_usd": 20000,
    "max_winners_c1": 4,
    "max_winners_c2": 4,
    "max_winners_t": 2,
    "amorti_top_n": 5
  }'
```

**Nasıl çalışır:** Aynı çekilişte ayarlanan sayıdan FAZLA kişi bir ödülü hak ederse (örn. 3 kişi
aynı anda tombala yaptı ama `max_winners_t: 2`), sistem sadakat puanı en yüksek olanları seçer,
geri kalanlar o ödülü kazanamaz. Kazanan sayısı sınırın altındaysa herkes eşit paylaşır.

**Her ödül anında kaydedilir** — oyunun sonunu beklemez. 1.Çinko olduğu an kim(ler) yaptığı ve
kişi başı ne kadar aldığı `/winners` uç noktasına düşer, ardından 2.Çinko, sonra Tombala + Amorti
(oyun biterken). `type` alanı: `cinko1`, `cinko2`, `tombala`, `amorti`. `prize_details` içinde
`per_winner_usd` (kişi başı) ve `total_usd` (kategori toplamı) bulunur.

## 🔒 Üç Farklı Ekran — Kim Ne Görür?

| Ekran | Kim görür | Nerede | Neyi GÖRMEZ |
|---|---|---|---|
| **Yönetici paneli** (`/admin`) | Sadece casino personeli | Kasa/ofis bilgisayarı, `x-internal-key` ile korumalı | — (her şeyi görür) |
| **Büyük ekran** (`/bigscreen`) | Salondaki herkes | Projeksiyon/TV | `max_winners` ayarları, hangi kartın kime ait olduğu |
| **Müşteri telefonu** (`/view/{token}`) | Sadece o kartın sahibi (token'ı bilen) | Kendi telefonu | `max_winners` ayarları, başka oyuncuların kartları |

**Neden önemli:** "1.Çinko'yu en fazla 4 kişi paylaşabilir" gibi ayarlar, casino'nun önceden
belirlediği iç kurallardır. Müşteri bunu bilirse hem oyunun "sürpriz" hissi kaybolur hem de
"neden benim payım küçüldü" gibi tartışmalara yol açabilir. Bu yüzden `/prizes`, `/state`,
`/view/{token}` ve `/bigscreen` — hepsi bilerek SADECE toplam ödül miktarını ve kazanıldıktan
SONRAKİ sonucu gösterir, "kaç kişiye bölünecek" ayarını hiçbir zaman göstermez. Bu ayar sadece
`/admin/start-week` çağrısında görünür ve o da `x-internal-key` ile korunur.

## 📨 Misafir Kartını Nasıl Alır? (Resepsiyon + Otomatik SMS)

Kartlar **ücretsiz** — casino bunu bir eğlence/atraksiyon olarak sunuyor, satış yok. Akış:

1. Misafir resepsiyonda giriş yapar (check-in).
2. Personel `http://sunucu:8000/reception` sayfasını açar — bir kere personel anahtarını
   girer (tarayıcı bir sonraki misafire kadar hatırlar), misafirin adını ve telefon
   numarasını yazıp "Kart Oluştur ve SMS Gönder"e basar.
3. Sistem otomatik olarak:
   - Misafire 1 kart atar (ücretsiz, satış yok — aynı isim/ID'ye ikinci kart verilmez)
   - Kart linkini SMS ile misafirin telefonuna gönderir
4. Misafir SMS'teki linke tıklar → kendi kartını telefonunda canlı görür. Kağıt yok, QR
   okutmaya bile gerek yok — link direkt SMS'te.

**SMS gerçekten gönderilsin diye ne yapman lazım:**

Bir [Twilio](https://www.twilio.com) hesabı aç (birkaç dakika sürer, ücretsiz deneme kredisi
var). Hesap 3 bilgi verir, bunları ortam değişkeni olarak ayarla:

```bash
export TWILIO_ACCOUNT_SID="..."
export TWILIO_AUTH_TOKEN="..."
export TWILIO_FROM_NUMBER="+1..."
```

**Bu değişkenleri ayarlamazsan ne olur?** Sistem "sandbox modu"na düşer — SMS'i gerçekten
göndermez, sadece sunucu ekranına yazdırır. Yani her şeyi test edebilirsin, gerçek SMS'e
geçmek için sadece yukarıdaki 3 satırı eklemen yeterli, kodda hiçbir değişiklik gerekmez.

**Alternatif (SMS istemezsen / yedek plan):** `/card/{token}/receipt` sayfası hâlâ duruyor —
kasadaki bir yazıcıdan QR'lı fiş de çıkarabilirsin. Ama önerilen akış artık resepsiyon + SMS.

## Çoklu Casino Sürümünden Farkı

- `tenant_id` kavramı tamamen kaldırıldı
- `GameConfig` ve `GameState` artık her zaman tek satır (singleton) — `database.py` içindeki
  `get_or_create_config()` / `get_or_create_state()` fonksiyonları bunu otomatik hallediyor
- `worker.py` artık casino listesi üzerinde dönmüyor, direkt tek çekiliş fonksiyonunu çağırıyor
- Daha fazla casino eklemek istersen, çoklu casino sürümüne geri dönmen gerekir (o dosyaları da elimde tutuyorum)
