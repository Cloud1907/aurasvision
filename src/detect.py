"""YOLO model yükleyici — bir kez yüklenir, döngüde reuse (manifest forbidden)."""
from __future__ import annotations

import functools

from .device import select_device


@functools.lru_cache(maxsize=4)
def load_yolo(model: str, device_pref: str = "auto"):
    """Ultralytics YOLO modelini yükler (model adı bazında cache'lenir).

    Model dosyası yoksa Ultralytics ilk çağrıda otomatik indirir.
    """
    from ultralytics import YOLO

    dev = select_device(device_pref)
    yolo = YOLO(model)
    yolo.to(dev)
    return yolo
