"""Yüz tespit + anonim demografi — InsightFace (buffalo_l: tespit + ArcFace + yaş/cinsiyet).

Varsayılan ANONİM: kimliklendirme yok, sadece yaş/cinsiyet tahmini + sayı (KVKK).
İzleme listesi eşleşmesi (embedding cosine) enroll edilmiş kişilerle sınırlıdır.

Olaylar TRACK bazlıdır: basit IoU takipçisi aynı kişiyi kareler arası birleştirir,
kişi sahneden çıkınca TEK satır yazılır (medyan yaş + çoğunluk cinsiyet).
Kare başına satır yazılmaz → mükerrer demografi ve DB şişmesi biter.
"""
from __future__ import annotations

import functools
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .config import Config
from .device import select_device


@dataclass
class FaceResult:
    detections: int = 0          # benzersiz KİŞİ (track) sayısı
    raw_detections: int = 0      # kare bazlı ham tespit (teşhis için)
    frames: int = 0
    male: int = 0
    female: int = 0
    avg_age: float = 0.0
    matches: list = field(default_factory=list)  # [{name,label,list_type,score}]


def _cosine(a, b) -> float:
    import numpy as np
    a = np.asarray(a, dtype="float32"); b = np.asarray(b, dtype="float32")
    na = (a @ a) ** 0.5; nb = (b @ b) ** 0.5
    return float(a @ b / (na * nb)) if na and nb else 0.0


def _iou(a, b) -> float:
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua > 0 else 0.0


def _affinity(a, b) -> float:
    """Kutu benzerliği: IoU + merkez mesafesi karışımı.

    Kare atlama (vid_stride) yüzünden ardışık işlenen kareler arasında yüz çok yer
    değiştirir ve IoU sıfıra düşebilir; merkez mesafesi (yüz boyutuna oranla) bu
    kopmaları yakalar. Dönen değer 0-1, eşik run_face'te uygulanır.
    """
    import math
    v = _iou(a, b)
    if v > 0:
        return v
    acx, acy = (a[0] + a[2]) / 2, (a[1] + a[3]) / 2
    bcx, bcy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
    size = max(a[2] - a[0], a[3] - a[1], b[2] - b[0], b[3] - b[1], 1.0)
    d = math.hypot(acx - bcx, acy - bcy) / size
    # merkez ≤ 2 yüz-boyu uzaklıkta → zayıf ama geçerli benzerlik (0-0.3 bandı);
    # 1 yüz-boyu kayma ≈ 0.15 çıkar, varsayılan eşik 0.1'i geçer (kare atlama toleransı)
    return max(0.0, 0.3 * (1.0 - d / 2.0))


class _FaceTrack:
    """Kareler arası aynı yüzü birleştiren hafif track durumu."""

    __slots__ = ("tid", "bbox", "last_frame", "first_frame", "first_ts",
                 "ages", "sexes", "conf", "match_name", "match_score", "match_meta",
                 "emb", "emb_score", "n_frames")

    def __init__(self, tid: int, bbox, frame_idx: int, ts: float):
        self.tid = tid
        self.bbox = bbox
        self.last_frame = frame_idx
        self.first_frame = frame_idx
        self.first_ts = ts
        self.ages: list[int] = []
        self.sexes: list[str] = []
        self.conf = 0.0
        self.match_name: str | None = None
        self.match_score = 0.0
        self.match_meta: dict = {}
        self.emb = None            # en kaliteli karenin ArcFace embedding'i (re-id için)
        self.emb_score = 0.0       # o embedding'in det_score'u (daha iyisi gelirse değişir)
        self.n_frames = 0          # track'in görüldüğü işlenen kare sayısı (hayalet filtresi)


def _best_reid(emb, gallery: list[_FaceTrack], thr: float) -> _FaceTrack | None:
    """Kapanmış kimlikler (gallery) içinde embedding'e en yakın track'i döndürür.

    En iyi cosine skoru `thr` eşiğinin altındaysa None (yeni kişi). Konumsal
    takipçi yüzü kaçırıp track kapansa da aynı kişi yeni kişi sayılmaz.
    """
    if emb is None:
        return None
    best: _FaceTrack | None = None
    best_sc = thr
    for t in gallery:
        if t.emb is None:
            continue
        sc = _cosine(emb, t.emb)
        if sc >= best_sc:
            best, best_sc = t, sc
    return best


