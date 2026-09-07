"""Taşınabilir analiz motoru (`worker.engine: akis`) — Windows/Linux, her GPU/CPU.

GB10 motoru (gpu_engine.py, PyNvVideoCodec + TensorRT) yalnız NVIDIA + Linux'ta
kuruluyor; onun dışındaki her makine ultralytics'in kendi akış okuyucusuna
düşüyordu. O yol her kareyi CPU'da tam çözünürlükte çözer (vid_stride yalnız
inference'ı atlar) ve kamera başına ayrı model kopyası tutar — 6 kamerada
4 çekirdekli makine %99'a doydu, GPU %0 decode ile boşta bekledi (ölçüm:
docs/denetim-2026-09-05-kararlilik-kaynak.md).

Bu motor global çözümlerin (Frigate, Milestone, DeepStream) ortak deseninin
taşınabilir hâlidir:

  go2rtc RTSP (substream, ~5 fps hedef) → PyAV donanım decode (cuda / d3d11va /
  dxva2 / qsv / vaapi / videotoolbox, yoksa yazılım) → hareket ön-filtresi →
  TEK YOLO örneği, kameralar tek batch'te → kamera başına BoT-SORT + çizgi +
  ihlal alanı → BusStore. Plaka/yüz/arama ikinci kademe (gpu_engine._SecondStage,
  olay-tetikli) aynen kullanılır.

Kamera başına TEK decoder: sayım + plaka açık kamerada kare iki kez çözülmez.
Kaynak seçimi: plaka görevi ana akış ister (plaka piksel boyu), diğerleri
substream'den koşar (`detect.use_substream`). go2rtc yoksa kameraya doğrudan.

Sözleşme: olaylar yalnız `store` (BusStore) ile yayınlanır — imzalar sabit
(ADR-0002). KVKK: ham kare diske/DB'ye yazılmaz. Önizleme/tespit kutuları
worker.py'nin bellek-içi sunucusuna verilir (canlı görünüm "Analiz" modu).
"""
from __future__ import annotations

import threading
import time
from typing import Any, Callable

from .bus import publish
from .config import http_options
from .gpu_engine import LineCounter, _SecondStage, _make_tracker
from .gpu_engine import _PERSON_CLASS, _VEHICLE_CLASSES

# gpu_engine._SecondStage log önekini "[nvdec]" basar; burada da anlaşılır kalsın
_ON = "[akis]"


