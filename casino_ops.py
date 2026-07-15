# =============================================================================
# NovaGuard Casino Ops - Müşteri Odaklı Sistem (4 Dilli: TR / EN / RU / KA)
# =============================================================================
# 4 modül + veri kaynağından bağımsız mimari + CSV doğrulama + 4 dil desteği:
#   1) Oyuncu Değeri & Promosyon Önerisi
#   2) Sadakat Puanı & Hediye/Bonus Önerisi
#   3) F&B Servis Listesi — sipariş geçmişinden OTOMATİK hesaplanır
#   4) Anomali & Risk Tespiti (müşteri dışı ama faydalı, ek modül)
#
# DİL MİMARİSİ (dashboard için):
#   Modüller metin ÜRETMEZ, "kod" üretir (örn. "segment_kod": "vip").
#   Çeviri SADECE html_olustur() içinde yapılır.
#
# VERİ ALMA MİMARİSİ (API/CSV alan adları için):
#   Bu sistem TEK bir CMS'e (örn. Nexio) bağımlı değil. Biz kendi API'mizi
#   sağlıyoruz; hangi CMS kullanılırsa kullanılsın, casino'nun IT ekibi
#   kendi sistemlerinden veri çekip BİZE gönderen bir köprü script yazar.
#   DIŞARIYA AÇILAN JSON/CSV ALAN ADLARI İNGİLİZCE'dir (id, name, handle,
#   table, game, player_id, category, item vb.) — bu, uluslararası bir
#   IT ekibinin okuyabileceği evrensel bir sözleşme olsun diye böyle.
#   Python kodunun İÇİNDEKİ değişken/fonksiyon isimleri (ad, masa,
#   oyuncu_analizi vb.) Türkçe kalmıştır — bunlar sadece senin okuyacağın
#   koddur, dışarıya hiç gitmez. Yani modüller veriyi İngilizce alanlardan
#   OKUR, ama kendi aralarında Türkçe isimlerle konuşmaya devam eder.
#
# KURULUM YOK. Sadece Python gerekir.
# Çalıştırma:  python casino_ops.py
# Dil değiştirme: sayfanın altındaki TR / EN / RU / KA butonları
# Veri alma: POST /api/players, /api/table_results, /api/fb_orders
# =============================================================================

import json
import csv
import os
import webbrowser
import threading
import time
import urllib.request
import urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from collections import Counter


# =============================================================================
# ⚙️  AYAR — Satışta sadece burayı değiştir
# =============================================================================

AYAR = {
    "kaynak": "ornek",   # "ornek" | "csv" | "api"
    "dil": "tr",          # varsayılan dil: "tr" | "en" | "ru" | "ka"

    # Casino'nun köprü scripti bize veri gönderirken bu anahtarı
    # X-NovaGuard-Key başlığında göndermeli. Rastgele, uzun bir şeyle değiştir.
    "api_anahtari": "DEGISTIR_BU_ANAHTARI_2026",

    # CSV dosya yolları — DOSYA ADLARI ve İÇİNDEKİ SÜTUN ADLARI İngilizce.
    "csv": {
        "players": "data/players.csv",
        "table_results": "data/table_results.csv",
        "fb_orders": "data/fb_orders.csv",
    },

    "api": {
        "base_url": "https://musteri-casino.example.com/api",
        "api_key": "BURAYA_MUSTERI_ANAHTARI",
        "endpoints": {
            "players": "/players",
            "table_results": "/table-results",
            "fb_orders": "/fb-orders",
        },
        # ALAN EŞLEME: "bizim isim (İngilizce)": "müşterinin JSON'daki ismi"
        "eslesme": {
            "players": {
                "id": "player_id", "name": "full_name", "handle": "total_handle",
                "house_edge": "house_edge", "visits": "visit_count",
                "days_since_last_visit": "days_since_last_visit",
                "fb_spend": "fb_spend", "fb_preference": "fb_preference",
                "favorite_game": "favorite_game",
            },
            "table_results": {
                "table": "table_id", "game": "game", "drop": "drop_amount",
                "expected_hold": "expected_hold", "actual_hold": "actual_hold",
            },
            "fb_orders": {
                "player_id": "player_id", "category": "category", "item": "item_name",
            },
        },
    },
}


# Her dosya tipinin OLMASI GEREKEN sütunları (CSV doğrulaması için)
# Bunlar dışarıya açılan sözleşme — İngilizce.
CSV_SEMA = {
    "players":  ["id", "name", "handle", "house_edge", "visits", "days_since_last_visit",
                 "fb_spend", "fb_preference", "favorite_game"],
    "table_results": ["table", "game", "drop", "expected_hold", "actual_hold"],
    "fb_orders": ["player_id", "category", "item"],
}


# =============================================================================
# ⚙️  SADAKAT PUANI AYARLARI
# =============================================================================

PUAN_KURALLARI = {
    "theo_bolen": 100,
    "fb_bolen": 50,
    "ziyaret_carpani": 3,
    "gumus_esik": 100,
    "altin_esik": 300,
    "platin_esik": 500,
    "uzun_sure_gun": 14,
}


# =============================================================================
# 🌍  METİN SÖZLÜĞÜ — Dashboard'ın kendi ürettiği metinler, 4 dilde.
# =============================================================================

