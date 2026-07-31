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

from .bus import BusStore, open_bus, publish
from .config import apply_cv2_http_headers, load_config
from .store import merged_cameras, open_store

# kamera_id → o an çalışan aşama (heartbeat bunu yayınlar)
_STAGE: dict[str, str] = {}


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
            fresh = next((c for c in merged_cameras(cfg, rstore) if c["id"] == cid), cam)
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
                          intrusions=ihlaller)
                did_work = True
            if tasks.get("plate"):
                _STAGE[cid] = "plate"
                from .plate import run_plate
                run_plate(source, cfg, store=bstore, camera_id=cid)
                did_work = True
            if tasks.get("face"):
                _STAGE[cid] = "face"
                from .face import run_face
                rstore = open_store(cfg)
                watch = rstore.faces_with_embedding()
                rstore.close()
                run_face(source, cfg, store=bstore, camera_id=cid, watch=watch)
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
    while True:
        for cam in cams:
            st = _STAGE.get(cam["id"], "başlıyor")
            status = "error" if st.startswith("error") else ("idle" if st in ("idle", "görev kapalı", "bitti") else "ok")
            publish(bus, "health", cam["id"], {"status": status, "stage": st})
        time.sleep(interval)


def main() -> None:
    cfg = load_config()
    from .gunluk import kur as gunluk_kur
    gunluk_kur("worker", cfg)
    apply_cv2_http_headers(cfg)   # HLS/CDN kaynakları için ek başlıklar
    bus = open_bus(cfg)
    if bus is None:
        raise SystemExit("REDIS_URL (veya config redis.url) gerekli — worker olay yolu olmadan çalışmaz")
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

    print(f"[worker] {len(cams)} kamera: {', '.join(c['id'] for c in cams)}")
    threads = [threading.Thread(target=_run_camera, args=(c, cfg, bus), daemon=True)
               for c in cams]
    for t in threads:
        t.start()
    hb = threading.Thread(target=_heartbeat, args=(cams, bus), daemon=True)
    hb.start()
    try:
        while any(t.is_alive() for t in threads):
            time.sleep(1)
        # dosya kaynakları tek geçişte bittiyse son durumu bir kez daha yayınla
        for c in cams:
            publish(bus, "health", c["id"], {"status": "idle", "stage": _STAGE.get(c["id"], "bitti")})
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
