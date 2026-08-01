"""Kişi sayma — YOLO + ByteTrack + çoklu çizgi geçişi.

Her track'in merkez noktası, her çizginin hangi tarafında olduğuna bakılır; taraf
değişimi = geçiş. A→B (pozitif tarafa) = giriş, B→A = çıkış. Birden çok çizgi
desteklenir; her çizgi ayrı sayılır (isim + giriş/çıkış).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from . import akis
from .config import Config
from .detect import load_yolo
from .device import select_device
from .evidence import kaydet as kanit_kaydet


@dataclass
class CountResult:
    in_count: int = 0
    out_count: int = 0
    frames: int = 0
    fps: float = 0.0
    events: list[dict[str, Any]] = field(default_factory=list)
    lines: list[dict[str, Any]] = field(default_factory=list)  # [{name,in,out}]
    intrusions: list[dict[str, Any]] = field(default_factory=list)  # ihlal alanı alarmları


def _side(px: float, py: float, line: tuple[float, float, float, float]) -> float:
    x1, y1, x2, y2 = line
    return (x2 - x1) * (py - y1) - (y2 - y1) * (px - x1)


def _ascii(s: str) -> str:
    """cv2 Hershey fontu Türkçe karakter basamaz → ASCII'ye çevir."""
    return (s or "").translate(str.maketrans("çğıİöşüÇĞÖŞÜ", "cgiIosuCGOSU"))