METIN = {
"tr": {
    "baslik": "🎰 NovaGuard Casino Ops",
    "alt_baslik": "Misafir odaklı, şeffaf ve açıklanabilir analiz",
    "kaynak_etiket": "Veri Kaynağı", "durum_etiket": "Durum",
    "uyari_baslik": "Veri uyarıları",
    "uyari_alt": "Sorunlu satırlar atlandı; gerisi gösteriliyor.",
    "sekme_oyuncu": "👤 Oyuncu & Promosyon", "sekme_sadakat": "🎁 Sadakat & Hediye",
    "sekme_fb": "☕ F&B Servis", "sekme_anomali": "🚨 Anomali & Risk",

    "th1_oyuncu": "Oyuncu", "th1_teorik": "Teorik", "th1_adt": "ADT",
    "th1_ziyaret": "Ziyaret", "th1_son": "Son", "th1_segment": "Segment",
    "th1_promosyon": "Önerilen Promosyon", "th1_oncelik": "Öncelik",
    "note1": "⚠️ = sorumlu oyun bayrağı. Theo = handle × house edge. ADT = theo / ziyaret.",

    "th2_oyuncu": "Oyuncu", "th2_puan": "Puan", "th2_seviye": "Seviye",
    "th2_fb_tercih": "F&B Tercihi", "th2_oyun_tercihi": "Oyun Tercihi",
    "th2_hediye": "Hediye / Bonus Önerisi",
    "note2": "🔔 = 14+ gündür gelmedi, iletişime geçilmeli. Puan = (teorik değer ÷ 100) + (F&B harcaması ÷ 50) + (ziyaret × 3).",

    "th3_oyuncu": "Oyuncu", "th3_kahve": "Kahve", "th3_icecek": "İçecek",
    "th3_cerez": "Çerez / Meyve", "th3_alkol": "Alkol", "th3_servis_notu": "Servis Notu",
    "note3": "☕ Bu tablo elle girilmez — F&B sisteminden gelen sipariş geçmişinden otomatik hesaplanır. 📝 = henüz sipariş geçmişi yok.",

    "th4_masa": "Masa", "th4_oyun": "Oyun", "th4_drop": "Drop",
    "th4_beklenen": "Beklenen", "th4_gercek": "Gerçek", "th4_sapma": "Sapma",
    "th4_fark": "Fark", "th4_durum": "Durum",
    "note4": "%50+ sapma = İNCELE, %25+ = İzle. Misafir konusundan bağımsız, ek modül.",

    "veri_gelmedi": "Veri gelmedi (uyarıları kontrol et)",
    "seg_vip": "VIP", "seg_yuksek": "Yüksek", "seg_orta": "Orta", "seg_dusuk": "Düşük",
    "onc_yuksek": "YÜKSEK", "onc_orta": "Orta", "onc_dusuk": "Düşük",

    "promo_geri_kazanim": "Geri kazanım: kişisel davet + konaklama",
    "promo_vip_host": "VIP host ataması + özel limit",
    "promo_loyalty": "Loyalty puan 2x + yemek",
    "promo_free_spin": "Free spin / küçük match bonus",
    "promo_email": "Düşük maliyetli e-posta kampanyası",

    "sev_platin": "Platin", "sev_altin": "Altın", "sev_gumus": "Gümüş", "sev_bronz": "Bronz",
    "hed_platin": "VIP özel etkinlik daveti + kişisel host ataması",
    "hed_altin": "Ücretsiz oda gecelemesi (1 gece)",
    "hed_gumus": "Restoran %20 indirim çeki",
    "hed_bronz": "Ücretsiz içecek kuponu",

    "onot_blackjack": "blackjack turnuvası bileti", "onot_roulette": "rulet gecesi VIP masası",
    "onot_poker": "poker turnuvası bileti", "onot_baccarat": "baccarat özel masa rezervasyonu",
    "oyun_blackjack": "Blackjack", "oyun_roulette": "Rulet", "oyun_poker": "Poker", "oyun_baccarat": "Bakara",

    "durum_incele": "🔴 İNCELE", "durum_izle": "🟡 İzle", "durum_normal": "🟢 Normal",
    "servis_var_on": "Sorulmadan hazırlanabilir: ",
    "servis_yok": "Sipariş geçmişi yok — bu ziyarette sorup kaydedin",
    "etiket_gun": "gün", "etiket_bilgi_eksik": "📝 sipariş yok", "etiket_yok": "Yok",
},
"en": {
    "baslik": "🎰 NovaGuard Casino Ops",
    "alt_baslik": "Guest-focused, transparent and explainable analysis",
    "kaynak_etiket": "Data Source", "durum_etiket": "Status",
    "uyari_baslik": "Data warnings",
    "uyari_alt": "Problem rows were skipped; the rest is shown.",
    "sekme_oyuncu": "👤 Player & Promotion", "sekme_sadakat": "🎁 Loyalty & Gifts",
    "sekme_fb": "☕ F&B Service", "sekme_anomali": "🚨 Anomaly & Risk",

    "th1_oyuncu": "Player", "th1_teorik": "Theoretical", "th1_adt": "ADT",
    "th1_ziyaret": "Visits", "th1_son": "Last", "th1_segment": "Segment",
    "th1_promosyon": "Recommended Promotion", "th1_oncelik": "Priority",
    "note1": "⚠️ = responsible gaming flag. Theo = handle × house edge. ADT = theo / visits.",

    "th2_oyuncu": "Player", "th2_puan": "Points", "th2_seviye": "Tier",
    "th2_fb_tercih": "F&B Preference", "th2_oyun_tercihi": "Favorite Game",
    "th2_hediye": "Gift / Bonus Suggestion",
    "note2": "🔔 = hasn't visited in 14+ days, should be contacted. Points = (theoretical value ÷ 100) + (F&B spend ÷ 50) + (visits × 3).",

    "th3_oyuncu": "Player", "th3_kahve": "Coffee", "th3_icecek": "Drink",
    "th3_cerez": "Snack / Fruit", "th3_alkol": "Alcohol", "th3_servis_notu": "Service Note",
    "note3": "☕ This table isn't entered manually — it's computed automatically from F&B order history. 📝 = no order history yet.",

    "th4_masa": "Table", "th4_oyun": "Game", "th4_drop": "Drop",
    "th4_beklenen": "Expected", "th4_gercek": "Actual", "th4_sapma": "Deviation",
    "th4_fark": "Difference", "th4_durum": "Status",
    "note4": "50%+ deviation = REVIEW, 25%+ = Watch. A separate module, unrelated to guest data.",

    "veri_gelmedi": "No data (check warnings)",
    "seg_vip": "VIP", "seg_yuksek": "High", "seg_orta": "Medium", "seg_dusuk": "Low",
    "onc_yuksek": "HIGH", "onc_orta": "Medium", "onc_dusuk": "Low",

    "promo_geri_kazanim": "Win-back: personal invitation + accommodation",
    "promo_vip_host": "VIP host assignment + special limit",
    "promo_loyalty": "2x loyalty points + dining",
    "promo_free_spin": "Free spin / small match bonus",
    "promo_email": "Low-cost email campaign",

    "sev_platin": "Platinum", "sev_altin": "Gold", "sev_gumus": "Silver", "sev_bronz": "Bronze",
    "hed_platin": "VIP exclusive event invitation + personal host assignment",
    "hed_altin": "Free room night (1 night)",
    "hed_gumus": "20% restaurant discount voucher",
    "hed_bronz": "Free drink voucher",

    "onot_blackjack": "blackjack tournament ticket", "onot_roulette": "roulette night VIP table",
    "onot_poker": "poker tournament ticket", "onot_baccarat": "private baccarat table reservation",
    "oyun_blackjack": "Blackjack", "oyun_roulette": "Roulette", "oyun_poker": "Poker", "oyun_baccarat": "Baccarat",

    "durum_incele": "🔴 REVIEW", "durum_izle": "🟡 Watch", "durum_normal": "🟢 Normal",
    "servis_var_on": "Can be prepared without asking: ",
    "servis_yok": "No order history — ask and record this visit",
    "etiket_gun": "days", "etiket_bilgi_eksik": "📝 no orders", "etiket_yok": "None",
},
"ru": {
    "baslik": "🎰 NovaGuard Casino Ops",
    "alt_baslik": "Анализ, ориентированный на гостя — прозрачный и понятный",
    "kaynak_etiket": "Источник данных", "durum_etiket": "Статус",
    "uyari_baslik": "Предупреждения о данных",
    "uyari_alt": "Проблемные строки пропущены; остальное показано.",
    "sekme_oyuncu": "👤 Игрок и промо", "sekme_sadakat": "🎁 Лояльность и подарки",
    "sekme_fb": "☕ Сервис Ф&Б", "sekme_anomali": "🚨 Аномалии и риск",

    "th1_oyuncu": "Игрок", "th1_teorik": "Теор. значение", "th1_adt": "ADT",
    "th1_ziyaret": "Визиты", "th1_son": "Последний", "th1_segment": "Сегмент",
    "th1_promosyon": "Рекомендуемая промо-акция", "th1_oncelik": "Приоритет",
    "note1": "⚠️ = флаг ответственной игры. Тео = handle × house edge. ADT = тео / визиты.",

    "th2_oyuncu": "Игрок", "th2_puan": "Баллы", "th2_seviye": "Уровень",
    "th2_fb_tercih": "Предпочтение Ф&Б", "th2_oyun_tercihi": "Любимая игра",
    "th2_hediye": "Подарок / бонус",
    "note2": "🔔 = не был 14+ дней, нужно связаться. Баллы = (тео значение ÷ 100) + (расходы на Ф&Б ÷ 50) + (визиты × 3).",

    "th3_oyuncu": "Игрок", "th3_kahve": "Кофе", "th3_icecek": "Напиток",
    "th3_cerez": "Снек / Фрукты", "th3_alkol": "Алкоголь", "th3_servis_notu": "Заметка для сервиса",
    "note3": "☕ Эта таблица не заполняется вручную — рассчитывается автоматически из истории заказов Ф&Б. 📝 = истории заказов пока нет.",

    "th4_masa": "Стол", "th4_oyun": "Игра", "th4_drop": "Дроп",
    "th4_beklenen": "Ожидаемый", "th4_gercek": "Фактический", "th4_sapma": "Отклонение",
    "th4_fark": "Разница", "th4_durum": "Статус",
    "note4": "Отклонение 50%+ = ПРОВЕРИТЬ, 25%+ = Наблюдать. Отдельный модуль, не связан с данными гостей.",

    "veri_gelmedi": "Нет данных (проверьте предупреждения)",
    "seg_vip": "VIP", "seg_yuksek": "Высокий", "seg_orta": "Средний", "seg_dusuk": "Низкий",
    "onc_yuksek": "ВЫСОКИЙ", "onc_orta": "Средний", "onc_dusuk": "Низкий",

    "promo_geri_kazanim": "Возврат гостя: личное приглашение + проживание",
    "promo_vip_host": "Назначение VIP-хоста + особый лимит",
    "promo_loyalty": "2x баллов лояльности + питание",
    "promo_free_spin": "Фриспин / небольшой match-бонус",
    "promo_email": "Недорогая email-рассылка",

    "sev_platin": "Платина", "sev_altin": "Золото", "sev_gumus": "Серебро", "sev_bronz": "Бронза",
    "hed_platin": "Приглашение на VIP-мероприятие + личный хост",
    "hed_altin": "Бесплатная ночь в номере (1 ночь)",
    "hed_gumus": "Скидка 20% в ресторане",
    "hed_bronz": "Купон на бесплатный напиток",

    "onot_blackjack": "билет на турнир по блэкджеку", "onot_roulette": "VIP-стол в вечер рулетки",
    "onot_poker": "билет на покерный турнир", "onot_baccarat": "бронирование отдельного стола баккара",
    "oyun_blackjack": "Блэкджек", "oyun_roulette": "Рулетка", "oyun_poker": "Покер", "oyun_baccarat": "Баккара",

    "durum_incele": "🔴 ПРОВЕРИТЬ", "durum_izle": "🟡 Наблюдать", "durum_normal": "🟢 Норма",
    "servis_var_on": "Можно подготовить не спрашивая: ",
    "servis_yok": "Истории заказов нет — уточните и запишите в этот визит",
    "etiket_gun": "дн.", "etiket_bilgi_eksik": "📝 нет заказов", "etiket_yok": "Нет",
},
"ka": {
    "baslik": "🎰 NovaGuard Casino Ops",
    "alt_baslik": "სტუმარზე ორიენტირებული, გამჭვირვალე და გასაგები ანალიზი",
    "kaynak_etiket": "მონაცემთა წყარო", "durum_etiket": "სტატუსი",
    "uyari_baslik": "მონაცემთა გაფრთხილებები",
    "uyari_alt": "პრობლემური სტრიქონები გამოტოვებულია; დანარჩენი ნაჩვენებია.",
    "sekme_oyuncu": "👤 მოთამაშე და პრომო", "sekme_sadakat": "🎁 ლოიალობა და საჩუქრები",
    "sekme_fb": "☕ კვების სერვისი", "sekme_anomali": "🚨 ანომალია და რისკი",

    "th1_oyuncu": "მოთამაშე", "th1_teorik": "თეორიული", "th1_adt": "ADT",
    "th1_ziyaret": "ვიზიტები", "th1_son": "ბოლო", "th1_segment": "სეგმენტი",
    "th1_promosyon": "რეკომენდებული პრომოცია", "th1_oncelik": "პრიორიტეტი",
    "note1": "⚠️ = პასუხისმგებლიანი თამაშის ნიშანი. თეო = handle × house edge. ADT = თეო / ვიზიტები.",

    "th2_oyuncu": "მოთამაშე", "th2_puan": "ქულები", "th2_seviye": "დონე",
    "th2_fb_tercih": "კვების პრეფერენცია", "th2_oyun_tercihi": "საყვარელი თამაში",
    "th2_hediye": "საჩუქარი / ბონუსი",
    "note2": "🔔 = 14+ დღეა არ ჩამოსულა, საჭიროა კონტაქტი. ქულები = (თეორიული ღირებულება ÷ 100) + (კვების ხარჯი ÷ 50) + (ვიზიტები × 3).",

    "th3_oyuncu": "მოთამაშე", "th3_kahve": "ყავა", "th3_icecek": "სასმელი",
    "th3_cerez": "მარცვლეული / ხილი", "th3_alkol": "ალკოჰოლი", "th3_servis_notu": "სერვისის შენიშვნა",
    "note3": "☕ ეს ცხრილი ხელით არ ივსება — ავტომატურად გამოითვლება შეკვეთების ისტორიიდან. 📝 = შეკვეთების ისტორია ჯერ არ არის.",

    "th4_masa": "მაგიდა", "th4_oyun": "თამაში", "th4_drop": "დროპი",
    "th4_beklenen": "მოსალოდნელი", "th4_gercek": "ფაქტობრივი", "th4_sapma": "გადახრა",
    "th4_fark": "სხვაობა", "th4_durum": "სტატუსი",
    "note4": "50%+ გადახრა = შემოწმება, 25%+ = დაკვირვება. ცალკე მოდული, სტუმრის მონაცემებთან კავშირი არ აქვს.",

    "veri_gelmedi": "მონაცემები არ მოვიდა (შეამოწმეთ გაფრთხილებები)",
    "seg_vip": "VIP", "seg_yuksek": "მაღალი", "seg_orta": "საშუალო", "seg_dusuk": "დაბალი",
    "onc_yuksek": "მაღალი", "onc_orta": "საშუალო", "onc_dusuk": "დაბალი",

    "promo_geri_kazanim": "დაბრუნების პრომო: პირადი მოწვევა + განთავსება",
    "promo_vip_host": "VIP ჰოსტის მინიჭება + სპეციალური ლიმიტი",
    "promo_loyalty": "ლოიალობის ქულები 2x + კვება",
    "promo_free_spin": "უფასო სპინი / მცირე match ბონუსი",
    "promo_email": "დაბალბიუჯეტიანი ელფოსტის კამპანია",

    "sev_platin": "პლატინა", "sev_altin": "ოქრო", "sev_gumus": "ვერცხლი", "sev_bronz": "ბრინჯაო",
    "hed_platin": "VIP ექსკლუზიური ღონისძიების მოწვევა + პირადი ჰოსტი",
    "hed_altin": "უფასო ღამე ნომერში (1 ღამე)",
    "hed_gumus": "20% ფასდაკლების ვაუჩერი რესტორანში",
    "hed_bronz": "უფასო სასმელის ვაუჩერი",

    "onot_blackjack": "ბლექჯეკის ტურნირის ბილეთი", "onot_roulette": "რულეტის საღამოს VIP მაგიდა",
    "onot_poker": "პოკერის ტურნირის ბილეთი", "onot_baccarat": "ბაკარას ცალკე მაგიდის დაჯავშნა",
    "oyun_blackjack": "ბლექჯეკი", "oyun_roulette": "რულეტი", "oyun_poker": "პოკერი", "oyun_baccarat": "ბაკარა",

    "durum_incele": "🔴 შემოწმება", "durum_izle": "🟡 დაკვირვება", "durum_normal": "🟢 ნორმალური",
    "servis_var_on": "შეკითხვის გარეშე შეიძლება მომზადდეს: ",
    "servis_yok": "შეკვეთების ისტორია არ არის — ამ ვიზიტზე ჰკითხეთ და ჩაწერეთ",
    "etiket_gun": "დღე", "etiket_bilgi_eksik": "📝 შეკვეთა არ არის", "etiket_yok": "არა",
},
}


