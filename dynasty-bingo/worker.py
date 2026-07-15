"""
worker.py — TEK CASİNO sürümü.

Fark: Çoklu casino versiyonunda bir liste (kaç casino ödeme yaptıysa)
üzerinde dönüp her biri için ayrı ayrı çekiliş yapıyordu (paralel bile).
Tek casino olduğunca döngüye hiç gerek yok — sadece tek bir fonksiyon
çağrısı yeterli.
"""

import time
from datetime import datetime
from app import automatic_draw_process
from database import SessionLocal, init_db

WORKER_SLEEP_SECONDS = 60  # Her 60 saniyede bir kontrol et


def run_draw_worker():
    print("-------------------------------------------------------------------")
    print(f"DYNASTY BINGO WORKER BAŞLADI: Her {WORKER_SLEEP_SECONDS} saniyede bir çekiliş kontrolü.")
    print("-------------------------------------------------------------------")

    while True:
        try:
            db = SessionLocal()
            automatic_draw_process(db)
            db.close()
        except Exception as e:
            print(f"WORKER GENEL HATA: {e}")
            if 'db' in locals() and db:
                db.close()

        time.sleep(WORKER_SLEEP_SECONDS)


if __name__ == "__main__":
    init_db()
    run_draw_worker()
