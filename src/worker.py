"""Analiz worker'ı — kameraları işler, olayları Redis Streams'e yayınlar.

Mimari (docs/mimari-100-kamera.md): worker DB'ye YAZMAZ; olaylar Redis'e gider,
ingestor DB'ye basar. Worker DB'yi yalnız OKUR (kamera/bölge/izleme listesi).

Çalıştırma:
  export REDIS_URL=redis://localhost:6379/0
  python -m src.worker                 # tüm etkin kameralar
  AURAS_CAMERAS=giris,otopark python -m src.worker   # alt küme (ölçekleme)

Kaynak dosya ise: görevler sırayla koşar, worker.loop_interval sn bekleyip tekrar
başlar (0 = tek geçiş). RTSP ise: sayım kesintisizdir; plaka/yüz görevleri için
kamerayı ayrı worker'a vermek gerekir (Faz 3'te DeepStream tek pipeline'da birleştirir).
"""
from __future__ import annotations

import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import akis
from .bus import BusStore, YerelBus, open_bus, publish
from .config import apply_cv2_http_headers, load_config
from .davranis import aktif_siniflar   # görev anahtarları: telefon, sigara (tek poz hattı)
from .store import merged_cameras, open_store

# kamera_id → o an çalışan aşama (heartbeat bunu yayınlar)
_STAGE: dict[str, str] = {}
_TASK_STAGE: dict[str, dict[str, str]] = {}
_STAGE_LOCK = threading.Lock()


def _gorev_durumu_yaz(cid: str, ad: str, durum: str) -> None:
    with _STAGE_LOCK:
        _TASK_STAGE.setdefault(cid, {})[ad] = durum


def _kamera_sagligi(cid: str) -> tuple[str, str]:
    """Görev durumlarını kamera heartbeat'ine indirger: (status, ayrıntı)."""
    with _STAGE_LOCK:
        durumlar = dict(_TASK_STAGE.get(cid, {}))
    if not durumlar:
        eski = _STAGE.get(cid, "başlıyor")
        return ("error" if eski.startswith("error") else "ok", eski)
    ayrinti = " | ".join(f"{ad}:{durum}" for ad, durum in sorted(durumlar.items()))
    if any(d.startswith("parked") for d in durumlar.values()):
        return "error", ayrinti
    if any(d.startswith("restarting") for d in durumlar.values()):
        return "degraded", ayrinti
    if all(d in ("done", "stopped") for d in durumlar.values()):
        return "idle", ayrinti
    return "ok", ayrinti


def _gorev_gozetmeni(cid: str, ad: str, fn, cfg, *, should_stop=None,
                     sleep_fn=time.sleep) -> str:
    """Tek analiz görevini sınırlı üstel geri çekilmeyle yeniden başlatır.

    Sürekli hata sonsuz hızlı yeniden açma döngüsüne girmez. Bütçe dolunca
    görev ``parked`` olur ve kardeş görevler çalışmayı sürdürür; heartbeat bu
    durumu hata olarak görünür kılar.
    """
    should_stop = should_stop or (lambda: False)
    azami = max(0, int(cfg.get("worker.task_max_restarts", 5)))
    ilk = max(0.0, float(cfg.get("worker.task_retry_initial_seconds", 1.0)))
    tavan = max(ilk, float(cfg.get("worker.task_retry_max_seconds", 30.0)))
    hata = 0
    while not should_stop():
        _gorev_durumu_yaz(cid, ad, "running")
        try:
            fn()
            _gorev_durumu_yaz(cid, ad, "done")
            return "done"
        except Exception as e:
            hata += 1
            kisa = f"{e.__class__.__name__}: {e}"[:160]
            if hata > azami:
                _gorev_durumu_yaz(cid, ad, f"parked ({kisa})")
                print(f"[worker] {cid}/{ad} park edildi ({hata} hata): {kisa}",
                      flush=True)
                return "parked"
            bekle = min(tavan, ilk * (2 ** (hata - 1)))
            _gorev_durumu_yaz(
                cid, ad, f"restarting {hata}/{azami} in {bekle:g}s ({kisa})")
            print(f"[worker] {cid}/{ad} hata: {kisa}; {bekle:g} sn sonra "
                  f"yeniden denenecek ({hata}/{azami})", flush=True)
            if bekle:
                sleep_fn(bekle)
    _gorev_durumu_yaz(cid, ad, "stopped")
    return "stopped"


