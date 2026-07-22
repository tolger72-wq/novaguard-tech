"""
Minor Bulgular — Regresyon Testleri

  7. Sinir ağı artık gerçekten eğitilebiliyor (backprop) ve eğitilmemiş bir ağın
     çıktısı karar motoru tarafından "AI kararı" olarak sunulmuyor.
  8. CORS origin listesi artık NANS_CORS_ORIGINS ile yapılandırılabiliyor.
  9. Aynı lisansa eşzamanlı istekler artık bir kilit altında sıralanıyor.
  10. check_in()'in KRİTİK dalı artık suspend()'i (kendi webhook'unu kendi
      içinde gönderen) çağırmıyor — bu, RLock reentrant olduğu için check_in'in
      DIŞ kilidi tutuluyorken bir ağ çağrısı yapılmasına (ve dolayısıyla aynı
      ürünün TÜM DİĞER lisanslarının bloklanmasına) yol açıyordu.
"""
import threading
import time

import pytest

from main import (
    FeedforwardNet, LicenseManager, LimbicSystem, PrefrontalCortex,
    ProductBrain, _load_cors_origins,
)


# ── 7. Sinir ağı eğitimi ───────────────────────────────────────────────────────

def test_untrained_network_reports_trained_examples_zero():
    net = FeedforwardNet(input_size=2, hidden_size=4, output_size=1)
    assert net.trained_examples == 0
    assert net.last_loss is None


def test_training_reduces_loss():
    """Backprop gerçekten çalışıyorsa, aynı basit örnek üzerinde kayıp düşmeli."""
    net = FeedforwardNet(input_size=2, hidden_size=4, output_size=1, seed=7)
    examples = [
        ([0.0, 0.0], [0.0]),
        ([1.0, 1.0], [1.0]),
        ([1.0, 0.0], [0.5]),
        ([0.0, 1.0], [0.5]),
    ]
    loss_after_few = net.train(examples, epochs=5, lr=0.3)

    net2 = FeedforwardNet(input_size=2, hidden_size=4, output_size=1, seed=7)
    loss_after_many = net2.train(examples, epochs=400, lr=0.3)

    assert loss_after_many < loss_after_few, "Daha uzun eğitim kaybı azaltmalı — backprop gerçek olmalı"
    assert net2.trained_examples == len(examples)


def test_trained_network_persists_across_save_load(tmp_path, monkeypatch):
    import main as m
    monkeypatch.setattr(m, "DATA_DIR", tmp_path)

    brain = ProductBrain("test-product")
    brain.neural_networks["risk"] = FeedforwardNet(2, 4, 1, seed=3)
    brain.neural_networks["risk"].train([([1.0, 0.0], [1.0])], epochs=50, lr=0.2)
    trained_w1 = brain.neural_networks["risk"].w1
    brain.save()

    brain2 = ProductBrain("test-product")
    brain2.load()

    assert "risk" in brain2.neural_networks
    assert brain2.neural_networks["risk"].trained_examples == 1
    assert brain2.neural_networks["risk"].w1 == trained_w1, "Eğitilmiş ağırlıklar restart'ta kaybolmamalı"


def test_prefrontal_cortex_refuses_untrained_neural_result():
    """Eğitilmemiş bir ağın çıktısı karar olarak sunulmamalı — STANDART_ISLEM'e düşmeli."""
    cortex = PrefrontalCortex()
    untrained_result = {"task_id": "x", "prediction": [0.83], "confidence": 0.83, "trained": False}
    d = cortex.decide(reflex=None, risk={"risk_level": "DÜŞÜK"}, habit=None, neural_result=untrained_result)
    assert d["action"] != "NEURAL_ONERI"
    assert d["action"] == "STANDART_ISLEM"


def test_prefrontal_cortex_uses_trained_neural_result():
    cortex = PrefrontalCortex()
    trained_result = {"task_id": "x", "prediction": [0.83], "confidence": 0.83, "trained": True}
    d = cortex.decide(reflex=None, risk={"risk_level": "DÜŞÜK"}, habit=None, neural_result=trained_result)
    assert d["action"] == "NEURAL_ONERI"


# ── 8. CORS yapılandırması ─────────────────────────────────────────────────────

def test_cors_defaults_to_wildcard_when_unset(monkeypatch):
    monkeypatch.delenv("NANS_CORS_ORIGINS", raising=False)
    assert _load_cors_origins() == ["*"]


