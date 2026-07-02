"""YOLO model yükleyici — bir kez yüklenir, döngüde reuse (manifest forbidden)."""
from __future__ import annotations

import functools

from .device import select_device


@functools.lru_cache(maxsize=32)
def load_yolo(model: str, device_pref: str = "auto", instance_key: str = ""):
    """Ultralytics YOLO modelini yükler (model adı + kamera bazında cache'lenir).

    Model dosyası yoksa Ultralytics ilk çağrıda otomatik indirir.
    `instance_key` (kamera id): aynı YOLO örneği iki kamera thread'inde paylaşılırsa
    tracker/GMC durumuna farklı kaynakların kareleri karışır (BoT-SORT GMC boyut
    assert'i) — kamera başına ayrı örnek zorunlu.
    """
    from ultralytics import YOLO

    dev = select_device(device_pref)
    yolo = YOLO(model)
    if model.endswith(".pt"):   # .engine/.onnx cihaza gömülü, .to() PyTorch'a özgü
        yolo.to(dev)
    return yolo