# kamera_id → işlenen toplam kare (heartbeat fps'i bunun farkından türetir)
_FRAMES: dict[str, int] = {}


def _kare_sayaci(cid: str):
    """Kare başına çağrılan sayaç; analiz fonksiyonlarına `should_stop` olarak verilir.

    `should_stop` üç analiz modülünde de kare başına tam bir kez çağrılır
    (count.py, plate.py, face.py) — durdurma isteği olmadığı için hep False döner.
    Tek amacı saymak.
    """
    def tik() -> bool:
        _FRAMES[cid] = _FRAMES.get(cid, 0) + 1
        return False
    return tik


# kamera_id → son ANNOTATE edilmiş kare (JPEG). Yalnız bellekte tutulur (KVKK,
# bkz. server.py:_frame_pusher ile aynı ilke) — canlı görünümün "Analiz" modu
# bunu server.py üzerinden (aynı-origin proxy) çeker.
_PREVIEW: dict[str, bytes] = {}
_PREVIEW_LOCK = threading.Lock()
_PREVIEW_MIN_INTERVAL = 0.35   # sn — sayım/analiz hızını ETKİLEMEZ, yalnız önizleme örnekleme sıklığı.
                                # Analiz zaten ~3-5 fps'te çalışıyor (heartbeat fps); bu sayı o tavanı
                                # AŞMAZ (on_frame'in kendisi kareden daha sık çağrılmıyor) — yalnız
                                # 1 sn'lik eski aralıkta atlanan kareleri de örneklemeye açar (kullanıcı
                                # geri bildirimi: "görüntü çok donuyor ve takılıyor").
_PREVIEW_MAX_W = 800   # 960 → 800: JPEG kodlama+aktarım süresi kısalır, daha sık örnekleme ucuzlaşır


def _onizleme_itici(cid: str):
    """count/plate/face'e `on_frame` olarak verilir.

    Üç modül de on_frame VARSA r.plot() ile ANNOTATE edilmiş kareyi (kutular +
    count.py'de ayrıca çizgi/bölge) üretir — bu zaten Test ekranının canlı
    önizlemesinde kullanılan yol (server.py:_frame_pusher), burada aynı örüntü
    sürekli çalışan worker'a taşınıyor. 1 sn'de bir örnekler; maliyet yalnız
    çizim+JPEG kodlama, tespit zaten HER KAREDE çalışıyordu (marjinal maliyet düşük).
    """
    state = {"t": 0.0}

    def push(frame) -> None:
        now = time.monotonic()
        if now - state["t"] < _PREVIEW_MIN_INTERVAL:
            return
        state["t"] = now
        try:
            import cv2
            h, w = frame.shape[:2]
            if w > _PREVIEW_MAX_W:
                frame = cv2.resize(frame, (_PREVIEW_MAX_W, int(h * _PREVIEW_MAX_W / w)))
            ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
            if ok:
                with _PREVIEW_LOCK:
                    _PREVIEW[cid] = buf.tobytes()
        except Exception:
            pass   # önizleme hatası analizi ASLA düşürmez

    return push


# kamera_id → {"dets":[{id,x1,y1,x2,y2,cls,conf}...], "frame_idx": N}. Yalnız
# bellekte (aynı KVKK ilkesi) — count.py'nin ZATEN hesapladığı kutuları taşır,
# ekstra kod tarafında bir maliyet yok (kare BAŞINA çağrılır, throttle YOK —
# resim değil birkaç onlarca baytlık liste, /api/detections istemciye kendi
# hızında ilettiği için burada geciktirmenin faydası yok).
_DETECTIONS: dict[str, dict] = {}
_DETECTIONS_LOCK = threading.Lock()


