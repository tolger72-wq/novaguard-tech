from typing import List

# BU SINIF, CASINO'NUN HARİCİ MÜŞTERİ YÖNETİM SİSTEMİ (CMS) İLE ENTEGRE OLMALIDIR.

class CasinoSystem:
    """
    Casino'nun dış CMS/CRM sistemleriyle entegrasyon için yer tutucu.
    """
    @staticmethod
    def get_active_players(tenant_id: str) -> List[str]:
        # Gerçek uygulamada: Casino'da QR kod okutmuş aktif oyuncuların ID'lerini döndürür.
        return [f"P{i}_{tenant_id}" for i in range(1, 3000)]

    @staticmethod
    def get_loyalty_points(user_id: str) -> int:
        # Gerçek uygulamada: Kullanıcının CMS'deki sadakat puanını döndürür.
        # Amorti kuralı için yüksek puan simülasyonu
        try:
            # Hashleme ile 1000 - 11000 arası puan simülasyonu
            return (hash(user_id) % 10000) + 1000 
        except:
            return 5000
