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
from .store import merged_cameras, open_store

# kamera_id → o an çalışan aşama (heartbeat bunu yayınlar)
_STAGE: dict[str, str] = {}
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
                        "direction": z.get("direction") or "AtoB"})
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


def _canli_kaynak(source: str) -> bool:
    """RTSP/RTMP/HTTP(S) — bitmeyen akış (yolo.track(stream=True) hiç dönmez).

    Dosya kaynağı bunun tersi: işlenir, biter, döner — sıralı görev dispatch'i
    orada sorun değil (bkz. _run_camera'daki canlı+çoklu-görev dalı).
    """
    return str(source).lower().startswith(("rtsp://", "rtmp://", "http://", "https://"))


def _gorev_calistir(gorev: str, source: str, cfg, bstore, cid: str,
                    lines, ihlaller, watch=None, fire_zones=None) -> None:
    """Tek analiz görevini (count/plate/face/fire) çalıştırır — dispatch tek yerde,
    hem sıralı hem eşzamanlı (bkz. _run_camera) çağrı yolu bunu kullanır."""
    if gorev == "count":
        from .count import run_count
        run_count(source, cfg, store=bstore, camera_id=cid, lines=lines,
                  intrusions=ihlaller, should_stop=_kare_sayaci(cid),
                  on_frame=_onizleme_itici(cid), on_detections=_tespit_itici(cid))
    elif gorev == "plate":
        from .plate import run_plate
        run_plate(source, cfg, store=bstore, camera_id=cid,
                  should_stop=_kare_sayaci(cid), on_frame=_onizleme_itici(cid))
    elif gorev == "face":
        from .face import run_face
        run_face(source, cfg, store=bstore, camera_id=cid, watch=watch,
                 should_stop=_kare_sayaci(cid), on_frame=_onizleme_itici(cid))
    elif gorev == "fire":
        # Yangın/duman erken uyarı (sertifikalı alarm DEĞİL — src/fire.py başlığı)
        from .fire import run_fire
        izleme, maske = fire_zones or ([], [])
        run_fire(source, cfg, store=bstore, camera_id=cid,
                 bolgeler=izleme, maskeler=maske,
                 should_stop=_kare_sayaci(cid), on_frame=_onizleme_itici(cid))


def _gorev_thread_calistir(gorev: str, source: str, cfg, bstore, cid: str,
                           lines, ihlaller, watch=None, fire_zones=None) -> None:
    """_gorev_calistir'i AYRI thread'de sarar — bir görevin hatası diğerini
    (veya kamerayı) düşürmesin diye burada yutulur (bkz. _run_camera)."""
    try:
        _gorev_calistir(gorev, source, cfg, bstore, cid, lines, ihlaller, watch, fire_zones)
    except Exception as e:
        print(f"[worker] {cid}/{gorev} hata: {e}", flush=True)


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
            fire_zones = _saved_fire_zones(rstore, cid)
            cizgiler = _saved_lines(rstore, cid)
            # İhlal alanı varken çizgi yoksa [] geçilir: None config varsayılanına düşerdi
            lines = cizgiler or ([] if ihlaller else None)
        finally:
            rstore.close()

        did_work = False
        aktif = [g for g in ("count", "plate", "face", "fire") if tasks.get(g)]
        canli = _canli_kaynak(source)
        watch = None
        if "face" in aktif:
            rstore = open_store(cfg)
            watch = rstore.faces_with_embedding()
            rstore.close()
        try:
            if canli and len(aktif) > 1:
                # RTSP/canlı kaynakta count() BİTMEYEN bir generator'dır
                # (yolo.track(stream=True), should_stop hep False). Aynı thread'de
                # sırayla çağrılırsa count SONRAKİ görevi sonsuza dek engeller —
                # sahada ölçüldü: kamera-204 count+plate açıkken plate_events
                # HİÇ satır üretmedi (count asla dönmediği için plate'e sıra
                # gelmiyordu). Her görev kendi RTSP bağlantısını açıp AYRI
                # thread'de koşar — recorder zaten aynı akışa ayrıca bağlanıyor,
                # çoklu istemci varsayımı burada yeni değil. Bir görevin hatası
                # diğerini düşürmez (_gorev_thread_calistir hatayı yutar).
                _STAGE[cid] = "+".join(aktif)
                gorev_threads = [threading.Thread(
                    target=_gorev_thread_calistir,
                    args=(g, source, cfg, bstore, cid, lines, ihlaller, watch, fire_zones),
                    daemon=True) for g in aktif]
                for t in gorev_threads:
                    t.start()
                for t in gorev_threads:
                    t.join()
                did_work = bool(aktif)
            else:
                for gorev in aktif:
                    _STAGE[cid] = gorev
                    _gorev_calistir(gorev, source, cfg, bstore, cid, lines, ihlaller, watch,
                                    fire_zones)
                    did_work = True
            _STAGE[cid] = "idle"
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
    """Kamera başına durum + KARE HIZI yayınlar.

    fps'i yalnızca nvdec motoru yayınlıyordu; ultralytics motorunda alan boş
    kalıyor ve panel (src/server.py, fps > 0.1 şartı) olaylar düzgün yazılırken
    bile "bağlı ama KARE ÜRETMİYOR" diyordu. Çalışan kurulumu hatalı göstermek,
    gerçek arızayı fark edilmez yapar — bu yüzden fps burada da üretilir:
    iki heartbeat arasındaki kare farkı / geçen süre.
    """
    onceki: dict[str, int] = {}
    son = time.monotonic()
    while True:
        time.sleep(interval)
        simdi = time.monotonic()
        gecen = max(simdi - son, 1e-6)
        son = simdi
        for cam in cams:
            cid = cam["id"]
            st = _STAGE.get(cid, "başlıyor")
            if st == "silindi":
                continue
            status = "error" if st.startswith("error") else ("idle" if st in ("idle", "görev kapalı", "bitti") else "ok")
            toplam = _FRAMES.get(cid, 0)
            fps = (toplam - onceki.get(cid, 0)) / gecen
            onceki[cid] = toplam
            publish(bus, "health", cid,
                    {"status": status, "stage": st, "fps": round(fps, 1)})


