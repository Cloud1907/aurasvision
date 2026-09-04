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
_PREVIEW_MIN_INTERVAL = 1.0   # sn — sayım/analiz hızını ETKİLEMEZ, yalnız önizleme örnekleme sıklığı
_PREVIEW_MAX_W = 960


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


class _OnizlemeHandler(BaseHTTPRequestHandler):
    """127.0.0.1'e bağlı, kimlik doğrulamasız minik sunucu — yalnız aynı makineden
    server.py'nin proxy'lediği son kareyi verir. Dışa açık DEĞİL (operatör ağına
    kimliksiz görüntü servisi koymamak için server.py:/api/live-frame arada durur)."""

    def log_message(self, *a) -> None:
        pass   # stdout'u istek başına satırla kirletme

    def do_GET(self) -> None:
        if not self.path.startswith("/frame/"):
            self.send_response(404)
            self.end_headers()
            return
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
            cizgiler = _saved_lines(rstore, cid)
            # İhlal alanı varken çizgi yoksa [] geçilir: None config varsayılanına düşerdi
            lines = cizgiler or ([] if ihlaller else None)
        finally:
            rstore.close()

        did_work = False
        try:
            if tasks.get("count"):
                _STAGE[cid] = "count"
                from .count import run_count
                run_count(source, cfg, store=bstore, camera_id=cid, lines=lines,
                          intrusions=ihlaller, should_stop=_kare_sayaci(cid),
                          on_frame=_onizleme_itici(cid))
                did_work = True
            if tasks.get("plate"):
                _STAGE[cid] = "plate"
                from .plate import run_plate
                run_plate(source, cfg, store=bstore, camera_id=cid,
                          should_stop=_kare_sayaci(cid), on_frame=_onizleme_itici(cid))
                did_work = True
            if tasks.get("face"):
                _STAGE[cid] = "face"
                from .face import run_face
                rstore = open_store(cfg)
                watch = rstore.faces_with_embedding()
                rstore.close()
                run_face(source, cfg, store=bstore, camera_id=cid, watch=watch,
                         should_stop=_kare_sayaci(cid), on_frame=_onizleme_itici(cid))
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

    engine = (cfg.get("worker.engine", "ultralytics") or "ultralytics").lower()
    if engine == "nvdec":
        # GB10 GPU pipeline (ADR-0003): NVDEC decode + batch TensorRT + tracker.
        # PyNvVideoCodec/TensorRT her platformda YOK (ör. Windows wheel'i belirsiz);
        # import patlarsa sessizce ölmek yerine ultralytics motoruna düşülür —
        # yavaş ama çalışır. Sessiz çökme sahada "worker açık ama olay yok" demek.
        sebep = _nvdec_kullanilabilir()
        if sebep:
            print(f"[worker] nvdec motoru kullanılamıyor ({sebep}) — ultralytics "
                  f"motoruna düşülüyor. Kalıcı çözüm: config.yaml → "
                  f"worker.engine: ultralytics", flush=True)
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
                      f"({e.__class__.__name__}: {e}) — ultralytics motoruna "
                      f"düşülüyor", flush=True)

    _onizleme_sunucusu_baslat(int(cfg.get("worker.preview_port", 8801)))
    print(f"[worker] {len(cams)} kamera: {', '.join(c['id'] for c in cams)}")
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
