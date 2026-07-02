"""nvdec motoru kapasite ölçümü — N eşzamanlı 720p/5fps akışta keep-up testi.

go2rtc'deki bench0..N-1 akışlarını sayım görevli sanal kamera olarak motorla işler;
motorun 5 sn'lik "[nvdec] inference" logları + NVML örneklemesiyle rapor üretir.

Kullanım: python scripts/bench_nvdec.py --cams 16 --duration 75 [--motion]
Hedef: inference ≈ N × detect.fps (hareket filtresi kapalıyken).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.bus import open_bus  # noqa: E402
from src.config import load_config  # noqa: E402


class _CfgOverride:
    """cfg.get sarmalayıcısı — ölçüm parametrelerini config dosyasına dokunmadan değiştirir."""

    def __init__(self, cfg, overrides: dict) -> None:
        self._cfg = cfg
        self._o = overrides

    def get(self, path, default=None):
        if path in self._o:
            return self._o[path]
        return self._cfg.get(path, default)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cams", type=int, default=16)
    ap.add_argument("--duration", type=float, default=75.0)
    ap.add_argument("--motion", action="store_true", help="hareket filtresi açık kalsın")
    args = ap.parse_args()

    cfg = _CfgOverride(load_config(), {"motion.enabled": bool(args.motion)})
    bus = open_bus(cfg._cfg)
    if bus is None:
        raise SystemExit("REDIS_URL gerekli")

    cams = [{"id": f"bench{i}", "name": f"bench{i}", "source": f"bench{i}",
             "enabled": True, "tasks": {"count": True, "plate": False, "face": False}}
            for i in range(args.cams)]

    # süre dolunca çık (run_gpu_worker sonsuz döngü)
    import threading
    import time

    def killer():
        time.sleep(args.duration)
        import os
        os._exit(0)

    threading.Thread(target=killer, daemon=True).start()

    from src.gpu_engine import run_gpu_worker
    run_gpu_worker(cams, cfg, bus)


if __name__ == "__main__":
    main()