# =============================================================================
# ÖRNEK VERİ (dış sözleşmeye uygun: İngilizce alan adları)
# =============================================================================

ORNEK_OYUNCULAR = [
    {"id": "P001", "name": "Ahmet Y.",  "handle": 240000,   "house_edge": 0.018, "visits": 22, "days_since_last_visit": 4,
     "fb_spend": 3200,  "fb_preference": "Restaurant",   "favorite_game": "blackjack"},
    {"id": "P002", "name": "Maria K.",  "handle": 11000000, "house_edge": 0.015, "visits": 31, "days_since_last_visit": 2,
     "fb_spend": 8500,  "fb_preference": "Bar",          "favorite_game": "poker"},
    {"id": "P003", "name": "Giorgi T.", "handle": 45000,    "house_edge": 0.025, "visits": 6,  "days_since_last_visit": 1,
     "fb_spend": 600,   "fb_preference": "None",         "favorite_game": "roulette"},
    {"id": "P004", "name": "Elena S.",  "handle": 1500000,  "house_edge": 0.013, "visits": 10, "days_since_last_visit": 18,
     "fb_spend": 15000, "fb_preference": "Room Service", "favorite_game": "baccarat"},
    {"id": "P005", "name": "Deniz A.",  "handle": 12000,    "house_edge": 0.030, "visits": 3,  "days_since_last_visit": 55,
     "fb_spend": 200,   "fb_preference": "None",         "favorite_game": "roulette"},
    {"id": "P006", "name": "Ivan P.",   "handle": 900000,   "house_edge": 0.020, "visits": 14, "days_since_last_visit": 9,
     "fb_spend": 4100,  "fb_preference": "Restaurant",   "favorite_game": "poker"},
]

