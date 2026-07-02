"""Yüz tespit + anonim demografi — InsightFace (buffalo_l: tespit + ArcFace + yaş/cinsiyet).

Varsayılan ANONİM: kimliklendirme yok, sadece yaş/cinsiyet tahmini + sayı (KVKK).
İsimli tanıma (identify=true) ileride embedding eşleştirmesiyle eklenir ve KVKK
kapısına bağlıdır (manifest forbidden: rıza/aydınlatma olmadan üretim akışı yok).
"""
from __future__ import annotations

import functools
from dataclasses import dataclass
from pathlib import Path

from .config import Config
from .device import select_device


@dataclass
class FaceResult:
    detections: int = 0
    frames: int = 0
    male: int = 0
    female: int = 0
    avg_age: float = 0.0
    matches: list = None  # [{name,label,list_type,score}]

    def __post_init__(self):
        if self.matches is None:
            self.matches = []


def _cosine(a, b) -> float:
    import numpy as np
    a = np.asarray(a, dtype="float32"); b = np.asarray(b, dtype="float32")
    na = (a @ a) ** 0.5; nb = (b @ b) ** 0.5
    return float(a @ b / (na * nb)) if na and nb else 0.0


def embed_largest_face(source: str, cfg: Config, samples: int = 12) -> list | None:
    """Kaynaktan en büyük yüzün embedding'ini çıkarır (enroll için).

    Tek kareye güvenmez: video boyunca eşit aralıklı `samples` kare tarar,
    bulunan en büyük yüzü seçer. Böylece gözetim açısında da yüz yakalanır.
    """
    import cv2
    app = _load_face(cfg.get("face.model_pack", "buffalo_l"),
                     cfg.get("face.det_size", 640), select_device(cfg.get("device", "auto")))
    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        return None
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    idxs = [int(total * i / (samples + 1)) for i in range(1, samples + 1)] if total > 1 else [0]
    best, best_area = None, 0.0
    for fi in idxs:
        if total > 1:
            cap.set(cv2.CAP_PROP_POS_FRAMES, fi)
        ok, frame = cap.read()
        if not ok:
            continue
        for f in app.get(frame):
            area = (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1])
            emb = getattr(f, "normed_embedding", None)
            if emb is not None and area > best_area:
                best, best_area = emb, area
    cap.release()
    return best.tolist() if best is not None else None


@functools.lru_cache(maxsize=1)
def _load_face(model_pack: str, det_size: int, device: str):
    """InsightFace FaceAnalysis'i bir kez yükler.

    Apple Silicon'da onnxruntime CPU provider kullanılır (ctx_id=-1).
    """
    from insightface.app import FaceAnalysis

    app = FaceAnalysis(name=model_pack)
    ctx_id = 0 if device == "cuda" else -1   # MPS/CPU → -1 (CPU provider)
    app.prepare(ctx_id=ctx_id, det_size=(det_size, det_size))
    return app


def run_face(source: str, cfg: Config, save_video: bool = False,
             store=None, run_id: int | None = None, watch: list | None = None) -> FaceResult:
    import cv2

    model_pack = cfg.get("face.model_pack", "buffalo_l")
    det_size = cfg.get("face.det_size", 640)
    vid_stride = max(cfg.get("detect.vid_stride", 1), 1)
    device = select_device(cfg.get("device", "auto"))
    thr = cfg.get("face.match_threshold", 0.5)
    # İzleme listesi embedding'leri (enroll edilmiş yüzler)
    watch = watch or []
    seen_match: set[str] = set()

    app = _load_face(model_pack, det_size, device)

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
        writer = cv2.VideoWriter(str(out_dir / (Path(source).stem + "_face.mp4")),
                                 fourcc, fps, (w, h))

    res = FaceResult()
    age_sum = 0.0
    frame_idx = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        frame_idx += 1
        # Demografi her karede gerekmez — seyrek örnekle (yük + tekrar sayımı azaltır)
        if frame_idx % vid_stride != 0:
            continue
        res.frames += 1
        ts = frame_idx / fps

        faces = app.get(frame)
        for f in faces:
            res.detections += 1
            age = int(getattr(f, "age", 0) or 0)
            sex = getattr(f, "sex", None)  # 'M' | 'F'
            score = float(getattr(f, "det_score", 0.0) or 0.0)
            age_sum += age
            if sex == "M":
                res.male += 1
            elif sex == "F":
                res.female += 1
            if store and run_id is not None:
                store.add_face_event(run_id, age, sex, score, frame_idx, ts)

            # İzleme listesi eşleşmesi (embedding cosine)
            if watch:
                emb = getattr(f, "normed_embedding", None)
                if emb is not None:
                    for w in watch:
                        if w["name"] in seen_match:
                            continue
                        sc = _cosine(emb, w["embedding"])
                        if sc >= thr:
                            seen_match.add(w["name"])
                            res.matches.append({"name": w["name"], "label": w.get("label", ""),
                                                "list_type": w["list_type"], "score": round(sc, 3)})

            if writer is not None:
                x1, y1, x2, y2 = [int(v) for v in f.bbox]
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 200, 255), 2)
                cv2.putText(frame, f"{sex} ~{age}", (x1, max(0, y1 - 8)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 200, 255), 2)

        if writer is not None:
            writer.write(frame)

    cap.release()
    if writer is not None:
        writer.release()
    if res.detections:
        res.avg_age = age_sum / res.detections
    if store is not None:
        store.commit()
    return res
