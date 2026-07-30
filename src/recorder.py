"""Sürekli kayıt servisi (NVR çekirdeği) — kamera akışını disk segmentlerine yazar.

Neden ayrı servis: analiz (worker) ile kayıt birbirini beklememeli. Worker çökse
bile kayıt sürmeli; kayıt diski dolsa bile analiz sürmeli.

Tasarım kararları:
* **Transcode YOK (`-c copy`).** GPU inference'a aittir; kayıt yalnız paketi diske
  yazar. Bu, kamera başına CPU maliyetini neredeyse sıfıra indirir.
* **Kaynak go2rtc'den alınır.** Dosya/RTSP/HLS ayrımı orada normalize edilmiştir;
  kayıt hepsini tek biçimde görür (ayrıca HLS başlıkları da orada çözülür).
* **Segment süresi NOMİNALDİR.** `-c copy` yalnız anahtar karede kesebilir, bu yüzden
  gerçek süre farklı çıkar. DB'ye ffprobe ile ÖLÇÜLEN süre yazılır — zaman çizelgesi
  nominal süreye güvenirse zamanla kayar.
* **Silme sırası: önce dosya, sonra DB satırı.** Tersi yetim dosya bırakır.

Çalıştırma:
  python -m src.recorder                      # kayıt açık tüm kameralar
  AURAS_CAMERAS=giris,otopark python -m src.recorder
"""
from __future__ import annotations

import os
import shutil
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import load_config
from .store import merged_cameras, open_store

_ROOT = Path(__file__).resolve().parent.parent
_DUR = 60          # sn — nominal segment süresi
_KAPANDI = 5.0     # sn — dosya bu süredir büyümüyorsa segment kapanmış sayılır


def kayit_kok(cfg) -> Path:
    return _ROOT / cfg.get("paths.output_dir", "output") / cfg.get("record.dir", "rec")


def _kaynak(cam: dict, cfg) -> tuple[str, str]:
    """(akış adresi, hangi akış) — go2rtc RTSP üzerinden (kaynak tipleri orada normalize).

    Substream kaydı ölçek için belirleyicidir: 100 kamerayı ana akıştan 30 gün
    kaydetmek ~114 TB, substream'den ~16 TB. Kameranın ikinci akışı tanımlıysa
    ve record.use_substream açıksa ondan kaydedilir — kalite düşer ama arşiv
    derinliği aynı diskte 7 kat artar. Tek kamera görünümü ve analiz ana akışı
    kullanmaya devam eder.
    """
    go2rtc = (cfg.get("go2rtc.url", "") or "").rstrip("/")
    sub = bool(cam.get("url_sub")) and bool(cfg.get("record.use_substream", False))
    if go2rtc:
        host = go2rtc.split("//", 1)[-1].split(":")[0] or "localhost"
        ad = f"{cam['id']}-sub" if sub else cam["id"]
        return f"rtsp://{host}:8554/{ad}", ("substream" if sub else "ana akış")
    return (str(cam["url_sub"]) if sub else str(cam["source"])), ("substream" if sub else "ana akış")


def _olcum(path: Path) -> tuple[float, int]:
    """(süre_sn, bayt) — süre ffprobe ile DEĞİL PyAV ile ölçülür.

    Konakta ffmpeg/ffprobe kurulu olmayabilir (bizde yoktu); PyAV zaten
    bağımlılığımız olduğu için harici ikiliye bağlanmıyoruz.
    """
    import av

    sure = 0.0
    try:
        with av.open(str(path)) as c:
            if c.duration:
                sure = c.duration / 1_000_000
            elif c.streams.video:
                vs = c.streams.video[0]
                if vs.duration and vs.time_base:
                    sure = float(vs.duration * vs.time_base)
    except Exception:
        sure = 0.0
    try:
        boyut = path.stat().st_size
    except OSError:
        boyut = 0
    return sure, boyut