def run_count(source: str, cfg: Config, save_video: bool = False,
              store=None, camera_id: str = "",
              lines: list[dict] | None = None, on_event=None,
              on_frame=None,
              should_stop: Callable[[], bool] | None = None,
              intrusions: list[dict] | None = None, on_alert=None) -> CountResult:
    """Videoda kişileri sayar.

    `lines`: [{"name","pts":[[ax,ay],[bx,by]],"direction"}] normalize koordinat.
    direction: 'AtoB' (A→B geçişi = giriş, varsayılan) | 'BtoA' (ters).
    Verilmezse config'teki tek çizgi kullanılır.
    """
    import cv2

    model = cfg.get("detect.model", "yolo11n.pt")
    device = select_device(cfg.get("device", "auto"))
    classes = cfg.get("count.classes", [0])
    tracker = cfg.get("count.tracker", "bytetrack.yaml")
    conf = cfg.get("detect.conf", 0.35)
    iou = cfg.get("detect.iou", 0.5)
    imgsz = cfg.get("detect.imgsz", 640)
    vid_stride = cfg.get("detect.vid_stride", 1)
    min_track_frames = cfg.get("count.min_track_frames", 0)
    anchor = cfg.get("count.anchor", "foot")   # foot=ayak (alt-orta, eğilmede kararlı) | center=merkez
    # Aynı track'in aynı çizgide iki sayımı arası asgari süre (titreşim/çizgi-üstü salınım filtresi)
    cooldown = float(cfg.get("count.cooldown_seconds", 2.0))
    camera_id = camera_id or Path(source).stem

    # lines=None → config varsayılanı (CLI); lines=[] → ÇİZGİ YOK (yalnız ihlal alanı
    # tanımlı kamera). Bu ayrım olmadan boş liste sessizce orta çizgiye düşer, kullanıcı
    # çizmediği bir çizgiden sayım görürdü.
    if lines is None:
        ln = cfg.get("count.line", {"x1": 0.5, "y1": 0.0, "x2": 0.5, "y2": 1.0})
        lines = [{"name": "Çizgi", "pts": [[ln["x1"], ln["y1"]], [ln["x2"], ln["y2"]]],
                  "direction": "AtoB"}]

    cap = akis.ac(source, cfg)
    if not cap.isOpened():
        raise FileNotFoundError(f"Video açılamadı: {source}")
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    cap.release()

    # Her çizgi için piksel koordinat + durum
    L = []
    for li in lines:
        a, b = li["pts"][0], li["pts"][1]
        L.append({"name": li.get("name") or "Çizgi",
                  "px": (a[0] * w, a[1] * h, b[0] * w, b[1] * h),
                  # 'BtoA' seçilirse yön etiketi ters çevrilir (B→A geçişi = giriş)
                  "flip": (li.get("direction") or "AtoB") == "BtoA",
                  "last": {}, "last_count": {}, "in": 0, "out": 0})

    writer = None
    if save_video:
        out_dir = Path(cfg.get("paths.output_dir", "output"))
        out_dir.mkdir(parents=True, exist_ok=True)
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        # Yalnız işlenen kareler yazılır (vid_stride) → gerçek süre için efektif fps
        writer = cv2.VideoWriter(str(out_dir / (Path(source).stem + "_count.mp4")), fourcc,
                                 fps / max(vid_stride, 1), (w, h))

    # İhlal alanları sayım hattında değerlendirilir: aynı tespit+takip çıktısını kullanır
    from .zones import IntrusionWatcher
    watcher = IntrusionWatcher(intrusions or [], w, h,
                               cfg.get("intrusion.dwell_seconds", 1.0),
                               cfg.get("intrusion.cooldown_seconds", 30.0))
    classes_sayim = set(classes)   # ÇİZGİ sayımına giren sınıflar (ihlal genişletmesinden önce)
    if watcher:
        # İhlal alanı insan DIŞI sınıf da isteyebilir (araç); tespit sınıflarını genişlet
        classes = sorted(classes_sayim | {c for z in watcher.zones for c in z["classes"]})

    yolo = load_yolo(model, device, instance_key=camera_id)
    # Akışı ultralytics kendi açar; kameraya özgü HTTP başlıkları koşu boyunca
    # ayarlı kalmalı (kopan bağlantıda kendi kendine yeniden bağlanıyor).
    _basliklar = akis.basliklarla(source, cfg)
    _basliklar.__enter__()
    result = CountResult(fps=fps)
    frame_idx = 0
    track_hits: dict[int, int] = {}   # her track_id kaç karede görüldü (parça filtresi)

    for r in yolo.track(source=source, stream=True, persist=True, tracker=tracker,
                        classes=classes, conf=conf, iou=iou, imgsz=imgsz,
                        vid_stride=vid_stride, device=device, verbose=False):
        # İptal istendi → temiz çık (writer.release döngü sonrasında koşar)
        if should_stop is not None and should_stop():
            break
        frame_idx += 1
        result.frames = frame_idx
        real_frame = frame_idx * vid_stride   # kaynaktaki gerçek kare numarası (yaklaşık)
        ts = real_frame / fps

        boxes = r.boxes
        if boxes is not None and boxes.id is not None:
            ids = boxes.id.int().tolist()
            xyxy = boxes.xyxy.tolist()
            cls_ids = (boxes.cls.int().tolist() if boxes.cls is not None
                       else [0] * len(ids))
            izler: list[tuple[int, float, float, int]] = []
            for tid, (x1, y1, x2, y2), cid in zip(ids, xyxy, cls_ids):
                izler.append((tid, (x1 + x2) / 2.0, y2, cid))   # ayak noktası
            for ihlal in watcher.update(izler, ts):
                ihlal["camera_id"] = camera_id
                ihlal["frame_idx"] = real_frame
                # Alarm anının kanıt karesi — operatör "gerçekten ihlal mi" diye bakabilsin
                ihlal["snapshot"] = kanit_kaydet(
                    cfg, r.orig_img, camera_id, "intrusion",
                    etiket=f"{_ascii(ihlal['zone'])}  track {ihlal['track_id']}  "
                           f"{ihlal['dwell']} sn")
                result.intrusions.append(ihlal)
                if on_alert is not None:
                    on_alert(ihlal)
                if store is not None:
                    store.add_alert("intrusion", ihlal["zone"], "intrusion",
                                    f"track {ihlal['track_id']} · {ihlal['dwell']} sn",
                                    camera_id, snapshot=ihlal["snapshot"])
            for tid, (x1, y1, x2, y2), cid in zip(ids, xyxy, cls_ids):
                if cid not in classes_sayim:
                    continue   # ihlal için eklenen sınıflar ÇİZGİ sayımına girmez
                track_hits[tid] = track_hits.get(tid, 0) + 1
                # Ayak noktası (alt-orta): eğilme/oturmada kutu merkezi kayar ama ayak sabit kalır
                cx = (x1 + x2) / 2.0
                cy = y2 if anchor == "foot" else (y1 + y2) / 2.0
                for lc in L:
                    s = _side(cx, cy, lc["px"])
                    prev = lc["last"].get(tid)
                    # Geçiş + track yeterince uzun + cooldown geçti mi
                    # (ömür-boyu-tek-sayım YOK: girip çıkan kişi iki olay üretir → in−out = içerideki)
                    if (prev is not None and (prev <= 0 < s or prev >= 0 > s)
                            and track_hits[tid] >= min_track_frames
                            and ts - lc["last_count"].get(tid, -1e9) >= cooldown):
                        direction = "in" if s > prev else "out"
                        if lc["flip"]:
                            direction = "out" if direction == "in" else "in"
                        lc["last_count"][tid] = ts
                        lc[direction] += 1
                        if direction == "in":
                            result.in_count += 1
                        else:
                            result.out_count += 1
                        event = {"track_id": tid, "direction": direction, "line": lc["name"],
                                 "frame_idx": real_frame, "ts_seconds": round(ts, 2),
                                 "in": result.in_count, "out": result.out_count}
                        result.events.append(event)
                        if on_event is not None:
                            on_event(event)
                        if store is not None:
                            store.add_count_event(camera_id, tid, direction, lc["name"], ts, real_frame)
                    lc["last"][tid] = s

        if writer is not None or on_frame is not None:
            annotated = r.plot()
            # Yüksek çözünürlükte (ör. 2560×1440) yazı/çizgi okunur kalsın diye ölçekle
            k = max(1.0, w / 1280)
            for z in watcher.zones:      # ihlal alanı — kırmızı poligon
                _draw_zone(cv2, annotated, z, k)
            for lc in L:
                _draw_line(cv2, annotated, lc, k)
            # Sol üst: toplam + çizgi başına döküm — koyu zemin + beyaz yazı (her sahnede okunur)
            y = int(44 * k)
            y += _badge(cv2, annotated, f"TOPLAM  giris:{result.in_count}  cikis:{result.out_count}",
                        14, y, 0.7 * k, max(2, round(2 * k)))
            for lc in L:
                y += _badge(cv2, annotated, f"{_ascii(lc['name'])}: {lc['in']} / {lc['out']}",
                            14, y, 0.55 * k, max(1, round(1.5 * k)))
            if writer is not None:
                writer.write(annotated)
            if on_frame is not None:
                on_frame(annotated)

    _basliklar.__exit__()
    if writer is not None:
        writer.release()
    if store is not None:
        store.commit()
    result.lines = [{"name": lc["name"], "in": lc["in"], "out": lc["out"]} for lc in L]
    return result