def _tespit_itici(cid: str):
    """count.py'ye `on_detections` olarak verilir — bkz. count.py docstring'i:
    video AYRI akar, kutular ayrı/hafif bir kanaldan gider (WebSocket ile
    istemciye), sunucu resmi yeniden kodlayıp göndermez. Bu, "Analiz" JPEG
    modunun slayt-gösterisi hissini gidermek için eklendi (kullanıcı: web/stream
    olması değil, kutuların RESME gömülüp yeniden gönderilmesi sorunun kaynağıydı)."""
    def push(dets: list[dict], frame_idx: int) -> None:
        with _DETECTIONS_LOCK:
            _DETECTIONS[cid] = {"dets": dets, "frame_idx": frame_idx}
    return push


class _OnizlemeHandler(BaseHTTPRequestHandler):
    """127.0.0.1'e bağlı, kimlik doğrulamasız minik sunucu — yalnız aynı makineden
    server.py'nin proxy'lediği son kareyi/tespit listesini verir. Dışa açık DEĞİL
    (operatör ağına kimliksiz servis koymamak için server.py arada durur)."""

    def log_message(self, *a) -> None:
        pass   # stdout'u istek başına satırla kirletme

    def _json(self, obj) -> None:
        import json
        data = json.dumps(obj).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        if self.path.startswith("/frame/"):
            cid = self.path[len("/frame/"):].split("?")[0]
            with _PREVIEW_LOCK:
                data = _PREVIEW.get(cid)
            if not data:
                self.send_response(204)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if self.path.startswith("/detections/"):
            cid = self.path[len("/detections/"):].split("?")[0]
            with _DETECTIONS_LOCK:
                snap = _DETECTIONS.get(cid)
            self._json(snap or {"dets": [], "frame_idx": None})
            return
        self.send_response(404)
        self.end_headers()


def _onizleme_sunucusu_baslat(port: int) -> None:
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", port), _OnizlemeHandler)
    except OSError as e:
        print(f"[worker] önizleme sunucusu başlatılamadı (port {port}): {e} — "
              f"canlı görünümün Analiz modu bu worker için çalışmaz", flush=True)
        return
    threading.Thread(target=srv.serve_forever, daemon=True).start()


def _saved_lines(store, camera_id: str) -> list[dict]:
    out = []
    for z in store.list_zones(camera_id):
        if z["kind"] == "line" and len(z["points"] or []) >= 2:
            out.append({"name": z.get("name") or "Çizgi",
                        "pts": [z["points"][0], z["points"][1]],
                        "direction": z.get("direction") or "AtoB",
                        "classes": z.get("classes") or []})
    return out


def _saved_intrusions(store, camera_id: str) -> list[dict]:
    """İhlal alanları — sayım hattında değerlendirilir (aynı tespit/takip çıktısı)."""
    return [{"name": z.get("name") or "İhlal alanı", "points": z["points"],
             "classes": z.get("classes") or []}
            for z in store.list_zones(camera_id)
            if z["kind"] == "intrusion" and len(z["points"] or []) >= 3]


def _saved_fire_zones(store, camera_id: str) -> tuple[list[dict], list[dict]]:
    """(izleme alanları, maskeler) — kind='fire' / 'firemask'.

    Maske ISO/TS 7240-30'un karşılığıdır: kaynak makinesi, egzoz bacası veya
    güneş vuran pencere maskelenmezse hat yanlış alarm üretir ve operatör
    uyarılara bakmayı bırakır — sessiz sistemden daha kötüsü budur.
    """
    izleme, maske = [], []
    for z in store.list_zones(camera_id):
        if len(z.get("points") or []) < 3:
            continue
        if z["kind"] == "fire":
            izleme.append({"name": z.get("name") or "Izleme alani", "points": z["points"]})
        elif z["kind"] == "firemask":
            maske.append({"name": z.get("name") or "Maske", "points": z["points"]})
    return izleme, maske


