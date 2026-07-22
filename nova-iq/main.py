"""
╔══════════════════════════════════════════════════════════════════╗
║  NOVA IQ (Nans_Core) SERVICE — Karar, Otomasyon,                  ║
║  Lisans Davranış Analizi + Süre/Ödeme Takibi                      ║
╠══════════════════════════════════════════════════════════════════╣
║  Kurulum:                                                          ║
║    pip install fastapi "uvicorn[standard]" apscheduler pydantic   ║
║  Çalıştırma:                                                       ║
║    python main.py                                                  ║
╚══════════════════════════════════════════════════════════════════╝
"""

import hashlib
import json
import logging
import math
import os
import random
import secrets
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from threading import Lock, RLock
from typing import Dict, List, Optional

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, Header, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field


# ══════════════════════════════════════════════════════════════
#  AYARLAR
# ══════════════════════════════════════════════════════════════

DATA_DIR = Path("./nans_data")
DATA_DIR.mkdir(exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("NovaIQ")


def _atomic_write(path: Path, content: str) -> None:
    """Yazma sırasında çökme olursa dosyayı yarım/bozuk bırakmamak için
    önce geçici dosyaya yazıp sonra atomik biçimde yerine taşır."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)


def _load_or_create_master_key() -> str:
    """
    NANS_MASTER_KEY ortam değişkeni PRODÜKSİYONDA her zaman verilmeli.
    Verilmemişse: her restart'ta YENİ bir anahtar üretmek yerine (bu, bir
    çökme/restart sonrası admin'i kendi panelinden kilitler), diskte
    kalıcı bir anahtar oluşturup bir sonraki başlangıçta onu okuyoruz.
    """
    env_key = os.environ.get("NANS_MASTER_KEY")
    if env_key:
        return env_key

    key_path = DATA_DIR / "_master_key.txt"
    if key_path.exists():
        existing = key_path.read_text(encoding="utf-8").strip()
        if existing:
            logger.warning(
                f"⚠️  NANS_MASTER_KEY ayarlanmamış! {key_path} dosyasındaki kalıcı "
                f"geçici anahtar kullanılıyor. Prodüksiyonda ortam değişkenini ayarlayın."
            )
            return existing

    new_key = secrets.token_hex(16)
    _atomic_write(key_path, new_key)
    logger.warning(
        f"⚠️  NANS_MASTER_KEY ayarlanmamış! Yeni geçici anahtar üretildi ve "
        f"{key_path} dosyasına kaydedildi (restart'larda bu dosyadan okunacak): {new_key}"
    )
    return new_key


MASTER_API_KEY = _load_or_create_master_key()


def _load_cors_origins() -> List[str]:
    """
    NANS_CORS_ORIGINS — virgülle ayrılmış izinli origin listesi, örn.
    "https://admin.novaguard.example,https://panel.novaguard.example".
    Ayarlanmazsa "*" (herkese açık) kullanılır — kimlik doğrulama header
    bazlı olduğu (çerez değil) için düşük risklidir, ama prodüksiyonda
    daraltılması önerilir.
    """
    raw = os.environ.get("NANS_CORS_ORIGINS")
    if not raw:
        logger.warning(
            "⚠️  NANS_CORS_ORIGINS ayarlanmamış! CORS herkese açık (*) — "
            "prodüksiyonda admin panelinizin adresine daraltmanız önerilir."
        )
        return ["*"]
    return [o.strip() for o in raw.split(",") if o.strip()]


CORS_ORIGINS = _load_cors_origins()


# ══════════════════════════════════════════════════════════════
#  BÖLÜM 1 — NEURAL LAYER
# ══════════════════════════════════════════════════════════════

def _sigmoid(x: float) -> float:
    try:
        return 1.0 / (1.0 + math.exp(-x))
    except OverflowError:
        return 0.0 if x < 0 else 1.0


def _sigmoid_deriv(y: float) -> float:
    """y, sigmoid'in ÇIKTISI (zaten hesaplanmış aktivasyon) — türev y*(1-y)."""
    return y * (1.0 - y)


class FeedforwardNet:
    """
    Tek gizli katmanlı, sigmoid aktivasyonlu basit bir ileri beslemeli ağ.
    train() ile gerçek gradyan inişi/geri yayılım yapılabilir — eğitilmeden
    sadece rastgele (ama sabit tohumlu, tekrarlanabilir) ağırlıklarla kurulur;
    /neural/predict eğitim yapılmadan çağrılırsa bu, anlamlı bir tahmin değil,
    rastgele bir çıktı döner (bkz. app'ta /neural/train endpoint'i).
    """
    def __init__(self, input_size: int, hidden_size: int, output_size: int, seed: int = 42):
        rnd = random.Random(seed)
        self.w1 = [[rnd.uniform(-1, 1) for _ in range(hidden_size)] for _ in range(input_size)]
        self.b1 = [rnd.uniform(-1, 1) for _ in range(hidden_size)]
        self.w2 = [[rnd.uniform(-1, 1) for _ in range(output_size)] for _ in range(hidden_size)]
        self.b2 = [rnd.uniform(-1, 1) for _ in range(output_size)]
        self.input_size = input_size
        self.hidden_size = hidden_size
        self.output_size = output_size
        self.trained_examples = 0
        self.last_loss: Optional[float] = None

    def _forward(self, inputs: List[float]) -> tuple[List[float], List[float]]:
        if len(inputs) != self.input_size:
            raise ValueError(f"Beklenen giriş boyutu {self.input_size}, alınan {len(inputs)}")
        hidden = []
        for h in range(self.hidden_size):
            total = self.b1[h]
            for i in range(self.input_size):
                total += inputs[i] * self.w1[i][h]
            hidden.append(_sigmoid(total))
        outputs = []
        for o in range(self.output_size):
            total = self.b2[o]
            for h in range(self.hidden_size):
                total += hidden[h] * self.w2[h][o]
            outputs.append(_sigmoid(total))
        return hidden, outputs

    def predict(self, inputs: List[float]) -> List[float]:
        _, outputs = self._forward(inputs)
        return outputs

    def _train_step(self, inputs: List[float], targets: List[float], lr: float) -> float:
        """Tek örnek üzerinde bir gradyan inişi adımı (klasik backprop). MSE kaybını döner."""
        if len(targets) != self.output_size:
            raise ValueError(f"Beklenen hedef boyutu {self.output_size}, alınan {len(targets)}")
        hidden, outputs = self._forward(inputs)

        # Çıkış katmanı hatası: dL/dz_o = (output - target) * sigmoid'(output)
        output_delta = [(outputs[o] - targets[o]) * _sigmoid_deriv(outputs[o]) for o in range(self.output_size)]
        loss = sum((outputs[o]-targets[o])**2 for o in range(self.output_size)) / self.output_size

        # Gizli katman hatası: dL/dz_h = (W2 · output_delta) * sigmoid'(hidden)
        hidden_delta = []
        for h in range(self.hidden_size):
            grad = sum(self.w2[h][o] * output_delta[o] for o in range(self.output_size))
            hidden_delta.append(grad * _sigmoid_deriv(hidden[h]))

        # Ağırlık/bias güncellemeleri
        for h in range(self.hidden_size):
            for o in range(self.output_size):
                self.w2[h][o] -= lr * hidden[h] * output_delta[o]
        for o in range(self.output_size):
            self.b2[o] -= lr * output_delta[o]

        for i in range(self.input_size):
            for h in range(self.hidden_size):
                self.w1[i][h] -= lr * inputs[i] * hidden_delta[h]
        for h in range(self.hidden_size):
            self.b1[h] -= lr * hidden_delta[h]

        return loss

    def train(self, examples: List[tuple[List[float], List[float]]], epochs: int = 200, lr: float = 0.15) -> float:
        """
        examples: [(inputs, targets), ...] — etiketli örnekler (ör. geçmişte insan onayı
        gerektiren/gerektirmeyen kararlar). epochs kadar tüm veri seti üzerinden geçer.
        Son epoch'un ortalama kaybını döner (düşüyorsa ağ gerçekten öğreniyor demektir).
        """
        if not examples:
            raise ValueError("En az bir eğitim örneği gerekli")
        avg_loss = 0.0
        for _ in range(epochs):
            total = 0.0
            for inputs, targets in examples:
                total += self._train_step(inputs, targets, lr)
            avg_loss = total / len(examples)
        self.trained_examples += len(examples)
        self.last_loss = avg_loss
        return avg_loss

    def to_dict(self) -> Dict:
        return {
            "input_size": self.input_size, "hidden_size": self.hidden_size, "output_size": self.output_size,
            "w1": self.w1, "b1": self.b1, "w2": self.w2, "b2": self.b2,
            "trained_examples": self.trained_examples, "last_loss": self.last_loss,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "FeedforwardNet":
        net = cls(d["input_size"], d["hidden_size"], d["output_size"])
        net.w1, net.b1, net.w2, net.b2 = d["w1"], d["b1"], d["w2"], d["b2"]
        net.trained_examples = d.get("trained_examples", 0)
        net.last_loss = d.get("last_loss")
        return net


# ══════════════════════════════════════════════════════════════
#  BÖLÜM 2 — 6 BEYİN KATMANI
# ══════════════════════════════════════════════════════════════

class BrainStem:
    def __init__(self):
        self.rules: Dict[str, Dict] = {}
        self.reflex_count = 0

    def register_rule(self, name: str, field: str, op: str, value: float):
        self.rules[name] = {"field": field, "op": op, "value": value}

    def check(self, context: Dict) -> Optional[str]:
        for name, rule in self.rules.items():
            val = context.get(rule["field"])
            if val is None:
                continue
            op, target = rule["op"], rule["value"]
            triggered = (
                (op == ">" and val > target) or (op == "<" and val < target) or
                (op == "==" and val == target) or (op == ">=" and val >= target) or
                (op == "<=" and val <= target)
            )
            if triggered:
                self.reflex_count += 1
                return name
        return None


class BasalGanglia:
    def __init__(self, habit_threshold: int = 5):
        self.action_history: Dict[str, List] = {}
        self.habits: Dict[str, str] = {}
        self.habit_threshold = habit_threshold

    def record(self, action_key: str, outcome: str):
        self.action_history.setdefault(action_key, []).append(outcome)
        recent = self.action_history[action_key][-self.habit_threshold:]
        if len(recent) >= self.habit_threshold and len(set(recent)) == 1:
            self.habits[action_key] = recent[-1]

    def suggest(self, action_key: str) -> Optional[str]:
        return self.habits.get(action_key)


class Hippocampus:
    def __init__(self, max_memories: int = 2000):
        self.memories: List[Dict] = []
        self.max_memories = max_memories

    def store(self, category: str, data: Dict, importance: int = 1):
        self.memories.append({
            "category": category, "data": data, "importance": importance,
            "timestamp": datetime.now().isoformat(),
        })
        if len(self.memories) > self.max_memories:
            self.memories = self.memories[-self.max_memories:]

    def recall(self, category: Optional[str] = None, limit: int = 20) -> List[Dict]:
        results = self.memories
        if category:
            results = [m for m in results if m["category"] == category]
        return list(reversed(results))[:limit]


class LimbicSystem:
    def __init__(self):
        self.weights = {"financial": 0.4, "operational": 0.3, "reputational": 0.3}

    def evaluate(self, factors: Dict[str, float]) -> Dict:
        score = sum(factors.get(k, 0.0) * w for k, w in self.weights.items())
        if score >= 0.7:
            level = "KRİTİK"
        elif score >= 0.4:
            level = "YÜKSEK"
        elif score >= 0.2:
            level = "ORTA"
        else:
            level = "DÜŞÜK"
        return {"risk_score": round(score, 3), "risk_level": level}


class PrefrontalCortex:
    def decide(self, reflex, risk, habit, neural_result) -> Dict:
        if reflex:
            d = {"action": "ACIL_MUDAHALE", "reason": f"Refleks: {reflex}", "confidence": 1.0}
        elif risk.get("risk_level") == "KRİTİK":
            d = {"action": "INSAN_ONAYI_GEREKLI", "reason": "Kritik risk", "confidence": 0.9}
        elif habit is not None:
            d = {"action": habit, "reason": "Öğrenilmiş alışkanlık", "confidence": 0.75}
        elif neural_result and neural_result.get("trained"):
            # Eğitilmemiş bir ağın (rastgele ağırlıklar) çıktısı bir karara dönüştürülmez —
            # bkz. FeedforwardNet.train / POST /neural/train. Aksi halde "NEURAL_ONERI"
            # etiketiyle sunulan şey aslında gürültüden ibaret olurdu.
            d = {"action": "NEURAL_ONERI", "reason": "Sinir ağı tahmini",
                 "confidence": neural_result.get("confidence", 0.5), "detail": neural_result}
        else:
            d = {"action": "STANDART_ISLEM", "reason": "Varsayılan", "confidence": 0.5}
        d["timestamp"] = datetime.now().isoformat()
        return d


# ══════════════════════════════════════════════════════════════
#  BÖLÜM 3 — DEKLARATİF OTOMASYON
# ══════════════════════════════════════════════════════════════

class AutomationRule:
    def __init__(self, rule_id: str, name: str, interval_seconds: int,
                 action_type: str, action_config: Dict):
        self.rule_id = rule_id
        self.name = name
        self.interval_seconds = interval_seconds
        self.action_type = action_type
        self.action_config = action_config
        self.is_active = True
        self.run_count = 0
        self.error_count = 0
        self.last_run: Optional[str] = None
        self.last_result: Optional[Dict] = None

    def execute(self) -> Dict:
        try:
            if self.action_type == "log":
                filepath = self.action_config.get("filepath", "nans_automation.log")
                with open(filepath, "a", encoding="utf-8") as f:
                    f.write(f"[{datetime.now().isoformat()}] Kural çalıştı: {self.rule_id}\n")
                result = {"logged": True, "file": filepath}
            elif self.action_type == "webhook":
                result = _send_webhook(self.action_config["url"], {"rule_id": self.rule_id})
            else:
                result = {"error": f"Bilinmeyen aksiyon tipi: {self.action_type}"}

            self.run_count += 1
            self.last_run = datetime.now().isoformat()
            self.last_result = result
            return {"success": True, "result": result}
        except Exception as e:
            self.error_count += 1
            self.last_result = {"error": str(e)}
            logger.error(f"Otomasyon hatası [{self.rule_id}]: {e}")
            return {"success": False, "error": str(e)}

    def to_dict(self) -> Dict:
        return {
            "rule_id": self.rule_id, "name": self.name, "interval_seconds": self.interval_seconds,
            "action_type": self.action_type, "is_active": self.is_active,
            "run_count": self.run_count, "error_count": self.error_count,
            "last_run": self.last_run, "last_result": self.last_result,
        }


def _send_webhook(url: str, payload: Dict) -> Dict:
    try:
        data = json.dumps({**payload, "sent_at": datetime.now().isoformat()}).encode()
        req = urllib.request.Request(url, data=data, method="POST",
                                      headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return {"status": resp.status}
    except Exception as e:
        logger.error(f"Webhook gönderilemedi: {e}")
        return {"error": str(e)}


# ══════════════════════════════════════════════════════════════
#  BÖLÜM 4 — LİSANS + SÜRE + ÖDEME TAKİBİ
# ══════════════════════════════════════════════════════════════
#
#  Akış:
#   ACTIVE --(süre dolar)--> GRACE (ödeme bekleme süresi) --(grace de dolar)--> SUSPENDED
#   GRACE veya SUSPENDED --(/renew çağrılır, ödeme onaylanınca)--> ACTIVE
#
#  Gerçek ödeme tahsilatı (kart/USDT) bu serviste YAPILMAZ. Kart için Stripe/iyzico gibi
#  bir sağlayıcı, USDT için bir cüzdan/blockchain izleme servisi SİZİN tarafınızda
#  ödemeyi doğrular; doğrulandığında bu servisin /renew endpoint'ini çağırırsınız
#  (kendi webhook handler'ınızdan, veya manuel olarak banka transferinde).
# ══════════════════════════════════════════════════════════════

class LicenseStatus:
    ACTIVE = "active"
    GRACE = "grace"            # süresi doldu, ödeme bekleniyor
    SUSPENDED = "suspended"
    CANCELLED = "cancelled"


class PaymentMethod:
    BANK_TRANSFER = "bank_transfer"
    CARD = "card"
    USDT = "usdt"


class License:
    # Bir cihaz bu kadar gündür check-in yapmadıysa "aktif cihaz" sayılmaz —
    # cihaz_sayısı = "şu an kullanılan cihaz sayısı" demek, "bugüne dek görülen
    # TÜM cihazlar" demek değil. Aksi halde normal cihaz değişimi (yeni laptop,
    # format vb.) zamanla lisansı kalıcı olarak "aşırı kullanım" bölgesine iter.
    DEVICE_ACTIVE_WINDOW_DAYS = 30

    def __init__(self, license_key: str, customer_name: str, plan: str,
                 max_devices: int, expires_at: Optional[str] = None,
                 grace_days: int = 7):
        self.license_key = license_key
        self.customer_name = customer_name
        self.plan = plan
        self.max_devices = max_devices
        self.expires_at = expires_at
        self.grace_days = grace_days
        self.grace_started_at: Optional[str] = None
        self.status = LicenseStatus.ACTIVE
        self.created_at = datetime.now().isoformat()
        self.known_devices: Dict[str, str] = {}   # device_id -> son görülme (ISO)
        self.usage_log: List[Dict] = []
        self.suggestion: Optional[str] = None
        self.payment_method: Optional[str] = None
        self.last_payment_at: Optional[str] = None
        self.payment_history: List[Dict] = []

    def is_past_expiry(self) -> bool:
        if not self.expires_at:
            return False
        return datetime.fromisoformat(self.expires_at) < datetime.now()

    def grace_deadline(self) -> Optional[datetime]:
        if not self.grace_started_at:
            return None
        return datetime.fromisoformat(self.grace_started_at) + timedelta(days=self.grace_days)

    def active_device_ids(self, window_days: Optional[int] = None) -> List[str]:
        """Son N gün içinde check-in yapmış cihazlar — 'şu an kullanılan' cihaz sayısı budur."""
        window_days = self.DEVICE_ACTIVE_WINDOW_DAYS if window_days is None else window_days
        cutoff = datetime.now() - timedelta(days=window_days)
        active = []
        for device_id, last_seen in self.known_devices.items():
            try:
                if datetime.fromisoformat(last_seen) > cutoff:
                    active.append(device_id)
            except (TypeError, ValueError):
                continue
        return active

    def to_dict(self) -> Dict:
        return {
            "license_key": self.license_key, "customer_name": self.customer_name,
            "plan": self.plan, "max_devices": self.max_devices, "status": self.status,
            "expires_at": self.expires_at, "grace_days": self.grace_days,
            "grace_started_at": self.grace_started_at, "created_at": self.created_at,
            "known_device_count": len(self.active_device_ids()),
            "known_device_count_all_time": len(self.known_devices),
            "usage_count_recent": len(self.usage_log),
            "suggestion": self.suggestion,
            "payment_method": self.payment_method, "last_payment_at": self.last_payment_at,
        }


class LicenseManager:
    PLAN_USAGE_LIMITS = {"basic": 50, "pro": 300, "enterprise": 2000}

    def __init__(self, limbic: LimbicSystem, alert_webhook_url: Optional[str] = None):
        self.licenses: Dict[str, License] = {}
        self.limbic = limbic
        self.alert_webhook_url = alert_webhook_url
        # Aynı lisansa eşzamanlı check-in/renew/suspend istekleri gelirse (birden
        # fazla thread'de işlenen istekler) durum güncellemeleri birbirini
        # ezmesin diye tüm mutasyonlar bu kilit altında yapılır. RLock: check_in
        # kritik risk durumunda kendi içinde _suspend_locked()'i çağırıyor — aynı
        # thread'in kilidi yeniden alabilmesi (deadlock olmadan) gerekiyor. Webhook
        # gönderimi gibi ağ I/O'su KİLİT DIŞINDA yapılır — aksi halde yavaş/
        # erişilemeyen bir webhook, bu ürünün TÜM lisanslarına gelen diğer
        # istekleri bloklardı (bkz. suspend/_suspend_locked ve check_in).
        self._lock = RLock()

    def create_license(self, license_key: str, customer_name: str, plan: str,
                        max_devices: int, expires_at: Optional[str], grace_days: int = 7) -> License:
        with self._lock:
            if license_key in self.licenses:
                raise ValueError("Bu lisans zaten kayıtlı")
            lic = License(license_key, customer_name, plan, max_devices, expires_at, grace_days)
            self.licenses[license_key] = lic
            return lic

    def _suspend_locked(self, lic: "License") -> None:
        """suspend()'in durum-değişikliği kısmı — çağıran zaten self._lock'u
        tutuyorken kullanılır (I/O yapmaz). suspend() ve check_in()'in KRİTİK
        dalı bunu paylaşır; her ikisi de webhook'u kendi kilit kapsamları
        DIŞINDA gönderir (bkz. suspend() ve check_in())."""
        lic.status = LicenseStatus.SUSPENDED

    def suspend(self, license_key: str, reason: str) -> Dict:
        with self._lock:
            lic = self.licenses.get(license_key)
            if not lic:
                return {"error": "Lisans bulunamadı"}
            self._suspend_locked(lic)
            customer_name = lic.customer_name
        if self.alert_webhook_url:
            _send_webhook(self.alert_webhook_url, {
                "event": "license_suspended", "license_key": license_key,
                "customer": customer_name, "reason": reason,
            })
        return {"status": "askıya alındı", "reason": reason}

    def reactivate(self, license_key: str) -> Dict:
        with self._lock:
            lic = self.licenses.get(license_key)
            if not lic:
                return {"error": "Lisans bulunamadı"}
            lic.status = LicenseStatus.ACTIVE
            lic.grace_started_at = None
        return {"status": "yeniden aktif edildi"}

    def renew(self, license_key: str, new_expires_at: str,
              payment_method: str, amount: Optional[float] = None,
              note: Optional[str] = None) -> Dict:
        """Ödeme onaylandığında (banka/kart/USDT fark etmez) bu çağrılır."""
        with self._lock:
            lic = self.licenses.get(license_key)
            if not lic:
                return {"error": "Lisans bulunamadı"}

            lic.expires_at = new_expires_at
            lic.status = LicenseStatus.ACTIVE
            lic.grace_started_at = None
            lic.payment_method = payment_method
            lic.last_payment_at = datetime.now().isoformat()
            lic.payment_history.append({
                "date": lic.last_payment_at, "method": payment_method,
                "amount": amount, "note": note, "new_expires_at": new_expires_at,
            })
            lic.payment_history = lic.payment_history[-50:]
            lic_dict = lic.to_dict()

        if self.alert_webhook_url:
            _send_webhook(self.alert_webhook_url, {
                "event": "license_renewed", "license_key": license_key,
                "customer": lic_dict["customer_name"], "method": payment_method,
                "new_expires_at": new_expires_at,
            })
        return {"status": "yenilendi", "license": lic_dict}

    def sweep_expiries(self) -> List[Dict]:
        """
        Günlük olarak TÜM lisansları tarar (kimse yazılımı açmasa bile çalışır):
          - Süresi yeni dolan ACTIVE lisansları GRACE'e alır + uyarı gönderir
          - GRACE süresi de dolanları SUSPENDED yapar
        Dönen liste: bu taramada etkilenen lisansların özetini içerir.
        """
        events = []
        for lic in list(self.licenses.values()):
            # Tek bir lisanstaki bozuk/eski bir tarih (ör. elle düzenlenmiş veri, eski
            # bir formattan migrasyon) tüm taramayı çökertip DİĞER TÜM ürünlerin/
            # lisansların süre kontrolünü o gün sessizce devre dışı bırakmasın diye
            # her lisans kendi try/except'inde işleniyor. Durum değişikliği kısa
            # süreli kilit altında yapılır, webhook gönderimi (yavaş olabilir)
            # kilit dışında — aynı anda gelen bir check-in/renew ile yarışmasın.
            webhook_payload = None
            should_suspend = False
            try:
                with self._lock:
                    if lic.status == LicenseStatus.ACTIVE and lic.is_past_expiry():
                        lic.status = LicenseStatus.GRACE
                        lic.grace_started_at = datetime.now().isoformat()
                        events.append({"license_key": lic.license_key, "event": "grace_started",
                                        "customer": lic.customer_name, "grace_days": lic.grace_days})
                        if self.alert_webhook_url:
                            webhook_payload = {
                                "event": "payment_reminder", "license_key": lic.license_key,
                                "customer": lic.customer_name,
                                "message": f"Lisans süresi doldu, {lic.grace_days} gün ödeme bekleme süresi başladı.",
                            }
                    elif lic.status == LicenseStatus.GRACE:
                        deadline = lic.grace_deadline()
                        should_suspend = bool(deadline and datetime.now() > deadline)

                if webhook_payload:
                    _send_webhook(self.alert_webhook_url, webhook_payload)

                if should_suspend:
                    self.suspend(lic.license_key, reason="Ödeme bekleme süresi doldu")
                    events.append({"license_key": lic.license_key, "event": "auto_suspended",
                                    "customer": lic.customer_name})
            except Exception as e:
                logger.error(f"Lisans taraması hatası [{lic.license_key}]: {e} — bu lisans atlanıyor, "
                              f"tarama diğer lisanslar için devam ediyor.")
                events.append({"license_key": lic.license_key, "event": "sweep_error",
                                "customer": lic.customer_name, "error": str(e)})
        return events

    def check_in(self, license_key: str, device_id: str, ip: Optional[str] = None) -> Dict:
        webhook_payload = None  # kilit dışında, en sonda gönderilecek (varsa)
        with self._lock:
            lic = self.licenses.get(license_key)
            if not lic:
                return {"allowed": False, "reason": "Lisans bulunamadı"}

            if lic.status == LicenseStatus.SUSPENDED:
                return {"allowed": False, "reason": "Lisans askıya alınmış (ödeme bekleniyor)"}
            if lic.status == LicenseStatus.CANCELLED:
                return {"allowed": False, "reason": "Lisans iptal edilmiş"}

            warnings = []
            if lic.status == LicenseStatus.GRACE:
                deadline = lic.grace_deadline()
                days_left = (deadline - datetime.now()).days if deadline else 0
                warnings.append(f"Ödeme bekleniyor — {max(days_left,0)} gün içinde erişim kesilecek.")

            now = datetime.now()
            lic.usage_log.append({"device_id": device_id, "ip": ip, "timestamp": now.isoformat()})
            lic.usage_log = lic.usage_log[-200:]
            lic.known_devices[device_id] = now.isoformat()

            # NOT: len(lic.known_devices) değil, active_device_ids() kullanılıyor —
            # aksi halde bugüne dek görülen HER cihaz sayılır ve normal cihaz değişimi
            # (yeni bilgisayar, format vb.) zamanla lisansı kalıcı olarak "aşırı
            # kullanım" bölgesine iter, hiç geri dönemez (bkz. License.active_device_ids).
            active_devices = lic.active_device_ids()
            device_ratio = len(active_devices) / max(lic.max_devices, 1)
            device_overuse = max(0.0, min(device_ratio - 1.0, 1.0))

            cutoff = datetime.now() - timedelta(hours=24)
            recent_usage = [u for u in lic.usage_log if datetime.fromisoformat(u["timestamp"]) > cutoff]
            limit = self.PLAN_USAGE_LIMITS.get(lic.plan, 100)
            frequency_ratio = len(recent_usage) / max(limit, 1)
            frequency_overuse = max(0.0, min(frequency_ratio - 1.0, 1.0))

            risk = self.limbic.evaluate({
                "operational": device_overuse, "financial": frequency_overuse, "reputational": 0.0,
            })

            action_taken = None
            if risk["risk_level"] == "KRİTİK":
                # DİKKAT: self.suspend() ÇAĞRILMAZ — suspend() webhook'unu kendi
                # gövdesinde gönderir, ve RLock reentrant olduğu için bu, check_in'in
                # DIŞ kilidi hâlâ tutuluyorken gerçekleşirdi. self._lock ürün
                # başınadır (lisans başına değil); yavaş/erişilemeyen bir webhook
                # o zaman aynı ürünün TÜM DİĞER lisanslarını (check-in/renew/
                # suspend) HTTP timeout'u kadar (10sn) bloklardı — tam olarak bu
                # kilidin "ağ I/O'su kilit dışında" tasarımının önlemeye çalıştığı
                # şey. Durum değişikliğini burada (kilit altında, I/O'suz) yapıp
                # webhook'u aşağıdaki ortak deferred mekanizmaya bırakıyoruz.
                reason = f"Kritik anomali (risk skoru: {risk['risk_score']})"
                self._suspend_locked(lic)
                action_taken = "otomatik_askiya_alindi"
                warnings.append("Cihaz/kullanım anomalisi kritik seviyede — lisans otomatik askıya alındı.")
                if self.alert_webhook_url:
                    webhook_payload = {
                        "event": "license_suspended", "license_key": license_key,
                        "customer": lic.customer_name, "reason": reason,
                    }
            elif risk["risk_level"] in ("YÜKSEK", "ORTA"):
                warnings.append(f"Şüpheli kullanım paterni tespit edildi (risk: {risk['risk_level']}).")
                if self.alert_webhook_url:
                    webhook_payload = {
                        "event": "suspicious_usage", "license_key": license_key,
                        "customer": lic.customer_name, "risk": risk,
                    }
                action_taken = "uyari_gonderildi"

            if frequency_ratio > 0.8:
                lic.suggestion = "paket_yukselt"
                warnings.append("Kullanım yoğunluğunuz plan limitinize yaklaşıyor — üst pakete geçmeyi düşünebilirsiniz.")
            else:
                lic.suggestion = None

            result = {
                "allowed": lic.status in (LicenseStatus.ACTIVE, LicenseStatus.GRACE),
                "status": lic.status, "risk": risk, "warnings": warnings,
                "action_taken": action_taken, "suggestion": lic.suggestion,
            }

        if webhook_payload and self.alert_webhook_url:
            _send_webhook(self.alert_webhook_url, webhook_payload)
        return result

    def deregister_device(self, license_key: str, device_id: str) -> Dict:
        """
        Bir cihazı lisanstan hemen kaldırır (ör. müşteri eski bilgisayarını
        elden çıkardı). active_device_ids() zaten 30 gün sonra otomatik
        düşürür — bu endpoint sadece anında/manuel düzeltme içindir.
        """
        with self._lock:
            lic = self.licenses.get(license_key)
            if not lic:
                return {"error": "Lisans bulunamadı"}
            if device_id in lic.known_devices:
                del lic.known_devices[device_id]
                return {"status": "cihaz kaldırıldı", "device_id": device_id}
            return {"status": "cihaz zaten kayıtlı değildi", "device_id": device_id}

    def list_licenses(self) -> List[Dict]:
        return [lic.to_dict() for lic in self.licenses.values()]

    def to_storage(self) -> Dict:
        out = {}
        for key, lic in self.licenses.items():
            d = lic.to_dict()
            d["known_devices"] = lic.known_devices
            d["usage_log"] = lic.usage_log
            d["payment_history"] = lic.payment_history
            out[key] = d
        return out

    def load_storage(self, data: Dict):
        for key, d in data.items():
            lic = License(d["license_key"], d["customer_name"], d["plan"],
                           d["max_devices"], d.get("expires_at"), d.get("grace_days", 7))
            lic.status = d.get("status", LicenseStatus.ACTIVE)
            lic.grace_started_at = d.get("grace_started_at")
            lic.created_at = d.get("created_at", lic.created_at)

            raw_devices = d.get("known_devices", {})
            if isinstance(raw_devices, list):
                # Eski format (düz liste, son görülme tarihi yok) — geriye dönük
                # uyumluluk için created_at'i son görülme kabul ediyoruz. Bu
                # cihazlar bir sonraki check-in'e kadar 30 günlük pencereye göre
                # değerlendirilir.
                raw_devices = {dev: lic.created_at for dev in raw_devices}
            lic.known_devices = raw_devices

            lic.usage_log = d.get("usage_log", [])
            lic.suggestion = d.get("suggestion")
            lic.payment_method = d.get("payment_method")
            lic.last_payment_at = d.get("last_payment_at")
            lic.payment_history = d.get("payment_history", [])
            self.licenses[key] = lic


# ══════════════════════════════════════════════════════════════
#  BÖLÜM 5 — ÜRÜN BAŞINA BRAIN
# ══════════════════════════════════════════════════════════════

class ProductBrain:
    def __init__(self, product_id: str):
        self.product_id = product_id
        self.brain_stem = BrainStem()
        self.basal_ganglia = BasalGanglia()
        self.hippocampus = Hippocampus()
        self.limbic_system = LimbicSystem()
        self.prefrontal_cortex = PrefrontalCortex()
        self.neural_networks: Dict[str, FeedforwardNet] = {}
        self.automation_rules: Dict[str, AutomationRule] = {}
        self.alert_webhook_url: Optional[str] = None
        self.default_grace_days: int = 7
        self.license_manager = LicenseManager(self.limbic_system)

    def decide(self, context: Dict, risk_factors: Dict, habit_key: Optional[str],
               neural_task: Optional[str], neural_input: Optional[List[float]]) -> Dict:
        reflex = self.brain_stem.check(context)
        risk = self.limbic_system.evaluate(risk_factors or {})
        habit = self.basal_ganglia.suggest(habit_key) if habit_key else None

        neural_result = None
        if neural_task and neural_input and neural_task in self.neural_networks:
            net = self.neural_networks[neural_task]
            outputs = net.predict(neural_input)
            neural_result = {
                "task_id": neural_task, "prediction": outputs, "confidence": max(outputs),
                "trained": net.trained_examples > 0,
            }

        decision = self.prefrontal_cortex.decide(reflex, risk, habit, neural_result)
        self.hippocampus.store("decision", {"context": context, "decision": decision},
                                importance=3 if risk["risk_level"] in ("KRİTİK", "YÜKSEK") else 1)
        if habit_key:
            self.basal_ganglia.record(habit_key, decision["action"])
        return decision

    def status(self) -> Dict:
        return {
            "product_id": self.product_id,
            "reflex_count": self.brain_stem.reflex_count,
            "known_habits": len(self.basal_ganglia.habits),
            "memory_count": len(self.hippocampus.memories),
            "neural_tasks": list(self.neural_networks.keys()),
            "automation_rules": len(self.automation_rules),
            "total_licenses": len(self.license_manager.licenses),
        }

    def save(self):
        path = DATA_DIR / f"{self.product_id}.json"
        data = {
            "habits": self.basal_ganglia.habits,
            "memories": self.hippocampus.memories[-500:],
            "reflex_rules": self.brain_stem.rules,
            "alert_webhook_url": self.alert_webhook_url,
            "default_grace_days": self.default_grace_days,
            "automation_rules": {
                rid: {**r.to_dict(), "action_config": r.action_config}
                for rid, r in self.automation_rules.items()
            },
            "licenses": self.license_manager.to_storage(),
            # Eğitilmiş ağırlıklar da kaydedilmeli — aksi halde her restart'ta
            # eğitim sıfırlanır ve /neural/train'in hiçbir kalıcı etkisi olmaz.
            "neural_networks": {tid: net.to_dict() for tid, net in self.neural_networks.items()},
        }
        _atomic_write(path, json.dumps(data, ensure_ascii=False, indent=2))

    def load(self):
        path = DATA_DIR / f"{self.product_id}.json"
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            self.basal_ganglia.habits = data.get("habits", {})
            self.hippocampus.memories = data.get("memories", [])
            self.brain_stem.rules = data.get("reflex_rules", {})
            self.alert_webhook_url = data.get("alert_webhook_url")
            self.default_grace_days = data.get("default_grace_days", 7)
            self.license_manager.alert_webhook_url = self.alert_webhook_url

            for rid, r in data.get("automation_rules", {}).items():
                rule = AutomationRule(rid, r["name"], r["interval_seconds"], r["action_type"], r["action_config"])
                rule.run_count = r.get("run_count", 0)
                rule.error_count = r.get("error_count", 0)
                self.automation_rules[rid] = rule

            self.license_manager.load_storage(data.get("licenses", {}))

            for tid, net_data in data.get("neural_networks", {}).items():
                self.neural_networks[tid] = FeedforwardNet.from_dict(net_data)
        except Exception as e:
            logger.error(f"Ürün verisi yüklenemedi [{self.product_id}]: {e}")


# ══════════════════════════════════════════════════════════════
#  BÖLÜM 6 — ÇOKLU-ÜRÜN REGISTRY
# ══════════════════════════════════════════════════════════════

class ProductRegistry:
    def __init__(self):
        self._lock = Lock()
        self.brains: Dict[str, ProductBrain] = {}
        self.api_keys: Dict[str, str] = {}
        self._load_keys()

    def _keys_path(self) -> Path:
        return DATA_DIR / "_api_keys.json"

    def _load_keys(self):
        path = self._keys_path()
        if path.exists():
            self.api_keys = json.loads(path.read_text(encoding="utf-8"))

    def _save_keys(self):
        _atomic_write(self._keys_path(), json.dumps(self.api_keys, indent=2))

    def register_product(self, product_id: str) -> str:
        with self._lock:
            raw_key = secrets.token_hex(24)
            self.api_keys[product_id] = hashlib.sha256(raw_key.encode()).hexdigest()
            self._save_keys()
            brain = ProductBrain(product_id)
            self.brains[product_id] = brain
            brain.save()
            return raw_key

    def verify_key(self, product_id: str, api_key: str) -> bool:
        stored = self.api_keys.get(product_id)
        if not stored:
            return False
        # secrets.compare_digest: timing-attack korumalı sabit zamanlı karşılaştırma.
        return secrets.compare_digest(hashlib.sha256(api_key.encode()).hexdigest(), stored)

    def get_brain(self, product_id: str) -> ProductBrain:
        with self._lock:
            if product_id not in self.brains:
                brain = ProductBrain(product_id)
                brain.load()
                self.brains[product_id] = brain
            return self.brains[product_id]

    def all_product_ids(self) -> List[str]:
        return list(self.api_keys.keys())


registry = ProductRegistry()
scheduler = BackgroundScheduler()


def _run_scheduled_rule(product_id: str, rule_id: str):
    brain = registry.get_brain(product_id)
    rule = brain.automation_rules.get(rule_id)
    if rule and rule.is_active:
        rule.execute()


def _daily_license_sweep():
    """TÜM ürünlerin TÜM lisanslarını günde bir kez tarar (global iş)."""
    for pid in registry.all_product_ids():
        # Bir üründeki beklenmedik bir hata (ör. bozuk veri dosyası) diğer
        # ürünlerin o günkü taramasını engellemesin diye izole ediliyor.
        try:
            brain = registry.get_brain(pid)
            events = brain.license_manager.sweep_expiries()
            if events:
                logger.info(f"📋 [{pid}] Lisans taraması: {len(events)} olay")
                brain.save()
        except Exception as e:
            logger.error(f"Günlük lisans taraması hatası [{pid}]: {e} — diğer ürünler için devam ediliyor.")


# ══════════════════════════════════════════════════════════════
#  BÖLÜM 7 — FASTAPI UYGULAMASI
# ══════════════════════════════════════════════════════════════

app = FastAPI(title="Nova IQ (Nans_Core)", version="1.2.0",
              description="Merkezi karar, otomasyon, lisans ve ödeme/süre takibi servisi")

# Admin panel (farklı bir adresten çalışır) buradan istek atabilsin diye.
# İzinli origin listesi NANS_CORS_ORIGINS ile yapılandırılır (bkz. _load_cors_origins) —
# ayarlanmazsa "*" (herkese açık) kullanılır.
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    scheduler.start()
    for pid in registry.all_product_ids():
        brain = registry.get_brain(pid)
        for rule_id, rule in brain.automation_rules.items():
            scheduler.add_job(
                _run_scheduled_rule, "interval", seconds=rule.interval_seconds,
                args=[pid, rule_id], id=f"{pid}:{rule_id}", replace_existing=True,
            )
    # Günlük lisans/süre taraması — her gün 03:00'te (sunucu saatine göre)
    scheduler.add_job(_daily_license_sweep, "cron", hour=3, id="daily_license_sweep", replace_existing=True)
    logger.info("🚀 Nova IQ servisi başlatıldı (günlük lisans taraması aktif)")


@app.on_event("shutdown")
def on_shutdown():
    scheduler.shutdown(wait=False)
    for brain in registry.brains.values():
        brain.save()
    logger.info("🛑 Nova IQ servisi durduruldu")


def require_master_key(x_master_key: str = Header(...)):
    if not secrets.compare_digest(x_master_key, MASTER_API_KEY):
        raise HTTPException(status_code=403, detail="Geçersiz master key")


def require_product_key(product_id: str, x_api_key: str = Header(...)) -> ProductBrain:
    if not registry.verify_key(product_id, x_api_key):
        raise HTTPException(status_code=403, detail="Geçersiz API key")
    return registry.get_brain(product_id)


# ── Pydantic Modelleri ───────────────────────────────────────────

class ProductRegisterRequest(BaseModel):
    product_id: str = Field(..., examples=["shiftmaster", "casinoiq", "dynastybingo"])


class DecideRequest(BaseModel):
    context: Dict = Field(default_factory=dict)
    risk_factors: Dict[str, float] = Field(default_factory=dict)
    habit_key: Optional[str] = None
    neural_task: Optional[str] = None
    neural_input: Optional[List[float]] = None


class ReflexRuleRequest(BaseModel):
    name: str
    field: str
    op: str
    value: float


class NeuralRegisterRequest(BaseModel):
    task_id: str
    input_size: int
    hidden_size: int = 8
    output_size: int = 1


class NeuralPredictRequest(BaseModel):
    task_id: str
    inputs: List[float]


class NeuralTrainExample(BaseModel):
    inputs: List[float]
    targets: List[float]


class NeuralTrainRequest(BaseModel):
    task_id: str
    examples: List[NeuralTrainExample] = Field(..., min_length=1)
    epochs: int = Field(default=200, ge=1, le=5000)
    learning_rate: float = Field(default=0.15, gt=0, le=2.0)


class AutomationRuleRequest(BaseModel):
    rule_id: str
    name: str
    interval_seconds: int = Field(..., ge=5)
    action_type: str = Field(..., pattern="^(log|webhook)$")
    action_config: Dict = Field(default_factory=dict)


class ConfigRequest(BaseModel):
    alert_webhook_url: Optional[str] = None
    default_grace_days: Optional[int] = Field(default=None, ge=0, le=90)


class LicenseCreateRequest(BaseModel):
    license_key: str
    customer_name: str
    plan: str = Field(..., pattern="^(basic|pro|enterprise)$")
    max_devices: int = Field(default=1, ge=1)
    # datetime tipi: bozuk/eksik bir tarih burada 422 ile hemen reddedilir —
    # aksi halde geçersiz bir string ancak günlük tarama (sweep_expiries) sırasında
    # patlar ve o günkü taramayı TÜM ürünler için sessizce durdurur (bkz. sweep_expiries).
    expires_at: Optional[datetime] = None
    grace_days: Optional[int] = None  # boşsa ürünün varsayılanı kullanılır


class LicenseCheckInRequest(BaseModel):
    device_id: str
    ip: Optional[str] = None


class LicenseSuspendRequest(BaseModel):
    reason: str = "Manuel askıya alma"


class LicenseRenewRequest(BaseModel):
    new_expires_at: datetime  # ISO 8601, örn "2027-01-01T00:00:00"
    payment_method: str = Field(..., pattern="^(bank_transfer|card|usdt)$")
    # Zorunlu: ödeme tahsilatı bu serviste yapılmıyor (çağıran taraf doğruluyor —
    # bkz. LicenseManager.renew docstring'i), ama en azından denetim/mutabakat
    # kaydında boş/None tutar olmasın diye tutar bildirimi mecburi kılınıyor.
    amount: float = Field(..., gt=0)
    note: Optional[str] = None


# ── ADMIN Endpoint'leri ──────────────────────────────────────────

@app.post("/v1/admin/products")
def create_product(req: ProductRegisterRequest, _: None = Depends(require_master_key)):
    if req.product_id in registry.api_keys:
        raise HTTPException(status_code=409, detail="Bu product_id zaten kayıtlı")
    api_key = registry.register_product(req.product_id)
    return {"product_id": req.product_id, "api_key": api_key,
            "warning": "Bu anahtarı güvenli saklayın, tekrar gösterilmeyecek."}


@app.get("/v1/admin/status")
def global_status(_: None = Depends(require_master_key)):
    return {
        "products": registry.all_product_ids(),
        "total_products": len(registry.all_product_ids()),
        "scheduler_jobs": len(scheduler.get_jobs()),
    }


@app.post("/v1/admin/run-license-sweep")
def force_license_sweep(_: None = Depends(require_master_key)):
    """Günlük taramayı beklemeden hemen çalıştırır (test için)."""
    _daily_license_sweep()
    return {"status": "tarama çalıştırıldı"}


# ── ÜRÜN Endpoint'leri ────────────────────────────────────────────

@app.post("/v1/{product_id}/decide")
def decide(product_id: str, req: DecideRequest, brain: ProductBrain = Depends(require_product_key)):
    return brain.decide(req.context, req.risk_factors, req.habit_key, req.neural_task, req.neural_input)


@app.post("/v1/{product_id}/reflex-rules")
def add_reflex_rule(product_id: str, req: ReflexRuleRequest, brain: ProductBrain = Depends(require_product_key)):
    brain.brain_stem.register_rule(req.name, req.field, req.op, req.value)
    brain.save()
    return {"status": "eklendi", "rule": req.model_dump()}


@app.post("/v1/{product_id}/neural/register")
def register_neural_task(product_id: str, req: NeuralRegisterRequest, brain: ProductBrain = Depends(require_product_key)):
    brain.neural_networks[req.task_id] = FeedforwardNet(req.input_size, req.hidden_size, req.output_size)
    return {"status": "kaydedildi", "task_id": req.task_id}


@app.post("/v1/{product_id}/neural/train")
def train_neural_task(product_id: str, req: NeuralTrainRequest, brain: ProductBrain = Depends(require_product_key)):
    """
    Etiketli örneklerle (geçmiş kararlar + gerçek sonuçları) ağı eğitir —
    gerçek geri yayılım/gradyan inişi (bkz. FeedforwardNet.train). Eğitilmemiş
    bir ağ /neural/predict çağrıldığında rastgele çıktı üretir; bu endpoint
    çağrılmadan "AI tahmini" güvenilir değildir.
    """
    if req.task_id not in brain.neural_networks:
        raise HTTPException(status_code=404, detail="Görev bulunamadı — önce /neural/register ile kaydedin")
    net = brain.neural_networks[req.task_id]
    examples = [(e.inputs, e.targets) for e in req.examples]
    try:
        loss = net.train(examples, epochs=req.epochs, lr=req.learning_rate)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    brain.save()
    return {
        "task_id": req.task_id, "final_loss": round(loss, 6),
        "trained_examples_total": net.trained_examples, "epochs": req.epochs,
    }


@app.post("/v1/{product_id}/neural/predict")
def neural_predict(product_id: str, req: NeuralPredictRequest, brain: ProductBrain = Depends(require_product_key)):
    if req.task_id not in brain.neural_networks:
        raise HTTPException(status_code=404, detail="Görev bulunamadı")
    net = brain.neural_networks[req.task_id]
    outputs = net.predict(req.inputs)
    return {
        "task_id": req.task_id, "prediction": outputs, "confidence": max(outputs),
        "trained": net.trained_examples > 0,
        "warning": None if net.trained_examples > 0 else "Bu ağ hiç eğitilmedi — tahmin rastgele ağırlıklardan geliyor, anlamlı değil.",
    }


@app.get("/v1/{product_id}/memory")
def get_memory(product_id: str, category: Optional[str] = None, limit: int = 20,
                brain: ProductBrain = Depends(require_product_key)):
    return {"memories": brain.hippocampus.recall(category, limit)}


@app.post("/v1/{product_id}/config")
def set_config(product_id: str, req: ConfigRequest, brain: ProductBrain = Depends(require_product_key)):
    if req.alert_webhook_url is not None:
        brain.alert_webhook_url = req.alert_webhook_url
        brain.license_manager.alert_webhook_url = req.alert_webhook_url
    if req.default_grace_days is not None:
        brain.default_grace_days = req.default_grace_days
    brain.save()
    return {"status": "güncellendi", "alert_webhook_url": brain.alert_webhook_url,
            "default_grace_days": brain.default_grace_days}


@app.post("/v1/{product_id}/automation/rules")
def create_rule(product_id: str, req: AutomationRuleRequest, brain: ProductBrain = Depends(require_product_key)):
    rule = AutomationRule(req.rule_id, req.name, req.interval_seconds, req.action_type, req.action_config)
    brain.automation_rules[req.rule_id] = rule
    scheduler.add_job(
        _run_scheduled_rule, "interval", seconds=req.interval_seconds,
        args=[product_id, req.rule_id], id=f"{product_id}:{req.rule_id}", replace_existing=True,
    )
    brain.save()
    return {"status": "kural oluşturuldu", "rule": rule.to_dict()}


@app.get("/v1/{product_id}/automation/rules")
def list_rules(product_id: str, brain: ProductBrain = Depends(require_product_key)):
    return {"rules": [r.to_dict() for r in brain.automation_rules.values()]}


@app.post("/v1/{product_id}/automation/rules/{rule_id}/run")
def run_rule_now(product_id: str, rule_id: str, brain: ProductBrain = Depends(require_product_key)):
    if rule_id not in brain.automation_rules:
        raise HTTPException(status_code=404, detail="Kural bulunamadı")
    return brain.automation_rules[rule_id].execute()


@app.get("/v1/{product_id}/status")
def product_status(product_id: str, brain: ProductBrain = Depends(require_product_key)):
    return brain.status()


# ── LİSANS + SÜRE + ÖDEME Endpoint'leri ───────────────────────────

@app.post("/v1/{product_id}/licenses")
def create_license(product_id: str, req: LicenseCreateRequest, brain: ProductBrain = Depends(require_product_key)):
    # Yinelenen kontrolü artık create_license() içinde, kilit altında yapılıyor —
    # burada önceden kontrol etmek eşzamanlı iki istekte yarış durumuna açıktı
    # (ikisi de "yok" görüp ikisi de eklerdi).
    grace = req.grace_days if req.grace_days is not None else brain.default_grace_days
    try:
        lic = brain.license_manager.create_license(
            req.license_key, req.customer_name, req.plan, req.max_devices,
            req.expires_at.isoformat() if req.expires_at else None, grace,
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    brain.save()
    return {"status": "kaydedildi", "license": lic.to_dict()}


@app.post("/v1/{product_id}/licenses/{license_key}/check-in")
def license_check_in(product_id: str, license_key: str, req: LicenseCheckInRequest,
                      brain: ProductBrain = Depends(require_product_key)):
    result = brain.license_manager.check_in(license_key, req.device_id, req.ip)
    brain.save()
    return result


@app.delete("/v1/{product_id}/licenses/{license_key}/devices/{device_id}")
def deregister_device(product_id: str, license_key: str, device_id: str,
                       brain: ProductBrain = Depends(require_product_key)):
    """Müşterinin artık kullanmadığı bir cihazı anında lisanstan kaldırır
    (30 günlük aktiflik penceresini beklemeden — bkz. License.active_device_ids)."""
    result = brain.license_manager.deregister_device(license_key, device_id)
    brain.save()
    return result


@app.get("/v1/{product_id}/licenses")
def list_licenses(product_id: str, brain: ProductBrain = Depends(require_product_key)):
    return {"licenses": brain.license_manager.list_licenses()}


@app.post("/v1/{product_id}/licenses/{license_key}/suspend")
def suspend_license(product_id: str, license_key: str, req: LicenseSuspendRequest,
                     brain: ProductBrain = Depends(require_product_key)):
    result = brain.license_manager.suspend(license_key, req.reason)
    brain.save()
    return result


@app.post("/v1/{product_id}/licenses/{license_key}/reactivate")
def reactivate_license(product_id: str, license_key: str, brain: ProductBrain = Depends(require_product_key)):
    result = brain.license_manager.reactivate(license_key)
    brain.save()
    return result


@app.post("/v1/{product_id}/licenses/{license_key}/renew")
def renew_license(product_id: str, license_key: str, req: LicenseRenewRequest,
                   brain: ProductBrain = Depends(require_product_key)):
    """
    Ödeme onaylandığında çağrılır (banka transferi sonrası siz manuel,
    kart/USDT sonrası kendi ödeme sağlayıcınızın webhook'undan bu endpoint'e).
    """
    result = brain.license_manager.renew(license_key, req.new_expires_at.isoformat(), req.payment_method,
                                          req.amount, req.note)
    brain.save()
    return result


@app.get("/health")
def health():
    return {"status": "ok", "time": datetime.now().isoformat()}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
