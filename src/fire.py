"""Yangın/duman ERKEN UYARI — sertifikalı yangın alarm sistemi DEĞİLDİR.

Bu modülün ne OLMADIĞI, ne olduğundan önce gelir: video tabanlı yangın tespiti
EN 54 kapsamında değildir; ürünler ancak VdS/BOSEC/CNPP gibi ulusal yollardan
sertifika alarak yasal alarmın yerine geçebilir (Bosch AVIOTEC VdS G217090,
Kasım 2017; Araani SmokeCatcher BOSEC/CNPP). Böyle bir belgemiz yok. Dolayısıyla
bu modül mevcut yangın sistemini TAMAMLAR — yerine geçmez. `FERAGAT` sabiti bu
cümleyi her alarm etiketine iliştirir; kaldırılması yasal risktir.

Tasarımı üç ölçüm belirledi (.agents/reports/2026-09-02-yangin-ve-tekstil-hata-tespiti.md):

* **Tek kare yetmez.** FIA/BRE'nin bağımsız testinde video duman dedektörleri
  arka planla kontrast eden küçük duman hacimlerinde ORTALAMA %58, benzer renkli
  arka planda %52 başarı gösterdi. SmokeyNet'in baseline'ları geçmesinin sebebi
  de uzam-ZAMANSAL bilgi. Bu yüzden burada tek kare asla alarm üretmez:
  `DumanTakip` pencere içinde N kare doğrulama arar (`izle → on_uyari → alarm`).
* **Ortam dedektörün parçasıdır.** ISO/TS 7240-30 kurulum standardı, maskelenen
  bölgeleri ve saha kabul testini şart koşuyor. Bu yüzden maskeleme (kaynak
  makinesi, egzoz, güneş vuran pencere) mantığın içinde, opsiyonel bir UI ayarı
  değil.
* **Durağan kareden duman ayırt edilemez.** İnsan da ayırt edemiyor — bu yüzden
  kanıt yalnız kare değil, doğrulayan karelerden oluşan KLİP'tir. Operatör
  dumanın hareketini görmeden "gerçek mi" sorusuna cevap veremez.

Uyarı kademeleri ikili değil üçlüdür (VESDA'nın çok kademeli uyarı mantığı):
  izle      — tek/az kare; kayda bile girmez, yalnız iç durum
  on_uyari  — pencere içinde N kare doğruladı; panelde rozet, webhook YOK
  alarm     — doğrulama `alarm_seconds` boyunca sürdü; uyarı + kanıt + webhook

Model: genel amaçlı YOLO ağırlığı BU İŞİ YAPMAZ (COCO'da duman sınıfı yok).
`model_yolu()` bunu sessiz sıfır olaya değil açık hataya çevirir.
"""
from __future__ import annotations

import re
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .zones import point_in_poly

_ROOT = Path(__file__).resolve().parent.parent

FERAGAT = "ERKEN UYARI - sertifikali yangin alarmi degildir (EN 54 kapsami disi)"

# Model sınıf adı → UI adı. Model İngilizce üretir, panel Türkçe gösterir.
SINIF_ADLARI = {"fire": "alev", "smoke": "duman", "alev": "alev", "duman": "duman"}

# Ultralytics'in otomatik indirdiği genel amaçlı ağırlık adları. Bunlardan biri
# `fire.model`e yazılırsa hat sorunsuz KOŞAR ve hiçbir zaman olay üretmez —
# sahadaki en pahalı hata tipi (worker.py'deki aynı gerekçe).
_GENEL_YOLO = re.compile(r"^yolo(v\d+|\d+)?[nsmlx]?(-[a-z]+)?\.(pt|engine|onnx)$", re.I)


