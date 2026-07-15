import secrets
import uuid
import hashlib
import hmac
import os
from datetime import date
from typing import List, Dict, Any, Set, Optional
import random

# 🔑 ANA GİZLİ ŞİFRE (MASTER SECRET)
# Bu şifre, lisans anahtarlarını "imzalamak" ve "doğrulamak" için kullanılır.
# Sadece SİZDE olmalı ve satacağınız her üründe (derlenmiş/gizlenmiş halde) bulunur.
# Bu değeri kesinlikle GitHub'a public repo olarak atmayın, .env dosyasında da tutmayın demiyoruz
# ama en azından her müşteriye özel bir versiyon derleyin ki bu sabit kolayca görünmesin.
# Gerçek kullanımda: bu satırı kod içine yazmak yerine ortam değişkeninden okuyun
# ve bu dosyayı PyInstaller/Cython gibi bir araçla derleyin (yorumda belirtildiği gibi).
MASTER_SECRET = os.getenv("DYNASTY_MASTER_SECRET", "DEGISTIR-BU-GERCEK-BIR_SIR_OLMALI-12345")


def _sign(tenant_id: str, expiry_str: str) -> str:
    """
    tenant_id + son kullanma tarihinden bir imza (signature) üretir.
    HMAC = "Bu iki bilgiyi, gizli şifremi bilen biri onayladı" demenin matematiksel yolu.
    Aynı gizli şifre olmadan, aynı imzayı üretmek (pratikte) imkansızdır.
    """
    message = f"{tenant_id}:{expiry_str}".encode("utf-8")
    signature = hmac.new(MASTER_SECRET.encode("utf-8"), message, hashlib.sha256).hexdigest()
    return signature[:16]  # İlk 16 karakter yeterli, anahtarı kısa tutar


def generate_license_key(tenant_id: str, expiry_date: date) -> str:
    """
    Bir casino için lisans anahtarı üretir. BU FONKSİYONU SİZ, KENDİ BİLGİSAYARINIZDA
    ÇALIŞTIRIRSINIZ (müşteriye satış yaparken). Üründe bu fonksiyonun çağrılmasına gerek yok.
    Örnek kullanım: generate_license_key("casino_batumi", date(2026, 12, 31))
    """
    expiry_str = expiry_date.strftime("%Y%m%d")
    signature = _sign(tenant_id, expiry_str)
    return f"{tenant_id}:{expiry_str}:{signature}"


class RoyalEngine:
    def __init__(self, license_key):
        self.locked = not self._check_license(license_key)

    def _check_license(self, key: str) -> bool:
        """
        Lisans anahtarını doğrular. Anahtar üç parçadan oluşur:
        "tenant_id:sonkullanma_tarihi:imza"
        1. Anahtarı parçalara ayır
        2. Aynı imzayı biz de hesaplayıp, gelen imzayla eşleşiyor mu bak
        3. Son kullanma tarihi geçmiş mi bak
        """
        try:
            tenant_id, expiry_str, signature = key.split(":")
        except (ValueError, AttributeError):
            print("LİSANS HATASI: Anahtar formatı yanlış. Beklenen format: tenant_id:YYYYAAGG:imza")
            return False

        expected_signature = _sign(tenant_id, expiry_str)

        # hmac.compare_digest kullanıyoruz çünkü normal '==' karşılaştırması
        # "zamanlama saldırısı" denen bir güvenlik açığına yol açabilir.
        if not hmac.compare_digest(signature, expected_signature):
            print("LİSANS HATASI: İmza eşleşmiyor. Bu anahtar geçersiz veya sahte.")
            return False

        try:
            expiry_date = date(int(expiry_str[0:4]), int(expiry_str[4:6]), int(expiry_str[6:8]))
        except ValueError:
            print("LİSANS HATASI: Tarih formatı bozuk.")
            return False

        if date.today() > expiry_date:
            print(f"LİSANS HATASI: Lisans süresi doldu ({expiry_date}).")
            return False

        return True

    def _analyze(self, grid: List[List[Optional[int]]], drawn_set: Set[int]) -> int:
        """Karttaki durumu analiz eder: 0, 1 (1.Çinko), 2 (2.Çinko), 3 (Tombala)"""
        cinko = 0
        for row in grid:
            row_numbers = {n for n in row if n is not None}
            if len(row_numbers) > 0 and row_numbers.issubset(drawn_set):
                cinko += 1
        return cinko

    def get_safe_number(self, remaining: List[int], drawn: List[int], active_cards: List[Dict[str, Any]], day_index: int, flags: Dict[str, bool], is_panic_mode: bool) -> Optional[int]:
        """
        GİZLİ SESSİZ HARD LOCK FİLTRELEME MOTORU
        """
        if self.locked: return None 

        rng = secrets.SystemRandom()
        candidates = list(remaining)
        rng.shuffle(candidates)

        # --- GÜNCELLENEN ZAMAN KİLİTLERİ KURALLARI ---
        if is_panic_mode:
            check_c1 = False; check_c2 = False; check_t = False # Panic Modda kilitler kalkar
        else:
            # 1. Çinko: Day 3'e (index 2) kadar yasak (index 0 ve 1 engellenir)
            check_c1 = (not flags["c1"]) and (day_index < 2) 
            # 2. Çinko: Day 4'e (index 3) kadar yasak (index 0, 1, 2 engellenir)
            check_c2 = (not flags["c2"]) and (day_index < 3) 
            # Tombala: Day 5'e (index 4) kadar yasak (index 0, 1, 2, 3 engellenir)
            check_t = (not flags["t"]) and (day_index < 4)   

        for ball in candidates:
            # Eğer hiçbir kilit aktif değilse, stratejik seçime git
            if not (check_c1 or check_c2 or check_t):
                return self._apply_proprietary_scoring(candidates, drawn, active_cards)

            temp_drawn = set(drawn); temp_drawn.add(ball)
            limit_hit = False

            for card in active_cards:
                score = self._analyze(card['grid'], temp_drawn)

                # HARD LOCK KONTROLÜ: Kilidi ihlal eden topu reddet
                if (check_c1 and score >= 1) or \
                   (check_c2 and score >= 2) or \
                   (check_t and score == 3): 
                    limit_hit = True; break
            
            if limit_hit:
                continue # Bu topu atla (Sessiz Hard Lock)
            
            # Güvenli top bulunduysa stratejik seçime git
            return self._apply_proprietary_scoring([ball], drawn, active_cards) # Sadece güvenli topu gönderir

        return candidates[0] if candidates else None

    def _apply_proprietary_scoring(self, balls, drawn, active_cards):
        # Burası, sizin tescilli algoritmanızdır. Basitçe rastgele döner.
        return random.choice(balls)
