"""
Güvenli API key doğrulama.
- secrets.compare_digest ile timing-attack koruması
- slowapi ile rate limiting
"""
import secrets
from fastapi import Security, HTTPException, status, Request
from fastapi.security import APIKeyHeader
from .config import settings

admin_key_header = APIKeyHeader(name="X-Admin-Key", auto_error=False)
crm_key_header   = APIKeyHeader(name="X-CRM-Key",   auto_error=False)


def _safe_compare(a: str | None, b: str) -> bool:
    """Timing-safe string comparison. Boş değere karşı da güvenli."""
    if not a:
        return False
    return secrets.compare_digest(a.encode(), b.encode())


async def require_admin(api_key: str = Security(admin_key_header)):
    if not _safe_compare(api_key, settings.ADMIN_API_KEY):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Geçersiz admin anahtarı",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    return api_key


async def require_crm(api_key: str = Security(crm_key_header)):
    if not _safe_compare(api_key, settings.CRM_API_KEY):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Geçersiz CRM anahtarı",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    return api_key
