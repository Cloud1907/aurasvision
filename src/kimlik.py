"""Kimlik — parola hash'i, imzalı oturum çerezi ve rol matrisi (RBAC).

Tasarım: docs/rbac-tasarim.md. Bilinçli kararlar:
  - hashlib.scrypt: saf stdlib, ek bağımlılık yok (bcrypt/argon2 kurulum yükü)
  - Oturum çerezi = base64(JSON{ad,rol,exp}) + HMAC-SHA256 imzası — JWT
    bağımlılığı YOK; sunucu tarafında oturum tablosu da yok (tek kutu kurulum)
  - İmza anahtarı: AURAS_TOKEN doluysa o; değilse ilk açılışta üretilip
    output/.oturum-anahtari'na yazılan rastgele anahtar (yeniden başlatmada
    oturumlar düşmesin)
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent

ROLLER = ("yonetici", "operator", "izleyici")
OTURUM_CEREZ = "auras_oturum"
OTURUM_SANIYE = 12 * 3600   # vardiya boyu yeter; sonsuz oturum denetim açığı

# scrypt maliyeti: GB10'da ~50 ms — giriş ucunda kabul edilebilir, kaba
# kuvveti anlamlı yavaşlatır (OWASP asgarisi n=2^14)
_SCRYPT = dict(n=2**14, r=8, p=1)


def parola_hashle(parola: str) -> str:
    tuz = secrets.token_bytes(16)
    h = hashlib.scrypt(parola.encode(), salt=tuz, **_SCRYPT)
    return tuz.hex() + "$" + h.hex()


def parola_dogru(parola: str, kayit: str) -> bool:
    try:
        tuz_hex, h_hex = (kayit or "").split("$", 1)
        h = hashlib.scrypt(parola.encode(), salt=bytes.fromhex(tuz_hex), **_SCRYPT)
        return hmac.compare_digest(h.hex(), h_hex)
    except Exception:
        return False


def _anahtar() -> bytes:
    tok = os.environ.get("AURAS_TOKEN", "")
    if tok:
        return ("oturum:" + tok).encode()   # ön ek: token'ın kendisi imza olamaz
    yol = _ROOT / "output" / ".oturum-anahtari"
    try:
        if yol.exists():
            return yol.read_bytes()
        yol.parent.mkdir(parents=True, exist_ok=True)
        anahtar = secrets.token_bytes(32)
        yol.write_bytes(anahtar)
        os.chmod(yol, 0o600)
        return anahtar
    except OSError:
        # Diske yazılamıyorsa süreç ömürlük anahtar (oturumlar restart'ta düşer)
        global _GECICI
        if "_GECICI" not in globals():
            _GECICI = secrets.token_bytes(32)
        return _GECICI


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _b64coz(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def imzala(ad: str, rol: str, saniye: int = OTURUM_SANIYE) -> str:
    govde = _b64(json.dumps(
        {"ad": ad, "rol": rol, "exp": int(time.time()) + saniye},
        ensure_ascii=False).encode())
    imza = _b64(hmac.new(_anahtar(), govde.encode(), hashlib.sha256).digest())
    return govde + "." + imza


def coz(token: str) -> dict | None:
    """İmzalı çerezi doğrular; geçersiz/süresi dolmuşsa None."""
    try:
        govde, imza = (token or "").split(".", 1)
        beklenen = _b64(hmac.new(_anahtar(), govde.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(imza, beklenen):
            return None
        veri = json.loads(_b64coz(govde))
        if int(veri.get("exp", 0)) < time.time():
            return None
        if veri.get("rol") not in ROLLER:
            return None
        return {"ad": str(veri.get("ad", "")), "rol": veri["rol"]}
    except Exception:
        return None


# ─────────────────────────── Rol matrisi ───────────────────────────
# Okuma (GET) herkese; yazma uçları role göre. Middleware bu tek
# fonksiyondan sorar — matris testi de bunu test eder (sunucusuz).

_HERKESE = ("/api/giris", "/api/cikis", "/api/ben")
# POST ama hiçbir şey yazmaz — sorgu gövdesi taşıyan salt-okuma ucu
_SALT_OKUMA_POST = ("/api/search",)
# Operatörün işi: olay kabulü, kanıt dışa aktarma, test koşusu, arşiv klasörü
_OPERATOR_YAZAR = ("/api/alerts", "/api/export", "/api/run",
                   "/api/recordings/open-folder")


def yetkili(rol: str, method: str, path: str) -> bool:
    if method in ("GET", "HEAD", "OPTIONS"):
        return True
    if path in _HERKESE or path.startswith(_SALT_OKUMA_POST):
        return True
    if rol == "yonetici":
        return True
    if rol == "operator":
        return path.startswith(_OPERATOR_YAZAR)
    return False   # izleyici: salt okuma