# ── Decoder: PyAV + hwaccel, son-kare-kazanır ───────────────────────
class _Decoder(threading.Thread):
    """Tek kamera: demux + (donanım) decode → BGR numpy son kare.

    Kuyruk YOK: analiz temposu (detect.fps) decode temposundan düşükse eski
    kareler atlanır, gecikme birikmez. Kopmada üstel bekleme ile yeniden bağlanır.
    Sayaçlar heartbeat'e gider: çözülen kare, atlanan (analize girmeyen) kare,
    decode hatası, yeniden bağlanma, kullanılan hwaccel.
    """

    def __init__(self, cam_id: str, url: str, hwaccel_adaylari: list[str],
                 extra_opts: dict | None = None) -> None:
        super().__init__(daemon=True, name=f"dec-{cam_id}")
        self.cam_id = cam_id
        self.url = url
        self.adaylar = list(hwaccel_adaylari)
        self.extra_opts = extra_opts or {}
        self.lock = threading.Lock()
        self.latest = None          # BGR (H,W,3) uint8
        self.latest_ts = 0.0        # kaynağın kare zamanı (sn), yoksa duvar saati
        self.wh: tuple[int, int] | None = None
        self.seq = 0
        self.status = "başlıyor"
        self.hwaccel = ""           # gerçekten kullanılan ("" = yazılım)
        self.fps = 0.0
        self.decoded = 0
        self.dropped = 0            # çözüldü ama analiz almadan üzerine yazıldı
        self.decode_err = 0
        self.reconnects = 0
        self.stop_flag = False
        self._consumed_seq = 0

    def _hwaccel_dene(self):
        """Adayları sırayla dener; açılan ilk cihazla döner (None = yazılım)."""
        try:
            from av.codec.hwaccel import HWAccel
        except Exception:
            return None
        for dev in self.adaylar:
            try:
                return HWAccel(device_type=dev, allow_software_fallback=False), dev
            except Exception:
                continue
        return None

    def run(self) -> None:
        import av

        bekle = 2.0
        while not self.stop_flag:
            cont = None
            try:
                opts = {"rtsp_transport": "tcp"} if self.url.startswith("rtsp") else {}
                opts.update(self.extra_opts)
                hw = self._hwaccel_dene()
                hwaccel, dev = (hw if hw else (None, ""))
                # (açılış, okuma) sn — kısa timeout çok kameralı açılışta flapping yapar
                cont = av.open(self.url, options=opts, timeout=(30.0, 30.0),
                               hwaccel=hwaccel)
                vs = cont.streams.video[0]
                vs.thread_type = "AUTO"
                self.hwaccel = dev
                self.status = "ok"
                bekle = 2.0
                n, t0 = 0, time.time()
                for frame in cont.decode(vs):
                    if self.stop_flag:
                        return
                    try:
                        bgr = frame.to_ndarray(format="bgr24")
                    except Exception:
                        self.decode_err += 1
                        continue
                    ts = frame.time if frame.time is not None else time.time()
                    with self.lock:
                        if self.seq != self._consumed_seq:
                            self.dropped += 1
                        self.latest = bgr
                        self.latest_ts = ts
                        self.wh = (bgr.shape[1], bgr.shape[0])
                        self.seq += 1
                    self.decoded += 1
                    n += 1
                    if n % 50 == 0:
                        self.fps = 50 / max(time.time() - t0, 1e-6)
                        t0 = time.time()
                # akış bitti (dosya sonu / kopma) → yeniden bağlan
                self.status = "no_signal"
            except Exception as e:
                # Donanım decode açıldı ama çözemedi (sürücü/codec uyumsuzluğu):
                # adayı listeden düşür, bir sonraki turda yazılıma kadar iner.
                self.status = "decode_err"
                self.decode_err += 1
                if self.hwaccel and self.hwaccel in self.adaylar and self.decoded == 0:
                    print(f"{_ON} {self.cam_id} hwaccel {self.hwaccel} çalışmadı ({e}) — "
                          f"sonraki aday deneniyor", flush=True)
                    self.adaylar.remove(self.hwaccel)
                else:
                    print(f"{_ON} {self.cam_id} decoder hatası: {e}", flush=True)
            finally:
                if cont is not None:
                    try:
                        cont.close()
                    except Exception:
                        pass
            if not self.stop_flag:
                self.reconnects += 1
                self.fps = 0.0
                time.sleep(bekle)
                bekle = min(bekle * 2, 30.0)   # üstel geri çekilme (fırtına yok)

    def grab(self):
        """(bgr, ts, (w,h), seq) — yeni kare yoksa bgr=None."""
        with self.lock:
            self._consumed_seq = self.seq
            return self.latest, self.latest_ts, self.wh, self.seq

    def durum(self) -> dict[str, Any]:
        """Heartbeat alanları. `dropped` = BOZUK/çözülemeyen kare (paket kaybı,
        decoder hatası) — analiz temposu için bilerek atlanan kareler değil
        (`skipped`); ikisi karışırsa panel sağlıklı kurulumu kırmızı gösterir."""
        return {"status": self.status, "decode_fps": round(self.fps, 1),
                "dropped": self.decode_err, "skipped": self.dropped,
                "reconnects": self.reconnects, "hwaccel": self.hwaccel or "yazılım"}


# ── Yardımcılar ─────────────────────────────────────────────────────
def _motion_frac(prev, cur) -> float:
    """Küçültülmüş gri düzlemde değişen piksel oranı (0-1) — CPU, numpy."""
    import numpy as np
    d = np.abs(cur.astype(np.int16) - prev.astype(np.int16))
    return float((d > 25).mean())


def _gri_kucuk(bgr):
    """8× alt-örneklenmiş yeşil kanal: hareket filtresi için yeterli, ucuz."""
    return bgr[::8, ::8, 1]