def _dedup_tracks(cands: list[_FaceTrack], thr: float) -> list[_FaceTrack]:
    """Finalize öncesi kimlik birleştirme: aynı kişinin track'lerini tek kümeye indirir.

    Canlı re-id'nin yakalayamadığı vakaları kapatır: aynı anda AÇIK olan iki track
    gallery'de hiç karşılaşmaz ve re-id kararı tek karelik (düşük kaliteli)
    embedding'le verilir; burada ise track'lerin EN KALİTELİ embedding'leri
    karşılaştırılır.

    Greedy: adaylar n_frames'e göre büyükten küçüğe gezilir; her aday, kabul
    edilmiş kümelerin temsilci embedding'iyle (kümenin en yüksek emb_score'lusu)
    cosine karşılaştırılır. En iyi skor ≥ thr → o kümeye birleşir; değilse
    (veya embedding'i yoksa) kendi kümesi olur. Dönen liste: küme temsilcileri
    (birleşenlerin demografisi temsilcide birikmiş halde).
    """
    clusters: list[_FaceTrack] = []
    for t in sorted(cands, key=lambda x: -x.n_frames):
        best: _FaceTrack | None = None
        best_sc = thr
        if t.emb is not None:
            for c in clusters:
                if c.emb is None:
                    continue
                sc = _cosine(t.emb, c.emb)
                if sc >= best_sc:
                    best, best_sc = c, sc
        if best is None:
            clusters.append(t)
            continue
        # Birleştir: demografi birikir, en güçlü eşleşme/embedding kümeyi temsil eder
        best.ages.extend(t.ages)
        best.sexes.extend(t.sexes)
        best.conf = max(best.conf, t.conf)
        best.n_frames += t.n_frames
        best.first_frame = min(best.first_frame, t.first_frame)
        best.first_ts = min(best.first_ts, t.first_ts)
        if t.match_score > best.match_score:
            best.match_name = t.match_name
            best.match_score = t.match_score
            best.match_meta = t.match_meta
        if t.emb_score > best.emb_score:
            best.emb, best.emb_score = t.emb, t.emb_score
    return clusters


