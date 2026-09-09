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


def _ortusme_orani(kutu, kisi) -> float:
    """Kesişim alanı / tespit kutusu alanı (IoU değil: küçük alev kutusu büyük
    kişi kutusunun içindeyse IoU düşük kalır, bu oran 1'e yaklaşır)."""
    x1 = max(kutu[0], kisi[0]); y1 = max(kutu[1], kisi[1])
    x2 = min(kutu[2], kisi[2]); y2 = min(kutu[3], kisi[3])
    kesisim = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    alan = max(1e-6, (kutu[2] - kutu[0]) * (kutu[3] - kutu[1]))
    return kesisim / alan


def kisi_bastir(tespitler, kisiler, oran: float = 0.5) -> list:
    """Kişi kutusuyla `oran` ve üstünde örtüşen alev/duman tespitlerini atar.

    Gerekçe (ölçüm 2026-09-07/08, kamera-210 ofis, 36 sahte alarm, 0 gerçek):
    dedektör kapıdan geçen kişinin kot pantolonunu "duman", parlak giysiyi
    "alev" sandı. Kişi üstünde yangın olmaz; sayım hattı zaten kişiyi
    biliyor. Yanan kişi senaryosu bilinçli kapsam dışı — o ölçekteki alev
    kişi kutusundan taşar ve bu oranın altında kalır.
    """
    if not kisiler or oran <= 0:
        return list(tespitler)
    kalan = []
    for d in tespitler:
        kutu = (float(d[1]), float(d[2]), float(d[3]), float(d[4]))
        if any(_ortusme_orani(kutu, k) >= oran for k in kisiler):
            continue
        kalan.append(d)
    return kalan


class DumanTakip:
    """Kareler arası duman/alev odaklarını izler; kademeli uyarı üretir.

    SAF mantık: cv2/torch/model bilmez, piksel kutu listesi alır. Böylece hattın
    asıl değeri (zamansal doğrulama) modelden bağımsız test edilebilir.
    """

    def __init__(self, w: int, h: int, *, pencere_sn: float = 6.0,
                 dogrulama_kare: int = 4, iou_baglama: float = 0.2,
                 alarm_sn: float = 3.0, cooldown_sn: float = 120.0,
                 bolgeler: list[dict] | None = None,
                 maskeler: list[dict] | None = None,
                 kisi_oran: float = 0.5) -> None:
        self.pencere = float(pencere_sn)
        self.dogrulama = int(dogrulama_kare)
        self.iou_baglama = float(iou_baglama)
        self.alarm_sn = float(alarm_sn)
        self.cooldown = float(cooldown_sn)
        # İzleme bölgesi: TANIMLIYSA yalnız içi değerlendirilir (boşsa tüm kadraj).
        self.bolgeler = _piksel_poligonlar(bolgeler, w, h)
        # Maske: içine düşen tespit hiç değerlendirilmez (ISO/TS 7240-30).
        self.maskeler = _piksel_poligonlar(maskeler, w, h)
        # Kişi bastırma: kişi kutusuyla bu oranda örtüşen alev/duman tespiti
        # değerlendirilmez. Ölçüm 2026-09-08 (kamera-210, ofis, 36 sahte alarm):
        # "duman" tespitlerinin tamamı kapıdan geçen kişilerin bacağı/kotu,
        # "alev"lerin çoğu kişi üstündeki parlak giysiydi. 0 = kapalı.
        self.kisi_oran = float(kisi_oran)
        self.odaklar: list[dict[str, Any]] = []
        self._sonraki_id = 1
        # KAMERA düzeyi alarm cooldown'u. Odak-başına cooldown yetmiyor: gerçek
        # yangında alev yer değiştirdikçe (IoU bağı kopar) her yeni odak kendi
        # alarmını üretiyordu — FURG mangal videosunda 30 sn'de 35 alarm (ölçüm
        # 2026-09-07). Aynı kamerada bir alarm verildikten sonra cooldown dolana
        # dek yeni odaklar alarm/ön uyarı YAYMAZ; hatırlatma tek odaktan gelir.
        self._kamera_son_alarm = -1e9

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

    def guncelle(self, tespitler, ts: float, kisiler=None) -> list[dict]:
        """tespitler: [(sinif, x1, y1, x2, y2, conf)] piksel. Yeni olayları döndürür.

        `kisiler`: aynı kadrajdaki kişi kutuları [(x1, y1, x2, y2)] piksel
        (sayım hattının YOLO çıktısı). Verilirse kişiyle örtüşen tespit atılır.

        Dönen olaylar yalnız DURUM DEĞİŞİMLERİdir (ve cooldown dolmuş alarm
        tekrarları); her karede olay üretmez — aksi hâlde panel spam olur.
        """
        if kisiler and self.kisi_oran > 0:
            tespitler = kisi_bastir(tespitler, kisiler, self.kisi_oran)
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
        sessiz = ts - self._kamera_son_alarm < self.cooldown   # kamera alarmda
        if o["durum"] == "izle":
            o["durum"] = "on_uyari"
            o["onay_ts"] = o["vurus"][0]     # doğrulamanın BAŞLADIĞI an
            return [] if sessiz else [self._olay(o, "on_uyari", ts, n)]
        if o["durum"] == "on_uyari" and ts - o["onay_ts"] >= self.alarm_sn:
            o["durum"] = "alarm"
            o["son_alarm"] = ts
            if sessiz:
                return []
            self._kamera_son_alarm = ts
            return [self._olay(o, "alarm", ts, n)]
        # Süren yangın sessizleşmesin: cooldown dolunca hatırlatılır
        if o["durum"] == "alarm" and ts - o["son_alarm"] >= self.cooldown and not sessiz:
            o["son_alarm"] = ts
            self._kamera_son_alarm = ts
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


