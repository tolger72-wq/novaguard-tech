from pydantic_settings import BaseSettings
from typing import Optional
import pytz


class Settings(BaseSettings):
    # Database
    DATABASE_URL:      str = "postgresql+asyncpg://promo:promo@localhost:5432/novaguard_promo"
    DATABASE_URL_SYNC: str = "postgresql://promo:promo@localhost:5432/novaguard_promo"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Security
    SECRET_KEY:    str = "dev-secret-key"
    ADMIN_API_KEY: str = "admin-key"
    CRM_API_KEY:   str = "crm-key"

    # CORS — production'da casino domain'ini girin
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:5173", "http://localhost:8080"]

    # App
    APP_NAME: str = "NovaGuard Promo Engine"
    VERSION:  str = "1.1.0"
    DEBUG:    bool = False

    # Campaign
    CAMPAIGN_YEAR: int = 2025

    # Timezone — casino'nun bulunduğu zaman dilimi
    # Gürcistan: "Asia/Tbilisi", Türkiye: "Europe/Istanbul"
    CASINO_TIMEZONE: str = "Asia/Tbilisi"

    # E-posta (SMTP) — çekiliş sertifikasını misafire mail ile göndermek için.
    # Boş bırakılırsa e-posta özelliği devre dışı kalır (PDF indirme etkilenmez).
    SMTP_HOST:     Optional[str] = None
    SMTP_PORT:     int = 587
    SMTP_USER:     Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_FROM:     Optional[str] = None
    SMTP_USE_TLS:  bool = True

    model_config = {"env_file": ".env", "case_sensitive": True}


settings = Settings()

# Casino timezone nesnesi (eager load)
CASINO_TZ = pytz.timezone(settings.CASINO_TIMEZONE)
