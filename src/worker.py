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

from . import akis
from .bus import BusStore, YerelBus, open_bus, publish
from .config import apply_cv2_http_headers, load_config
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
    if tasks.get("count"):
        from .count import run_count
        gorevler.append(("count", lambda: run_count(
            source, cfg, store=bstore, camera_id=cid, lines=lines,
            intrusions=ihlaller)))
    if tasks.get("fire"):
        from .fire import run_fire
        def _fire():
            if not cfg.get("fire.enabled", False):
                raise RuntimeError("yangın görevi açık ama fire.enabled=false")
            run_fire(source, cfg, store=bstore, camera_id=cid,
                     bolgeler=fire_izleme, maskeler=fire_maske)
        gorevler.append(("fire", _fire))
    if tasks.get("plate"):
        from .plate import run_plate
        gorevler.append(("plate", lambda: run_plate(
            source, cfg, store=bstore, camera_id=cid)))
    if tasks.get("face"):
        from .face import run_face
        def _face():
            rstore = open_store(cfg)
            try:
                watch = rstore.faces_with_embedding()
            finally:
                rstore.close()
            run_face(source, cfg, store=bstore, camera_id=cid, watch=watch)
        gorevler.append(("face", _face))
    return gorevler


def _gorevleri_kos(cid: str, source: str, cfg, bstore, tasks: dict, lines,
                   ihlaller, fire_izleme, fire_maske) -> bool:
    """Kamera görevlerini bağımsız supervisor thread'lerinde koşar."""
    gorevler = _gorev_listesi(cid, source, cfg, bstore, tasks, lines, ihlaller,
                              fire_izleme, fire_maske)
    with _STAGE_LOCK:
        _TASK_STAGE[cid] = {}

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
    while True:
        for cam in cams:
            durum, st = _kamera_sagligi(cam["id"])
            if st == "silindi":
                continue
            status = ("idle" if st in ("idle", "görev kapalı", "bitti") else durum)
            publish(bus, "health", cam["id"], {"status": status, "stage": st})
        time.sleep(interval)


def _nvdec_kameralarini_ayir(cams: list[dict]) -> tuple[list[dict], list[dict]]:
    """Yangınlı kamerayı standart hatta ayır; diğer kameralar NVDEC'de kalır."""
    standart = [c for c in cams if (c.get("tasks") or {}).get("fire")]
    nvdec = [c for c in cams if c not in standart]
    return nvdec, standart


def _standart_workerlar(cams: list[dict], cfg, bus) -> None:
    """Standart çok-görevli kamera worker'larını başlat ve tamamlanmalarını bekle."""
    if not cams:
        return
    print(f"[worker] standart hat, {len(cams)} kamera: "
          f"{', '.join(c['id'] for c in cams)}")
    threads = [threading.Thread(target=_run_camera, args=(c, cfg, bus), daemon=True)
               for c in cams]
    for t in threads:
        t.start()
    hb = threading.Thread(target=_heartbeat, args=(cams, bus), daemon=True)
    hb.start()
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
    apply_cv2_http_headers(cfg)
    bus, cams = _kameralari_yukle(cfg)
    engine = (cfg.get("worker.engine", "ultralytics") or "ultralytics").lower()
    if engine == "nvdec":
        cams = _nvdec_calistir(cams, cfg, bus)
        if cams is None:
            return

    try:
        _standart_workerlar(cams, cfg, bus)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