def _compact_gallery(gallery: list[_FaceTrack], retired: list[_FaceTrack],
                     gallery_max: int, thr: float) -> list[_FaceTrack]:
    """Gallery bellek sınırı (uzun kayıt/RTSP): sınır aşılırsa yeni gallery döndürür.

    Önce dedup ile kompaktlanır (aynı kişinin girdileri birleşir); hâlâ sınır
    üstündeyse en düşük n_frames'li fazlalık `retired` listesine taşınır —
    retired final sayımda dedup'a girer (sayım kaybolmaz) ama canlı re-ID
    taramasından çıkar (her tespitte taranan liste sabit boyda kalır).
    """
    if len(gallery) <= gallery_max:
        return gallery
    gallery = _dedup_tracks(gallery, thr)
    if len(gallery) > gallery_max:
        gallery.sort(key=lambda t: -t.n_frames)
        retired.extend(gallery[gallery_max:])
        gallery = gallery[:gallery_max]
    return gallery


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

    CUDA'da GPU provider (ctx_id=0, onnxruntime-gpu varsa CUDA EP);
    Apple Silicon/CPU'da CPU provider (ctx_id=-1).
    """
    from insightface.app import FaceAnalysis

    from .device import ort_providers

    app = FaceAnalysis(name=model_pack, providers=ort_providers(device))
    ctx_id = 0 if device == "cuda" else -1   # MPS/CPU → -1 (CPU provider)
    app.prepare(ctx_id=ctx_id, det_size=(det_size, det_size))
    return app


def run_face(source: str, cfg: Config, save_video: bool = False,
             store=None, camera_id: str = "", watch: list | None = None,
             on_progress=None, on_frame=None,
             should_stop: Callable[[], bool] | None = None) -> FaceResult:
    import cv2

    model_pack = cfg.get("face.model_pack", "buffalo_l")
    det_size = cfg.get("face.det_size", 640)
    vid_stride = max(cfg.get("detect.vid_stride", 1), 1)
    device = select_device(cfg.get("device", "auto"))
    thr = cfg.get("face.match_threshold", 0.5)
    aff_thr = cfg.get("face.track_affinity", 0.1)
    reid_thr = cfg.get("face.reid_threshold", 0.40)
    min_track_frames = cfg.get("face.min_track_frames", 3)
    gallery_max = cfg.get("face.gallery_max", 128)
    camera_id = camera_id or Path(source).stem
    watch = watch or []
    seen_match: set[str] = set()

    app = _load_face(model_pack, det_size, device)

    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        raise FileNotFoundError(f"Video açılamadı: {source}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    # Track bu kadar GERÇEK kare boyunca görünmezse kapanır (kişi sahneden çıktı)
    miss_frames = max(int(fps), vid_stride * 8)   # ~1 saniye

    writer = None
    if save_video:
        out_dir = Path(cfg.get("paths.output_dir", "output"))
        out_dir.mkdir(parents=True, exist_ok=True)
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        # Yalnız işlenen kareler yazılır (vid_stride) → gerçek süre için efektif fps
        writer = cv2.VideoWriter(str(out_dir / (Path(source).stem + "_face.mp4")),
                                 fourcc, fps / max(vid_stride, 1), (w, h))

    res = FaceResult()
    tracks: list[_FaceTrack] = []
    gallery: list[_FaceTrack] = []   # kapanmış kimlikler — re-id ile diriltilebilir
    retired: list[_FaceTrack] = []   # gallery sınırından emekliler — yalnız final sayıma girer
    next_tid = 1
    age_sum = 0.0

    def emit_progress(frame=None, active=None) -> None:
        if on_progress is None:
            return
        avg_age = (age_sum / res.detections) if res.detections else 0.0
        # Canlı "benzersiz kişi": kapananlar + yeterince uzun yaşayan açık/kapanmış track'ler
        live_det = res.detections + sum(
            1 for t in (*tracks, *gallery, *retired) if t.n_frames >= min_track_frames)
        on_progress({"frames": res.frames, "frame_idx": frame_idx if frame is None else frame,
                     "raw": res.raw_detections, "active": len(tracks) if active is None else active,
                     "detections": live_det, "male": res.male, "female": res.female,
                     "avg_age": round(avg_age, 1), "matches": res.matches[-10:]})

    def finalize(t: _FaceTrack) -> None:
        nonlocal age_sum
        age = int(statistics.median(t.ages)) if t.ages else None
        gender = max(set(t.sexes), key=t.sexes.count) if t.sexes else None
        res.detections += 1
        if gender == "M":
            res.male += 1
        elif gender == "F":
            res.female += 1
        if age is not None:
            age_sum += age
        if store is not None:
            store.add_face_event(camera_id, age, gender, round(t.conf, 3),
                                 t.first_ts, t.first_frame, track_id=t.tid,
                                 match_name=t.match_name,
                                 match_score=round(t.match_score, 3) if t.match_name else None)
        emit_progress(active=len(tracks))

    frame_idx = 0
    while True:
        # İptal istendi → temiz çık (writer.release/finalize döngü sonrasında koşar)
        if should_stop is not None and should_stop():
            break
        ok, frame = cap.read()
        if not ok:
            break
        frame_idx += 1
        # Demografi her karede gerekmez — seyrek örnekle (yük azaltır)
        if frame_idx % vid_stride != 0:
            continue
        res.frames += 1
        ts = frame_idx / fps

        faces = app.get(frame)
        # Kaybolan track'ler finalize EDİLMEZ — gallery'ye taşınır (kapanmış kimlik):
        # kısa süre kaçırılan yüz embedding ile diriltilir, aynı kişi iki kez sayılmaz.
        # Hayaletler (kısa yaşamış VE eşleşmesiz) gallery'ye hiç alınmaz — video-sonu
        # eleme kuralının erken uygulanması (bellek + tarama maliyeti düşer).
        gone = [t for t in tracks if frame_idx - t.last_frame > miss_frames]
        tracks = [t for t in tracks if frame_idx - t.last_frame <= miss_frames]
        gallery.extend(t for t in gone
                       if t.n_frames >= min_track_frames or t.match_name is not None)
        gallery = _compact_gallery(gallery, retired, gallery_max, reid_thr)

        for f in faces:
            res.raw_detections += 1
            bbox = tuple(float(v) for v in f.bbox)
            age = int(getattr(f, "age", 0) or 0)
            sex = getattr(f, "sex", None)  # 'M' | 'F'
            score = float(getattr(f, "det_score", 0.0) or 0.0)
            emb = getattr(f, "normed_embedding", None)

            # Benzerlikle (IoU + merkez) mevcut track'e bağla; yoksa önce re-id dene
            best_t, best_aff = None, aff_thr
            for t in tracks:
                v = _affinity(bbox, t.bbox)
                if v > best_aff:
                    best_t, best_aff = t, v
            if best_t is None:
                # Konumsal eşleşme yok → kapanmış kimliklerde embedding ara (re-id)
                revived = _best_reid(emb, gallery, reid_thr)
                if revived is not None:
                    gallery.remove(revived)
                    tracks.append(revived)
                    best_t = revived
                else:
                    best_t = _FaceTrack(next_tid, bbox, frame_idx, ts)
                    next_tid += 1
                    tracks.append(best_t)
            best_t.bbox = bbox
            best_t.last_frame = frame_idx
            best_t.n_frames += 1
            if age:
                best_t.ages.append(age)
            if sex in ("M", "F"):
                best_t.sexes.append(sex)
            best_t.conf = max(best_t.conf, score)
            # Re-id için en kaliteli (en yüksek det_score) karenin embedding'i tutulur
            if emb is not None and score > best_t.emb_score:
                best_t.emb, best_t.emb_score = emb, score

            # İzleme listesi eşleşmesi (embedding cosine) — track'e işlenir
            if watch:
                if emb is not None:
                    for wt in watch:
                        sc = _cosine(emb, wt["embedding"])
                        if sc >= thr and sc > best_t.match_score:
                            best_t.match_name = wt["name"]
                            best_t.match_score = sc
                            best_t.match_meta = {"label": wt.get("label", ""),
                                                 "list_type": wt["list_type"]}
                        if sc >= thr and wt["name"] not in seen_match:
                            seen_match.add(wt["name"])
                            res.matches.append({"name": wt["name"], "label": wt.get("label", ""),
                                                "list_type": wt["list_type"], "score": round(sc, 3)})

            if writer is not None or on_frame is not None:
                x1, y1, x2, y2 = [int(v) for v in bbox]
                k = max(1.0, frame.shape[1] / 1280)  # yüksek çözünürlükte okunur kalsın
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 200, 255), max(2, round(2 * k)))
                cv2.putText(frame, f"#{best_t.tid} {sex} ~{age}", (x1, max(0, int(y1 - 8 * k))),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6 * k, (0, 200, 255), max(2, round(2 * k)))

        emit_progress(frame_idx, len(tracks))

        if writer is not None:
            writer.write(frame)
        if on_frame is not None:
            on_frame(frame)

    # Video bitti (veya iptal) — açık track'ler + kapanmış/emekli kimlikler birlikte
    # kapanır. Kısa yaşamış VE izleme eşleşmesi olmayan track'ler hayalet tespittir:
    # sayılmaz, DB'ye yazılmaz. Kalanlar finalize öncesi embedding-dedup'tan geçer
    # (aynı kişinin birleşmemiş track'leri tek kişiye iner → tek DB satırı).
    dead = [*tracks, *gallery, *retired]
    tracks, gallery, retired = [], [], []
    cands = [t for t in dead
             if t.n_frames >= min_track_frames or t.match_name is not None]
    for t in _dedup_tracks(cands, reid_thr):
        finalize(t)

    cap.release()
    if writer is not None:
        writer.release()
    if res.detections:
        res.avg_age = age_sum / res.detections
    emit_progress(frame_idx, 0)
    if store is not None:
        store.commit()
    return res
