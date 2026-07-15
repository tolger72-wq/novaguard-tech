"""
NovaGuard Promo Engine v1.1
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .core.config import settings
from .database import init_db
from .routers import sessions, draws, admin, display, analytics


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
    description="""
## NovaGuard Promosyon Motoru

### Kimlik Doğrulama
- CRM endpointleri: `X-CRM-Key` header
- Admin endpointleri: `X-Admin-Key` header
- Display / WebSocket: açık (iç ağda kullanılır)

### Temel Akış
1. CRM → `POST /api/v1/sessions/push`
2. Oturum kapandı → `PATCH /api/v1/sessions/{id}/end` → biletler hesaplanır
3. Admin çekiliş programlar → `POST /api/v1/draws/schedule`
4. Admin çekilişi yürütür → `POST /api/v1/draws/{id}/execute`
5. Display real-time güncelleme → `WS /api/v1/draws/ws`
    """,
    lifespan=lifespan,
)

# CORS — production'da settings.CORS_ORIGINS kullanılır
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS if not settings.DEBUG else ["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
    allow_headers=["*"],
)

# Routers
app.include_router(sessions.router, prefix="/api/v1")
app.include_router(draws.router,    prefix="/api/v1")
app.include_router(admin.router,    prefix="/api/v1")
app.include_router(display.router,   prefix="/api/v1")
app.include_router(analytics.router, prefix="/api/v1")


@app.get("/", tags=["Health"])
async def root():
    return {"service": settings.APP_NAME, "version": settings.VERSION, "status": "running"}


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok", "timezone": settings.CASINO_TIMEZONE, "campaign_year": settings.CAMPAIGN_YEAR}