def _nvdec_kullanilabilir() -> str:
    """GPU hattı gerçekten çalışır mı — çalışmıyorsa NEDENİNİ döndürür ("" = çalışır).

    Import başarılı olması yetmez: kart yok, sürücü uyumsuz veya CUDA görünmüyor
    olabilir. Bunu ÖNCEDEN anlamak, çalışma anında çökmekten iyidir; sahada
    "worker açık ama olay üretmiyor" en pahalı hata tipidir.
    """
    try:
        import torch
    except Exception as e:
        return f"torch yok: {e}"
    try:
        if not torch.cuda.is_available():
            return "CUDA görünmüyor (GPU yok veya sürücü eksik)"
    except Exception as e:
        return f"CUDA sorgusu başarısız: {e}"
    try:
        import PyNvVideoCodec  # noqa: F401
    except Exception as e:
        return f"PyNvVideoCodec yok ({e.__class__.__name__}) — bu platformda desteklenmiyor olabilir"
    try:
        import tensorrt  # noqa: F401
    except Exception as e:
        return f"tensorrt yok ({e.__class__.__name__})"
    return ""


def _gorev_listesi(cid, source, cfg, bstore, tasks, lines, ihlaller,
                   fire_izleme, fire_maske):
    """Etkin kamera görevlerini geç yüklenen çağrılabilirler olarak kurar."""
    gorevler: list[tuple[str, callable]] = []
    # main #7 kuralı: çizgi ya da ihlal alanı yoksa sayım motoru hiç açılmaz —
    # kullanıcının çizmediği hat config varsayılanıyla sayılmasın.
    if tasks.get("count") and (lines or ihlaller):
        from .count import run_count
        gorevler.append(("count", lambda: run_count(
            source, cfg, store=bstore, camera_id=cid, lines=lines,
            intrusions=ihlaller, should_stop=_kare_sayaci(cid),
            on_frame=_onizleme_itici(cid), on_detections=_tespit_itici(cid))))
    # Küresel kapalı özellik çöken görev DEĞİLDİR: görev listesine girmez, durumu
    # "kapalı" olarak görünür (bkz. _gorevleri_kos). Aksi hâlde her turda beş
    # yeniden deneme, park ve kırmızı kamera üretiyordu — bozuk hiçbir şey yokken.
    if tasks.get("fire") and cfg.get("fire.enabled", False):
        from .fire import run_fire
        gorevler.append(("fire", lambda: run_fire(
            source, cfg, store=bstore, camera_id=cid,
            bolgeler=fire_izleme, maskeler=fire_maske,
            should_stop=_kare_sayaci(cid), on_frame=_onizleme_itici(cid))))
    if tasks.get("plate"):
        from .plate import run_plate
        gorevler.append(("plate", lambda: run_plate(
            source, cfg, store=bstore, camera_id=cid,
            should_stop=_kare_sayaci(cid), on_frame=_onizleme_itici(cid))))
    if tasks.get("face"):
        from .face import run_face
        def _face():
            rstore = open_store(cfg)
            try:
                watch = rstore.faces_with_embedding()
            finally:
                rstore.close()
            run_face(source, cfg, store=bstore, camera_id=cid, watch=watch,
                     should_stop=_kare_sayaci(cid), on_frame=_onizleme_itici(cid))
        gorevler.append(("face", _face))
    # Telefon ve sigara AYRI görev ama tek poz hattı: ikisi açıksa bir kez koşar
    # (src/davranis.py). Ad, heartbeat ayrıntısında "telefon+sigara" gibi görünür.
    siniflar = aktif_siniflar(tasks)
    if siniflar:
        from .davranis import run_davranis
        gorevler.append(("+".join(siniflar), lambda: run_davranis(
            source, cfg, store=bstore, camera_id=cid, siniflar=siniflar,
            should_stop=_kare_sayaci(cid), on_frame=_onizleme_itici(cid))))
    return gorevler