def _badge(cv2, img, text: str, x: int, y: int, scale: float, thick: int) -> int:
    """Koyu zemin üzerine beyaz yazı basar; kaplanan yüksekliği (satır aralığı) döndürür."""
    (tw, th), base = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, thick)
    pad = max(4, int(th * 0.45))
    cv2.rectangle(img, (x - pad, y - th - pad), (x + tw + pad, y + base + pad), (32, 28, 24), -1)
    cv2.putText(img, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, scale, (255, 255, 255), thick)
    return th + base + 2 * pad + int(th * 0.3)


def _draw_zone(cv2, img, z, k: float = 1.0) -> None:
    """İhlal alanını yarı saydam kırmızı poligon + isim olarak çizer."""
    import numpy as np

    pts = np.array([[int(x), int(y)] for x, y in z["poly"]], dtype=np.int32)
    kapla = img.copy()
    cv2.fillPoly(kapla, [pts], (0, 0, 220))
    cv2.addWeighted(kapla, 0.22, img, 0.78, 0, img)   # dolgu görüntüyü boğmasın
    cv2.polylines(img, [pts], True, (0, 0, 255), max(2, round(2.5 * k)))
    x, y = pts[0]
    cv2.putText(img, _ascii(z["name"]), (int(x + 6 * k), int(y - 8 * k)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55 * k, (0, 0, 255), max(2, round(2 * k)))


def _draw_line(cv2, img, lc, k: float = 1.0) -> None:
    """Çizgiyi A/B yan etiketleri + isim ile çizer (editörle aynı görünüm).
    k: çözünürlük ölçeği — yüksek çözünürlükte kalınlık/yazı okunur kalır."""
    col = (0, 0, 255)  # KIRMIZI (BGR) — yoğun/parlak sahnede en görünür
    ax, ay, bx, by = [int(v) for v in lc["px"]]
    cv2.line(img, (ax, ay), (bx, by), col, max(4, round(4 * k)))
    for x, y in ((ax, ay), (bx, by)):           # uç tutamaçları
        cv2.circle(img, (x, y), round(5 * k), (255, 255, 255), -1)
        cv2.circle(img, (x, y), round(5 * k), col, max(2, round(2 * k)))
    mx, my = (ax + bx) / 2.0, (ay + by) / 2.0
    dx, dy = bx - ax, by - ay
    n = math.hypot(dx, dy) or 1.0
    ux, uy = dx / n, dy / n
    nx, ny = -uy, ux
    off = 26 * k
    A = (int(mx - nx * off), int(my - ny * off))   # A yanı (negatif taraf)
    B = (int(mx + nx * off), int(my + ny * off))   # B yanı (pozitif taraf = giriş)
    for pt, lbl in ((A, "A"), (B, "B")):
        cv2.circle(img, pt, round(11 * k), col, -1)
        cv2.putText(img, lbl, (int(pt[0] - 5 * k), int(pt[1] + 5 * k)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5 * k, (255, 255, 255), max(2, round(2 * k)))
    # çizgi adı — çizginin üstünde
    cv2.putText(img, _ascii(lc["name"]), (int(ax + 8 * k), int(ay - 8 * k)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55 * k, col, max(2, round(2 * k)))