def _kaynak_ac(source: str, cfg):
    """Akışı açar ve açık bırakır; (cap, genişlik, yükseklik, fps) döndürür.

    Akışı KENDİMİZ açıyoruz (ultralytics'in kendi çözücüsüne devretmiyoruz):
    kamera başına HTTP başlıkları `akis.ac` üzerinden doğru uygulanıyor ve
    kare temposunu biz kontrol ediyoruz.
    """
    import cv2

    from . import akis

    cap = akis.ac(source, cfg)
    if not cap.isOpened():
        raise FileNotFoundError(f"Video açılamadı: {source}")
    return (cap,
            int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            cap.get(cv2.CAP_PROP_FPS) or 25.0)


def _takip_kur(cfg, w: int, h: int, bolgeler, maskeler) -> DumanTakip:
    return DumanTakip(
        w, h,
        pencere_sn=cfg.get("fire.window_seconds", 6.0),
        dogrulama_kare=cfg.get("fire.confirm_frames", 4),
        iou_baglama=cfg.get("fire.iou_link", 0.2),
        alarm_sn=cfg.get("fire.alarm_seconds", 3.0),
        cooldown_sn=cfg.get("fire.cooldown_seconds", 120.0),
        bolgeler=bolgeler, maskeler=maskeler,
        kisi_oran=cfg.get("fire.person_overlap", 0.5),
    )


def _dedektor_kur(cfg):
    """Lisans kapısından geçmiş dedektörü kurar (varsayılan: Apache-2.0)."""
    from .dedektor import VARSAYILAN_MOTOR, yukle

    ham = cfg.get("fire.classes", {0: "smoke", 1: "fire"}) or {}
    adlar = {int(k): str(v) for k, v in dict(ham).items()}
    return yukle(motor=cfg.get("fire.engine", VARSAYILAN_MOTOR),
                 model=str(model_yolu(cfg.get("fire.model", "models/fire.pt"))),
                 adlar=adlar,
                 esik=float(cfg.get("fire.conf", 0.35)),
                 agpl_kabul=bool(cfg.get("fire.agpl_kabul", False)),
                 device_pref=cfg.get("device", "auto"))


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


def _karo_birlestir(tespitler: list[tuple], iou_esik: float = 0.5) -> list[tuple]:
    """Bindirmeli karolarda aynı nesne iki kez çıkar: aynı sınıf + IoU ≥ eşik → yüksek güvenli kalır."""
    sirali = sorted(tespitler, key=lambda t: -float(t[5]))
    kalan: list[tuple] = []
    for t in sirali:
        if any(t[0] == k[0] and _iou(t[1:5], k[1:5]) >= iou_esik for k in kalan):
            continue
        kalan.append(t)
    return kalan


def tespit_karolu(ded, kare, n: int, bindirme: float = 0.08) -> list[tuple]:
    """Kareyi n×n bindirmeli karoya böler, her karoyu ayrı geçirir, kutuları geri taşır.

    Neden: dedektör 512'ye küçültür; 2K kadrajda kovada yeni tutuşan alev ~10
    piksele iner ve ilk 10-15 sn GÖRÜLMEZ. Saha ölçümü (docs/olcumler-yangin-saha-
    2026-09-02.md): tek karede ilk alev tespiti tutuşmadan 14 sn sonra, 2×2 karoda
    3 sn sonra; tespitli kare oranı 100/550 → 349/550. Maliyet n² kat inference —
    yangın hattı zaten seyrek (stride) koştuğu için kabul edilebilir.
    """
    if n <= 1:
        return ded.tespit(kare)
    h, w = kare.shape[:2]
    kh, kw = h // n, w // n
    ph, pw = int(kh * bindirme), int(kw * bindirme)
    karolar, ofsetler = [], []
    for i in range(n):
        for j in range(n):
            y0, x0 = max(0, i * kh - ph), max(0, j * kw - pw)
            y1, x1 = min(h, (i + 1) * kh + ph), min(w, (j + 1) * kw + pw)
            karolar.append(kare[y0:y1, x0:x1])
            ofsetler.append((x0, y0))
    # Karolar tek çağrıda (batch) geçer — dedektör destekliyorsa; yoksa tek tek.
    coklu = getattr(ded, "tespit_coklu", None)
    sonuclar = coklu(karolar) if coklu else [ded.tespit(k) for k in karolar]
    out: list[tuple] = []
    for (x0, y0), tespitler in zip(ofsetler, sonuclar):
        for s, bx1, by1, bx2, by2, c in tespitler:
            out.append((s, bx1 + x0, by1 + y0, bx2 + x0, by2 + y0, c))
    return _karo_birlestir(out)