ORNEK_MASA_SONUC = [
    {"table": "M1", "game": "blackjack", "drop": 200000, "expected_hold": 0.18,  "actual_hold": 0.17},
    {"table": "M2", "game": "roulette",  "drop": 150000, "expected_hold": 0.27,  "actual_hold": 0.04},
    {"table": "M3", "game": "poker",     "drop": 90000,  "expected_hold": 0.05,  "actual_hold": 0.06},
    {"table": "M4", "game": "baccarat",  "drop": 500000, "expected_hold": 0.012, "actual_hold": 0.011},
]

ORNEK_FB_SIPARISLER = [
    {"player_id": "P001", "category": "coffee", "item": "Turkish Coffee (Medium Sweet)"},
    {"player_id": "P001", "category": "coffee", "item": "Turkish Coffee (Medium Sweet)"},
    {"player_id": "P001", "category": "coffee", "item": "Turkish Coffee (Medium Sweet)"},
    {"player_id": "P001", "category": "coffee", "item": "Espresso"},
    {"player_id": "P001", "category": "drink", "item": "Mineral Water"},
    {"player_id": "P001", "category": "drink", "item": "Mineral Water"},
    {"player_id": "P001", "category": "drink", "item": "Cola"},
    {"player_id": "P001", "category": "snack", "item": "Mixed Nuts"},
    {"player_id": "P001", "category": "snack", "item": "Mixed Nuts"},

    {"player_id": "P002", "category": "drink", "item": "Cola"},
    {"player_id": "P002", "category": "drink", "item": "Cola"},
    {"player_id": "P002", "category": "drink", "item": "Mineral Water"},
    {"player_id": "P002", "category": "snack", "item": "Fruit Plate"},
    {"player_id": "P002", "category": "snack", "item": "Fruit Plate"},
    {"player_id": "P002", "category": "snack", "item": "Fruit Plate"},
    {"player_id": "P002", "category": "alcohol", "item": "Chivas Regal"},
    {"player_id": "P002", "category": "alcohol", "item": "Chivas Regal"},
    {"player_id": "P002", "category": "alcohol", "item": "Vodka"},

    {"player_id": "P003", "category": "drink", "item": "Water"},

    {"player_id": "P004", "category": "coffee", "item": "Espresso"},
    {"player_id": "P004", "category": "coffee", "item": "Espresso"},
    {"player_id": "P004", "category": "snack", "item": "Chocolate Plate"},
    {"player_id": "P004", "category": "snack", "item": "Chocolate Plate"},
    {"player_id": "P004", "category": "alcohol", "item": "Red Wine"},
    {"player_id": "P004", "category": "alcohol", "item": "Red Wine"},
    {"player_id": "P004", "category": "alcohol", "item": "White Wine"},

    {"player_id": "P006", "category": "coffee", "item": "Turkish Coffee (Plain)"},
    {"player_id": "P006", "category": "coffee", "item": "Turkish Coffee (Plain)"},
    {"player_id": "P006", "category": "snack", "item": "Mixed Nuts"},
    {"player_id": "P006", "category": "alcohol", "item": "Vodka"},
    {"player_id": "P006", "category": "alcohol", "item": "Vodka"},
    {"player_id": "P006", "category": "alcohol", "item": "Chivas Regal"},
]