class CameraRecorder(threading.Thread):
    """Tek kamera: ffmpeg segment yazıcısı + kapanan segmentleri DB'ye kaydeden gözcü."""

    def __init__(self, cam: dict, cfg) -> None:
        super().__init__(daemon=True, name=f"rec-{cam['id']}")
        self.cam = cam
        self.cfg = cfg
        self.dur = int(cfg.get("record.segment_seconds", _DUR))
        self.dizin = kayit_kok(cfg) / cam["id"]
        self.stop_flag = False
        self.ilk_pts = 0
        self.durum = "başlıyor"
        self.kayitli: set[str] = set()

    def run(self) -> None:
        self.dizin.mkdir(parents=True, exist_ok=True)
        threading.Thread(target=self._gozcu, daemon=True,
                         name=f"scan-{self.cam['id']}").start()
        while not self.stop_flag:
            try:
                self._kaydet()
            except Exception as e:
                self.durum = f"hata: {e}"
                print(f"[rec] {self.cam['id']} kayıt hatası: {e}", flush=True)
            if not self.stop_flag:
                time.sleep(5)   # akış koptu → yeniden bağlan

    def _kaydet(self) -> None:
        """Paketleri yeniden KODLAMADAN mp4 segmentlerine yazar (remux).

        Kesim yalnız ANAHTAR KAREDE yapılır — aksi hâlde segment başı çözülemez.
        Bu yüzden gerçek segment süresi nominalden farklı çıkar (GOP'a bağlı);
        DB'ye ölçülen süre yazıldığı için zaman çizelgesi kaymaz.
        """
        import av

        from .config import http_options

        url, akis_tipi = _kaynak(self.cam, self.cfg)
        opts = {"rtsp_transport": "tcp"} if url.startswith("rtsp") else {}
        opts.update(http_options(self.cfg, url))
        inp = av.open(url, options=opts, timeout=(30.0, 30.0))
        self.durum = f"kaydediyor ({akis_tipi})"
        cikis = None
        ovs = None
        seg_bas = 0.0        # segmentin ilk paket zamanı (kaynak saatinde)
        yol: Path | None = None
        try:
            ivs = inp.streams.video[0]
            tb = ivs.time_base
            for pkt in inp.demux(ivs):
                if self.stop_flag:
                    break
                if pkt.dts is None or pkt.pts is None or pkt.size == 0:
                    continue
                t = float(pkt.pts * tb)
                yeni_gerek = cikis is None or (pkt.is_keyframe and t - seg_bas >= self.dur)
                if yeni_gerek:
                    if cikis is not None:
                        cikis.close()
                    if not pkt.is_keyframe and cikis is None:
                        continue          # ilk anahtar kareyi bekle (bozuk segment olmasın)
                    simdi = datetime.now().astimezone()
                    yol = self.dizin / simdi.strftime("%Y-%m-%d") / simdi.strftime("%H-%M-%S.mp4")
                    yol.parent.mkdir(parents=True, exist_ok=True)
                    cikis = av.open(str(yol), "w", format="mp4")
                    ovs = cikis.add_stream_from_template(ivs)
                    seg_bas = t
                    self.ilk_pts = pkt.pts
                # Zaman damgalarını segment başına göre sıfırla (her dosya 0'dan başlar)
                pkt.pts -= self.ilk_pts
                pkt.dts -= self.ilk_pts
                pkt.stream = ovs
                cikis.mux(pkt)
        finally:
            if cikis is not None:
                try:
                    cikis.close()
                except Exception:
                    pass
            try:
                inp.close()
            except Exception:
                pass
            if not self.stop_flag:
                self.durum = "kesildi"

    def _gozcu(self) -> None:
        """Kapanmış segmentleri (artık büyümeyen dosyalar) DB'ye yazar."""
        while not self.stop_flag:
            try:
                self._tara()
            except Exception as e:
                print(f"[rec] {self.cam['id']} tarama hatası: {e}", flush=True)
            time.sleep(10)

    def _tara(self) -> None:
        dosyalar = sorted(self.dizin.rglob("*.mp4"))
        if not dosyalar:
            return
        simdi = time.time()
        store = open_store(self.cfg)
        try:
            for f in dosyalar:
                yol = str(f.relative_to(kayit_kok(self.cfg)))
                if yol in self.kayitli:
                    continue
                try:
                    st = f.stat()
                except OSError:
                    continue
                if simdi - st.st_mtime < _KAPANDI:
                    continue          # hâlâ yazılıyor
                sure, boyut = _olcum(f)
                if sure <= 0 or boyut <= 0:
                    continue          # bozuk/yarım segment — bir sonraki turda tekrar bak
                # Dosya adı segmentin BAŞLANGIÇ zamanı (strftime ile yazıldı, yerel saat)
                try:
                    bas = datetime.strptime(f"{f.parent.name} {f.stem}",
                                            "%Y-%m-%d %H-%M-%S").astimezone()
                except ValueError:
                    continue
                store.add_recording(self.cam["id"], yol, bas,
                                    bas + timedelta(seconds=sure), sure, boyut)
                self.kayitli.add(yol)
            store.commit()
        finally:
            store.close()

    def dur_(self) -> None:
        self.stop_flag = True   # döngü son segmenti finally'de düzgün kapatır