def _gorevleri_kos(cid: str, source: str, cfg, bstore, tasks: dict, lines,
                   ihlaller, fire_izleme, fire_maske) -> bool:
    """Kamera görevlerini bağımsız supervisor thread'lerinde koşar."""
    gorevler = _gorev_listesi(cid, source, cfg, bstore, tasks, lines, ihlaller,
                              fire_izleme, fire_maske)
    with _STAGE_LOCK:
        _TASK_STAGE[cid] = {}
    if tasks.get("fire") and not cfg.get("fire.enabled", False):
        _gorev_durumu_yaz(cid, "fire", "kapalı (fire.enabled=false)")

    if not gorevler:
        return False
    azami = max(1, int(cfg.get("worker.max_parallel_tasks_per_camera", 4)))
    if len(gorevler) > azami:
        raise RuntimeError(
            f"{cid}: {len(gorevler)} analiz görevi açık; bağlantı bütçesi {azami} "
            "(worker.max_parallel_tasks_per_camera)")

    _STAGE[cid] = "+".join(ad for ad, _ in gorevler)
    threads = [threading.Thread(target=_gorev_gozetmeni,
                                args=(cid, ad, fn, cfg), daemon=True,
                                name=f"auras-{cid}-{ad}")
               for ad, fn in gorevler]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    _STAGE[cid] = _kamera_sagligi(cid)[1]
    return True


def _run_camera(cam: dict, cfg, bus) -> None:
    cid = cam["id"]
    source = cam["source"]
    bstore = BusStore(bus)
    loop_interval = int(cfg.get("worker.loop_interval", 30))

    while True:
        # görevler + bölgeler her turda DB'den tazelenir (UI değişikliği restart istemez)
        rstore = open_store(cfg)
        try:
            guncel = merged_cameras(cfg, rstore)
            # Kamera silindiyse iş parçacığı çıkar. Liste yalnız açılışta
            # okunduğu için silinen kamera işlenmeye ve "hatalı" heartbeat
            # yaymaya devam ediyordu — panelde olmayan kamera hata gösteriyordu.
            if not any(c["id"] == cid for c in guncel):
                print(f"[worker] {cid} silinmiş — işleme durduruluyor", flush=True)
                _STAGE[cid] = "silindi"
                return
            fresh = next(c for c in guncel if c["id"] == cid)
            # Kameraya özgü HTTP başlıkları (bazı HLS sağlayıcıları Referer şart koşar)
            akis.kaydet(fresh.get("source") or source, fresh.get("http_headers") or "")
            tasks = fresh.get("tasks") or {}
            ihlaller = _saved_intrusions(rstore, cid)
            fire_izleme, fire_maske = _saved_fire_zones(rstore, cid)
            cizgiler = _saved_lines(rstore, cid)
            # Worker yalnız UI'da kaydedilmiş geometriyi işler. None, CLI'daki
            # config varsayılanına düşer ve kullanıcının çizmediği hattı sayardı.
            lines = cizgiler or []
        finally:
            rstore.close()

        try:
            did_work = _gorevleri_kos(cid, source, cfg, bstore, tasks,
                                      lines, ihlaller, fire_izleme, fire_maske)
            durum, ayrinti = _kamera_sagligi(cid)
            _STAGE[cid] = ayrinti if durum == "error" else "idle"
        except Exception as e:
            _STAGE[cid] = f"error: {e}"
            print(f"[worker] {cid} hata: {e}", flush=True)
            time.sleep(10)
            continue
        if not did_work:
            _STAGE[cid] = "görev kapalı"
        if loop_interval <= 0:
            break
        time.sleep(loop_interval)
    _STAGE[cid] = "bitti"


def _heartbeat(cams: list[dict], bus, interval: float = 5.0) -> None:
    """Kamera sağlığı: görev denetçisinin durumu (ok/degraded/error/idle) + analize
    giren kare hızı (fps; panel bunu 'KARE ÜRETMİYOR' uyarısı için okur)."""
    onceki: dict[str, int] = {}
    son_t = time.monotonic()
    while True:
        time.sleep(interval)
        simdi = time.monotonic()
        gecen = max(simdi - son_t, 1e-6)
        son_t = simdi
        for cam in list(cams):
            cid = cam["id"]
            durum, st = _kamera_sagligi(cid)
            status = "idle" if st in ("idle", "görev kapalı", "bitti") else durum
            toplam = _FRAMES.get(cid, 0)
            fps = (toplam - onceki.get(cid, 0)) / gecen
            onceki[cid] = toplam
            publish(bus, "health", cid, {"status": status, "stage": st, "fps": round(fps, 1)})