# =============================================================================
# VERİ KAYNAĞI KATMANI (agnostik mimari)
# =============================================================================

class VeriKaynagi:
    durum = "—"
    ad = "Bilinmiyor"
    uyarilar = []
    def players(self): raise NotImplementedError
    def table_results(self): raise NotImplementedError
    def fb_orders(self): raise NotImplementedError


class OrnekKaynak(VeriKaynagi):
    ad = "Örnek Veri (yerleşik)"
    durum = "🟢 Aktif"
    def players(self): return list(ORNEK_OYUNCULAR)
    def table_results(self): return list(ORNEK_MASA_SONUC)
    def fb_orders(self): return list(ORNEK_FB_SIPARISLER)


class CSVKaynak(VeriKaynagi):
    ad = "CSV Dosyaları"
    SAYI_ALAN = {"handle", "house_edge", "visits", "days_since_last_visit", "fb_spend",
                 "drop", "expected_hold", "actual_hold"}
    LISTE_ALAN = set()
    BOOL_ALAN = set()

    def __init__(self, yollar):
        self.yollar = yollar
        self.durum = "🟢 Aktif"
        self.uyarilar = []

    def _sayi_cevir(self, ham):
        ham = ham.strip().replace(" ", "")
        if "," in ham and "." not in ham:
            ham = ham.replace(",", ".")
        return float(ham) if "." in ham else int(ham)

    def _oku(self, tip):
        yol = self.yollar[tip]
        gerekli = CSV_SEMA[tip]

        if not os.path.exists(yol):
            self.durum = "🔴 Eksik / hatalı dosya var"
            self.uyarilar.append(f"❌ {tip}: dosya bulunamadı → {yol}")
            return []

        satirlar = []
        with open(yol, encoding="utf-8-sig") as f:
            okuyucu = csv.DictReader(f)
            basliklar = [h.strip() for h in (okuyucu.fieldnames or [])]
            eksik = [s for s in gerekli if s not in basliklar]
            if eksik:
                self.durum = "🔴 Eksik / hatalı dosya var"
                self.uyarilar.append(
                    f"❌ {tip}.csv: şu sütun(lar) eksik → {', '.join(eksik)}")
                return []

            for i, row in enumerate(okuyucu, start=2):
                temiz, hatali = {}, False
                for k in gerekli:
                    ham = (row.get(k) or "").strip()
                    if ham == "":
                        self.uyarilar.append(f"⚠️ {tip}.csv satır {i}: '{k}' boş")
                        hatali = True
                        continue
                    if k in self.SAYI_ALAN:
                        try:
                            temiz[k] = self._sayi_cevir(ham)
                        except ValueError:
                            self.uyarilar.append(
                                f"⚠️ {tip}.csv satır {i}: '{k}' sayı değil → '{ham}'")
                            hatali = True
                    elif k in self.LISTE_ALAN:
                        temiz[k] = [x.strip() for x in ham.split("|") if x.strip()]
                    elif k in self.BOOL_ALAN:
                        temiz[k] = ham.lower() in ("1", "true", "evet", "yes")
                    else:
                        temiz[k] = ham
                if hatali:
                    self.durum = "🔴 Eksik / hatalı dosya var"
                else:
                    satirlar.append(temiz)

        if not satirlar:
            self.uyarilar.append(f"⚠️ {tip}.csv: geçerli satır bulunamadı")
        return satirlar

    def players(self): return self._oku("players")
    def table_results(self): return self._oku("table_results")
    def fb_orders(self): return self._oku("fb_orders")


class APIKaynak(VeriKaynagi):
    ad = "Müşteri REST API"

    def __init__(self, cfg):
        self.cfg = cfg
        self.durum = "🟡 Henüz çağrılmadı"
        self.uyarilar = []

    def _cek(self, tip):
        url = self.cfg["base_url"].rstrip("/") + self.cfg["endpoints"][tip]
        eslesme = self.cfg["eslesme"][tip]
        try:
            req = urllib.request.Request(url, headers={
                "Authorization": f"Bearer {self.cfg['api_key']}",
                "Accept": "application/json",
            })
            with urllib.request.urlopen(req, timeout=10) as resp:
                ham = json.loads(resp.read().decode("utf-8"))
            if isinstance(ham, dict):
                ham = ham.get("data") or ham.get("items") or []
            self.durum = "🟢 Bağlı"
            sonuc = []
            for kayit in ham:
                cevrili = {bizim: kayit.get(onlarin) for bizim, onlarin in eslesme.items()}
                sonuc.append(cevrili)
            return sonuc
        except (urllib.error.URLError, urllib.error.HTTPError, ValueError, TimeoutError) as e:
            self.durum = "🔴 Bağlantı hatası"
            self.uyarilar.append(f"❌ {tip}: API'ye ulaşılamadı → {e}")
            return []

    def players(self): return self._cek("players")
    def table_results(self): return self._cek("table_results")
    def fb_orders(self): return self._cek("fb_orders")


def kaynak_olustur():
    secim = AYAR["kaynak"]
    if secim == "csv":
        return CSVKaynak(AYAR["csv"])
    if secim == "api":
        return APIKaynak(AYAR["api"])
    return OrnekKaynak()


