"""Cihaz seçimi — MPS (Apple Silicon) > CUDA > CPU (manifest convention)."""
from __future__ import annotations

import functools


@functools.lru_cache(maxsize=1)
def select_device(preference: str = "auto") -> str:
    """Ultralytics'in beklediği cihaz string'ini döndürür.

    preference: auto | mps | cuda | cpu
    """
    pref = (preference or "auto").lower()
    if pref in ("mps", "cuda", "cpu"):
        return pref

    try:
        import torch

        if torch.backends.mps.is_available():
            return "mps"
        if torch.cuda.is_available():
            return "cuda"
    except Exception:
        pass
    return "cpu"