def model_yolu(model: str) -> Path:
    """Yangın modelini doğrular; yoksa ADIYLA hata verir (sessiz sıfır olay değil)."""
    ad = Path(model).name
    if _GENEL_YOLO.match(ad):
        raise FileNotFoundError(
            f"'{model}' genel amaçlı bir YOLO ağırlığıdır — yangın/duman sınıfı "
            "içermez, bu hat hiç olay üretmez. `fire.model` alanına yangın "
            "veri setiyle eğitilmiş bir ağırlık verin (bkz. docs/yangin-modeli.md)."
        )
    p = Path(model)
    if not p.is_absolute():
        p = _ROOT / p
    if not p.is_file():
        raise FileNotFoundError(
            f"Yangın modeli bulunamadı: {model} (aranan: {p}). Eğitim ve indirme "
            "adımları: docs/yangin-modeli.md"
        )
    return p


def alarm_etiketi(olay: dict) -> str:
    """Kanıt karesine/uyarıya basılacak etiket — feragat ibaresi ZORUNLU."""
    sinif = str(olay.get("sinif", "?")).upper()
    return (f"{sinif}  {olay.get('dogrulama', 0)} kare / "
            f"{float(olay.get('sure', 0.0)):.1f} sn  |  {FERAGAT}")


def pencere_kare(fps: float, vid_stride: int, pencere_sn: float) -> int:
    """Doğrulama penceresine kaç İŞLENMİŞ kare sığar (kaynak fps'i değil)."""
    efektif = max(1.0, float(fps)) / max(1, int(vid_stride))
    return max(1, int(efektif * float(pencere_sn)))


def onay_olasiligi(kare_recall: float, kare: int, dogrulama: int) -> float:
    """P(en az `dogrulama` kare onaylar | `kare` bağımsız kare, kare-başına recall).

    Model metriğini ÜRÜN metriğine çeviren fonksiyon. Kareler bağımsız
    varsayılır; gerçekte ardışık kareler ilintilidir (aynı poz, aynı ışık),
    yani bu HAFİF İYİMSER bir üst sınırdır — eşik seçerken marj bırak.
    """
    p = min(1.0, max(0.0, float(kare_recall)))
    n, k = int(kare), int(dogrulama)
    if k <= 0:
        return 1.0
    if k > n:
        return 0.0
    # P(X >= k) = 1 - P(X <= k-1); küçük k için doğrudan toplam yeterli
    from math import comb

    kuyruk = sum(comb(n, i) * (p ** i) * ((1.0 - p) ** (n - i)) for i in range(k))
    return max(0.0, min(1.0, 1.0 - kuyruk))


def gereken_recall(kare: int, dogrulama: int, hedef: float = 0.95,
                   adim: float = 0.01) -> float:
    """Hedef onay olasılığı için gereken asgari kare-başına recall.

    Bu sayı `fire.conf` eşiğini yükseltme kararının dayanağıdır: gereken recall
    düşükse (tipik olarak %15'in altı) güven eşiğini yükseltip precision satın
    almak ürünü İYİLEŞTİRİR — mAP düşse bile. `adim` çözünürlüğüdür.
    """
    if int(dogrulama) > int(kare):
        return 1.0        # olanaksız: yanıltıcı düşük sayı dönmesin
    p = 0.0
    while p <= 1.0:
        if onay_olasiligi(p, kare, dogrulama) >= hedef:
            return round(p, 4)
        p += adim
    return 1.0