# =============================================================================
# MODÜL 1 — OYUNCU DEĞERİ & PROMOSYON
# =============================================================================

def oyuncu_analizi(kaynak):
    sonuc = []
    for o in kaynak.players():
        if not o.get("visits") or o.get("handle") is None:
            continue
        theo = o["handle"] * o["house_edge"]
        adt = theo / o["visits"] if o["visits"] else 0

        if adt >= 5000:   segment_kod = "vip"
        elif adt >= 1500: segment_kod = "yuksek"
        elif adt >= 400:  segment_kod = "orta"
        else:             segment_kod = "dusuk"

        if segment_kod in ("vip", "yuksek") and o["days_since_last_visit"] >= 14:
            promosyon_kod, oncelik_kod = "geri_kazanim", "yuksek"
        elif segment_kod == "vip":
            promosyon_kod, oncelik_kod = "vip_host", "yuksek"
        elif segment_kod == "yuksek":
            promosyon_kod, oncelik_kod = "loyalty", "orta"
        elif segment_kod == "orta":
            promosyon_kod, oncelik_kod = "free_spin", "orta"
        else:
            promosyon_kod, oncelik_kod = "email", "dusuk"

        rg_flag = (o["visits"] >= 30 and adt >= 5000)

        sonuc.append({
            "ad": o["name"], "theo": round(theo), "adt": round(adt),
            "visits": o["visits"], "days_since": o["days_since_last_visit"],
            "segment_kod": segment_kod, "promosyon_kod": promosyon_kod,
            "oncelik_kod": oncelik_kod, "rg_flag": rg_flag,
        })
    sonuc.sort(key=lambda x: x["theo"], reverse=True)
    return sonuc


# =============================================================================
# MODÜL 2 — SADAKAT PUANI & HEDİYE/BONUS ÖNERİSİ
# =============================================================================

def sadakat_hesapla(kaynak):
    kural = PUAN_KURALLARI
    sonuc = []
    for o in kaynak.players():
        if not o.get("visits") or o.get("handle") is None:
            continue
        theo = o["handle"] * o["house_edge"]
        fb = o.get("fb_spend") or 0

        theo_puan = theo / kural["theo_bolen"]
        fb_puan = fb / kural["fb_bolen"]
        ziyaret_puan = o["visits"] * kural["ziyaret_carpani"]
        toplam_puan = round(theo_puan + fb_puan + ziyaret_puan)

        if toplam_puan >= kural["platin_esik"]:   seviye_kod = "platin"
        elif toplam_puan >= kural["altin_esik"]:  seviye_kod = "altin"
        elif toplam_puan >= kural["gumus_esik"]:  seviye_kod = "gumus"
        else:                                     seviye_kod = "bronz"

        uzun_sure = o["days_since_last_visit"] >= kural["uzun_sure_gun"]

        sonuc.append({
            "ad": o["name"], "puan": toplam_puan, "seviye_kod": seviye_kod,
            "fb_tercih": o.get("fb_preference") or "—",
            "oyun_tercihi_kod": o.get("favorite_game") or None,
            "uzun_sure": uzun_sure, "days_since": o["days_since_last_visit"],
        })
    sonuc.sort(key=lambda x: x["puan"], reverse=True)
    return sonuc


# =============================================================================
# MODÜL 3 — F&B SERVİS LİSTESİ (sipariş geçmişinden OTOMATİK hesaplanır)
# =============================================================================

def en_sik_urun(siparisler, oyuncu_id, kategori):
    urunler = [s["item"] for s in siparisler
               if s.get("player_id") == oyuncu_id and s.get("category") == kategori]
    if not urunler:
        return None
    sayac = Counter(urunler)
    en_sik, _ = sayac.most_common(1)[0]
    return en_sik


def fb_servis_listesi(kaynak):
    siparisler = kaynak.fb_orders()
    sonuc = []
    for o in kaynak.players():
        if not o.get("name") or not o.get("id"):
            continue
        kahve = en_sik_urun(siparisler, o["id"], "coffee")
        icecek = en_sik_urun(siparisler, o["id"], "drink")
        cerez = en_sik_urun(siparisler, o["id"], "snack")
        alkol = en_sik_urun(siparisler, o["id"], "alcohol")
        kalemler = [k for k in [kahve, icecek, cerez, alkol] if k]
        sonuc.append({
            "ad": o["name"], "kahve": kahve, "icecek": icecek,
            "cerez": cerez, "alkol": alkol,
            "kalemler": kalemler, "eksik": len(kalemler) == 0,
        })
    sonuc.sort(key=lambda x: x["eksik"], reverse=True)
    return sonuc


# =============================================================================
# MODÜL 4 — ANOMALİ & RİSK
# =============================================================================

def anomali_tespiti(kaynak):
    sonuc = []
    for s in kaynak.table_results():
        beklenen = s["expected_hold"]
        sapma = s["actual_hold"] - beklenen
        sapma_yuzde = (sapma / beklenen * 100) if beklenen else 0
        fark = round(sapma * s["drop"])
        if abs(sapma_yuzde) >= 50:   durum_kod = "incele"
        elif abs(sapma_yuzde) >= 25: durum_kod = "izle"
        else:                        durum_kod = "normal"
        sonuc.append({
            "masa": s["table"], "oyun_kod": s["game"], "drop": s["drop"],
            "beklenen": f"%{beklenen*100:.1f}", "gercek": f"%{s['actual_hold']*100:.1f}",
            "sapma_yuzde": round(sapma_yuzde), "fark": fark, "durum_kod": durum_kod,
        })
    sonuc.sort(key=lambda x: abs(x["sapma_yuzde"]), reverse=True)
    return sonuc


# =============================================================================
# DASHBOARD
# =============================================================================

SEVIYE_RENK = {"platin": "#a855f7", "altin": "#d97706", "gumus": "#94a3b8", "bronz": "#b45309"}
ONCELIK_RENK = {"yuksek": "#dc2626", "orta": "#d97706", "dusuk": "#6b7280"}