def kaynak_url(cam: dict, cfg, gorevler: dict) -> tuple[str, str]:
    """(url, akış tipi). Plaka açıksa ana akış; değilse substream (varsa).

    go2rtc varsa ondan (kameraya TEK bağlantı, recorder ile aynı desen); yoksa
    kameraya doğrudan. Dosya kaynağı go2rtc'siz doğrudan açılır.
    """
    go2rtc = (cfg.get("go2rtc.url", "") or "").rstrip("/")
    sub_ok = bool(cam.get("url_sub")) and bool(cfg.get("detect.use_substream", True))
    plaka = bool(gorevler.get("plate")) and bool(cfg.get("plate.use_main_stream", True))
    sub = sub_ok and not plaka
    tip = "substream" if sub else "ana akış"
    if go2rtc:
        # go2rtc dosya kaynaklarını da (exec ffmpeg döngüsü) aynı adla yayınlar
        host = go2rtc.split("//", 1)[-1].split(":")[0] or "localhost"
        return f"rtsp://{host}:8554/{cam['id']}{'-sub' if sub else ''}", tip
    return (str(cam["url_sub"]) if sub else str(cam["source"])), tip


def _cizgiler(store, cid: str) -> list[dict]:
    return [{"name": z.get("name") or "Çizgi", "pts": z["points"][:2],
             "direction": z.get("direction") or "AtoB"}
            for z in store.list_zones(cid)
            if z["kind"] == "line" and len(z["points"] or []) >= 2]


def _ihlaller(store, cid: str) -> list[dict]:
    return [{"name": z.get("name") or "İhlal alanı", "points": z["points"],
             "classes": z.get("classes") or []}
            for z in store.list_zones(cid)
            if z["kind"] == "intrusion" and len(z["points"] or []) >= 3]