def main() -> None:
    cfg = load_config()
    from .gunluk import kur as gunluk_kur
    gunluk_kur("worker", cfg)
    apply_cv2_http_headers(cfg)   # HLS/CDN kaynakları için ek başlıklar
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

    from . import donanim
    prof = donanim.profil()
    print(f"[worker] donanım: {donanim.ozet_satiri()}", flush=True)
    engine = (cfg.get("worker.engine", "auto") or "auto").lower()
    if engine == "auto":
        # Makine ne ise o: nvdec (GB10/Linux+NVIDIA, PyNvVideoCodec+TensorRT) >
        # akis (taşınabilir: PyAV hwaccel + batch YOLO, her OS/GPU/CPU).
        # ultralytics motoru yalnız açıkça istenirse (dosya kaynağı deneme kipi).
        engine = prof["oneri"]["engine"]
        print(f"[worker] motor=auto → {engine}", flush=True)
    if engine == "nvdec":
        # GB10 GPU pipeline (ADR-0003): NVDEC decode + batch TensorRT + tracker.
        # PyNvVideoCodec/TensorRT her platformda YOK (ör. Windows wheel'i belirsiz);
        # import patlarsa sessizce ölmek yerine ultralytics motoruna düşülür —
        # yavaş ama çalışır. Sessiz çökme sahada "worker açık ama olay yok" demek.
        sebep = _nvdec_kullanilabilir()
        if sebep:
            print(f"[worker] nvdec motoru kullanılamıyor ({sebep}) — taşınabilir "
                  f"akis motoruna düşülüyor (config.yaml → worker.engine: auto)", flush=True)
        else:
            try:
                from .gpu_engine import run_gpu_worker
                print(f"[worker] motor=nvdec, {len(cams)} kamera: "
                      f"{', '.join(c['id'] for c in cams)}")
                run_gpu_worker(cams, cfg, bus)
                return
            except Exception as e:
                # Çalışma anında patlarsa (sürücü uyumsuzluğu, engine dosyası başka
                # karta ait, VRAM yetmedi) worker ÖLMEZ — yavaş motorla devam eder.
                print(f"[worker] nvdec motoru çalışırken hata verdi "
                      f"({e.__class__.__name__}: {e}) — akis motoruna "
                      f"düşülüyor", flush=True)

    _onizleme_sunucusu_baslat(int(cfg.get("worker.preview_port", 8801)))
    if engine in ("akis", "nvdec"):
        # nvdec buraya yalnız çalışamayınca düşer → taşınabilir motor devralır
        # (ultralytics'e değil: o yol CPU'yu doyuran eski hattır).
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
    threads = [threading.Thread(target=_run_camera, args=(c, cfg, bus), daemon=True)
               for c in cams]
    for t in threads:
        t.start()
    hb = threading.Thread(target=_heartbeat, args=(cams, bus), daemon=True)
    hb.start()

    def _yeni_kameralari_al() -> None:
        """Panelden EKLENEN kameraya iş parçacığı açar.

        Kamera listesi yalnız açılışta okunuyordu: silinme ele alınmıştı
        (_run_camera kendini durdurur) ama EKLENME alınmıyordu. Sonuç: panelden
        kamera eklenince "kaydettim, hiçbir şey olmuyor" — worker elle yeniden
        başlatılana kadar o kamera görünmezdi. Görev değişikliği zaten her turda
        DB'den tazeleniyor; eksik olan tek şey buydu.
        """
        while True:
            time.sleep(int(cfg.get("worker.loop_interval", 30)))
            try:
                st = open_store(cfg)
                try:
                    guncel = [c for c in merged_cameras(cfg, st) if c.get("enabled", True)]
                finally:
                    st.close()
            except Exception as e:
                print(f"[worker] kamera listesi okunamadı: {e}", flush=True)
                continue
            if selector:
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

    izci = threading.Thread(target=_yeni_kameralari_al, daemon=True)
    izci.start()

    try:
        while any(t.is_alive() for t in threads) or izci.is_alive():
            time.sleep(1)
        # dosya kaynakları tek geçişte bittiyse son durumu bir kez daha yayınla
        for c in cams:
            publish(bus, "health", c["id"], {"status": "idle", "stage": _STAGE.get(c["id"], "bitti")})
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