def _ciz(kare, tespitler) -> Any:
    """Canlı görünüm için tespitleri kareye çizer (ultralytics plot yerine)."""
    import cv2

    img = kare.copy()
    for sinif, x1, y1, x2, y2, conf in tespitler:
        cv2.rectangle(img, (int(x1), int(y1)), (int(x2), int(y2)), (0, 165, 255), 2)
        cv2.putText(img, f"{_ascii(sinif)} {conf:.2f}", (int(x1), max(14, int(y1) - 6)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 165, 255), 2)
    return img


class YanginHatti:
    """Kare-bazlı yangın hattı: dedektör + zamansal doğrulama + kanıt halkası.

    Kaynağı AÇMAZ — kareyi çağıran verir. İki çağrı yolu vardır: `run_fire`
    (dosya/RTSP'yi kendisi okur, CLI ve Test ekranı) ve akis motoru
    (`src/akis_motoru.py`, kareyi donanım çözücüden alır; ana akış NVDEC'te
    çözülür, CPU'ya tam çözünürlük decode yükü binmez — 2026-09-05 denetiminin
    sebebi buydu). Mantık tek yerde kalsın diye ikisi de bu sınıfı kullanır.
    """

    def __init__(self, cfg, ded, w: int, h: int, camera_id: str, efektif_fps: float,
                 bolgeler=None, maskeler=None, store=None,
                 on_event=None, on_alert=None) -> None:
        self.cfg = cfg
        self.ded = ded
        self.camera_id = camera_id
        self.karo = int(cfg.get("fire.tiles", 1))   # 2 = 2×2 karo (erken/küçük alev için)
        self.takip = _takip_kur(cfg, w, h, bolgeler, maskeler)
        self.efektif_fps = max(1.0, float(efektif_fps))
        self.halka: deque = deque(maxlen=max(2, int(cfg.get("fire.clip_seconds", 4.0)
                                                    * self.efektif_fps)))
        self.sonuc = FireResult(fps=efektif_fps)
        self.store = store
        self.on_event = on_event
        self.on_alert = on_alert

    def kare(self, bgr, ts: float, frame_idx: int, kisiler=None) -> list[tuple]:
        """Bir kareyi işler; tespitleri (sinif, x1, y1, x2, y2, conf) döndürür.

        `kisiler`: kadrajdaki kişi kutuları (piksel) — sayım hattından gelir,
        kişiyle örtüşen tespit bastırılır (`kisi_bastir`). Dönen liste
        bastırma SONRASIdır: panel, kişi üstündeki sahte kutuyu da görmesin.
        """
        self.sonuc.frames += 1
        self.halka.append(bgr.copy())
        tespitler = tespit_karolu(self.ded, bgr, self.karo)
        if kisiler and self.takip.kisi_oran > 0:
            tespitler = kisi_bastir(tespitler, kisiler, self.takip.kisi_oran)
        for olay in self.takip.guncelle(tespitler, ts):
            olay["camera_id"] = self.camera_id
            olay["frame_idx"] = frame_idx
            _yay(self.cfg, olay, self.sonuc, bgr, self.halka, self.camera_id,
                 self.efektif_fps, self.store, self.on_event, self.on_alert)
        return tespitler


def run_fire(source: str, cfg, store=None, camera_id: str = "",
             bolgeler: list[dict] | None = None, maskeler: list[dict] | None = None,
             on_event=None, on_alert=None, on_frame=None,
             should_stop: Callable[[], bool] | None = None) -> FireResult:
    """Kaynakta yangın/duman erken uyarısı koşar.

    `bolgeler` / `maskeler`: normalize poligonlar (zones tablosundan; kind
    'fire' ve 'firemask'). Bölge verilmezse tüm kadraj izlenir.
    """
    vid_stride = max(1, int(cfg.get("fire.vid_stride",
                                    cfg.get("detect.vid_stride", 3))))
    camera_id = camera_id or Path(source).stem
    ded = _dedektor_kur(cfg)
    cap, w, h, fps = _kaynak_ac(source, cfg)
    # İşlenen kare temposu — klip halkasının uzunluğu buna göre hesaplanır
    hat = YanginHatti(cfg, ded, w, h, camera_id, fps / vid_stride,
                      bolgeler, maskeler, store, on_event, on_alert)
    ham_idx = 0
    try:
        while should_stop is None or not should_stop():
            okundu, kare = cap.read()
            if not okundu:
                break
            ham_idx += 1
            if ham_idx % vid_stride:
                continue          # stride: her N karede bir analiz
            tespitler = hat.kare(kare, ham_idx / fps, ham_idx)
            if on_frame is not None:
                on_frame(_ciz(kare, tespitler))
    finally:
        cap.release()
        if store is not None:
            store.commit()
    return hat.sonuc


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