def _nvdec_kameralarini_ayir(cams: list[dict]) -> tuple[list[dict], list[dict]]:
    """Yangınlı kamerayı standart hatta ayır; diğer kameralar NVDEC'de kalır."""
    standart = [c for c in cams if (c.get("tasks") or {}).get("fire")]
    nvdec = [c for c in cams if c not in standart]
    return nvdec, standart


def _standart_workerlar(cams: list[dict], cfg, bus) -> None:
    """Standart çok-görevli kamera worker'larını başlat ve tamamlanmalarını bekle.

    Panelden EKLENEN kamera da alınır (`worker.loop_interval` aralığıyla DB
    taranır): liste yalnız açılışta okunduğunda "kaydettim, hiçbir şey olmuyor"
    oluyordu — worker elle yeniden başlatılana dek yeni kamera görünmüyordu.
    """
    if not cams:
        return
    print(f"[worker] standart hat, {len(cams)} kamera: "
          f"{', '.join(c['id'] for c in cams)}", flush=True)
    threads = [threading.Thread(target=_run_camera, args=(c, cfg, bus), daemon=True)
               for c in cams]
    for t in threads:
        t.start()
    hb = threading.Thread(target=_heartbeat, args=(cams, bus), daemon=True)
    hb.start()
    selector = os.environ.get("AURAS_CAMERAS", "")
    keep = {x.strip() for x in selector.split(",") if x.strip()}

    def _yeni_kameralari_al() -> None:
        while True:
            time.sleep(int(cfg.get("worker.loop_interval", 30)) or 30)
            try:
                st = open_store(cfg)
                try:
                    guncel = [c for c in merged_cameras(cfg, st) if c.get("enabled", True)]
                finally:
                    st.close()
            except Exception as e:
                print(f"[worker] kamera listesi okunamadı: {e}", flush=True)
                continue
            if keep:
                guncel = [c for c in guncel if c["id"] in keep]
            var = {c["id"] for c in cams}
            for c in guncel:
                if c["id"] in var:
                    continue
                print(f"[worker] yeni kamera: {c['id']} — işleme alınıyor", flush=True)
                cams.append(c)          # heartbeat aynı listeyi okur, o da alır
                t = threading.Thread(target=_run_camera, args=(c, cfg, bus), daemon=True)
                t.start()
                threads.append(t)

    if int(cfg.get("worker.loop_interval", 30)) > 0:
        threading.Thread(target=_yeni_kameralari_al, daemon=True).start()
    while any(t.is_alive() for t in threads):
        time.sleep(1)
    for c in cams:
        publish(bus, "health", c["id"],
                {"status": "idle", "stage": _STAGE.get(c["id"], "bitti")})


def _kameralari_yukle(cfg):
    """Bus ve etkin/filtrelenmiş kamera listesini kurar."""
    # Redis yoksa TEK MAKİNE kipi: worker olayları doğrudan veritabanına yazar.
    # Olay yolu çok worker'lı/çok makineli kurulum için vardır; tek kutuda Docker
    # (dolayısıyla Redis) kurmaya zorlamak kurulumu gereksiz ağırlaştırıyordu.
    # Bu kipte ingestor'a gerek yoktur.
    bus = open_bus(cfg)
    if bus is None:
        bus = YerelBus(cfg)
        print("[worker] Redis yok — tek makine kipi: olaylar doğrudan "
              "veritabanına yazılacak (ingestor gerekmez)", flush=True)
    store = open_store(cfg)
    cams = [c for c in merged_cameras(cfg, store) if c.get("enabled", True)]
    store.close()

    selector = os.environ.get("AURAS_CAMERAS", "")
    if selector:
        keep = {x.strip() for x in selector.split(",") if x.strip()}
        cams = [c for c in cams if c["id"] in keep]
    if not cams:
        raise SystemExit("İşlenecek kamera yok")
    return bus, cams