def html_olustur(kaynak, dil):
    if dil not in METIN:
        dil = AYAR["dil"]
    m = METIN[dil]

    oyuncular = oyuncu_analizi(kaynak)
    sadakat = sadakat_hesapla(kaynak)
    fb_liste = fb_servis_listesi(kaynak)
    anomali = anomali_tespiti(kaynak)

    uyari_html = ""
    if kaynak.uyarilar:
        liste = "".join(f"<li>{u}</li>" for u in kaynak.uyarilar)
        uyari_html = f"""<div class="uyari">
          <b>⚠️ {m['uyari_baslik']} ({len(kaynak.uyarilar)}):</b>
          <ul>{liste}</ul>
          <div style="margin-top:6px;font-size:12px">{m['uyari_alt']}</div>
        </div>"""

    oyuncu_satir = ""
    for o in oyuncular:
        rg = " ⚠️" if o["rg_flag"] else ""
        renk = ONCELIK_RENK[o["oncelik_kod"]]
        oyuncu_satir += f"""<tr><td>{o['ad']}{rg}</td><td><b>{o['theo']:,}</b></td>
            <td>{o['adt']:,}</td><td>{o['visits']}</td><td>{o['days_since']} {m['etiket_gun']}</td>
            <td><span class="seg">{m['seg_'+o['segment_kod']]}</span></td>
            <td>{m['promo_'+o['promosyon_kod']]}</td>
            <td style="color:{renk};font-weight:600">{m['onc_'+o['oncelik_kod']]}</td></tr>"""
    if not oyuncu_satir:
        oyuncu_satir = f'<tr><td colspan="8">{m["veri_gelmedi"]}</td></tr>'

    sadakat_satir = ""
    for s in sadakat:
        uyari = " 🔔" if s["uzun_sure"] else ""
        renk = SEVIYE_RENK[s["seviye_kod"]]
        hediye = m["hed_" + s["seviye_kod"]]
        if s["oyun_tercihi_kod"] and ("onot_" + s["oyun_tercihi_kod"]) in m:
            hediye = f"{hediye} + {m['onot_' + s['oyun_tercihi_kod']]}"
        oyun_metni = m.get("oyun_" + (s["oyun_tercihi_kod"] or ""), "—")
        sadakat_satir += f"""<tr><td>{s['ad']}{uyari}</td><td><b>{s['puan']}</b></td>
            <td><span class="seg" style="background:{renk};color:#0f172a;font-weight:700">{m['sev_'+s['seviye_kod']]}</span></td>
            <td>{s['fb_tercih']}</td><td>{oyun_metni}</td>
            <td>{hediye}</td></tr>"""
    if not sadakat_satir:
        sadakat_satir = f'<tr><td colspan="6">{m["veri_gelmedi"]}</td></tr>'

    fb_satir = ""
    for f in fb_liste:
        etiket = f' <span style="color:#f59e0b;font-size:11px">{m["etiket_bilgi_eksik"]}</span>' if f["eksik"] else ""
        if f["kalemler"]:
            servis_notu = m["servis_var_on"] + ", ".join(f["kalemler"])
        else:
            servis_notu = m["servis_yok"]
        fb_satir += f"""<tr><td>{f['ad']}{etiket}</td>
            <td>{f['kahve'] or m['etiket_yok']}</td><td>{f['icecek'] or m['etiket_yok']}</td>
            <td>{f['cerez'] or m['etiket_yok']}</td><td>{f['alkol'] or m['etiket_yok']}</td>
            <td style="color:#86efac">{servis_notu}</td></tr>"""
    if not fb_satir:
        fb_satir = f'<tr><td colspan="6">{m["veri_gelmedi"]}</td></tr>'

    anomali_satir = ""
    for a in anomali:
        oyun_metni = m.get("oyun_" + a["oyun_kod"], a["oyun_kod"])
        durum_metni = m["durum_" + a["durum_kod"]]
        anomali_satir += f"""<tr><td>{a['masa']}</td><td>{oyun_metni}</td><td>{a['drop']:,}</td>
            <td>{a['beklenen']}</td><td>{a['gercek']}</td><td>{a['sapma_yuzde']:+}%</td>
            <td>{a['fark']:+,}</td><td>{durum_metni}</td></tr>"""
    if not anomali_satir:
        anomali_satir = f'<tr><td colspan="8">{m["veri_gelmedi"]}</td></tr>'

    dil_butonlari = ""
    for kod, etiket in [("tr", "TR"), ("en", "EN"), ("ru", "RU"), ("ka", "KA")]:
        aktif = "background:#2563eb;color:#fff" if kod == dil else "background:#1e293b;color:#94a3b8"
        dil_butonlari += f'<a href="/?dil={kod}" style="padding:6px 12px;border-radius:6px;text-decoration:none;font-size:12px;font-weight:600;{aktif}">{etiket}</a>'

    return f"""<!DOCTYPE html><html lang="{dil}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>NovaGuard Casino Ops</title><style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:system-ui,Arial,sans-serif;background:#0f172a;color:#e2e8f0;padding:20px}}
h1{{font-size:22px;margin-bottom:4px}}
.alt{{color:#94a3b8;font-size:13px;margin-bottom:14px}}
.kaynak{{background:#1e293b;border:1px solid #334155;border-radius:8px;padding:10px 14px;
  margin-bottom:14px;font-size:13px;display:flex;gap:20px;flex-wrap:wrap;align-items:center}}
.kaynak b{{color:#60a5fa}}
.uyari{{background:#422006;border:1px solid #a16207;border-radius:8px;padding:12px 14px;
  margin-bottom:14px;font-size:13px;color:#fde68a}}
.uyari ul{{margin:8px 0 0 18px}}
.uyari li{{margin:2px 0}}
.tabs{{display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap}}
.tab{{background:#1e293b;border:none;color:#cbd5e1;padding:10px 16px;border-radius:8px;cursor:pointer;font-size:14px}}
.tab.active{{background:#2563eb;color:#fff}}
.panel{{display:none;background:#1e293b;border-radius:12px;padding:16px;overflow-x:auto}}
.panel.active{{display:block}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
th{{text-align:left;padding:8px;color:#94a3b8;border-bottom:2px solid #334155;white-space:nowrap}}
td{{padding:8px;border-bottom:1px solid #334155}}
.seg{{background:#334155;padding:2px 8px;border-radius:6px;font-size:12px}}
.note{{color:#94a3b8;font-size:12px;margin-top:12px;line-height:1.5}}
.dilbar{{display:flex;gap:6px;margin-top:16px;padding-top:12px;border-top:1px solid #334155}}
</style></head><body>
<h1>{m['baslik']}</h1>
<div class="alt">{m['alt_baslik']}</div>

<div class="kaynak">
  <span>📡 {m['kaynak_etiket']}: <b>{kaynak.ad}</b></span>
  <span>{m['durum_etiket']}: {kaynak.durum}</span>
</div>
{uyari_html}

<div class="tabs">
  <button class="tab active" onclick="goster(0)">{m['sekme_oyuncu']}</button>
  <button class="tab" onclick="goster(1)">{m['sekme_sadakat']}</button>
  <button class="tab" onclick="goster(2)">{m['sekme_fb']}</button>
  <button class="tab" onclick="goster(3)">{m['sekme_anomali']}</button>
</div>

<div class="panel active" id="p0">
  <table><tr><th>{m['th1_oyuncu']}</th><th>{m['th1_teorik']}</th><th>{m['th1_adt']}</th>
    <th>{m['th1_ziyaret']}</th><th>{m['th1_son']}</th><th>{m['th1_segment']}</th>
    <th>{m['th1_promosyon']}</th><th>{m['th1_oncelik']}</th></tr>{oyuncu_satir}</table>
  <div class="note">{m['note1']}</div>
</div>
<div class="panel" id="p1">
  <table><tr><th>{m['th2_oyuncu']}</th><th>{m['th2_puan']}</th><th>{m['th2_seviye']}</th>
    <th>{m['th2_fb_tercih']}</th><th>{m['th2_oyun_tercihi']}</th><th>{m['th2_hediye']}</th></tr>{sadakat_satir}</table>
  <div class="note">{m['note2']}</div>
</div>
<div class="panel" id="p2">
  <table><tr><th>{m['th3_oyuncu']}</th><th>{m['th3_kahve']}</th><th>{m['th3_icecek']}</th>
    <th>{m['th3_cerez']}</th><th>{m['th3_alkol']}</th><th>{m['th3_servis_notu']}</th></tr>{fb_satir}</table>
  <div class="note">{m['note3']}</div>
</div>
<div class="panel" id="p3">
  <table><tr><th>{m['th4_masa']}</th><th>{m['th4_oyun']}</th><th>{m['th4_drop']}</th>
    <th>{m['th4_beklenen']}</th><th>{m['th4_gercek']}</th><th>{m['th4_sapma']}</th>
    <th>{m['th4_fark']}</th><th>{m['th4_durum']}</th></tr>{anomali_satir}</table>
  <div class="note">{m['note4']}</div>
</div>

<div class="dilbar">{dil_butonlari}</div>

<script>
function goster(i){{
  document.querySelectorAll('.tab').forEach((t,j)=>t.classList.toggle('active',i===j));
  document.querySelectorAll('.panel').forEach((p,j)=>p.classList.toggle('active',i===j));
}}
</script></body></html>"""


