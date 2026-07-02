"""GB10 FPS/kaynak ölçüm koşumu — docs/olcumler-gb10.md tabloları bunu kullanır.

Mevcut motorun (Ultralytics track döngüsü) N eşzamanlı akıştaki verimini ölçer:
her akış için ayrı thread + ayrı YOLO örneği + kendi cv2.VideoCapture döngüsü,
count.py ile aynı parametreler (conf/iou/imgsz/vid_stride/tracker).

İki mod:
  RTSP kaynak  → gerçek-zaman "keep-up" testi: kaynak hızında kare gelir,
                 işlenen FPS ≈ kaynak_fps/vid_stride olmalı; düşükse yetişemiyor.
  Dosya kaynak → maksimum verim testi: decode+inference ne kadar hızlı koşuyor
                 (kamera kapasitesi ekstrapolasyonu buradan yapılır).

Kullanım:
  python scripts/bench_fps.py --streams 1 4 8 16 --duration 60 \
      --source rtsp://127.0.0.1:8554/bench{i}     # {i} → akış indeksi
  python scripts/bench_fps.py --streams 8 --source data/videos/people-detection.mp4 \
      --model yolo11s.engine --vid-stride 1
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import load_config  # noqa: E402


def _gpu_stats() -> dict:
    """nvidia-ml üzerinden GPU util + bellek (GB10 birleşik bellekte mem sayacı olmayabilir)."""
    try:
        import pynvml

        pynvml.nvmlInit()
        h = pynvml.nvmlDeviceGetHandleByIndex(0)
        util = pynvml.nvmlDeviceGetUtilizationRates(h)
        try:
            mem = pynvml.nvmlDeviceGetMemoryInfo(h)
            mem_used = round(mem.used / 1e9, 1)
        except Exception:
            mem_used = None
        return {"gpu_util": util.gpu, "mem_gb": mem_used}
    except Exception:
        return {"gpu_util": None, "mem_gb": None}


def _stream_worker(idx: int, source: str, cfg, duration: float, out: list[dict],
                   ready: threading.Barrier, model_override: str | None,
                   imgsz_override: int | None, stride_override: int | None) -> None:
    import cv2
    from ultralytics import YOLO

    source = source.replace("{i}", str(idx))
    is_live = source.startswith(("rtsp://", "rtmp://", "http://"))
    model = model_override or cfg.get("detect.model", "yolo11n.pt")
    yolo = YOLO(model)
    if model.endswith(".pt"):
        yolo.to("cuda")
    vid_stride = stride_override or cfg.get("detect.vid_stride", 3)
    kw = dict(classes=cfg.get("count.classes", [0]),
              conf=cfg.get("detect.conf", 0.35), iou=cfg.get("detect.iou", 0.5),
              imgsz=imgsz_override or cfg.get("detect.imgsz", 640),
              tracker=cfg.get("count.tracker", "botsort.yaml"),
              device="cuda", verbose=False, persist=True)

    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        out[idx] = {"error": f"açılamadı: {source}"}
        ready.wait()
        return
    # warmup: ilk inference (CUDA init + engine yükleme) ölçüme girmesin
    ok, frame = cap.read()
    if ok:
        yolo.track(frame, **kw)
    ready.wait()

    t0 = time.time()
    decoded = processed = stalls = 0
    fidx = 0
    while time.time() - t0 < duration:
        ok = cap.grab()
        if not ok:
            if is_live:
                stalls += 1
                time.sleep(0.05)
                continue
            cap.release()                     # dosya bitti → başa sar (döngü)
            cap = cv2.VideoCapture(source)
            continue
        decoded += 1
        fidx += 1
        if fidx % vid_stride != 0:
            continue
        ok, frame = cap.retrieve()
        if not ok:
            continue
        yolo.track(frame, **kw)
        processed += 1
    dt = time.time() - t0
    cap.release()
    out[idx] = {"decoded_fps": decoded / dt, "proc_fps": processed / dt, "stalls": stalls}


def run_bench(source: str, n_streams: int, duration: float, model: str | None,
              imgsz: int | None, vid_stride: int | None) -> dict:
    import psutil

    cfg = load_config()
    out: list[dict] = [{} for _ in range(n_streams)]
    ready = threading.Barrier(n_streams + 1)
    threads = [threading.Thread(target=_stream_worker,
                                args=(i, source, cfg, duration, out, ready, model, imgsz, vid_stride),
                                daemon=True) for i in range(n_streams)]
    for t in threads:
        t.start()
    ready.wait()   # tüm akışlar açıldı, ölçüm penceresi başlıyor
    psutil.cpu_percent(None)
    gpu_samples = []
    t0 = time.time()
    while any(t.is_alive() for t in threads) and time.time() - t0 < duration + 60:
        time.sleep(2)
        g = _gpu_stats()
        if g["gpu_util"] is not None:
            gpu_samples.append(g["gpu_util"])
    cpu = psutil.cpu_percent(None)
    for t in threads:
        t.join(timeout=30)
    ok = [r for r in out if r and "error" not in r]
    proc = [r["proc_fps"] for r in ok]
    dec = [r["decoded_fps"] for r in ok]
    return {
        "streams": n_streams,
        "ok_streams": len(ok),
        "proc_fps_avg": round(statistics.mean(proc), 1) if proc else 0,
        "proc_fps_min": round(min(proc), 1) if proc else 0,
        "proc_fps_total": round(sum(proc), 1),
        "decode_fps_total": round(sum(dec), 1),
        "gpu_util_avg": round(statistics.mean(gpu_samples)) if gpu_samples else None,
        "gpu_util_max": max(gpu_samples) if gpu_samples else None,
        "cpu_pct": cpu,
        "mem_gb": _gpu_stats()["mem_gb"],
        "errors": [r["error"] for r in out if r.get("error")],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True,
                    help="video dosyası veya RTSP url; {i} akış indeksiyle doldurulur")
    ap.add_argument("--streams", type=int, nargs="+", default=[1])
    ap.add_argument("--duration", type=float, default=60.0)
    ap.add_argument("--model", default=None, help="config'teki detect.model yerine")
    ap.add_argument("--imgsz", type=int, default=None)
    ap.add_argument("--vid-stride", type=int, default=None)
    args = ap.parse_args()

    import logging

    logging.getLogger("ultralytics").setLevel(logging.ERROR)

    print("| akış | işlenen FPS ort/min | toplam işlenen | toplam decode | GPU util ort/maks | CPU % |")
    print("|---|---|---|---|---|---|")
    for n in args.streams:
        r = run_bench(args.source, n, args.duration, args.model, args.imgsz, args.vid_stride)
        print(f"| {r['streams']} | {r['proc_fps_avg']}/{r['proc_fps_min']} | {r['proc_fps_total']} | "
              f"{r['decode_fps_total']} | {r['gpu_util_avg']}/{r['gpu_util_max']} | {r['cpu_pct']} |",
              flush=True)
        print(json.dumps(r), file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
