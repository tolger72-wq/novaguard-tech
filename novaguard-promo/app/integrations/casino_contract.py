"""
NovaGuard Promo Engine — Evrensel Casino Entegrasyon Sözleşmesi
================================================================

BİZ SADECE ÜÇ ŞEY İSTİYORUZ:

  1. Kart numarası (casino'nun kendi sistemindeki oyuncu ID'si)
  2. Oturum süresi  (ne zaman başladı, ne zaman bitti)
  3. Ciro miktarı   (o oturumda ne kadar para döndü)

HEPSİ BU.

Oyuncunun adını, kayıp/kazancını, kişisel bilgilerini, oynadığı
oyunların detayını GÖRMEK İSTEMİYORUZ. Verinin casino sisteminde
kalması hem sizin veri güvenliğiniz hem de bizim bağımsızlığımız
açısından doğru olan budur.

Casino hangi sistemi kullanıyor olursa olsun (Nexio, Caleo,
CasinoAssist, kendi yazılımı) tek gereken: oturum başında ve
bitişinde bu iki endpoint'i çağırmak.

AKIŞ:
  Oyuncu masaya/makineye oturur
    → Casino sistemi: POST /api/v1/sessions/push   (oturum başladı)

  Oyuncu kalktığında
    → Casino sistemi: PATCH /api/v1/sessions/by-external/{id}/end  (oturum bitti + ciro)

  NovaGuard:
    → Süre + ciroyu formüle göre bilet sayısına çevirir
    → Benzersiz bilet numaralarını karta yükler
    → Çekiliş günü ağırlıklı rastgele seçim yapar


NASIL BAĞLANIR — Herhangi Bir Sistemden:

  Seçenek A — Casino sistemi doğrudan push eder (tercih edilen)
    Casino'nun floor management yazılımı, masa/makine kapanışında
    bir HTTP POST atar. Her dilde bu bir satır kod:

    Python:  requests.post(url, json=payload, headers=headers)
    Node:    fetch(url, {method:'POST', body: JSON.stringify(payload)})
    PHP:     file_get_contents($url, false, stream_context_create(['http'=>...]))
    C# :     httpClient.PostAsJsonAsync(url, payload)

  Seçenek B — Periyodik senkronizasyon (casino IT müdahalesi azdır)
    Casino'nun raporlama DB'sinden veya dışa aktarma API'sinden
    her 5-10 dakikada bir son oturumları çekip bize besleyen
    küçük bir script — casino'nun kendi IT'si yazar.
    Örnek script: bkz. casino_sync_example.py (bu klasörde)

  Seçenek C — Manuel CSV yükleme (demo / küçük casino)
    Günlük oyuncu listesi CSV olarak admin panelinden yüklenir.
    Tam otomasyona geçilene kadar kullanılabilir.


İHTİYAÇ DUYDUĞUMUZ ALANLAR:

  Zorunlu:
    card_id          : str   — Casino'nun oyuncu kart numarası (herhangi bir format)
    game_type        : str   — "live" veya "slot"
    started_at       : ISO8601 datetime
    final_turnover   : decimal — Oturum sonundaki toplam ciro

  İsteğe bağlı (varsa alıyoruz, yoksa çalışır):
    external_session_id : str   — Casino'nun kendi oturum ID'si (idempotency için önerilir)
    game_name           : str   — "Blackjack", "Book of Ra" vb.
    currency            : str   — "TRY", "GEL", "EUR", "USD" (varsayılan: GEL)

  Görmek İSTEMEDİKLERİMİZ:
    × Oyuncu adı / TC / pasaport
    × Net kazanç veya kayıp
    × Bakiye bilgisi
    × Ödeme yöntemi
    × Kişisel iletişim bilgileri
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional


@dataclass
class SessionPushPayload:
    """
    Casino sisteminin bize göndereceği minimum veri.
    Bu yapıyı kullanan herhangi bir casino sistemi entegre olabilir.
    """
    card_id: str                          # Zorunlu
    game_type: str                        # Zorunlu: "live" | "slot"
    started_at: datetime                  # Zorunlu

    external_session_id: Optional[str] = None   # Önerilir (idempotency)
    game_name: Optional[str] = None             # Opsiyonel
    currency: str = "GEL"                       # Varsayılan

    # Oturum başında bilinmeyebilir — sonunda güncellenir
    turnover_amount: Decimal = Decimal("0")


@dataclass
class SessionEndPayload:
    """Oturum kapandığında gönderilecek ek veri."""
    ended_at: datetime
    final_turnover_amount: Decimal


# API endpoint özeti
ENDPOINTS = {
    "session_start": {
        "method": "POST",
        "path": "/api/v1/sessions/push",
        "auth_header": "X-CRM-Key",
        "description": "Oyuncu masaya/makineye oturduğunda çağrılır",
    },
    "session_end": {
        "method": "PATCH",
        "path": "/api/v1/sessions/by-external/{external_session_id}/end",
        "auth_header": "X-CRM-Key",
        "description": "Oyuncu kalktığında çağrılır. Biletler burada hesaplanır.",
    },
    "player_sync": {
        "method": "POST",
        "path": "/api/v1/sessions/players/sync",
        "auth_header": "X-CRM-Key",
        "description": "Oyuncu adını senkronize etmek için (opsiyonel, display ekranı için)",
    },
}