def _annotate(bgr, dets: list[dict], w: int, h: int, sayac, ihlal):
    """Canlı görünüm "Analiz" modu için kutu+çizgi çizili kopya (count.py görünümü)."""
    import cv2
    from .count import _badge, _draw_line, _draw_zone
    img = bgr.copy()
    k = max(1.0, w / 1280)
    for d in dets:
        x1, y1, x2, y2 = int(d["x1"] * w), int(d["y1"] * h), int(d["x2"] * w), int(d["y2"] * h)
        cv2.rectangle(img, (x1, y1), (x2, y2), (238, 211, 34), max(2, round(2 * k)))
        cv2.putText(img, f"{d['cls']} {d['id']}", (x1, max(12, y1 - 4)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5 * k, (238, 211, 34), max(1, round(1.5 * k)))
    if ihlal:
        for z in ihlal.zones:
            _draw_zone(cv2, img, z, k)
    if sayac is not None:
        for lc in sayac.lines:
            _draw_line(cv2, img, {"px": lc["px"], "name": lc["name"]}, k)
        y = int(44 * k)
        for lc in sayac.lines:
            y += _badge(cv2, img, f"{lc['name']}: {lc.get('in', 0)} / {lc.get('out', 0)}",
                        14, y, 0.6 * k, max(1, round(1.5 * k)))
    return img


# ── Ana motor ───────────────────────────────────────────────────────
def run_akis_worker(cams: list[dict], cfg, bus,
                    on_frame: Callable[[str], Callable] | None = None,
                    on_detections: Callable[[str], Callable] | None = None,
                    detector: Callable | None = None,
                    stop: Callable[[], bool] | None = None,
                    health_cb: Callable[[str, dict], None] | None = None) -> None:
    """Sürekli döngü. `detector(list[bgr]) -> list[(xyxy, conf, cls)]` testte
    gerçek YOLO yerine takılabilir; `stop()` True dönünce döngü biter."""
    import numpy as np

    from . import donanim
    from .bus import BusStore
    from .evidence import kaydet as kanit_kaydet
    from .store import merged_cameras, open_store
    from .zones import IntrusionWatcher

    prof = donanim.profil()
    bstore = BusStore(bus)
    model_ad = cfg.get("detect.model") or prof["oneri"]["model"]
    imgsz = int(cfg.get("detect.imgsz", 640))
    conf = float(cfg.get("detect.conf", 0.35))
    iou = float(cfg.get("detect.iou", 0.5))
    fps = float(cfg.get("detect.fps") or prof["oneri"]["fps"])
    batch_max = int(cfg.get("worker.batch_max") or prof["oneri"]["batch_max"])
    motion_on = bool(cfg.get("motion.enabled", True))
    motion_frac = float(cfg.get("motion.min_frac", 0.002))
    count_classes = set(cfg.get("count.classes", [0]))
    cooldown = float(cfg.get("count.cooldown_seconds", 2.0))
    min_track = int(cfg.get("count.min_track_frames", 6))
    dwell = float(cfg.get("intrusion.dwell_seconds", 1.0))
    ihlal_cooldown = float(cfg.get("intrusion.cooldown_seconds", 30.0))
    hw_adaylar = list(cfg.get("detect.hwaccel") or prof["hwaccel"])
    if cfg.get("detect.hwaccel") == "none":
        hw_adaylar = []

    # ── Tek model örneği: kameralar tek batch'te ──
    if detector is None:
        from .device import select_device
        from ultralytics import YOLO
        device = select_device(cfg.get("device", "auto"))
        yolo = YOLO(model_ad)
        if str(model_ad).endswith(".pt"):
            yolo.to(device)
        names = yolo.names
        # FP16 yalnız CUDA'da; ultralytics 8.4 `quantize="fp16"` ister, eskisi
        # `half=True` (yenisinde her çağrıda uyarı basar). İlk çağrıda seçilir.
        kw: dict[str, Any] = {"quantize": "fp16"} if device == "cuda" else {}

        def detector(imgs):
            nonlocal kw
            try:
                res = yolo.predict(imgs, imgsz=imgsz, conf=conf, iou=iou,
                                   device=device, verbose=False, **kw)
            except (TypeError, ValueError, SyntaxError):
                if not kw:
                    raise
                kw = {"half": True}
                res = yolo.predict(imgs, imgsz=imgsz, conf=conf, iou=iou,
                                   device=device, verbose=False, **kw)
            out = []
            for r in res:
                b = r.boxes
                if b is None or len(b) == 0:
                    out.append((np.zeros((0, 4)), np.zeros(0), np.zeros(0, dtype=int)))
                else:
                    out.append((b.xyxy.cpu().numpy(), b.conf.cpu().numpy(),
                                b.cls.cpu().numpy().astype(int)))
            return out
    else:
        names = {0: "person", 2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}

    store = open_store(cfg)
    watch = store.faces_with_embedding()
    store.close()
    stage2 = _SecondStage(cfg, bstore, watch)

    import os
    sec = os.environ.get("AURAS_CAMERAS", "")
    secim = {x.strip() for x in sec.split(",") if x.strip()} if sec else None
    state: dict[str, dict[str, Any]] = {}
    decoders: dict[str, _Decoder] = {}

    def _ac(c: dict) -> None:
        url, tip = kaynak_url(c, cfg, c.get("tasks") or {})
        d = _Decoder(c["id"], url, hw_adaylar, http_options(cfg, url))
        d.start()
        decoders[c["id"]] = d
        state[c["id"]] = {"cam": c, "url": url, "tip": tip, "tracker": None,
                          "counter": None, "counter_key": None, "lines": [],
                          "ihlal": None, "ihlal_key": None, "prev": None,
                          "seq": 0, "frame_idx": 0, "next_ts": 0.0, "hb_idx": 0,
                          "push_frame": on_frame(c["id"]) if on_frame else None,
                          "push_dets": on_detections(c["id"]) if on_detections else None}
        print(f"{_ON} {c['id']}: {tip} <- {url.split('@')[-1]}", flush=True)

    def refresh_db() -> None:
        s = open_store(cfg)
        try:
            fresh = {c["id"]: c for c in merged_cameras(cfg, s) if c.get("enabled", True)}
            if secim is not None:
                fresh = {k: v for k, v in fresh.items() if k in secim}
            for cid, c in fresh.items():
                if cid not in state:
                    print(f"{_ON} yeni kamera: {cid} — çözücü açılıyor", flush=True)
                    _ac(c)
                    continue
                st = state[cid]
                st["cam"] = c
                # Görev değişince kaynak (ana/sub) değişebilir → çözücüyü yenile
                url, tip = kaynak_url(c, cfg, c.get("tasks") or {})
                if url != st["url"]:
                    print(f"{_ON} {cid}: kaynak {st['tip']} → {tip}", flush=True)
                    decoders[cid].stop_flag = True
                    _ac(c)
            for cid in [x for x in state if x not in fresh]:
                print(f"{_ON} kamera silinmiş: {cid} — çözücü kapatılıyor", flush=True)
                decoders.pop(cid).stop_flag = True
                state.pop(cid, None)
            for cid, st in state.items():
                st["lines"] = _cizgiler(s, cid)
                st["ihlal_tanim"] = _ihlaller(s, cid)
            stage2.watch = s.faces_with_embedding()
        finally:
            s.close()

    for i, c in enumerate(cams):
        _ac(c)
        if i % 8 == 7:
            time.sleep(1.0)
    refresh_db()
    print(f"{_ON} {len(state)} kamera · model={model_ad} · hedef {fps} fps · "
          f"hwaccel adayları: {','.join(hw_adaylar) or 'yok (yazılım)'} · "
          f"{donanim.ozet_satiri()}", flush=True)

    def cam_fps(st) -> float:
        return float(st["cam"].get("detect_fps") or fps)

    tick = 1.0 / max([fps] + [cam_fps(st) for st in state.values()] + [1.0])
    last_refresh = last_health = last_hb_t = time.time()
    infer_n, infer_t0 = 0, time.time()

    while not (stop and stop()):
        t_loop = time.time()
        batch, meta = [], []
        for cid, st in list(state.items()):
            if t_loop < st["next_ts"]:
                continue
            bgr, ts, wh, seq = decoders[cid].grab()
            if bgr is None or seq == st["seq"]:
                continue
            st["next_ts"] = t_loop + 1.0 / cam_fps(st)
            st["seq"] = seq
            st["frame_idx"] += 1
            tasks = st["cam"].get("tasks") or {}
            if not (tasks.get("count") or tasks.get("plate") or tasks.get("face")):
                continue
            if motion_on:
                g = _gri_kucuk(bgr)
                if st["prev"] is not None and st["prev"].shape == g.shape \
                        and _motion_frac(st["prev"], g) < motion_frac:
                    st["prev"] = g
                    continue
                st["prev"] = g
            batch.append(bgr)
            meta.append((cid, st, bgr, wh, ts))

        if batch:
            wall = time.time()
            for i0 in range(0, len(batch), batch_max):
                sonuc = detector(batch[i0:i0 + batch_max])
                infer_n += len(sonuc)
                for (xyxy, confs, cls), (cid, st, bgr, (w, h), ts) in zip(sonuc, meta[i0:i0 + batch_max]):
                    tasks = st["cam"].get("tasks") or {}
                    dets_ui: list[dict] = []
                    if tasks.get("count"):
                        keep = np.array([int(c) in count_classes for c in cls], dtype=bool)
                        # ihlal alanı insan dışı sınıf da isteyebilir
                        ihlal_tanim = st.get("ihlal_tanim") or []
                        ihlal_key = repr(ihlal_tanim)
                        if st["ihlal_key"] != ihlal_key:
                            st["ihlal"] = IntrusionWatcher(ihlal_tanim, w, h, dwell, ihlal_cooldown) \
                                if ihlal_tanim else None
                            st["ihlal_key"] = ihlal_key
                        if st["ihlal"]:
                            ek = {c for z in st["ihlal"].zones for c in z["classes"]}
                            keep = keep | np.array([int(c) in ek for c in cls], dtype=bool)
                        lines = st.get("lines") or []
                        if not lines and not ihlal_tanim:
                            ln = cfg.get("count.line", {"x1": 0.5, "y1": 0.0, "x2": 0.5, "y2": 1.0})
                            lines = [{"name": "Çizgi", "pts": [[ln["x1"], ln["y1"]], [ln["x2"], ln["y2"]]],
                                      "direction": "AtoB"}]
                        key = (repr(lines), w, h)
                        if st["counter_key"] != key:
                            st["counter"] = LineCounter(lines, w, h, cooldown, min_track)
                            for lc in st["counter"].lines:
                                lc["in"] = lc["out"] = 0
                            st["counter_key"] = key
                        if st["tracker"] is None:
                            st["tracker"] = _make_tracker(cfg)
                        # Takipçi HER karede güncellenir (boş karede de): kaybolan
                        # izler ancak böyle yaşlanıp kapanır (count.py ile aynı).
                        from ultralytics.engine.results import Boxes
                        import torch
                        data = (np.concatenate((xyxy[keep], confs[keep, None], cls[keep, None]), 1)
                                if keep.any() else np.zeros((0, 6), dtype=np.float32))
                        det = Boxes(torch.from_numpy(data.astype(np.float32)), orig_shape=(h, w)).numpy()
                        tracks = st["tracker"].update(det, None)
                        # BoT-SORT çıktısı satır başına [x1,y1,x2,y2,id,conf,cls,idx]
                        izler = [(int(t[4]), (float(t[0]) + float(t[2])) / 2.0, float(t[3]),
                                  int(t[6]), float(t[5]), t) for t in tracks]   # ayak: alt-orta
                        sayim_pts = [(tid, x, y) for tid, x, y, c, _cf, _t in izler if c in count_classes]
                        for ev in st["counter"].update(sayim_pts, ts):
                            bstore.add_count_event(cid, ev["track_id"], ev["direction"],
                                                   ev["line"], ts, st["frame_idx"])
                            for lc in st["counter"].lines:
                                if lc["name"] == ev["line"]:
                                    lc[ev["direction"]] = lc.get(ev["direction"], 0) + 1
                        if st["ihlal"]:
                            for ih in st["ihlal"].update([(tid, x, y, c) for tid, x, y, c, _cf, _t in izler], ts):
                                snap = kanit_kaydet(cfg, bgr, cid, "intrusion",
                                                    etiket=f"{ih['zone']}  track {ih['track_id']}  {ih['dwell']} sn")
                                bstore.add_alert("intrusion", ih["zone"], "intrusion",
                                                 f"track {ih['track_id']} · {ih['dwell']} sn", cid,
                                                 snapshot=snap)
                        for tid, _x, _y, c, cf, t in izler:
                            dets_ui.append({"id": tid, "x1": round(float(t[0]) / w, 4),
                                            "y1": round(float(t[1]) / h, 4),
                                            "x2": round(float(t[2]) / w, 4),
                                            "y2": round(float(t[3]) / h, 4),
                                            "cls": names.get(c, "obj"), "conf": round(cf, 2)})
                    if st["push_dets"]:
                        st["push_dets"](dets_ui, st["frame_idx"])
                    if st["push_frame"]:
                        st["push_frame"](_annotate(bgr, dets_ui, w, h, st["counter"], st["ihlal"]))

                    want_plate = tasks.get("plate") and any(int(c) in _VEHICLE_CLASSES for c in cls)
                    want_face = tasks.get("face") and any(int(c) == _PERSON_CLASS for c in cls)
                    want_vektor = stage2.vektor_acik and stage2.vektor_aralik > 0 and any(
                        int(c) == _PERSON_CLASS or int(c) in _VEHICLE_CLASSES for c in cls)
                    if want_plate or want_face or want_vektor:
                        if want_vektor:
                            vk = [(*map(float, xyxy[i]), int(cls[i])) for i in range(len(cls))
                                  if int(cls[i]) == _PERSON_CLASS or int(cls[i]) in _VEHICLE_CLASSES]
                            stage2.maybe_submit("vektor", cid, bgr, wall, st["frame_idx"], vk)
                        if want_plate:
                            arac = [tuple(float(v) for v in xyxy[i]) for i in range(len(cls))
                                    if int(cls[i]) in _VEHICLE_CLASSES]
                            stage2.maybe_submit("plate", cid, bgr, wall, st["frame_idx"], arac)
                        if want_face:
                            stage2.maybe_submit("face", cid, bgr, wall, st["frame_idx"])

        now = time.time()
        if now - last_health >= 5.0:
            last_hb_t, last_health = last_health, now
            rate = infer_n / max(now - infer_t0, 1e-6)
            infer_n, infer_t0 = 0, now
            kul = donanim.kullanim()
            for cid, d in decoders.items():
                if cid not in state:
                    continue
                st = state[cid]
                du = d.durum()
                # fps = ANALİZE giren kare hızı (panelin beklediği anlam); decode
                # hızı ayrıca decode_fps'te. Hareket filtresi durgun sahnede
                # kareyi atlar → düşük fps arıza değildir; status zaten "ok".
                du["fps"] = round((st["frame_idx"] - st["hb_idx"]) / max(now - last_hb_t, 1e-6), 1)
                st["hb_idx"] = st["frame_idx"]
                du["stage"] = f"akis {st['tip']} {du['hwaccel']} decode {du['decode_fps']}fps"
                if health_cb:
                    health_cb(cid, du)
                publish(bus, "health", cid, du)
            print(f"{_ON} inference {rate:.1f} kare/sn · CPU {kul.get('cpu_pct', '?')}% · "
                  f"GPU {kul.get('gpu_pct', '?')}% · NVDEC {kul.get('nvdec_pct', '?')}%", flush=True)
        if now - last_refresh >= 30.0:
            last_refresh = now
            try:
                refresh_db()
            except Exception as e:
                print(f"{_ON} DB tazeleme hatası: {e}", flush=True)

        dt = time.time() - t_loop
        if dt < tick:
            time.sleep(tick - dt)

    for d in decoders.values():
        d.stop_flag = True