def temizlik(cfg, cams: list[dict]) -> None:
    """Saklama süresi + disk kotası uygular. Dosya ÖNCE, DB satırı SONRA silinir."""
    gun = int(cfg.get("record.keep_days", 15))
    kota_gb = float(cfg.get("record.max_size_gb", 0))
    kok = kayit_kok(cfg)
    store = open_store(cfg)
    try:
        if gun > 0:
            sinir = datetime.now(timezone.utc) - timedelta(days=gun)
            for r in store.recordings_before(sinir):
                _sil(kok, r, store)
        if kota_gb > 0:
            # Kota aşılıyorsa en ESKİ segmentten başlayarak sil
            toplam = store.recordings_size()
            hedef = kota_gb * (1024 ** 3)
            if toplam > hedef:
                for r in store.recordings_oldest(limit=500):
                    if toplam <= hedef:
                        break
                    toplam -= int(r.get("size_bytes") or 0)
                    _sil(kok, r, store)
        # Boş kalan gün klasörlerini topla
        for d in kok.glob("*/*"):
            if d.is_dir() and not any(d.iterdir()):
                shutil.rmtree(d, ignore_errors=True)
        store.commit()
    finally:
        store.close()


def _sil(kok: Path, r: dict, store) -> None:
    try:
        (kok / r["path"]).unlink(missing_ok=True)
    except OSError as e:
        print(f"[rec] silinemedi {r['path']}: {e}", flush=True)
        return          # dosya silinemedIYSE DB satırını da bırak (tutarlılık)
    store.delete_recording(r["path"])


def main() -> None:
    cfg = load_config()
    if not cfg.get("record.enabled", True):
        raise SystemExit("record.enabled=false — kayıt servisi kapalı")
    store = open_store(cfg)
    cams = [c for c in merged_cameras(cfg, store) if c.get("enabled", True)]
    store.close()

    sec = os.environ.get("AURAS_CAMERAS", "")
    if sec:
        keep = {x.strip() for x in sec.split(",") if x.strip()}
        cams = [c for c in cams if c["id"] in keep]
    if not cams:
        raise SystemExit("Kaydedilecek kamera yok")

    print(f"[rec] {len(cams)} kamera kaydediliyor → {kayit_kok(cfg)}", flush=True)
    kayitcilar = [CameraRecorder(c, cfg) for c in cams]
    for k in kayitcilar:
        k.start()

    try:
        while True:
            temizlik(cfg, cams)
            time.sleep(300)   # 5 dakikada bir saklama/kota kontrolü
    except KeyboardInterrupt:
        pass
    finally:
        for k in kayitcilar:
            k.dur_()
        time.sleep(2)


if __name__ == "__main__":
    main()
