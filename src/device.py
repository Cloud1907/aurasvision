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


@functools.lru_cache(maxsize=1)
def _preload_cuda_libs() -> None:
    """pip `nvidia-*` paketlerindeki cuDNN/cuBLAS/cuFFT'yi RTLD_GLOBAL ile önden yükler.

    onnxruntime-gpu'nun CUDA EP'si cuDNN 9'u sistem dlopen yolunda arar; venv'e
    torch bağımlılığı olarak gelen kütüphaneler o yolda değildir (torch kendi
    RPATH'ini gömer, ORT gömmez). Önden yüklenince dlopen zaten-yüklü kopyayı bulur.
    """
    import ctypes
    import glob

    try:
        import nvidia
    except ImportError:
        return
    for base in nvidia.__path__:
        for name in ("cublas", "cudnn", "cufft", "curand"):
            for so in sorted(glob.glob(f"{base}/{name}/lib/lib*.so.*")):
                try:
                    ctypes.CDLL(so, mode=ctypes.RTLD_GLOBAL)
                except OSError:
                    pass  # eksik/uyumsuz lib EP yüklenirken zaten raporlanır


def ort_providers(preference: str = "auto") -> list[str]:
    """onnxruntime provider listesi — cihaz CUDA ise GPU EP, değilse CPU.

    (Apple Silicon'da CoreML EP, plaka detektörünün dinamik şekliyle uyuşmuyor;
    MPS/CPU'da bilinçli olarak CPU provider'da kalınır.)
    """
    if select_device(preference) != "cuda":
        return ["CPUExecutionProvider"]
    _preload_cuda_libs()
    try:
        import onnxruntime as ort

        if "CUDAExecutionProvider" in ort.get_available_providers():
            return ["CUDAExecutionProvider", "CPUExecutionProvider"]
    except Exception:
        pass
    return ["CPUExecutionProvider"]