def _iou(a, b) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    kesisim = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    if kesisim <= 0:
        return 0.0
    birlesim = ((ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - kesisim)
    return kesisim / birlesim if birlesim > 0 else 0.0


def _piksel_poligonlar(bolgeler, w: int, h: int) -> list[list[tuple[float, float]]]:
    """Normalize poligonları piksele çevirir; 3 noktadan az olanı atar."""
    cikti = []
    for z in bolgeler or []:
        pts = z.get("points") or []
        if len(pts) >= 3:
            cikti.append([(p[0] * w, p[1] * h) for p in pts])
    return cikti


class DumanTakip:
    """Kareler arası duman/alev odaklarını izler; kademeli uyarı üretir.

    SAF mantık: cv2/torch/model bilmez, piksel kutu listesi alır. Böylece hattın
    asıl değeri (zamansal doğrulama) modelden bağımsız test edilebilir.
    """

    def __init__(self, w: int, h: int, *, pencere_sn: float = 6.0,
                 dogrulama_kare: int = 4, iou_baglama: float = 0.2,
                 alarm_sn: float = 3.0, cooldown_sn: float = 120.0,
                 bolgeler: list[dict] | None = None,
                 maskeler: list[dict] | None = None) -> None:
        self.pencere = float(pencere_sn)
        self.dogrulama = int(dogrulama_kare)
        self.iou_baglama = float(iou_baglama)
        self.alarm_sn = float(alarm_sn)
        self.cooldown = float(cooldown_sn)
        # İzleme bölgesi: TANIMLIYSA yalnız içi değerlendirilir (boşsa tüm kadraj).
        self.bolgeler = _piksel_poligonlar(bolgeler, w, h)
        # Maske: içine düşen tespit hiç değerlendirilmez (ISO/TS 7240-30).
        self.maskeler = _piksel_poligonlar(maskeler, w, h)
        self.odaklar: list[dict[str, Any]] = []
        self._sonraki_id = 1

    def _gecerli(self, kutu) -> bool:
        cx = (kutu[0] + kutu[2]) / 2.0
        cy = (kutu[1] + kutu[3]) / 2.0
        for m in self.maskeler:
            if point_in_poly(cx, cy, m):
                return False
        if self.bolgeler:
            return any(point_in_poly(cx, cy, b) for b in self.bolgeler)
        return True

    def _esle(self, kutu, sinif: str, kullanilan: set[int]):
        """Aynı sınıftan, en yüksek IoU'lu ve bu karede henüz kullanılmamış odak."""
        en_iyi, en_iou = None, self.iou_baglama
        for o in self.odaklar:
            if o["id"] in kullanilan or o["sinif"] != sinif:
                continue
            s = _iou(kutu, o["kutu"])
            if s >= en_iou:
                en_iyi, en_iou = o, s
        return en_iyi

    def guncelle(self, tespitler, ts: float) -> list[dict]:
        """tespitler: [(sinif, x1, y1, x2, y2, conf)] piksel. Yeni olayları döndürür.

        Dönen olaylar yalnız DURUM DEĞİŞİMLERİdir (ve cooldown dolmuş alarm
        tekrarları); her karede olay üretmez — aksi hâlde panel spam olur.
        """
        kullanilan: set[int] = set()
        for d in tespitler:
            sinif = SINIF_ADLARI.get(str(d[0]).lower(), str(d[0]).lower())
            kutu = (float(d[1]), float(d[2]), float(d[3]), float(d[4]))
            conf = float(d[5]) if len(d) > 5 else 0.0
            if not self._gecerli(kutu):
                continue
            o = self._esle(kutu, sinif, kullanilan)
            if o is None:
                o = {"id": self._sonraki_id, "sinif": sinif, "kutu": kutu,
                     "conf": conf, "vurus": deque(), "durum": "izle",
                     "onay_ts": 0.0, "son_alarm": -1e9}
                self._sonraki_id += 1
                self.odaklar.append(o)
            kullanilan.add(o["id"])
            o["kutu"] = kutu
            o["conf"] = conf
            o["vurus"].append(ts)

        olaylar: list[dict] = []
        for o in list(self.odaklar):
            # Pencereden düşen vuruşlar birikmemeli: seyrek tespit alarma yükselemez
            while o["vurus"] and ts - o["vurus"][0] > self.pencere:
                o["vurus"].popleft()
            if not o["vurus"]:
                self.odaklar.remove(o)      # odak söndü — durumu da gitsin
                continue
            olaylar += self._degerlendir(o, ts)
        return olaylar

    def _degerlendir(self, o: dict, ts: float) -> list[dict]:
        n = len(o["vurus"])
        if n < self.dogrulama:
            return []
        if o["durum"] == "izle":
            o["durum"] = "on_uyari"
            o["onay_ts"] = o["vurus"][0]     # doğrulamanın BAŞLADIĞI an
            return [self._olay(o, "on_uyari", ts, n)]
        if o["durum"] == "on_uyari" and ts - o["onay_ts"] >= self.alarm_sn:
            o["durum"] = "alarm"
            o["son_alarm"] = ts
            return [self._olay(o, "alarm", ts, n)]
        # Süren yangın sessizleşmesin: cooldown dolunca hatırlatılır
        if o["durum"] == "alarm" and ts - o["son_alarm"] >= self.cooldown:
            o["son_alarm"] = ts
            return [self._olay(o, "alarm", ts, n)]
        return []

    def _olay(self, o: dict, durum: str, ts: float, n: int) -> dict:
        return {"durum": durum, "sinif": o["sinif"], "odak_id": o["id"],
                "kutu": o["kutu"], "conf": round(o["conf"], 3),
                "dogrulama": n, "sure": round(ts - o["onay_ts"], 2),
                "ts_seconds": round(ts, 2)}


@dataclass
class FireResult:
    frames: int = 0
    fps: float = 0.0
    on_uyarilar: list[dict[str, Any]] = field(default_factory=list)
    alarmlar: list[dict[str, Any]] = field(default_factory=list)


def _ascii(s: str) -> str:
    """cv2 Hershey fontu Türkçe karakter basamaz → ASCII'ye çevir (count.py ile aynı)."""
    return (s or "").translate(str.maketrans("çğıİöşüÇĞÖŞÜ", "cgiIosuCGOSU"))


def _kaynak_olculeri(source: str, cfg) -> tuple[int, int, float]:
    """Kaynağı bir kez açıp (genişlik, yükseklik, fps) okur ve kapatır."""
    import cv2

    from . import akis

    cap = akis.ac(source, cfg)
    if not cap.isOpened():
        raise FileNotFoundError(f"Video açılamadı: {source}")
    try:
        return (int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                cap.get(cv2.CAP_PROP_FPS) or 25.0)
    finally:
        cap.release()


def _takip_kur(cfg, w: int, h: int, bolgeler, maskeler) -> DumanTakip:
    return DumanTakip(
        w, h,
        pencere_sn=cfg.get("fire.window_seconds", 6.0),
        dogrulama_kare=cfg.get("fire.confirm_frames", 4),
        iou_baglama=cfg.get("fire.iou_link", 0.2),
        alarm_sn=cfg.get("fire.alarm_seconds", 3.0),
        cooldown_sn=cfg.get("fire.cooldown_seconds", 120.0),
        bolgeler=bolgeler, maskeler=maskeler,
    )


def _tespitler(r) -> list[tuple]:
    """Ultralytics sonucunu (sinif, x1, y1, x2, y2, conf) listesine çevirir."""
    if r.boxes is None or not len(r.boxes):
        return []
    adlar = r.names or {}
    return [(adlar.get(int(cid), str(cid)), *kutu, c)
            for kutu, cid, c in zip(r.boxes.xyxy.tolist(),
                                    r.boxes.cls.int().tolist(),
                                    r.boxes.conf.tolist())]


def _alarm_kanitla(cfg, olay: dict, kare, halka, camera_id: str,
                   efektif_fps: float) -> None:
    """Alarma kanıt karesi + doğrulayan karelerin klibini iliştirir."""
    from .evidence import kaydet as kanit_kaydet
    from .evidence import klip_kaydet

    olay["snapshot"] = kanit_kaydet(cfg, kare, camera_id, "fire",
                                    box=olay["kutu"],
                                    etiket=_ascii(alarm_etiketi(olay)))
    olay["clip"] = klip_kaydet(cfg, list(halka), camera_id, "fire",
                               fps=efektif_fps)


def _tahmin_ayarlari(cfg, vid_stride: int) -> dict:
    """Ultralytics predict parametreleri. `.pt` + device=auto bilinçli tercih:
    TensorRT `.engine` GPU mimarisine özgüdür, GB10'da üretilen 3050'de yüklenmez
    (docs/yangin-modeli.md)."""
    from .device import select_device

    return {"conf": float(cfg.get("fire.conf", 0.35)),
            "imgsz": int(cfg.get("fire.imgsz", 640)),
            "vid_stride": vid_stride,
            "device": select_device(cfg.get("device", "auto"))}


def run_fire(source: str, cfg, store=None, camera_id: str = "",
             bolgeler: list[dict] | None = None, maskeler: list[dict] | None = None,
             on_event=None, on_alert=None, on_frame=None,
             should_stop: Callable[[], bool] | None = None) -> FireResult:
    """Kaynakta yangın/duman erken uyarısı koşar.

    `bolgeler` / `maskeler`: normalize poligonlar (zones tablosundan; kind
    'fire' ve 'firemask'). Bölge verilmezse tüm kadraj izlenir.
    """
    from . import akis
    from .detect import load_yolo

    model = str(model_yolu(cfg.get("fire.model", "models/fire.pt")))
    vid_stride = int(cfg.get("fire.vid_stride", cfg.get("detect.vid_stride", 3)))
    camera_id = camera_id or Path(source).stem
    w, h, fps = _kaynak_olculeri(source, cfg)
    takip = _takip_kur(cfg, w, h, bolgeler, maskeler)

    # İşlenen kare temposu — klip halkasının uzunluğu buna göre hesaplanır
    efektif_fps = max(1.0, fps / max(vid_stride, 1))
    halka: deque = deque(maxlen=max(2, int(cfg.get("fire.clip_seconds", 4.0)
                                           * efektif_fps)))

    yolo = load_yolo(model, cfg.get("device", "auto"), instance_key=camera_id)
    basliklar = akis.basliklarla(source, cfg)
    basliklar.__enter__()
    sonuc = FireResult(fps=fps)
    try:
        for r in yolo.predict(source=source, stream=True, verbose=False,
                              **_tahmin_ayarlari(cfg, vid_stride)):
            if should_stop is not None and should_stop():
                break
            sonuc.frames += 1
            kare = r.orig_img
            if kare is not None:
                halka.append(kare.copy())
            ts = (sonuc.frames * vid_stride) / fps
            for olay in takip.guncelle(_tespitler(r), ts):
                olay["camera_id"] = camera_id
                olay["frame_idx"] = sonuc.frames * vid_stride
                _yay(cfg, olay, sonuc, kare, halka, camera_id, efektif_fps,
                     store, on_event, on_alert)
            if on_frame is not None and kare is not None:
                on_frame(r.plot())
    finally:
        basliklar.__exit__()
        if store is not None:
            store.commit()
    return sonuc


def _yay(cfg, olay: dict, sonuc: FireResult, kare, halka, camera_id: str,
         efektif_fps: float, store, on_event, on_alert) -> None:
    """Ön uyarıyı panele, alarmı kanıt + uyarı kaydına dağıtır.

    Ön uyarıda kanıt YAZILMAZ: doğrulanmamış her tetikte disk yazmak hem KVKK
    açısından orantısız hem de saklama kotasını doğrulanmamış gürültüyle doldurur.
    """
    if olay["durum"] == "on_uyari":
        sonuc.on_uyarilar.append(olay)
        if on_event is not None:
            on_event(olay)
        return
    _alarm_kanitla(cfg, olay, kare, halka, camera_id, efektif_fps)
    sonuc.alarmlar.append(olay)
    if on_alert is not None:
        on_alert(olay)
    if store is not None:
        store.add_alert("fire_warning", olay["sinif"], "fire",
                        f"{olay['dogrulama']} kare / {olay['sure']} sn · {FERAGAT}",
                        camera_id, snapshot=olay["snapshot"])