def test_cors_reads_comma_separated_origins(monkeypatch):
    monkeypatch.setenv(
        "NANS_CORS_ORIGINS",
        "https://admin.novaguard.example, https://panel.novaguard.example",
    )
    origins = _load_cors_origins()
    assert origins == ["https://admin.novaguard.example", "https://panel.novaguard.example"]


# ── 9. Eşzamanlılık kilidi ─────────────────────────────────────────────────────

def test_concurrent_check_ins_do_not_lose_usage_log_entries():
    """
    Kilit olmadan, aynı lisansa eşzamanlı gelen check-in'ler usage_log'a
    yazarken birbirini ezebilir (klasik read-modify-write yarışı). 50 thread'in
    hepsinin kaydı görünür olmalı.
    """
    lm = LicenseManager(LimbicSystem())
    lm.create_license("LIC-RACE", "Race Test Customer", "enterprise", max_devices=100, expires_at=None)

    def do_check_in(i):
        lm.check_in("LIC-RACE", device_id=f"device-{i}")

    threads = [threading.Thread(target=do_check_in, args=(i,)) for i in range(50)]
    for t in threads: t.start()
    for t in threads: t.join()

    assert len(lm.licenses["LIC-RACE"].usage_log) == 50


def test_concurrent_create_license_only_one_wins():
    """Aynı lisans anahtarıyla eşzamanlı iki oluşturma isteğinden sadece biri başarılı olmalı."""
    lm = LicenseManager(LimbicSystem())
    results = []
    lock = threading.Lock()

    def try_create():
        try:
            lm.create_license("LIC-DUP", "Customer", "basic", 1, None)
            with lock: results.append("ok")
        except ValueError:
            with lock: results.append("rejected")

    threads = [threading.Thread(target=try_create) for _ in range(20)]
    for t in threads: t.start()
    for t in threads: t.join()

    assert results.count("ok") == 1, "Sadece bir oluşturma başarılı olmalı, geri kalanı reddedilmeli"
    assert results.count("rejected") == 19


# ── 10. KRİTİK askıya alma, ürünün diğer lisanslarını bloklamamalı ────────────

def test_critical_suspend_does_not_hold_lock_during_webhook(monkeypatch):
    """
    check_in() KRİTİK risk tespit ettiğinde eskiden self.suspend()'i çağırıyordu;
    suspend() webhook'unu kendi gövdesinde gönderir, ve RLock reentrant olduğu
    için bu ağ çağrısı check_in'in DIŞ kilidi (ürün başına, lisans başına değil)
    HÂLÂ tutuluyorken gerçekleşiyordu. Yavaş/erişilemeyen bir webhook, o zaman
    aynı ürünün TÜM DİĞER lisanslarını (check-in/renew/suspend) HTTP timeout'u
    kadar bloklardı. Bu test, KRİTİK yoldaki webhook çağrısı devam ederken
    BAŞKA bir lisansa yapılan check-in'in hemen dönmesi gerektiğini doğrular.
    """
    import main as main_module

    call_started = threading.Event()
    release_call = threading.Event()

    def slow_webhook(url, payload):
        call_started.set()
        release_call.wait(timeout=2)
        return {"status": 200}

    monkeypatch.setattr(main_module, "_send_webhook", slow_webhook)

    lm = LicenseManager(LimbicSystem(), alert_webhook_url="http://example.test/hook")

    # KRİTİK risk tetikleyecek kadar cihaz VE kullanım aşımı (bkz. LimbicSystem
    # ağırlıkları: financial 0.4 + operational 0.3 >= 0.7 eşiği).
    lm.create_license("CRITICAL", "Kritik Musteri", "basic", max_devices=1, expires_at=None)
    lic = lm.licenses["CRITICAL"]
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%S")
    lic.known_devices = {f"dev-{i}": now_iso for i in range(5)}
    lic.usage_log = [{"device_id": "x", "ip": None, "timestamp": now_iso} for _ in range(200)]

    lm.create_license("OTHER", "Diger Musteri", "basic", max_devices=5, expires_at=None)

    def trigger_critical():
        lm.check_in("CRITICAL", device_id="dev-new")

    t = threading.Thread(target=trigger_critical)
    t.start()
    assert call_started.wait(timeout=1), "Webhook hiç başlamadı — test kurulumunu kontrol edin"

    started = time.monotonic()
    lm.check_in("OTHER", device_id="other-dev")
    elapsed = time.monotonic() - started

    release_call.set()
    t.join(timeout=2)

    assert elapsed < 0.3, (
        f"OTHER lisansına check-in {elapsed:.2f}s sürdü — KRİTİK yoldaki webhook "
        "hâlâ paylaşılan LicenseManager kilidini tutuyor olmalı."
    )