def _nvdec_calistir(cams, cfg, bus):
    """NVDEC bölümünü koşar; fallback gereken kamera listesini veya None döndürür."""
    nvdec_cams, standart_cams = _nvdec_kameralarini_ayir(cams)
    if standart_cams:
        print("[worker] yangın görevi NVDEC hattından ayrıldı; standart hat: "
              f"{', '.join(c['id'] for c in standart_cams)}", flush=True)
    if not nvdec_cams:
        _standart_workerlar(standart_cams, cfg, bus)
        return None
    sebep = _nvdec_kullanilabilir()
    if sebep:
        print(f"[worker] nvdec kullanılamıyor ({sebep}) — ultralytics fallback",
              flush=True)
        return cams
    try:
        from .gpu_engine import run_gpu_worker
        arkadas = None
        if standart_cams:
            arkadas = threading.Thread(target=_standart_workerlar,
                args=(standart_cams, cfg, bus), daemon=True,
                name="auras-standart-fire-cameras")
            arkadas.start()
        print(f"[worker] motor=nvdec, {len(nvdec_cams)} kamera: "
              f"{', '.join(c['id'] for c in nvdec_cams)}")
        run_gpu_worker(nvdec_cams, cfg, bus)
        if arkadas is not None:
            arkadas.join()
        return None
    except Exception as e:
        print(f"[worker] nvdec çalışma hatası ({e.__class__.__name__}: {e}) — "
              "ultralytics fallback", flush=True)
        # Standart yangın kameraları zaten açıldı; yalnız NVDEC bölümünü döndür.
        return nvdec_cams


def main() -> None:
    cfg = load_config()
    from .gunluk import kur as gunluk_kur
    gunluk_kur("worker", cfg)
    apply_cv2_http_headers(cfg)   # HLS/CDN kaynakları için ek başlıklar
    bus, cams = _kameralari_yukle(cfg)

    from . import donanim
    engine = (cfg.get("worker.engine", "auto") or "auto").lower()
    if engine == "auto":
        # Makine ne ise o: nvdec (GB10/Linux+NVIDIA, PyNvVideoCodec+TensorRT) >
        # akis (taşınabilir: PyAV hwaccel + batch YOLO, her OS/GPU/CPU).
        # ultralytics motoru yalnız açıkça istenirse (dosya kaynağı deneme kipi).
        prof = donanim.profil()
        print(f"[worker] donanım: {donanim.ozet_satiri()}", flush=True)
        engine = prof["oneri"]["engine"]
        print(f"[worker] motor=auto → {engine}", flush=True)
    if engine == "nvdec":
        # GB10 GPU hattı (ADR-0003). Yangın kamerası NVDEC'te desteklenmez, standart
        # hatta ayrılır; NVDEC kullanılamıyor/çökerse kalan kameralar düşer.
        cams = _nvdec_calistir(cams, cfg, bus)
        if cams is None:
            return
        engine = "ultralytics"   # NVDEC düştü: kalan kameralar standart hatta (çift açma yok)

    _onizleme_sunucusu_baslat(int(cfg.get("worker.preview_port", 8801)))
    if engine == "akis":
        # Taşınabilir motor: sayım/plaka/yüz/yangın/telefon/sigara tek batch hattında
        # (src/akis_motoru.py). Çalışamazsa ultralytics standart hatta düşülür.
        from .akis_motoru import run_akis_worker

        def _hb(cid: str, du: dict) -> None:
            _STAGE[cid] = du.get("stage", "akis")
        print(f"[worker] motor=akis, {len(cams)} kamera: "
              f"{', '.join(c['id'] for c in cams)}", flush=True)
        try:
            run_akis_worker(cams, cfg, bus, on_frame=_onizleme_itici,
                            on_detections=_tespit_itici, health_cb=_hb)
            return
        except Exception as e:
            print(f"[worker] akis motoru çalışırken hata verdi "
                  f"({e.__class__.__name__}: {e}) — ultralytics motoruna "
                  f"düşülüyor", flush=True)
    print(f"[worker] motor=ultralytics, {len(cams)} kamera: {', '.join(c['id'] for c in cams)}")
    try:
        _standart_workerlar(cams, cfg, bus)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
