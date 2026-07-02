"""Plaka okuma — fast-alpr (tespit + OCR).

Plaka METİN olduğu için eşleştirme düz string'tir (yüz embedding'inden kolay).
Asıl zorluk OCR doğruluğu: aynı geçişte birden çok kare okunup en güveniliri tutulur.
"""
from __future__ import annotations

import functools
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import Config


@dataclass
class PlateResult:
    plates: set[str] = field(default_factory=set)
    total_reads: int = 0
    frames: int = 0
    reads: list[dict[str, Any]] = field(default_factory=list)
    voted: list[dict[str, Any]] = field(default_factory=list)  # [{plate,count,conf}]


def _lev(a: str, b: str) -> int:
    """Levenshtein mesafesi (kısa stringler için yeterli)."""
    if a == b:
        return 0
    if not a or not b:
        return max(len(a), len(b))
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _vote(reads: list[dict[str, Any]], max_dist: int = 2) -> list[dict[str, Any]]:
    """Çok-kareli oylama: benzer okumaları kümeler, her küme için en güvenilir
    metni seçer. Aynı aracın kareler arası ufak OCR farkları tek plakaya iner.
    """
    clusters: list[dict[str, Any]] = []  # {rep, members:[(text,conf)]}
    for r in sorted(reads, key=lambda x: -(x.get("confidence") or 0)):
        t = r["plate"]
        c = r.get("confidence") or 0.0
        hit = None
        for cl in clusters:
            if abs(len(cl["rep"]) - len(t)) <= 1 and _lev(cl["rep"], t) <= max_dist:
                hit = cl
                break
        if hit:
            hit["members"].append((t, c))
        else:
            # temsilci okumadan kare/zaman bilgisini de taşı (DB olayı için)
            clusters.append({"rep": t, "members": [(t, c)],
                             "frame_idx": r.get("frame_idx", 0),
                             "ts_seconds": r.get("ts_seconds", 0.0)})
    out = []
    for cl in clusters:
        # küme içinde en sık + en güvenilir metni temsilci seç
        score: dict[str, float] = {}
        cnt: dict[str, int] = {}
        for t, c in cl["members"]:
            score[t] = score.get(t, 0.0) + (c or 0.5)
            cnt[t] = cnt.get(t, 0) + 1
        best = max(score, key=lambda k: (cnt[k], score[k]))
        confs = [c for _, c in cl["members"] if c]
        out.append({"plate": best, "count": len(cl["members"]),
                    "conf": round(sum(confs) / len(confs), 3) if confs else None,
                    "frame_idx": cl["frame_idx"], "ts_seconds": cl["ts_seconds"]})
    return sorted(out, key=lambda x: -x["count"])


@functools.lru_cache(maxsize=1)
def _load_alpr(detector: str, ocr: str):
    """fast-alpr ALPR örneğini bir kez yükler (model reuse).

    Apple Silicon: CoreML EP, yolo-v9 detektörünün dinamik şekliyle uyuşmuyor
    (zero-element hatası). Bu yüzden CPU provider'a zorlanır — POC için yeterli.
    """
    from fast_alpr import ALPR

    providers = ["CPUExecutionProvider"]
    return ALPR(detector_model=detector, ocr_model=ocr,
                detector_providers=providers, ocr_providers=providers)


def _as_float_conf(conf) -> float | None:
    """OCR confidence float veya (karakter bazlı) liste olabilir → tek skora indir."""
    if conf is None:
        return None
    if isinstance(conf, (list, tuple)):
        vals = [float(x) for x in conf if x is not None]
        return sum(vals) / len(vals) if vals else None
    return float(conf)


def run_plate(source: str, cfg: Config, save_video: bool = False,
              store=None, camera_id: str = "", on_read=None) -> PlateResult:
    import cv2

    detector = cfg.get("plate.detector", "yolo-v9-t-384-license-plate-end2end")
    ocr = cfg.get("plate.ocr", "global-plates-mobile-vit-v2-model")
    min_conf = cfg.get("plate.min_conf", 0.4)
    vid_stride = cfg.get("detect.vid_stride", 1)
    camera_id = camera_id or Path(source).stem

    alpr = _load_alpr(detector, ocr)

    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        raise FileNotFoundError(f"Video açılamadı: {source}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0

    writer = None
    if save_video:
        out_dir = Path(cfg.get("paths.output_dir", "output"))
        out_dir.mkdir(parents=True, exist_ok=True)
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(str(out_dir / (Path(source).stem + "_plate.mp4")),
                                 fourcc, fps, (w, h))

    res = PlateResult()
    frame_idx = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        frame_idx += 1
        if vid_stride > 1 and frame_idx % vid_stride != 0:
            continue
        res.frames += 1
        ts = frame_idx / fps

        for pred in alpr.predict(frame):
            ocr_res = getattr(pred, "ocr", None)
            text = getattr(ocr_res, "text", None) if ocr_res else None
            conf = _as_float_conf(getattr(ocr_res, "confidence", None) if ocr_res else None)
            if not text or (conf is not None and conf < min_conf):
                continue
            plate = text.replace(" ", "").upper()
            res.plates.add(plate)
            res.total_reads += 1
            res.reads.append({"plate": plate, "confidence": conf,
                              "frame_idx": frame_idx, "ts_seconds": round(ts, 2)})
            if on_read:
                on_read(plate, conf, frame_idx, round(ts, 2))

        if writer is not None:
            drawn = alpr.draw_predictions(frame)
            # fast-alpr sürümüne göre ndarray veya .image taşıyan nesne dönebilir
            writer.write(getattr(drawn, "image", drawn))

    cap.release()
    if writer is not None:
        writer.release()
    # Çok-kareli oylama: gürültülü okumaları konsolide et.
    # DB'ye kare başına değil ARAÇ başına tek satır yazılır (track bazlı olay).
    res.voted = _vote(res.reads)
    if store is not None:
        for v in res.voted:
            store.add_plate_event(camera_id, v["plate"], v["conf"], v["count"],
                                  v["ts_seconds"], v["frame_idx"])
        store.commit()
    return res
