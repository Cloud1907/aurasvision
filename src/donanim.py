"""Donanım profili — işletim sistemi, CPU, GPU ve donanım decode yetenekleri.

Neden ayrı modül: sistem artık tek bir hedef makine (GB10/Linux) için değil,
Windows ya da Linux'ta farklı CPU/GPU'larda kurulacak. "Hangi motor, hangi
model, hangi decode yolu" kararı elle config'e yazılmak yerine BURADAN
ölçülerek verilir; panel de aynı bilgiyi gösterir ("GPU var ama kullanılmıyor"
sahada en pahalı sessiz hatadır).

İki iş yapar:
  1. `profil()`  — bir kez ölçülür: OS, çekirdek, RAM, GPU adı/VRAM, hwaccel
                   adayları (PyAV), nvdec motoru kurulu mu, önerilen ayarlar.
  2. `kullanim()` — anlık yük: CPU %, RAM %, GPU %, VRAM, NVDEC/NVENC %
                   (pynvml varsa). /api/status ve heartbeat bunu taşır.

Hiçbir bağımlılık zorunlu değildir: torch/pynvml/psutil yoksa ilgili alan
None döner, sistem çalışmaya devam eder.
"""
from __future__ import annotations

import functools
import os
import platform
import sys
from typing import Any

# İşletim sistemine göre denenecek PyAV hwaccel cihazları — sıra tercih sırasıdır.
# cuda: NVIDIA (her OS). d3d11va/dxva2: Windows'ta her GPU (Intel/AMD/NVIDIA).
# vaapi: Linux Intel/AMD. qsv: Intel. videotoolbox: macOS. Yoksa yazılım decode.
_HWACCEL_TERCIH = {
    "win32": ("cuda", "d3d11va", "dxva2", "qsv"),
    "linux": ("cuda", "vaapi", "qsv", "vdpau"),
    "darwin": ("videotoolbox",),
}


def _gpu_torch() -> dict[str, Any]:
    try:
        import torch
    except Exception:
        return {"cuda": False, "mps": False}
    out: dict[str, Any] = {"cuda": False, "mps": False, "torch": torch.__version__}
    try:
        out["mps"] = bool(torch.backends.mps.is_available())
    except Exception:
        pass
    try:
        if torch.cuda.is_available():
            p = torch.cuda.get_device_properties(0)
            out.update({"cuda": True, "gpu": p.name,
                        "vram_mb": int(p.total_memory / (1024 ** 2)),
                        "cuda_surum": torch.version.cuda})
    except Exception:
        pass
    return out


def _hwaccel_adaylari() -> list[str]:
    """PyAV'ın bu makinede derlenmiş hwaccel cihazları, OS tercih sırasında."""
    try:
        from av.codec.hwaccel import hwdevices_available
        var = set(hwdevices_available())
    except Exception:
        return []
    tercih = _HWACCEL_TERCIH.get(sys.platform, ())
    return [d for d in tercih if d in var]


def _nvdec_motoru() -> str:
    """GB10 motoru (PyNvVideoCodec + TensorRT) kullanılabilir mi — "" = evet."""
    try:
        import torch
        if not torch.cuda.is_available():
            return "CUDA yok"
    except Exception as e:
        return f"torch yok: {e}"
    for m in ("PyNvVideoCodec", "tensorrt"):
        try:
            __import__(m)
        except Exception:
            return f"{m} kurulu değil"
    return ""


