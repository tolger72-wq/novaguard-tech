"""
database.py — TEK CASİNO sürümü.

Fark: Çoklu casino (multi-tenant) versiyonunda her tabloda bir 'tenant_id'
sütunu vardı (hangi casino'ya ait olduğunu belirtmek için). Burada tek
casino olduğu için o sütuna hiç gerek yok — tüm veriler zaten tek casino'ya ait.

GameConfig ve GameState tablolarında her zaman tek bir satır olacak (id=1).
Buna "singleton" (tekil) tablo denir — basitçe "bu tablo hep 1 satırlık" demek.
"""

import secrets

from sqlalchemy import create_engine, Column, Integer, String, Date, DateTime, Boolean, JSON, func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.ext.mutable import MutableList, MutableDict
from sqlalchemy.orm import sessionmaker

# --- AYARLAR ---
SQLALCHEMY_DATABASE_URL = "sqlite:///./bingo.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Singleton tablo satırlarının sabit ID'si
SINGLETON_ID = 1


class GameConfig(Base):
    """Casino'nun haftalık ayarları: ödül havuzu, komisyon sonrası dağılım."""
    __tablename__ = "game_config"
    id = Column(Integer, primary_key=True, default=SINGLETON_ID)
    declared_weekly_pool_usd = Column(Integer, default=0)
    prize_c1_usd = Column(Integer, default=0)
    prize_c2_usd = Column(Integer, default=0)
    prize_t_usd = Column(Integer, default=0)
    prize_amorti_usd = Column(Integer, default=0)
    current_week_start_date = Column(Date, nullable=True)
    is_paid_for_current_week = Column(Boolean, default=False)

    # 🆕 Casino, her ödül kategorisini KAÇ KİŞİNİN paylaşabileceğini kendi belirler.
    # Örnek: max_winners_c1=4 demek, 1.Çinko'yu aynı anda en fazla 4 kişi paylaşabilir.
    # Eğer aynı çekilişte bu sayıdan FAZLA kişi hak kazanırsa, sadakat puanı en
    # yüksek olanlar seçilir (aynı Amorti'deki mantık gibi).
    max_winners_c1 = Column(Integer, default=4)
    max_winners_c2 = Column(Integer, default=4)
    max_winners_t = Column(Integer, default=2)
    amorti_top_n = Column(Integer, default=5)


class GameState(Base):
    """Anlık oyun durumu: hangi toplar çekildi, hangi kilitler açıldı."""
    __tablename__ = "game_state"
    id = Column(Integer, primary_key=True, default=SINGLETON_ID)
    start_date = Column(DateTime)  # Tombala kilitleri için esas alınan Day 1
    # MutableList/MutableDict: .append() veya ["x"]=y gibi yerinde değişikliklerin
    # veritabanına kaydedilmesi için gerekli (düz JSON sütununda bu fark edilmez).
    drawn_numbers = Column(MutableList.as_mutable(JSON), default=list)
    flags = Column(MutableDict.as_mutable(JSON), default=lambda: {"c1": False, "c2": False, "t": False, "over": False})
    daily_draw_count = Column(Integer, default=0)
    last_session_date = Column(Date, nullable=True)
    last_draw_time = Column(DateTime, nullable=True)


class Card(Base):
    """Bir oyuncunun bingo kartı. tenant_id yok çünkü tek casino var."""
    __tablename__ = "cards"
    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(String, index=True)
    grid = Column(JSON)
    # Oyuncuya gösterilen linklerde (QR, /view, fiş) bu kullanılır — sıralı
    # 'id' değil, çünkü id tahmin edilebilir (1, 2, 3...) ve kimlik doğrulama
    # olmadan başka oyuncuların kartını görmeyi mümkün kılardı. 'id' hâlâ var,
    # sadece personel/yönetici ekranlarında insan-dostu referans numarası olarak.
    token = Column(String, unique=True, index=True, default=lambda: secrets.token_urlsafe(16))


class Winners(Base):
    """Kazananlar listesi (çinko/tombala/amorti)."""
    __tablename__ = "winners"
    id = Column(Integer, primary_key=True, index=True)
    type = Column(String)  # 'cinko1', 'cinko2', 'tombala', 'amorti'
    users = Column(JSON)
    prize_details = Column(JSON)
    draw_time = Column(DateTime, default=func.now())
    # Hangi haftaya ait olduğunu işaretler — /winners bunu kullanarak sadece
    # mevcut haftanın kazananlarını gösterir. Bu olmadan eski haftaların
    # kazananları sonsuza kadar listede/büyük ekranda görünmeye devam ediyordu.
    # DateTime (Date değil): aynı takvim gününde hafta iki kez başlatılırsa
    # (örn. yanlışlıkla yeniden başlatma) iki haftayı birbirinden ayırt
    # edebilmek için state.start_date'in saniye hassasiyetini kullanıyoruz.
    week_start_date = Column(DateTime, nullable=True, index=True)


def init_db():
    Base.metadata.create_all(bind=engine)


def get_or_create_config(db) -> GameConfig:
    """Tek casino ayarını getirir, yoksa boş bir tane oluşturur."""
    config = db.query(GameConfig).filter(GameConfig.id == SINGLETON_ID).first()
    if not config:
        config = GameConfig(id=SINGLETON_ID)
        db.add(config)
        db.commit()
        db.refresh(config)
    return config


def get_or_create_state(db) -> GameState:
    """Tek casino oyun durumunu getirir, yoksa (oyun 'bitmiş' halde) oluşturur."""
    from datetime import datetime
    state = db.query(GameState).filter(GameState.id == SINGLETON_ID).first()
    if not state:
        state = GameState(
            id=SINGLETON_ID,
            start_date=datetime.now(),
            drawn_numbers=[],
            flags={"c1": False, "c2": False, "t": False, "over": True},  # start-week'e kadar kapalı
            daily_draw_count=0,
        )
        db.add(state)
        db.commit()
        db.refresh(state)
    return state
