"""GPU pipeline motoru (`worker.engine: nvdec`) — ADR-0003.

Akış: go2rtc HTTP-TS → PyNvVideoCodec (NVDEC, kamera başına decoder thread,
son-kare-kazanır) → hareket ön-filtresi (Y-düzlemi fark, GPU) → NV12→BGR +
letterbox (torch) → TEK batch TensorRT YOLO → kamera başına BoT-SORT +
çizgi mantığı → BusStore. Plaka/yüz olay-tetikli ikinci kademe (her karede değil).

Sözleşme: olaylar yalnız `store` (BusStore) üzerinden yayınlanır —
add_count_event / add_plate_event / add_face_event imzaları değişmez (ADR-0002).
KVKK: ham kare diske/DB'ye yazılmaz; yalnız bellekte işlenir.

Not: PyNvVideoCodec demuxer'ı RTSP'de TCP'ye düşemiyor (461 → çökme);
bu yüzden kaynaklar go2rtc'nin HTTP MPEG-TS çıkışından alınır (ADR-0003).
"""
from __future__ import annotations

import threading
import time
from typing import Any

from .bus import publish
from .config import http_options
from .count import _side
from .plate import _lev, _vote

# COCO: plaka tetiği için araç sınıfları (sabit sınıf uzayı, eşik değil)
_VEHICLE_CLASSES = {2, 3, 5, 7}   # car, motorcycle, bus, truck
_PERSON_CLASS = 0


# ── Çizgi sayacı — count.py ile aynı semantik (taraf değişimi + cooldown) ──
class LineCounter:
    def __init__(self, lines: list[dict], w: int, h: int,
                 cooldown: float, min_track_frames: int) -> None:
        self.cooldown = cooldown
        self.min_track_frames = min_track_frames
        self.lines = []
        for li in lines:
            a, b = li["pts"][0], li["pts"][1]
            self.lines.append({"name": li.get("name") or "Çizgi",
                               "px": (a[0] * w, a[1] * h, b[0] * w, b[1] * h),
                               "flip": (li.get("direction") or "AtoB") == "BtoA",
                               "last": {}, "last_count": {}})
        self.track_hits: dict[int, int] = {}

    def update(self, tracks: list[tuple[int, float, float]], ts: float) -> list[dict]:
        """tracks: [(track_id, ayak_x, ayak_y)] piksel koordinat. Olay listesi döner."""
        events = []
        for tid, cx, cy in tracks:
            self.track_hits[tid] = self.track_hits.get(tid, 0) + 1
            for lc in self.lines:
                s = _side(cx, cy, lc["px"])
                prev = lc["last"].get(tid)
                if (prev is not None and (prev <= 0 < s or prev >= 0 > s)
                        and self.track_hits[tid] >= self.min_track_frames
                        and ts - lc["last_count"].get(tid, -1e9) >= self.cooldown):
                    direction = "in" if s > prev else "out"
                    if lc["flip"]:
                        direction = "out" if direction == "in" else "in"
                    lc["last_count"][tid] = ts
                    events.append({"track_id": tid, "direction": direction,
                                   "line": lc["name"]})
                lc["last"][tid] = s
        return events


