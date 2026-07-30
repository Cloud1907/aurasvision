"""config.yaml yükleyici — tüm eşik/parametreler tek yerden (manifest convention)."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_CONFIG = _ROOT / "config.yaml"


class Config:
    """config.yaml üzerine ince bir sarmalayıcı; nokta yoluyla erişim sağlar."""

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    def get(self, dotted: str, default: Any = None) -> Any:
        """'detect.conf' gibi noktalı anahtarla değer döndürür."""
        node: Any = self._data
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    @property
    def root(self) -> Path:
        return _ROOT


def load_env(path: str = ".env") -> int:
    """`.env` dosyasını ortam değişkenlerine yükler (bağımlılıksız).

    Neden gerekli: kod bugüne dek `DATABASE_URL`/`REDIS_URL`/`AURAS_TOKEN`
    değişkenlerinin kabuktan export edilmiş olmasını bekliyordu
    (`set -a; . ./.env`). Bu Windows'ta karşılığı olmayan bir varsayım; orada
    değişkenler boş kalır ve sistem SESSİZCE SQLite'a düşüp kimlik doğrulamasız
    açılır. Artık dosya varsa Python'un kendisi okur.

    Zaten tanımlı değişkenler EZİLMEZ — systemd/compose ortamı önceliklidir.
    """
    p = _ROOT / path
    if not p.is_file():
        return 0
    n = 0
    for satir in p.read_text(encoding="utf-8", errors="replace").splitlines():
        satir = satir.strip()
        if not satir or satir.startswith("#") or "=" not in satir:
            continue
        anahtar, _, deger = satir.partition("=")
        anahtar = anahtar.strip()
        deger = deger.strip().strip('"').strip("'")
        if anahtar and anahtar not in os.environ:
            os.environ[anahtar] = deger
            n += 1
    return n


def http_options(cfg, url: str) -> dict:
    """HTTP(S) kaynakları için ek FFmpeg başlık seçenekleri (stream.http_headers).

    Bazı CDN/HLS kaynakları ve IP kameralar Referer / User-Agent / Authorization ister.
    Yalnız http(s) adreslerine uygulanır; RTSP ve dosyalar etkilenmez.
    """
    h = (cfg.get("stream.http_headers", "") or "").strip()
    if not h or not str(url).startswith(("http://", "https://")):
        return {}
    satirlar = [s.strip() for s in h.splitlines() if s.strip()]
    return {"headers": "".join(f"{s}\r\n" for s in satirlar)}


def apply_cv2_http_headers(cfg) -> None:
    """cv2.VideoCapture FFmpeg arka ucuna başlıkları geçirir (env ile, tek yol).

    count/plate hattı cv2 kullanıyor; PyAV gibi seçenek sözlüğü alamıyor.
    """
    import os as _os

    h = (cfg.get("stream.http_headers", "") or "").strip()
    if not h:
        return
    hdr = "".join(f"{s.strip()}\r\n" for s in h.splitlines() if s.strip())
    mevcut = _os.environ.get("OPENCV_FFMPEG_CAPTURE_OPTIONS", "")
    yeni = f"headers;{hdr}"
    if yeni not in mevcut:
        _os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (mevcut + "|" + yeni) if mevcut else yeni


def load_config(path: str | Path | None = None) -> Config:
    """config.yaml'i yükler. Yoksa boş config döner (varsayılanlar kodda)."""
    load_env()   # .env varsa ortama yükle (Windows'ta kabuk export'u yok)
    cfg_path = Path(path) if path else _DEFAULT_CONFIG
    if not cfg_path.exists():
        return Config({})
    with open(cfg_path, "r", encoding="utf-8") as f:
        return Config(yaml.safe_load(f) or {})
