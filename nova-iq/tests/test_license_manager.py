"""
Lisans/Ödeme Takibi — Regresyon Testleri

Bu testler, kod incelemesinde bulunan ve düzeltilen dört sorunu belgeler:
  1. Bozuk bir expires_at, TÜM lisans taramasını çökertip diğer tüm
     ürünlerin/lisansların süre kontrolünü sessizce durdurmamalı.
  2. known_devices hiç küçülmediği için normal cihaz değişimi (yeni bilgisayar,
     format vb.) sadık bir müşteriyi kalıcı olarak kilitlememeli.
  3. API anahtarı karşılaştırmaları sabit zamanlı olmalı (timing attack).
  4. /renew tutar bildirmeden (denetim izi boş kalacak şekilde) geçmemeli.
"""
from datetime import datetime, timedelta

import pytest
from pydantic import ValidationError

from main import (
    LicenseManager, LimbicSystem, ProductRegistry,
    LicenseCreateRequest, LicenseRenewRequest,
)


def make_manager() -> LicenseManager:
    return LicenseManager(LimbicSystem())


# ── 1. Bozuk tarih tüm taramayı çökertmemeli ──────────────────────────────────

def test_sweep_survives_one_bad_expiry_and_processes_the_rest():
    lm = make_manager()
    lm.create_license("BAD", "Bad Customer", "basic", 1, expires_at="not-a-real-date")
    lm.create_license("EXPIRED", "Expired Customer", "basic", 1,
                       expires_at="2020-01-01T00:00:00")

    events = lm.sweep_expiries()

    assert lm.licenses["EXPIRED"].status == "grace", (
        "Bozuk tarihli bir lisans, süresi gerçekten dolmuş başka bir lisansın "
        "taranmasını engellememeli"
    )
    assert any(e["event"] == "sweep_error" for e in events)
    assert any(e["event"] == "grace_started" for e in events)


def test_expires_at_rejected_at_api_boundary_not_deferred_to_cron_crash():
    """Bozuk tarih artık istek anında 422 ile reddedilmeli, cron'a ertelenmemeli."""
    with pytest.raises(ValidationError):
        LicenseCreateRequest(license_key="X", customer_name="Y", plan="basic",
                              expires_at="not-a-real-date")


# ── 2. Cihaz değişimi kalıcı kilitlemeye yol açmamalı ─────────────────────────

def test_normal_device_turnover_does_not_permanently_suspend_license():
    lm = make_manager()
    lm.create_license("LIC", "Legit Customer", "pro", max_devices=1, expires_at=None)

    for i in range(5):
        result = lm.check_in("LIC", device_id=f"device-{i}")

    assert lm.licenses["LIC"].status == "active", (
        "Zaman içinde birkaç farklı cihaz kullanmak (normal cihaz değişimi) "
        "lisansı otomatik askıya almamalı"
    )


def test_devices_not_seen_in_30_days_do_not_count_toward_device_limit():
    lm = make_manager()
    lm.create_license("LIC", "Old Customer", "pro", max_devices=1, expires_at=None)
    lic = lm.licenses["LIC"]

    old_ts = (datetime.now() - timedelta(days=45)).isoformat()
    lic.known_devices = {f"old-device-{i}": old_ts for i in range(4)}

    result = lm.check_in("LIC", device_id="current-device")

    assert lic.active_device_ids() == ["current-device"]
    assert result["status"] == "active"
    assert result["risk"]["risk_level"] == "DÜŞÜK"


def test_deregister_device_removes_it_immediately():
    lm = make_manager()
    lm.create_license("LIC", "Customer", "pro", max_devices=2, expires_at=None)
    lm.check_in("LIC", device_id="dev-1")

    result = lm.deregister_device("LIC", "dev-1")

    assert result["status"] == "cihaz kaldırıldı"
    assert "dev-1" not in lm.licenses["LIC"].known_devices


def test_load_storage_migrates_legacy_list_shaped_known_devices():
    """Eski formatta (düz liste) kaydedilmiş verinin yüklenmesi çökmemeli."""
    lm = make_manager()
    lm.load_storage({
        "LIC": {
            "license_key": "LIC", "customer_name": "Legacy Customer", "plan": "basic",
            "max_devices": 3, "known_devices": ["dev-a", "dev-b"],
        }
    })
    lic = lm.licenses["LIC"]
    assert set(lic.known_devices.keys()) == {"dev-a", "dev-b"}
    # Eski veri çökmeden active_device_ids() üzerinden okunabilmeli
    assert isinstance(lic.active_device_ids(), list)


# ── 3. Sabit zamanlı anahtar karşılaştırması ──────────────────────────────────

def test_verify_key_uses_constant_time_comparison(monkeypatch):
    calls = []
    import main as main_module
    real_compare = main_module.secrets.compare_digest

    def spy(a, b):
        calls.append((a, b))
        return real_compare(a, b)

    monkeypatch.setattr(main_module.secrets, "compare_digest", spy)

    registry = ProductRegistry.__new__(ProductRegistry)
    from threading import Lock
    registry._lock = Lock()
    registry.brains = {}
    registry.api_keys = {"demo": main_module.hashlib.sha256(b"correct-key").hexdigest()}

    assert registry.verify_key("demo", "correct-key") is True
    assert registry.verify_key("demo", "wrong-key") is False
    assert len(calls) == 2, "verify_key artık secrets.compare_digest kullanmalı"


# ── 4. /renew tutar bildirmeden geçmemeli ─────────────────────────────────────

def test_renew_request_requires_amount():
    with pytest.raises(ValidationError):
        LicenseRenewRequest(new_expires_at="2027-01-01T00:00:00", payment_method="bank_transfer")


def test_renew_request_accepts_valid_amount():
    req = LicenseRenewRequest(
        new_expires_at="2027-01-01T00:00:00", payment_method="card", amount=499.0,
    )
    assert req.amount == 499.0