# ── NVDEC decoder thread'i — son kareyi tutar (kuyruk yok, gecikme birikmez) ──
class _Decoder(threading.Thread):
    def __init__(self, cam_id: str, url: str, extra_opts: dict | None = None) -> None:
        super().__init__(daemon=True, name=f"dec-{cam_id}")
        self.cam_id = cam_id
        self.url = url
        self.extra_opts = extra_opts or {}   # CDN/HLS başlıkları (stream.http_headers)
        self.lock = threading.Lock()
        self.latest = None          # torch NV12 (H*3/2, W) uint8 cuda
        self.wh: tuple[int, int] | None = None
        self.seq = 0
        self.status = "başlıyor"
        self.fps = 0.0
        self.stop_flag = False

    def run(self) -> None:
        import ctypes

        import av
        import torch

        import PyNvVideoCodec as nvc

        # Demux PyAV ile yapılır: PyNvVideoCodec'in kendi demuxer'ı ağ
        # okuması sırasında GIL'i bırakmıyor — tek canlı akış bile tüm Python
        # sürecini ~30× yavaşlatıyor (ölçüldü). PyAV av_read_frame'i GIL'siz
        # çağırır; paketler PacketData ile NVDEC'e beslenir.
        # Bu thread'de torch'un birincil CUDA bağlamını aktive et — decoder
        # cudacontext=0 ile MEVCUT bağlamı kullanır; bağlam yoksa kendi
        # bağlamını yaratır ve DLPack işaretçileri torch tarafında çöp okunur.
        torch.zeros(1, device="cuda")
        codec_map = {"h264": nvc.cudaVideoCodec.H264, "hevc": nvc.cudaVideoCodec.HEVC,
                     "av1": nvc.cudaVideoCodec.AV1, "vp9": nvc.cudaVideoCodec.VP9}

        while not self.stop_flag:
            cont = None
            try:
                opts = {"rtsp_transport": "tcp"} if self.url.startswith("rtsp") else {}
                opts.update(self.extra_opts)
                # (açılış, okuma) sn — çok kameralı başlangıç fırtınasında go2rtc
                # producer'ı geç ayağa kalkabiliyor; kısa timeout flapping yapar
                cont = av.open(self.url, options=opts, timeout=(30.0, 30.0))
                vs = cont.streams.video[0]
                cname = vs.codec_context.name
                dec = nvc.CreateDecoder(gpuid=0, codec=codec_map.get(cname, nvc.cudaVideoCodec.H264),
                                        cudacontext=0, cudastream=0, usedevicememory=True)
                pkt = nvc.PacketData()
                extradata = vs.codec_context.extradata or b""
                # avcC/mp4 kaplı akışlarda annex-b'ye çevir (TS/RTSP zaten annex-b)
                bsf = None
                if extradata[:1] == b"\x01" and cname in ("h264", "hevc"):
                    bsf = av.bitstream.BitStreamFilterContext(f"{cname}_mp4toannexb", vs)
                self.status = "ok"
                n, t0 = 0, time.time()
                for packet in cont.demux(vs):
                    if self.stop_flag:
                        return
                    if packet.size == 0:
                        continue
                    for p in (bsf.filter(packet) if bsf else (packet,)):
                        buf = bytes(p)
                        if not buf:
                            continue
                        arr = (ctypes.c_uint8 * len(buf)).from_buffer_copy(buf)
                        pkt.bsl_data = ctypes.addressof(arr)
                        pkt.bsl = len(buf)
                        for frame in dec.Decode(pkt):
                            # decoder tamponu yeniden kullanılır → kopya şart
                            t = torch.from_dlpack(frame).clone()
                            with self.lock:
                                self.latest = t
                                self.wh = (t.shape[1], t.shape[0] * 2 // 3)
                                self.seq += 1
                            n += 1
                            if n % 50 == 0:
                                self.fps = 50 / max(time.time() - t0, 1e-6)
                                t0 = time.time()
                # akış bitti (dosya sonu / kopma) → yeniden bağlan
                self.status = "no_signal"
            except Exception as e:
                self.status = "decode_err"
                print(f"[nvdec] {self.cam_id} decoder hatası: {e}", flush=True)
            finally:
                if cont is not None:
                    try:
                        cont.close()
                    except Exception:
                        pass
            time.sleep(3)

    def grab(self):
        """(nv12, (w,h), seq) — yeni kare yoksa nv12=None."""
        with self.lock:
            return self.latest, self.wh, self.seq


# ── GPU yardımcıları ────────────────────────────────────────────────
def _nv12_to_bgr(nv12, w: int, h: int):
    """NV12 (H*3/2, W) uint8 → BGR (H, W, 3) uint8, tümü GPU'da (BT.601)."""
    import torch

    y = nv12[:h].float() - 16.0
    uv = nv12[h:h + h // 2].reshape(h // 2, w // 2, 2).float() - 128.0
    u = uv[..., 0].repeat_interleave(2, 0).repeat_interleave(2, 1)
    v = uv[..., 1].repeat_interleave(2, 0).repeat_interleave(2, 1)
    y = 1.164 * y
    r = y + 1.596 * v
    g = y - 0.392 * u - 0.813 * v
    b = y + 2.017 * u
    return torch.stack((b, g, r), dim=-1).clamp_(0, 255).to(torch.uint8)


def _letterbox(bgr, size: int):
    """BGR (H,W,3) uint8 GPU → (3,size,size) float yarı-normalize + geri-dönüşüm parametreleri."""
    import torch
    import torch.nn.functional as F

    h, w = bgr.shape[:2]
    r = min(size / w, size / h)
    nw, nh = round(w * r), round(h * r)
    img = bgr.permute(2, 0, 1).float().unsqueeze(0)          # 1,3,H,W (BGR→model RGB aşağıda)
    img = F.interpolate(img, size=(nh, nw), mode="bilinear", align_corners=False)
    canvas = torch.full((1, 3, size, size), 114.0, device=bgr.device)
    px, py = (size - nw) // 2, (size - nh) // 2
    canvas[:, :, py:py + nh, px:px + nw] = img
    rgb = canvas[:, [2, 1, 0]] / 255.0                        # BGR→RGB + 0-1
    return rgb[0], (r, px, py)


def _nv12_letterbox_rgb(nv12, w: int, h: int, size: int):
    """NV12 → letterbox'lı (3,size,size) RGB float — renk dönüşümü HEDEF çözünürlükte.

    Tam çözünürlükte BGR üretip küçültmek yerine Y/UV düzlemleri önce hedefe
    ölçeklenir, renk matematiği ~4× daha az piksele uygulanır (GPU bant genişliği
    ana maliyet — 48+ kamerada belirleyici).
    """
    import torch
    import torch.nn.functional as F

    r = min(size / w, size / h)
    nw, nh = round(w * r), round(h * r)
    y = nv12[:h].float().unsqueeze(0).unsqueeze(0)
    y = F.interpolate(y, size=(nh, nw), mode="bilinear", align_corners=False)[0, 0]
    uv = nv12[h:h + h // 2].reshape(h // 2, w // 2, 2).permute(2, 0, 1).float().unsqueeze(0)
    uv = F.interpolate(uv, size=(nh, nw), mode="bilinear", align_corners=False)[0]
    y = 1.164 * (y - 16.0)
    u = uv[0] - 128.0
    v = uv[1] - 128.0
    rgb = torch.stack((y + 1.596 * v,
                       y - 0.392 * u - 0.813 * v,
                       y + 2.017 * u)).clamp_(0.0, 255.0)
    canvas = torch.full((3, size, size), 114.0, device=nv12.device)
    px, py = (size - nw) // 2, (size - nh) // 2
    canvas[:, py:py + nh, px:px + nw] = rgb
    return canvas / 255.0, (r, px, py)


def _motion_frac(prev_y, cur_y) -> float:
    """Küçültülmüş Y düzlemlerinde değişen piksel oranı (0-1)."""
    d = (cur_y.float() - prev_y.float()).abs()
    return float((d > 25.0).float().mean())


# ── İkinci kademe: plaka + yüz (olay-tetikli, oranlı) ───────────────
class _SecondStage:
    def __init__(self, cfg, store, watch: list) -> None:
        from concurrent.futures import ThreadPoolExecutor

        self.cfg = cfg
        self.store = store
        self.watch = watch
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="stage2")
        self.min_interval = float(cfg.get("worker.second_stage_interval", 0.7))
        self.plate_flush = float(cfg.get("worker.plate_flush_seconds", 5.0))
        self.last_run: dict[tuple[str, str], float] = {}   # (cam, görev) → son ts
        self.plate_reads: dict[str, list[dict]] = {}
        self.plate_last_flush: dict[str, float] = {}
        # kamera → {plaka → son yazım ts}: bekleyen araç her flush'ta yeni
        # satır olmasın (sahada: kavşakta duran araç 5-6 sn'de bir satır yazdı)
        self.plate_yazilan: dict[str, dict[str, float]] = {}
        self.face_tracks: dict[str, list] = {}
        self.face_next_tid: dict[str, int] = {}
        self.busy: set[tuple[str, str]] = set()

    def maybe_submit(self, kind: str, cam_id: str, bgr_cpu, ts: float, frame_idx: int) -> None:
        key = (cam_id, kind)
        if ts - self.last_run.get(key, -1e9) < self.min_interval or key in self.busy:
            return
        self.last_run[key] = ts
        self.busy.add(key)
        fn = self._run_plate if kind == "plate" else self._run_face
        self.pool.submit(self._guard, fn, key, cam_id, bgr_cpu, ts, frame_idx)

    def _guard(self, fn, key, *args) -> None:
        try:
            fn(*args)
        except Exception as e:
            print(f"[nvdec] ikinci kademe {key} hatası: {e}", flush=True)
        finally:
            self.busy.discard(key)

    # — plaka: okumaları biriktir, aralıklarla oylayıp TEK olay yaz —
    def _run_plate(self, cam_id: str, bgr, ts: float, frame_idx: int) -> None:
        from .plate import _as_float_conf, _load_alpr, accept_read

        alpr = _load_alpr(self.cfg.get("plate.detector", "yolo-v9-t-384-license-plate-end2end"),
                          self.cfg.get("plate.ocr", "global-plates-mobile-vit-v2-model"),
                          self.cfg.get("device", "auto"))
        min_conf = self.cfg.get("plate.min_conf", 0.4)
        fmt = self.cfg.get("plate.format", "tr")
        yabanci_conf = self.cfg.get("plate.foreign_min_conf", 0.75)
        reads = self.plate_reads.setdefault(cam_id, [])
        for pred in alpr.predict(bgr):
            ocr = getattr(pred, "ocr", None)
            text = getattr(ocr, "text", None) if ocr else None
            conf = _as_float_conf(getattr(ocr, "confidence", None) if ocr else None)
            plate = accept_read(text, conf, min_conf, fmt, yabanci_conf)
            if plate is None:
                continue
            reads.append({"plate": plate, "confidence": conf,
                          "frame_idx": frame_idx, "ts_seconds": round(ts, 2)})
        if ts - self.plate_last_flush.get(cam_id, 0.0) >= self.plate_flush and reads:
            self.plate_last_flush[cam_id] = ts
            yazilan = self.plate_yazilan.setdefault(cam_id, {})
            bastirma = float(self.cfg.get("plate.rewrite_suppress_seconds", 45.0))
            for v in _vote(reads):
                # Az önce yazılan plakanın varyantı → duran aracın devamı, satır yok
                pl = v["plate"]
                es = next((y for y in yazilan
                           if abs(len(y) - len(pl)) <= 1 and _lev(y, pl) <= 2), None)
                if es is not None and ts - yazilan[es] < bastirma:
                    yazilan[es] = ts
                    continue
                yazilan[pl] = ts
                self.store.add_plate_event(cam_id, v["plate"], v["conf"], v["count"],
                                           v["ts_seconds"], v["frame_idx"])
            for y in [y for y, t in yazilan.items() if ts - t > 2 * bastirma]:
                del yazilan[y]
            reads.clear()

    # — yüz: hafif IoU takibi, track kapanınca TEK olay (face.py semantiği) —
    def _run_face(self, cam_id: str, bgr, ts: float, frame_idx: int) -> None:
        from .face import _FaceTrack, _affinity, _cosine, _load_face

        app = _load_face(self.cfg.get("face.model_pack", "buffalo_l"),
                         self.cfg.get("face.det_size", 640),
                         "cuda")
        thr = self.cfg.get("face.match_threshold", 0.5)
        aff_thr = self.cfg.get("face.track_affinity", 0.1)
        timeout = float(self.cfg.get("face.track_timeout_seconds", 2.0))
        tracks = self.face_tracks.setdefault(cam_id, [])

        # süresi dolan track'leri kapat → tek satır olay
        alive = []
        for t in tracks:
            if ts - t.first_ts > 0 and ts - t.match_meta.get("_last_ts", t.first_ts) > timeout:
                self._finalize_face(cam_id, t)
            else:
                alive.append(t)
        self.face_tracks[cam_id] = tracks = alive

        for f in app.get(bgr):
            bbox = tuple(float(v) for v in f.bbox)
            best, best_aff = None, aff_thr
            for t in tracks:
                v = _affinity(bbox, t.bbox)
                if v > best_aff:
                    best, best_aff = t, v
            if best is None:
                tid = self.face_next_tid.get(cam_id, 1)
                self.face_next_tid[cam_id] = tid + 1
                best = _FaceTrack(tid, bbox, frame_idx, ts)
                tracks.append(best)
            best.bbox = bbox
            best.last_frame = frame_idx
            best.match_meta["_last_ts"] = ts
            age = int(getattr(f, "age", 0) or 0)
            sex = getattr(f, "sex", None)
            if age:
                best.ages.append(age)
            if sex in ("M", "F"):
                best.sexes.append(sex)
            best.conf = max(best.conf, float(getattr(f, "det_score", 0.0) or 0.0))
            if self.watch:
                emb = getattr(f, "normed_embedding", None)
                if emb is not None:
                    for wt in self.watch:
                        sc = _cosine(emb, wt["embedding"])
                        if sc >= thr and sc > best.match_score:
                            best.match_name = wt["name"]
                            best.match_score = sc

    def _finalize_face(self, cam_id: str, t) -> None:
        import statistics

        age = int(statistics.median(t.ages)) if t.ages else None
        gender = max(set(t.sexes), key=t.sexes.count) if t.sexes else None
        self.store.add_face_event(cam_id, age, gender, round(t.conf, 3),
                                  t.first_ts, t.first_frame, track_id=t.tid,
                                  match_name=t.match_name,
                                  match_score=round(t.match_score, 3) if t.match_name else None)


# ── Ana motor ───────────────────────────────────────────────────────
def _stream_url(cam: dict, cfg) -> str:
    """Kamera için NVDEC'in demux'layabileceği URL (go2rtc HTTP-TS öncelikli)."""
    go2rtc = (cfg.get("go2rtc.url", "") or "").rstrip("/")
    if go2rtc:
        return f"{go2rtc}/api/stream.ts?src={cam['id']}"
    src = cam["source"]
    if src.startswith(("http://", "https://")):
        return src
    return src   # yerel dosya — demuxer doğrudan açar (döngüsüz; go2rtc önerilir)


def _make_tracker(cfg):
    """BoT-SORT — sabit kameralarda GMC kapalı (kamera hareketi yok; CPU maliyeti sıfırlanır)."""
    from ultralytics.trackers.bot_sort import BOTSORT
    from ultralytics.utils import YAML, IterableSimpleNamespace
    from ultralytics.utils.checks import check_yaml

    tcfg = IterableSimpleNamespace(**YAML.load(check_yaml(cfg.get("count.tracker", "botsort.yaml"))))
    tcfg.gmc_method = "none"
    return BOTSORT(args=tcfg)


def run_gpu_worker(cams: list[dict], cfg, bus) -> None:
    import torch

    from ultralytics import YOLO
    from ultralytics.engine.results import Boxes

    from .bus import BusStore
    from .store import merged_cameras, open_store

    bstore = BusStore(bus)
    model = cfg.get("detect.model", "yolo11s.engine")
    imgsz = int(cfg.get("detect.imgsz", 640))
    conf = cfg.get("detect.conf", 0.35)
    iou = cfg.get("detect.iou", 0.5)
    fps = float(cfg.get("detect.fps", 5))
    batch_max = int(cfg.get("worker.batch_max", 32))
    motion_on = bool(cfg.get("motion.enabled", True))
    motion_frac = float(cfg.get("motion.min_frac", 0.002))
    count_classes = set(cfg.get("count.classes", [0]))
    cooldown = float(cfg.get("count.cooldown_seconds", 2.0))
    min_track = int(cfg.get("count.min_track_frames", 6))

    yolo = YOLO(model)

    # DB'den görev/bölge durumu (periyodik tazelenir) + izleme listesi
    store = open_store(cfg)
    watch = store.faces_with_embedding()
    store.close()
    stage2 = _SecondStage(cfg, bstore, watch)

    decoders = {c["id"]: _Decoder(c["id"], _stream_url(c, cfg),
                                  http_options(cfg, _stream_url(c, cfg)))
                for c in cams}
    for i, d in enumerate(decoders.values()):
        d.start()
        if i % 8 == 7:
            time.sleep(1.0)   # bağlantı fırtınasını yumuşat (go2rtc producer açılışı)

    state: dict[str, dict[str, Any]] = {
        c["id"]: {"cam": c, "tracker": None, "counter": None,
                  "prev_y": None, "seq": 0, "frame_idx": 0, "next_ts": 0.0} for c in cams}

    def refresh_db() -> None:
        s = open_store(cfg)
        try:
            fresh = {c["id"]: c for c in merged_cameras(cfg, s)}
            for cid, st in state.items():
                if cid in fresh:
                    st["cam"] = fresh[cid]
                lines = [{"name": z.get("name") or "Çizgi", "pts": z["points"][:2],
                          "direction": z.get("direction") or "AtoB"}
                         for z in s.list_zones(cid)
                         if z["kind"] == "line" and len(z["points"] or []) >= 2]
                st["lines"] = lines
            stage2.watch = s.faces_with_embedding()
        finally:
            s.close()

    refresh_db()
    print(f"[nvdec] {len(cams)} kamera, model={model}, fps={fps}", flush=True)

    # döngü temposu = en hızlı kameranın temposu; her kamera kendi
    # detect_fps'inde işlenir (kapı/turnike 10, genel sahne 5 — DB cameras.detect_fps)
    def cam_fps(st) -> float:
        return float(st["cam"].get("detect_fps") or fps)

    tick = 1.0 / max([fps] + [cam_fps(st) for st in state.values()])
    last_refresh = last_health = time.time()
    infer_n, infer_t0 = 0, time.time()

    while True:
        t_loop = time.time()
        batch, meta = [], []
        for cid, st in state.items():
            if t_loop < st["next_ts"]:
                continue
            nv12, wh, seq = decoders[cid].grab()
            if nv12 is None or seq == st["seq"]:
                continue
            st["next_ts"] = t_loop + 1.0 / cam_fps(st)
            st["seq"] = seq
            st["frame_idx"] += 1
            w, h = wh
            tasks = st["cam"].get("tasks") or {}
            if not (tasks.get("count") or tasks.get("plate") or tasks.get("face")):
                continue
            # hareket ön-filtresi: küçültülmüş Y düzlemi farkı
            if motion_on:
                y_small = nv12[:h:8, ::8]
                if st["prev_y"] is not None and _motion_frac(st["prev_y"], y_small) < motion_frac:
                    st["prev_y"] = y_small
                    continue
                st["prev_y"] = y_small
            img, (r, px, py) = _nv12_letterbox_rgb(nv12, w, h, imgsz)
            batch.append(img)
            # BGR yalnız ikinci kademe tetiklenirse üretilir (nv12 saklanır)
            meta.append((cid, st, nv12, (r, px, py), (w, h)))

        if batch:
            ts = time.time()
            for i0 in range(0, len(batch), batch_max):
                chunk = batch[i0:i0 + batch_max]
                x = torch.stack(chunk).half()
                results = yolo.predict(x, conf=conf, iou=iou, verbose=False)
                infer_n += len(chunk)
                for res, (cid, st, nv12, (r, px, py), (w, h)) in zip(results, meta[i0:i0 + batch_max]):
                    tasks = st["cam"].get("tasks") or {}
                    boxes = res.boxes
                    if boxes is None or len(boxes) == 0:
                        continue
                    # letterbox uzayı → orijinal piksel uzayı
                    xyxy = boxes.xyxy.clone()
                    xyxy[:, [0, 2]] = (xyxy[:, [0, 2]] - px) / r
                    xyxy[:, [1, 3]] = (xyxy[:, [1, 3]] - py) / r
                    cls = boxes.cls
                    confs = boxes.conf

                    if tasks.get("count"):
                        keep = torch.tensor([int(c) in count_classes for c in cls],
                                            device=cls.device, dtype=torch.bool)
                        if keep.any():
                            data = torch.cat((xyxy[keep], confs[keep, None], cls[keep, None]), 1)
                            det = Boxes(data.cpu(), orig_shape=(h, w)).numpy()
                            if st["tracker"] is None:
                                st["tracker"] = _make_tracker(cfg)
                            if st["counter"] is None or st.get("counter_lines") != st.get("lines"):
                                lines = st.get("lines") or [{"name": "Çizgi",
                                                             "pts": [[0.5, 0.0], [0.5, 1.0]],
                                                             "direction": "AtoB"}]
                                ln = cfg.get("count.line", None)
                                if not st.get("lines") and ln:
                                    lines = [{"name": "Çizgi",
                                              "pts": [[ln["x1"], ln["y1"]], [ln["x2"], ln["y2"]]],
                                              "direction": "AtoB"}]
                                st["counter"] = LineCounter(lines, w, h, cooldown, min_track)
                                st["counter_lines"] = st.get("lines")
                            tracks = st["tracker"].update(det, None)
                            pts = [(int(t[4]), (t[0] + t[2]) / 2.0, t[3]) for t in tracks]  # ayak: alt-orta
                            for ev in st["counter"].update(pts, ts):
                                bstore.add_count_event(cid, ev["track_id"], ev["direction"],
                                                       ev["line"], ts, st["frame_idx"])

                    want_plate = tasks.get("plate") and any(int(c) in _VEHICLE_CLASSES for c in cls)
                    want_face = tasks.get("face") and any(int(c) == _PERSON_CLASS for c in cls)
                    if want_plate or want_face:
                        bgr_cpu = _nv12_to_bgr(nv12, w, h).cpu().numpy()
                        if want_plate:
                            stage2.maybe_submit("plate", cid, bgr_cpu, ts, st["frame_idx"])
                        if want_face:
                            stage2.maybe_submit("face", cid, bgr_cpu, ts, st["frame_idx"])

        now = time.time()
        if now - last_health >= 5.0:
            last_health = now
            rate = infer_n / max(now - infer_t0, 1e-6)
            infer_n, infer_t0 = 0, now
            for cid, d in decoders.items():
                publish(bus, "health", cid,
                        {"status": d.status if d.status in ("ok", "no_signal", "decode_err") else "ok",
                         "stage": f"nvdec {d.fps:.1f}fps", "fps": round(d.fps, 1)})
            print(f"[nvdec] inference: {rate:.1f} kare/sn", flush=True)
        if now - last_refresh >= 30.0:
            last_refresh = now
            try:
                refresh_db()
            except Exception as e:
                print(f"[nvdec] DB tazeleme hatası: {e}", flush=True)

        dt = time.time() - t_loop
        if dt < tick:
            time.sleep(tick - dt)