@functools.lru_cache(maxsize=1)
def profil() -> dict[str, Any]:
    """Donanım profili + önerilen çalışma ayarları (bir kez ölçülür)."""
    cpu = os.cpu_count() or 1
    ram_gb = None
    try:
        import psutil
        ram_gb = round(psutil.virtual_memory().total / (1024 ** 3), 1)
    except Exception:
        pass
    gpu = _gpu_torch()
    hw = _hwaccel_adaylari()
    nvdec_sebep = _nvdec_motoru()

    # Öneri: motor → nvdec (GB10 hattı) > akis (taşınabilir: PyAV hwaccel + batch
    # YOLO) — akis her yerde çalışır, hwaccel yoksa yazılım decode'a düşer.
    if not nvdec_sebep:
        motor = "nvdec"
    else:
        motor = "akis"
    # Model: GPU'da yolo11s (doğruluk), yalnız CPU'da yolo11n (hız). imgsz sabit 640;
    # kalabalık sahnede kullanıcı 1280 yapar (config yorumu).
    if gpu.get("cuda") or gpu.get("mps"):
        model, fps, batch = "yolo11s.pt", 5, 32
    else:
        model, fps, batch = "yolo11n.pt", 3, 8
    return {
        "os": platform.system(), "os_surum": platform.release(),
        "python": platform.python_version(),
        "cpu": platform.processor() or platform.machine(), "cekirdek": cpu,
        "ram_gb": ram_gb,
        "gpu": gpu.get("gpu"), "vram_mb": gpu.get("vram_mb"), "cuda": bool(gpu.get("cuda")),
        "mps": bool(gpu.get("mps")), "torch": gpu.get("torch"),
        "hwaccel": hw,                       # tercih sırasıyla denenecek liste
        "nvdec_motoru": not nvdec_sebep, "nvdec_sebep": nvdec_sebep,
        "oneri": {"engine": motor, "model": model, "fps": fps, "batch_max": batch},
    }


_son_cpu = 0.0   # son cpu_percent örneği (monotonic) — çok sık/ilk çağrıda 0 dönmesin


def kullanim() -> dict[str, Any]:
    """Anlık kaynak kullanımı — panel ve heartbeat için.

    cpu_percent(None) son çağrıdan bu yana ölçer; ilk çağrıda ya da 0,5 sn'den
    kısa aralıkta anlamsız 0 döner (panelde "CPU %0" görüldü). O durumda 0,3 sn
    bloklayan ölçüm yapılır — durum ucu için kabul edilebilir."""
    global _son_cpu
    out: dict[str, Any] = {}
    try:
        import time as _t
        import psutil
        simdi = _t.monotonic()
        if simdi - _son_cpu < 0.5:
            out["cpu_pct"] = psutil.cpu_percent(interval=0.3)
        else:
            out["cpu_pct"] = psutil.cpu_percent(interval=None)
            if out["cpu_pct"] == 0.0 and _son_cpu == 0.0:   # ilk çağrı
                out["cpu_pct"] = psutil.cpu_percent(interval=0.3)
        _son_cpu = _t.monotonic()
        vm = psutil.virtual_memory()
        out["ram_pct"] = vm.percent
        out["ram_used_gb"] = round(vm.used / (1024 ** 3), 1)
    except Exception:
        pass
    try:
        import pynvml
        pynvml.nvmlInit()
        h = pynvml.nvmlDeviceGetHandleByIndex(0)
        u = pynvml.nvmlDeviceGetUtilizationRates(h)
        m = pynvml.nvmlDeviceGetMemoryInfo(h)
        out["gpu_pct"] = int(u.gpu)
        out["vram_used_mb"] = int(m.used / (1024 ** 2))
        out["vram_total_mb"] = int(m.total / (1024 ** 2))
        try:
            out["nvdec_pct"] = int(pynvml.nvmlDeviceGetDecoderUtilization(h)[0])
            out["nvenc_pct"] = int(pynvml.nvmlDeviceGetEncoderUtilization(h)[0])
        except Exception:
            pass
        try:
            pynvml.nvmlShutdown()
        except Exception:
            pass
    except Exception:
        pass
    return out


def ozet_satiri() -> str:
    """Log/CLI için tek satır: 'Windows · 8 çekirdek · RTX 3050 6 GB · hwaccel cuda,d3d11va · motor akis'."""
    p = profil()
    gpu = f"{p['gpu']} {p['vram_mb'] // 1024} GB" if p.get("gpu") else "GPU yok"
    hw = ",".join(p["hwaccel"]) or "yazılım decode"
    return (f"{p['os']} · {p['cekirdek']} çekirdek · {gpu} · hwaccel {hw} · "
            f"önerilen motor {p['oneri']['engine']} / {p['oneri']['model']}")


if __name__ == "__main__":
    import json
    print(json.dumps({"profil": profil(), "kullanim": kullanim()}, indent=1, ensure_ascii=False))
