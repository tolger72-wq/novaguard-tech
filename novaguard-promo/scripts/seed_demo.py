#!/usr/bin/env python3
"""
NovaGuard — Demo Veri Üretici
================================
Satış toplantısında "boş ekran" göstermemek için gerçekçi demo veri yükler.
Çalıştırma: python3 scripts/seed_demo.py

Bu script API üzerinden çalışır — veritabanına doğrudan dokunmaz,
gerçek production akışını test eder (CRM push → ticket engine → draw).
"""
import asyncio
import random
from datetime import datetime, timedelta, timezone

import httpx

API_BASE  = "http://localhost:8000"
ADMIN_KEY = "casino-admin-key-change-me"
CRM_KEY   = "crm-integration-key-change-me"

DEMO_PLAYERS = [
    {"card_id": "KRT-001", "name": "Ahmet Yılmaz"},
    {"card_id": "KRT-002", "name": "Fatma Kaya"},
    {"card_id": "KRT-003", "name": "Mehmet Demir"},
    {"card_id": "KRT-004", "name": "Ayşe Şahin"},
    {"card_id": "KRT-005", "name": "Mustafa Çelik"},
    {"card_id": "KRT-006", "name": "Zeynep Arslan"},
    {"card_id": "KRT-007", "name": "Hasan Koç"},
    {"card_id": "KRT-008", "name": "Elif Yıldız"},
    {"card_id": "KRT-009", "name": "İbrahim Öztürk"},
    {"card_id": "KRT-010", "name": "Hatice Aydın"},
]

GAME_TYPES = ["live", "slot"]
GAME_NAMES = {"live": ["Blackjack", "Rulet", "Bakara", "Poker"],
              "slot": ["Book of Ra", "Starburst", "Gonzo's Quest"]}


async def main():
    async with httpx.AsyncClient(timeout=30) as client:
        admin_headers = {"X-Admin-Key": ADMIN_KEY}
        crm_headers   = {"X-CRM-Key": CRM_KEY}

        print("→ Oyuncular CRM'den senkronize ediliyor...")
        for p in DEMO_PLAYERS:
            await client.post(f"{API_BASE}/api/v1/sessions/players/sync",
                               json=p, headers=crm_headers)
        print(f"  ✓ {len(DEMO_PLAYERS)} oyuncu senkronize edildi")

        print("→ Geçmiş oyun oturumları simüle ediliyor (bilet kazanımı için)...")
        session_count = 0
        for p in DEMO_PLAYERS:
            # Her oyuncuya rastgele sayıda geçmiş oturum
            num_sessions = random.randint(3, 12)
            for i in range(num_sessions):
                game_type  = random.choice(GAME_TYPES)
                started_at = datetime.now(timezone.utc) - timedelta(
                    days=random.randint(1, 25), hours=random.randint(0, 20)
                )
                duration   = random.randint(20, 240)  # dakika
                ended_at   = started_at + timedelta(minutes=duration)
                turnover   = round(random.uniform(200, 8000), 2)

                push = await client.post(
                    f"{API_BASE}/api/v1/sessions/push",
                    json={
                        "external_session_id": f"DEMO-{p['card_id']}-{i}",
                        "card_id": p["card_id"],
                        "game_type": game_type,
                        "game_name": random.choice(GAME_NAMES[game_type]),
                        "started_at": started_at.isoformat(),
                        "turnover_amount": 0,
                        "currency": "TRY",
                    },
                    headers=crm_headers,
                )
                if push.status_code != 201:
                    continue
                session_id = push.json()["id"]

                await client.patch(
                    f"{API_BASE}/api/v1/sessions/{session_id}/end",
                    json={"ended_at": ended_at.isoformat(), "final_turnover_amount": turnover},
                    headers=crm_headers,
                )
                session_count += 1

        print(f"  ✓ {session_count} oturum işlendi, biletler hesaplandı")

        print("→ Örnek çekilişler programlanıyor...")
        draws = [
            {"draw_tier": "daily", "name": "Günlük Çekiliş — Bugün",
             "scheduled_at": (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat(),
             "prize_amount": 500, "prize_currency": "TRY",
             "prize_description": "500 TL Free Play Kredisi"},
            {"draw_tier": "weekly", "name": "Haftalık Çekiliş — Bu Hafta",
             "scheduled_at": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
             "prize_amount": 4900, "prize_currency": "TRY",
             "prize_description": "4,900 TL Free Play Kredisi"},
            {"draw_tier": "annual", "name": "Yıl Sonu Büyük Final",
             "scheduled_at": (datetime.now(timezone.utc) + timedelta(days=200)).isoformat(),
             "prize_amount": 500000, "prize_currency": "TRY",
             "prize_description": "500,000 TL veya Mercedes S-Class veya 2+1 Lüks Daire"},
        ]
        created = 0
        for d in draws:
            r = await client.post(f"{API_BASE}/api/v1/draws/schedule",
                                   json=d, headers=admin_headers)
            if r.status_code == 201:
                created += 1
        print(f"  ✓ {created} çekiliş programlandı")

        print("\n" + "═"*50)
        print("  DEMO VERİ HAZIR — admin.html üzerinden gösterebilirsiniz")
        print("═"*50)


if __name__ == "__main__":
    asyncio.run(main())
