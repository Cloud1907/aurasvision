"""Servis günlükleri — sahada "ne oldu" sorusunun tek cevabı.

Neden gerekli: servisler konsola yazıyordu. Windows'ta küçültülmüş pencerede
çalışıyorlar, pencere kapanınca çıktı kayboluyor; systemd'de journal'a gidiyor
ama müşteri makinesinden alması zahmetli. Bir şey ters gittiğinde destek için
gönderilecek somut bir dosya olmalı.

Her servis kendi dosyasına yazar: output/logs/<servis>.log
Dosya büyüyünce döner (varsayılan 5 MB × 3 kopya) — disk şişmez.
Konsol çıktısı KESİLMEZ; hem ekrana hem dosyaya gider.
"""
from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_KURULDU: set[str] = set()


def kur(servis: str, cfg=None, mb: int = 5, kopya: int = 3) -> Path | None:
    """Servisin stdout/stderr çıktısını dosyaya da yazar. Günlük yolunu döndürür.

    print() çağrılarını da yakalar — kod tabanı boyunca print kullanılıyor ve
    hepsini logging'e çevirmek gereksiz risk; çıktıyı kaynağında çoğaltmak yeter.
    """
    if servis in _KURULDU:
        return None
    _KURULDU.add(servis)
    try:
        cikti = (cfg.get("paths.output_dir", "output") if cfg else "output")
        dizin = _ROOT / cikti / "logs"
        dizin.mkdir(parents=True, exist_ok=True)
        yol = dizin / f"{servis}.log"

        h = RotatingFileHandler(yol, maxBytes=mb * 1024 * 1024,
                                backupCount=kopya, encoding="utf-8")
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s",
                                         "%Y-%m-%d %H:%M:%S"))
        kok = logging.getLogger()
        kok.setLevel(logging.INFO)
        kok.addHandler(h)

        # print() → hem konsol hem dosya
        sys.stdout = _Cift(sys.stdout, yol)
        sys.stderr = _Cift(sys.stderr, yol)
        print(f"[{servis}] günlük: {yol}")
        return yol
    except Exception as e:                      # günlük kurulamazsa servis YİNE çalışır
        print(f"[{servis}] günlük dosyası açılamadı: {e}", flush=True)
        return None


class _Cift:
    """Çıktıyı hem asıl akışa hem dosyaya yazar (tee)."""

    def __init__(self, akis, yol: Path) -> None:
        self._akis = akis
        self._yol = yol

    def write(self, s: str) -> int:
        try:
            self._akis.write(s)
        except Exception:
            pass
        if s.strip():
            try:
                with open(self._yol, "a", encoding="utf-8") as f:
                    from datetime import datetime
                    f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} {s.rstrip()}\n")
            except Exception:
                pass
        return len(s)

    def flush(self) -> None:
        try:
            self._akis.flush()
        except Exception:
            pass

    def isatty(self) -> bool:
        return getattr(self._akis, "isatty", lambda: False)()
