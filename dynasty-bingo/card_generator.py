"""
card_generator.py — Standart 90 sayılı (Avrupa tipi) bingo/tombala kartı üretici.

Bir kart: 3 satır x 9 sütun.
Her satırda tam 5 dolu hücre olur, geri kalan 4 hücre boş (None) kalır.
Sütunlar sayı aralıklarına göre bölünür:
  Sütun 0: 1-9
  Sütun 1: 10-19
  Sütun 2: 20-29
  ...
  Sütun 7: 70-79
  Sütun 8: 80-90

Bu basit ama gerçek çalışan bir üreteçtir. Her satırda 5, her sütunda
en az 1 en fazla 3 dolu hücre olacak şekilde rastgele üretir (deneme-yanılma ile).
"""

import random
from typing import List, Optional

# Her sütunun (min, max) sayı aralığı
COLUMN_RANGES = [(1, 9)] + [(10 * i, 10 * i + 9) for i in range(1, 8)] + [(80, 90)]


def _generate_fill_pattern() -> List[List[bool]]:
    """
    3x9'luk True/False deseni üretir:
    - Her satırda tam 5 True
    - Her sütunda 1-3 arası True
    Deneme yanılma (rejection sampling) ile bulunur, birkaç denemede bulunur.
    """
    for _ in range(2000):
        # Önce her sütun için kaç tane dolu hücre olacağını belirle (1-3 arası, toplam 15)
        col_counts = [1] * 9
        remaining = 15 - 9  # Dağıtılacak kalan 6 birim
        while remaining > 0:
            idx = random.randrange(9)
            if col_counts[idx] < 3:
                col_counts[idx] += 1
                remaining -= 1

        # Şimdi bu sütun sayılarını satırlara dağıtmayı dene
        grid = [[False] * 9 for _ in range(3)]
        row_remaining = [5, 5, 5]
        col_remaining = col_counts[:]
        cols_order = list(range(9))
        random.shuffle(cols_order)

        ok = True
        for col in cols_order:
            need = col_remaining[col]
            # Bu sütunda dolu olacak satırları seç (kaç satırda varsa)
            available_rows = [r for r in range(3) if row_remaining[r] > 0]
            if len(available_rows) < need:
                ok = False
                break
            chosen_rows = random.sample(available_rows, need)
            for r in chosen_rows:
                grid[r][col] = True
                row_remaining[r] -= 1

        if ok and all(x == 0 for x in row_remaining):
            return grid

    # Çok nadir durumda 2000 denemede bulunamazsa hata ver
    raise RuntimeError("Kart deseni üretilemedi, tekrar deneyin.")


def generate_card() -> List[List[Optional[int]]]:
    """
    Tek bir bingo kartı üretir: 3 satır x 9 sütun, her satırda 5 sayı.
    Dönüş: [[sayı_veya_None, ...], [...], [...]]
    """
    pattern = _generate_fill_pattern()
    grid: List[List[Optional[int]]] = [[None] * 9 for _ in range(3)]

    for col in range(9):
        low, high = COLUMN_RANGES[col]
        rows_with_number = [r for r in range(3) if pattern[r][col]]
        count_needed = len(rows_with_number)
        pool = list(range(low, high + 1))
        random.shuffle(pool)
        chosen_numbers = sorted(pool[:count_needed])  # Sütun içinde yukarıdan aşağı artan sırada
        for r, number in zip(rows_with_number, chosen_numbers):
            grid[r][col] = number

    return grid


def generate_cards(count: int) -> List[List[List[Optional[int]]]]:
    """Birden fazla kart üretir (örn. bir oyuncu 3 kart alırsa)."""
    return [generate_card() for _ in range(count)]