# =============================================================================
# WEB SUNUCU
# =============================================================================

def tarayici_dilini_algila(accept_language_header):
    """Tarayıcının/bilgisayarın dil ayarından desteklenen bir dil bulur.
    Bulamazsa None döner, o zaman AYAR'daki varsayılan dil kullanılır."""
    if not accept_language_header:
        return None
    ilk_tercih = accept_language_header.split(",")[0]
    dil_kodu = ilk_tercih.split(";")[0].split("-")[0].strip().lower()
    if dil_kodu in METIN:
        return dil_kodu
    return None


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            qs = parse_qs(parsed.query)
            if "dil" in qs:
                dil = qs["dil"][0]
            else:
                algilanan = tarayici_dilini_algila(self.headers.get("Accept-Language"))
                dil = algilanan or AYAR["dil"]
            if dil not in METIN:
                dil = AYAR["dil"]

            kaynak = kaynak_olustur()
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html_olustur(kaynak, dil).encode("utf-8"))
        else:
            self.send_response(404); self.end_headers()

    def do_POST(self):
        """Casino'nun köprü scripti buraya veri PUSH eder (JSON).
        Örn: POST /api/players  gövde: [ {...}, {...} ]
        Başlıkta X-NovaGuard-Key olmalı (AYAR'daki api_anahtari ile eşleşmeli).
        Doğrulama geçerse ilgili CSV dosyasını bu yeni listeyle YENİDEN YAZAR."""
        yol_esleme = {
            "/api/players": "players",
            "/api/table_results": "table_results",
            "/api/fb_orders": "fb_orders",
        }
        parsed = urlparse(self.path)
        tip = yol_esleme.get(parsed.path)
        if tip is None:
            self.send_response(404); self.end_headers()
            return

        gelen_anahtar = self.headers.get("X-NovaGuard-Key", "")
        if gelen_anahtar != AYAR["api_anahtari"]:
            self._json_yanit(401, {"basarili": False, "hata": "Geçersiz veya eksik anahtar (X-NovaGuard-Key)"})
            return

        try:
            uzunluk = int(self.headers.get("Content-Length", 0))
            govde = self.rfile.read(uzunluk)
            kayitlar = json.loads(govde.decode("utf-8"))
        except (ValueError, json.JSONDecodeError):
            self._json_yanit(400, {"basarili": False, "hata": "Geçersiz JSON"})
            return

        if not isinstance(kayitlar, list):
            self._json_yanit(400, {"basarili": False, "hata": "Gövde bir liste olmalı, örn. [ {...}, {...} ]"})
            return

        gerekli = CSV_SEMA[tip]
        hatalar = []
        for i, kayit in enumerate(kayitlar):
            eksik = [alan for alan in gerekli if alan not in kayit]
            if eksik:
                hatalar.append(f"Kayıt {i}: eksik alan(lar) → {', '.join(eksik)}")
        if hatalar:
            self._json_yanit(400, {"basarili": False, "hatalar": hatalar})
            return

        yol = AYAR["csv"][tip]
        klasor = os.path.dirname(yol)
        if klasor:
            os.makedirs(klasor, exist_ok=True)
        with open(yol, "w", newline="", encoding="utf-8") as f:
            yazici = csv.DictWriter(f, fieldnames=gerekli)
            yazici.writeheader()
            for kayit in kayitlar:
                yazici.writerow({alan: kayit.get(alan, "") for alan in gerekli})

        self._json_yanit(200, {"basarili": True, "kayit_sayisi": len(kayitlar)})

    def _json_yanit(self, kod, veri):
        self.send_response(kod)
        self.send_header("Content-type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(veri, ensure_ascii=False).encode("utf-8"))

    def log_message(self, *args): pass


def main():
    port = 8000
    print("=" * 52)
    print("  NovaGuard Casino Ops çalışıyor")
    print(f"  Veri kaynağı:  {AYAR['kaynak']}   |  Varsayılan dil: {AYAR['dil']}")
    print(f"  Tarayıcı:      http://localhost:{port}")
    print("  Durdurmak için: Ctrl + C")
    print("=" * 52)
    def ac():
        time.sleep(1); webbrowser.open(f"http://localhost:{port}")
    threading.Thread(target=ac, daemon=True).start()
    try:
        HTTPServer(("", port), Handler).serve_forever()
    except KeyboardInterrupt:
        print("\nKapatıldı.")


if __name__ == "__main__":
    main()
