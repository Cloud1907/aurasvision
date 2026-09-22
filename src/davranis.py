"""Davranış tespiti — telefon kullanımı ve sigara içme (poz sezgiseli + nesne doğrulama).

Neden ayrı bir modül: yangın gibi bu da "tek karede karar verilemeyen" bir iştir.
Sigara birkaç piksel, telefon kulakta ele gizli; tek kare dedektörü sahada
kalem/bardak/saç düzeltmeyi alarm yapar. Literatürün işe yarayan yolu iki
katmanlıdır (SPIE 2025 anahtar-nokta + YOLOv8; GD-YOLO 2024; TACR-YOLO/PABD
2025 — docs/davranis-tespiti.md):

  1. POZ SEZGİSELİ — insan anahtar noktalarından (COCO-17) el-kulak ve
     el-ağız ilişkisi, ZAMAN içinde:
       telefon : bir el kulakta, `telefon_sn` boyunca kesintisiz
       sigara  : el ağza `sigara_tekrar` kez gidip geliyor (`sigara_pencere_sn`)
  2. NESNE DOĞRULAMA — aday üstünde küçük dedektör:
       telefon : COCO "cell phone" (67) kutusu başın yakınında (stok ağırlık,
                 ek eğitim yok; akis motorunda sayım batch'inden bedava gelir)
       sigara  : ayrı sigara ağırlığı (`davranis.sigara_model`, ör. Beehzod
                 yolo11m, MIT) baş kırpması üzerinde — isteğe bağlı

Kademeler yangınla aynı: `izle → on_uyari → alarm`. Ön uyarı yalnız panel;
alarm kanıt karesi + klip + uyarı satırı + webhook. Doğrulama kipi
(`davranis.*_dogrulama`): "tercih" = doğrulayan kutu varsa hemen alarm, yoksa
sezgisel tek başına daha uzun sürerse (telefon 3×, sigara bir nefes daha) alarm; "zorunlu" = kutu olmadan alarm YOK;
"kapali" = yalnız sezgisel.

KVKK: bu modül KİŞİ davranışı izler. Kanıt karesi kişiyi içerir; tür bazında
`evidence.davranis` ile kapatılır, saklama `evidence.keep_days`. Yüz
embedding'i ÜRETİLMEZ, kimlik eşlemesi yapılmaz — yalnız "biri, şurada,
şu kadar süre" bilgisi.

Lisans: poz modeli Ultralytics YOLO11-pose (AGPL-3.0) — sayım/plaka/yüz
hatlarıyla aynı motor, aynı hukuki durum (src/dedektor.py başlığı). Ayrı
motor kararı verilirse `_poz_kur` tek değişecek yerdir.

Sınır (baştan söylenir): geniş açılı koridor kamerasında baş 30 pikselin
altına düşünce bilek-kulak mesafesi gürültüye gömülür; `min_bas_px` altındaki
kişi değerlendirilmez. Kişi kameraya yakın olmalı (kapı, kasa, sigara yasağı
olan koridor ağzı).
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

_ROOT = Path(__file__).resolve().parent.parent

# COCO-17 anahtar nokta indeksleri
BURUN, GOZ_SOL, GOZ_SAG, KULAK_SOL, KULAK_SAG = 0, 1, 2, 3, 4
OMUZ_SOL, OMUZ_SAG, DIRSEK_SOL, DIRSEK_SAG, BILEK_SOL, BILEK_SAG = 5, 6, 7, 8, 9, 10

SINIFLAR = ("telefon", "sigara")   # her biri AYRI görev anahtarı ve AYRI alarm türüdür
ETIKETLER = {"telefon": "telefon kullanımı", "sigara": "sigara içme"}


def aktif_siniflar(tasks: dict | None) -> tuple[str, ...]:
    """Kamera görevlerinden bu hattın izleyeceği sınıflar ('telefon', 'sigara')."""
    return tuple(s for s in SINIFLAR if (tasks or {}).get(s))
COCO_TELEFON = 67   # stok COCO ağırlığında "cell phone"


# ───────────────────────── geometri ─────────────────────────

def _uzak(a, b) -> float:
    return float(((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5)


def bas_olcegi(kp, kc, kutu, esik: float = 0.3) -> float:
    """Baş ölçeği (piksel) — birkaç ölçünün EN BÜYÜĞÜ.

    Her ölçü perspektifte yalnız KÜÇÜLEBİLİR (profilde kulaklar arası ve omuz
    genişliği sıfıra iner, burun-omuz mesafesi kalır); bu yüzden en büyüğü
    gerçeğe en yakındır. Ölçüldü (docs/davranis-tespiti.md): önden bakışta
    kulaklar arası, profilde burun→omuz ortası×0,6 kazanıyor.
    """
    adaylar = []
    if kc[KULAK_SOL] > esik and kc[KULAK_SAG] > esik:
        adaylar.append(_uzak(kp[KULAK_SOL], kp[KULAK_SAG]))
    if kc[GOZ_SOL] > esik and kc[GOZ_SAG] > esik:
        adaylar.append(_uzak(kp[GOZ_SOL], kp[GOZ_SAG]) * 1.6)
    omuzlar = [kp[i] for i in (OMUZ_SOL, OMUZ_SAG) if kc[i] > esik]
    if len(omuzlar) == 2:
        adaylar.append(_uzak(omuzlar[0], omuzlar[1]) * 0.28)
    if kc[BURUN] > esik and omuzlar:
        mid = ((omuzlar[0][0] + omuzlar[-1][0]) / 2, (omuzlar[0][1] + omuzlar[-1][1]) / 2)
        adaylar.append(_uzak(kp[BURUN], mid) * 0.6)
    bas = max(adaylar) if adaylar else 0.0
    return bas if bas > 2 else max(4.0, (kutu[3] - kutu[1]) * 0.1)


def ozellikler(kp, kc, kutu, esik: float = 0.3,
               kulak_oran: float = 0.8, agiz_oran: float = 1.4, ignore_wrists=()) -> dict:
    """Bir kişinin tek karedeki poz özellikleri.

    Döner: {bas: px, kulak: bool, agiz: bool, bas_kutu: (x1,y1,x2,y2)}

    Gerçek geometri (Pexels örnekleriyle ölçüldü, docs/davranis-tespiti.md):
      * Telefon kulaktayken BİLEK kulakta değil, kulağın ~1,2 baş ALTINDA ve yüzün
        YAN tarafındadır (çene/boyun hizası); dirsek bileğin altındadır.
      * Sigara nefesinde bilek ağız tahmininin ~1 baş çevresindedir.
    Buna göre:
      kulak : "telefon pozu" — bilek en yakın kulağın altında (0,5–2,0 baş),
              yatayda kulağa `kulak_oran` baştan yakın, burun hizasından en az
              0,3 baş dışarıda (çeneye dayanan el sayılmaz), dirsek bilekten aşağıda.
      agiz  : bilek tahmini ağız noktasına (burnun 0,5 baş altı) `agiz_oran`
              baştan yakın ve omuz hizasının çok altında değil.
    İkisi bağımsızdır; ayrım ZAMANLA yapılır (telefon: kesintisiz, sigara: gidip gelen).
    """
    bas = bas_olcegi(kp, kc, kutu, esik)
    burun_ok = kc[BURUN] > esik
    kulaklar = [kp[i] for i in (KULAK_SOL, KULAK_SAG) if kc[i] > esik]
    oy = [kp[i][1] for i in (OMUZ_SOL, OMUZ_SAG) if kc[i] > esik]
    omuz_y = sum(oy) / len(oy) if oy else None
    agiz_pt = (kp[BURUN][0], kp[BURUN][1] + 0.5 * bas) if burun_ok else None
    kulak = agiz = False
    for b, d in ((BILEK_SOL, DIRSEK_SOL), (BILEK_SAG, DIRSEK_SAG)):
        if kc[b] <= esik or b in ignore_wrists:
            continue
        w = kp[b]
        if omuz_y is not None and w[1] > omuz_y + 0.6 * bas:
            continue            # el gövdede: ne telefon ne sigara
        dirsek_ok = kc[d] <= esik or kp[d][1] > w[1] + 0.2 * bas
        if kulaklar and dirsek_ok:
            k = min(kulaklar, key=lambda q: _uzak(q, w))
            dx, dy = (w[0] - k[0]) / bas, (w[1] - k[1]) / bas
            yanda = not burun_ok or abs(w[0] - kp[BURUN][0]) >= 0.3 * bas
            if abs(dx) < kulak_oran and 0.5 <= dy <= 2.0 and yanda:
                kulak = True
        if agiz_pt is not None and _uzak(w, agiz_pt) < agiz_oran * bas:
            agiz = True
    # Baş kutusu: doğrulayıcı dedektörlerin bakacağı bölge (burun merkezli)
    if burun_ok:
        cx, cy = kp[BURUN]
    else:
        cx, cy = (kutu[0] + kutu[2]) / 2, kutu[1] + bas
    r = 1.6 * bas
    bas_kutu = (cx - r, cy - r, cx + r, cy + 1.6 * r)
    return {"bas": bas, "kulak": kulak, "agiz": agiz, "bas_kutu": bas_kutu}


def _iou(a, b) -> float:
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua > 0 else 0.0


def _kesisir(kutu, alan, oran: float = 0.5) -> bool:
    """`kutu`nun en az `oran`ı `alan` içinde mi (küçük nesne büyük bölgede)."""
    ix1, iy1 = max(kutu[0], alan[0]), max(kutu[1], alan[1])
    ix2, iy2 = min(kutu[2], alan[2]), min(kutu[3], alan[3])
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    a = max(1e-6, (kutu[2] - kutu[0]) * (kutu[3] - kutu[1]))
    return inter / a >= oran


# ───────────────────────── zamansal karar ─────────────────────────

class _Iz:
    """Bir kişinin izi: kutu, özellik geçmişi, davranış durumları."""
    __slots__ = ("id", "kutu", "son_ts", "gecmis", "durum", "baslangic", "son_alarm",
                 "dokunus", "agiz_giris", "dogrulama", "bas_kutu", "son_dogrulama_ts")

    def __init__(self, tid: int, kutu, ts: float) -> None:
        self.id = tid
        self.kutu = kutu
        self.son_ts = ts
        self.gecmis: deque = deque()          # (ts, kulak, agiz)
        self.durum = {s: "izle" for s in SINIFLAR}
        self.baslangic = {s: None for s in SINIFLAR}   # on_uyari anı
        self.son_alarm = {s: -1e9 for s in SINIFLAR}
        self.dokunus: deque = deque()         # ağza gidiş anları (sigara)
        self.agiz_giris: float | None = None  # şu anki ağız temasının başlangıcı
        self.dogrulama = {s: None for s in SINIFLAR}   # (ts, kaynak) son pozitif doğrulama
        self.bas_kutu = None
        self.son_dogrulama_ts = -1e9


@dataclass
class DavranisResult:
    frames: int = 0
    fps: float = 0.0
    on_uyarilar: list[dict[str, Any]] = field(default_factory=list)
    alarmlar: list[dict[str, Any]] = field(default_factory=list)
    kisiler_max: int = 0


class DavranisTakip:
    """Kişi izleme + poz özelliklerinin zamansal değerlendirmesi. Model bilmez.

    Girdi: her kare için [(kutu, kp[17][2], kc[17])] listesi ve isteğe bağlı
    doğrulayıcı kutular. Çıktı: durum değişimi olayları (on_uyari/alarm).
    Basit IoU eşleme yeter: kişi sayısı az, hareket yavaş (konuşan/içen durur).
    """

    def __init__(self, *, telefon_sn: float = 4.0, telefon_oran: float = 0.7,
                 sigara_tekrar: int = 2, sigara_pencere_sn: float = 40.0,
                 dokunus_min_sn: float = 0.3, dokunus_max_sn: float = 6.0,
                 telefon_dogrulama: str = "tercih", sigara_dogrulama: str = "tercih",
                 dogrulama_taze_sn: float = 5.0,
                 cooldown_sn: float = 120.0, kamera_cooldown_sn: float = 30.0,
                 kayip_sn: float = 2.0, iou_esle: float = 0.3,
                 min_bas_px: float = 24.0, kp_esik: float = 0.3,
                 kulak_oran: float = 0.8, agiz_oran: float = 1.4,
                 siniflar=SINIFLAR, telefon_poz_kat: float = 3.0) -> None:
        self.siniflar = tuple(s for s in SINIFLAR if s in siniflar)
        self.telefon_sn = float(telefon_sn)
        self.telefon_poz_kat = float(telefon_poz_kat)
        self.telefon_oran = float(telefon_oran)
        self.sigara_tekrar = int(sigara_tekrar)
        self.sigara_pencere_sn = float(sigara_pencere_sn)
        self.dokunus_min_sn = float(dokunus_min_sn)
        self.dokunus_max_sn = float(dokunus_max_sn)
        self.dogrulama = {"telefon": telefon_dogrulama, "sigara": sigara_dogrulama}
        self.dogrulama_taze_sn = float(dogrulama_taze_sn)
        self.cooldown_sn = float(cooldown_sn)
        self.kamera_cooldown_sn = float(kamera_cooldown_sn)
        self.kayip_sn = float(kayip_sn)
        self.iou_esle = float(iou_esle)
        self.min_bas_px = float(min_bas_px)
        self.kp_esik = float(kp_esik)
        self.kulak_oran = float(kulak_oran)
        self.agiz_oran = float(agiz_oran)
        self.izler: dict[int, _Iz] = {}
        self._sonraki_id = 1
        self.kamera_son_alarm = {s: -1e9 for s in SINIFLAR}

    # --- eşleme ---
    def _esle(self, kisiler, ts: float) -> list[tuple[_Iz, Any]]:
        for tid in [t for t, iz in self.izler.items() if ts - iz.son_ts > self.kayip_sn]:
            del self.izler[tid]
        adaylar = sorted(((_iou(iz.kutu, k[0]), tid, i) for tid, iz in self.izler.items()
                          for i, k in enumerate(kisiler)), reverse=True)
        kullanilan_iz, kullanilan_kisi, ciftler = set(), set(), []
        for sc, tid, i in adaylar:
            if sc < self.iou_esle or tid in kullanilan_iz or i in kullanilan_kisi:
                continue
            kullanilan_iz.add(tid); kullanilan_kisi.add(i)
            ciftler.append((self.izler[tid], kisiler[i]))
        for i, k in enumerate(kisiler):
            if i in kullanilan_kisi:
                continue
            iz = _Iz(self._sonraki_id, k[0], ts)
            self._sonraki_id += 1
            self.izler[iz.id] = iz
            ciftler.append((iz, k))
        return ciftler

    # --- ana güncelleme ---
    def guncelle(self, kisiler, ts: float, telefon_kutular=None,
                 sigara_kontrol: Callable[[_Iz], bool] | None = None) -> list[dict]:
        """Bir kare işler; durum değişimlerini olay listesi olarak döndürür.

        `kisiler`: [(kutu, kp, kc)] — kutu piksel (x1,y1,x2,y2), kp 17×2, kc 17.
        `telefon_kutular`: bu kareye yakın COCO telefon kutuları (piksel) veya None.
        `sigara_kontrol(iz)`: ağız teması sırasında çağrılır; True = sigara görüldü.
        """
        olaylar: list[dict] = []
        for iz, (kutu, kp, kc) in self._esle(kisiler, ts):
            iz.kutu = kutu
            iz.son_ts = ts
            oz = ozellikler(kp, kc, kutu, self.kp_esik, self.kulak_oran, self.agiz_oran)
            iz.bas_kutu = oz["bas_kutu"]
            if oz["bas"] < self.min_bas_px:
                continue            # çok uzak: sezgisel gürültüde, değerlendirme
            # Telefonun kulakta olması şart değil; kişinin elinde nesne olarak
            # doğrulanması gerekir. Masadaki/komşu kişideki telefon kabul edilmez.
            telefon_eller = set()
            for tk in telefon_kutular or ():
                if not _kesisir(tk, kutu):
                    continue
                for wrist in (BILEK_SOL, BILEK_SAG):
                    if kc[wrist] <= self.kp_esik:
                        continue
                    x, y = kp[wrist]
                    dx = max(tk[0] - x, 0, x - tk[2])
                    dy = max(tk[1] - y, 0, y - tk[3])
                    if (dx * dx + dy * dy) ** 0.5 <= oz["bas"] * 0.9:
                        telefon_eller.add(wrist)
            iz.gecmis.append((ts, oz["kulak"] or bool(telefon_eller), oz["agiz"]))
            ufuk = ts - max(self.telefon_sn * 2.5, self.sigara_pencere_sn)
            while iz.gecmis and iz.gecmis[0][0] < ufuk:
                iz.gecmis.popleft()
            # doğrulayıcılar
            if telefon_kutular:
                if telefon_eller or any(_kesisir(tk, iz.bas_kutu) for tk in telefon_kutular):
                    iz.dogrulama["telefon"] = (ts, "telefon kutusu")
            # Telefon pozundaki el ağız yarıçapına da girer: o karede dokunuş sayılmaz
            sig_oz = ozellikler(kp, kc, kutu, self.kp_esik, self.kulak_oran,
                               self.agiz_oran, ignore_wrists=telefon_eller)
            self._sigara_dokunus(iz, sig_oz["agiz"] and not sig_oz["kulak"], ts, sigara_kontrol)
            olaylar += self._degerlendir(iz, ts)
        return olaylar

    def _sigara_dokunus(self, iz: _Iz, agiz: bool, ts: float, kontrol) -> None:
        if agiz:
            if iz.agiz_giris is None:
                iz.agiz_giris = ts
            # temas sırasında en fazla 0,5 sn'de bir doğrulayıcıya sor
            if kontrol is not None and ts - iz.son_dogrulama_ts >= 0.5:
                iz.son_dogrulama_ts = ts
                try:
                    if kontrol(iz):
                        iz.dogrulama["sigara"] = (ts, "sigara dedektörü")
                except Exception:
                    pass
        elif iz.agiz_giris is not None:
            sure = ts - iz.agiz_giris
            iz.agiz_giris = None
            if self.dokunus_min_sn <= sure <= self.dokunus_max_sn:
                iz.dokunus.append(ts)
        while iz.dokunus and iz.dokunus[0] < ts - self.sigara_pencere_sn:
            iz.dokunus.popleft()

    def _telefon_adayi(self, iz: _Iz, ts: float) -> tuple[bool, float]:
        pencere = [g for g in iz.gecmis if g[0] >= ts - self.telefon_sn]
        if len(pencere) < 3 or ts - pencere[0][0] < self.telefon_sn * 0.8:
            return False, 0.0
        oran = sum(1 for g in pencere if g[1]) / len(pencere)
        return oran >= self.telefon_oran, oran

    def _sigara_adayi(self, iz: _Iz, ts: float) -> tuple[bool, float]:
        n = len(iz.dokunus) + (1 if iz.agiz_giris is not None else 0)
        return n >= self.sigara_tekrar, min(1.0, n / max(1, self.sigara_tekrar))

    def _degerlendir(self, iz: _Iz, ts: float) -> list[dict]:
        olaylar = []
        for sinif in self.siniflar:
            aday, skor = (self._telefon_adayi if sinif == "telefon" else self._sigara_adayi)(iz, ts)
            d = iz.dogrulama[sinif]
            dogrulandi = d is not None and ts - d[0] <= self.dogrulama_taze_sn
            kip = self.dogrulama[sinif]
            durum = iz.durum[sinif]
            if not aday:
                if durum != "izle" and (sinif == "telefon" or iz.agiz_giris is None):
                    # telefon: el indi → sıfırla. sigara: temas sürüyorsa bekle.
                    iz.durum[sinif] = "izle"; iz.baslangic[sinif] = None
                continue
            if durum == "izle":
                if ts - iz.son_alarm[sinif] < self.cooldown_sn:
                    continue
                iz.durum[sinif] = "on_uyari"; iz.baslangic[sinif] = ts
                olaylar.append(self._olay(iz, sinif, "on_uyari", ts, skor,
                                          d[1] if dogrulandi else "poz"))
                durum = "on_uyari"
            if durum == "on_uyari":
                sure = ts - (iz.baslangic[sinif] or ts)
                if kip == "zorunlu":
                    alarm = dogrulandi
                elif kip == "kapali":
                    alarm = sure >= self.telefon_sn if sinif == "telefon" else True
                else:   # tercih
                    if sinif == "telefon":
                        # Kutu yoksa poz tek başına 3× süre ister: sigara içerken yüze
                        # yaslanan el 8 sn'de sahte telefon alarmı üretti (balkon klibi)
                        alarm = dogrulandi or sure >= self.telefon_sn * self.telefon_poz_kat
                    else:
                        # doğrulayıcı yoksa bir nefes daha (tekrar+1) ya da yarım pencere
                        n_dok = len(iz.dokunus) + (1 if iz.agiz_giris is not None else 0)
                        alarm = dogrulandi or n_dok >= self.sigara_tekrar + 1                             or sure >= self.sigara_pencere_sn * 0.5
                if alarm and ts - self.kamera_son_alarm[sinif] >= self.kamera_cooldown_sn:
                    iz.durum[sinif] = "alarm"
                    iz.son_alarm[sinif] = ts
                    self.kamera_son_alarm[sinif] = ts
                    olaylar.append(self._olay(iz, sinif, "alarm", ts, max(skor, 0.9 if dogrulandi else skor),
                                              d[1] if dogrulandi else "poz",
                                              sure=sure))
        return olaylar

    def _olay(self, iz: _Iz, sinif: str, durum: str, ts: float, skor: float,
              kaynak: str, sure: float = 0.0) -> dict:
        return {"sinif": sinif, "durum": durum, "conf": round(float(skor), 2),
                "kutu": tuple(float(v) for v in iz.kutu), "track_id": iz.id,
                "dogrulama": kaynak, "sure": round(float(sure), 1),
                "ts_seconds": round(ts, 2)}

    def etiketler(self) -> dict[int, str]:
        """iz id → panel etiketi ('telefon', 'sigara?', ...). Yalnız aktif olanlar."""
        out = {}
        for tid, iz in self.izler.items():
            for s in SINIFLAR:
                if iz.durum[s] == "alarm":
                    out[tid] = s
                    break
                if iz.durum[s] == "on_uyari":
                    out[tid] = s + "?"
        return out


# ───────────────────────── modeller ─────────────────────────

def _poz_kur(cfg):
    """YOLO11-pose yükler; (bgr) → [(kutu, kp, kc)] döndüren çağrılabilir verir."""
    from ultralytics import YOLO
    from .device import select_device

    yol = str(cfg.get("davranis.pose_model", "weights/yolo11n-pose.pt"))
    p = Path(yol)
    if not p.is_absolute() and not p.exists():
        p2 = _ROOT / yol
        if p2.exists() or p2.parent.exists():
            p = p2
    model = YOLO(str(p))     # yoksa ultralytics resmi ağırlığı bu yola indirir
    device = select_device(cfg.get("device", "auto"))
    imgsz = int(cfg.get("davranis.imgsz", 640))
    conf = float(cfg.get("davranis.conf", 0.4))

    def poz(bgr):
        r = model.predict(bgr, imgsz=imgsz, conf=conf, device=device, verbose=False)[0]
        if r.keypoints is None or r.boxes is None or len(r.boxes) == 0:
            return []
        kutular = r.boxes.xyxy.cpu().numpy()
        kps = r.keypoints.xy.cpu().numpy()
        kcs = r.keypoints.conf
        kcs = kcs.cpu().numpy() if kcs is not None else [[1.0] * 17] * len(kutular)
        return [(tuple(float(v) for v in kutular[i]), kps[i], kcs[i]) for i in range(len(kutular))]
    return poz


def _sigara_kur(cfg):
    """İsteğe bağlı sigara dedektörü: (bgr_kirpma) → bool. Ağırlık yoksa None (hat çalışır)."""
    yol = cfg.get("davranis.sigara_model", "") or ""
    if not yol:
        return None
    p = Path(yol)
    if not p.is_absolute():
        p = _ROOT / yol
    if not p.exists():
        print(f"[davranis] sigara modeli yok: {p} — yalnız poz sezgiseliyle devam", flush=True)
        return None
    from ultralytics import YOLO
    from .device import select_device
    model = YOLO(str(p))
    device = select_device(cfg.get("device", "auto"))
    esik = float(cfg.get("davranis.sigara_conf", 0.35))
    imgsz = int(cfg.get("davranis.sigara_imgsz", 320))

    def kontrol(bgr):
        if bgr is None or bgr.size == 0:
            return False
        r = model.predict(bgr, imgsz=imgsz, conf=esik, device=device, verbose=False)[0]
        return r.boxes is not None and len(r.boxes) > 0
    return kontrol


def _telefon_kur(cfg):
    """Canlı ve dosya yolunda stok COCO dedektörü: kişi kırpması → telefon kutuları."""
    if str(cfg.get("davranis.telefon_dogrulama", "tercih")) == "kapali":
        return None
    from ultralytics import YOLO
    from .device import select_device
    model = YOLO(str(cfg.get("detect.model", "yolo11s.pt")))
    device = select_device(cfg.get("device", "auto"))

    def telefonlar(bgr):
        r = model.predict(bgr, imgsz=int(cfg.get("detect.imgsz", 640)), conf=0.25,
                          classes=[COCO_TELEFON], device=device, verbose=False)[0]
        if r.boxes is None or len(r.boxes) == 0:
            return []
        return [tuple(float(v) for v in b) for b in r.boxes.xyxy.cpu().numpy()]
    return telefonlar


def _takip_kur(cfg, siniflar=SINIFLAR) -> DavranisTakip:
    g = lambda k, d: cfg.get(f"davranis.{k}", d)
    return DavranisTakip(
        siniflar=siniflar,
        telefon_poz_kat=g("telefon_poz_kat", 3.0),
        telefon_sn=g("telefon_sn", 4.0), telefon_oran=g("telefon_oran", 0.7),
        sigara_tekrar=g("sigara_tekrar", 2), sigara_pencere_sn=g("sigara_pencere_sn", 40.0),
        dokunus_min_sn=g("dokunus_min_sn", 0.3), dokunus_max_sn=g("dokunus_max_sn", 6.0),
        telefon_dogrulama=str(g("telefon_dogrulama", "tercih")),
        sigara_dogrulama=str(g("sigara_dogrulama", "tercih")),
        dogrulama_taze_sn=g("dogrulama_taze_sn", 5.0),
        cooldown_sn=g("cooldown_seconds", 120.0),
        kamera_cooldown_sn=g("camera_cooldown_seconds", 30.0),
        kayip_sn=g("kayip_sn", 2.0), min_bas_px=g("min_bas_px", 24.0),
        kp_esik=g("kp_conf", 0.3), kulak_oran=g("kulak_oran", 0.8), agiz_oran=g("agiz_oran", 1.4),
    )


# ───────────────────────── hat ─────────────────────────

def _ascii(s: str) -> str:
    return (s or "").translate(str.maketrans("çğıİöşüÇĞÖŞÜ", "cgiIosuCGOSU"))


def alarm_etiketi(o: dict) -> str:
    return (f"{ETIKETLER.get(o['sinif'], o['sinif'])} · {o.get('sure', 0)} sn · "
            f"doğrulama: {o.get('dogrulama', 'poz')}")


class DavranisHatti:
    """Kare-bazlı davranış hattı: poz + takip + doğrulama + kanıt halkası.

    Kaynağı AÇMAZ; `run_davranis` (dosya/RTSP, Test ekranı) ve akis motoru
    (`_DavranisKademe`) aynı sınıfı kullanır — yangın hattıyla aynı ilke.
    `poz` çağrılabilir dışarıdan verilebilir (testler sahte poz geçer).
    """

    def __init__(self, cfg, w: int, h: int, camera_id: str, efektif_fps: float,
                 *, poz=None, sigara=None, telefon=None, store=None, on_event=None, on_alert=None,
                 siniflar=SINIFLAR) -> None:
        self.cfg = cfg
        self.w, self.h = w, h
        self.camera_id = camera_id
        self.poz = poz or _poz_kur(cfg)
        self.sigara = sigara if "sigara" in siniflar else None
        self.telefon = telefon if "telefon" in siniflar else None
        self._telefon_ts = -1e9
        self._telefon_boxes = []
        self.siniflar = tuple(siniflar)
        self.takip = _takip_kur(cfg, siniflar)
        self.efektif_fps = max(1.0, float(efektif_fps))
        self.halka: deque = deque(maxlen=max(2, int(cfg.get("davranis.clip_seconds", 5.0)
                                                    * self.efektif_fps)))
        self.sonuc = DavranisResult(fps=efektif_fps)
        self.store = store
        self.on_event = on_event
        self.on_alert = on_alert

    def _sigara_kontrol(self, bgr):
        if self.sigara is None:
            return None

        def kontrol(iz) -> bool:
            x1, y1, x2, y2 = iz.bas_kutu
            x1, y1 = max(0, int(x1)), max(0, int(y1))
            x2, y2 = min(self.w, int(x2)), min(self.h, int(y2))
            if x2 - x1 < 8 or y2 - y1 < 8:
                return False
            return bool(self.sigara(bgr[y1:y2, x1:x2]))
        return kontrol

    def kare(self, bgr, ts: float, frame_idx: int, telefon_kutular=None) -> list[tuple]:
        """Bir kareyi işler; kişileri (etiket, x1, y1, x2, y2, conf) olarak döndürür.

        etiket: 'kisi' | 'telefon?' | 'telefon' | 'sigara?' | 'sigara'
        """
        self.sonuc.frames += 1
        self.halka.append(bgr.copy())
        kisiler = self.poz(bgr)
        # Tam karede kaybolan küçük telefonu kişi kırpmasında ara. Çağrı sayısı
        # kamera başına saniyede bir, en büyük altı kişiyle sınırlıdır.
        interval = max(0.25, float(self.cfg.get("davranis.telefon_aralik_sn", 1.0)))
        if self.telefon is not None and ts - self._telefon_ts >= interval:
            self._telefon_boxes = []
            self._telefon_ts = ts
            for box, _, _ in sorted(kisiler, key=lambda p: (p[0][2]-p[0][0])*(p[0][3]-p[0][1]), reverse=True)[:6]:
                x1, y1, x2, y2 = box
                dx, dy = (x2 - x1) * 0.35, (y2 - y1) * 0.15
                x1, y1 = max(0, int(x1-dx)), max(0, int(y1-dy))
                x2, y2 = min(self.w, int(x2+dx)), min(self.h, int(y2+dy))
                if x2-x1 < 16 or y2-y1 < 16:
                    continue
                self._telefon_boxes.extend((a+x1, b+y1, c+x1, d+y1)
                                           for a,b,c,d in self.telefon(bgr[y1:y2, x1:x2]))
        boxes = list(telefon_kutular or ())
        if 0 <= ts - self._telefon_ts < interval:
            boxes.extend(self._telefon_boxes)
        self.sonuc.kisiler_max = max(self.sonuc.kisiler_max, len(kisiler))
        for o in self.takip.guncelle(kisiler, ts, boxes, self._sigara_kontrol(bgr)):
            o["camera_id"] = self.camera_id
            o["frame_idx"] = frame_idx
            self._yay(o, bgr)
        et = self.takip.etiketler()
        out = []
        for iz in self.takip.izler.values():
            if iz.son_ts != ts:
                continue
            out.append((et.get(iz.id, "kisi"), *iz.kutu, 1.0))
        return out

    def _yay(self, o: dict, kare) -> None:
        if o["durum"] == "on_uyari":
            self.sonuc.on_uyarilar.append(o)
            if self.on_event is not None:
                self.on_event(o)
            return
        from .evidence import kaydet as kanit_kaydet
        from .evidence import klip_kaydet
        # Kanıt türü ve uyarı türü = sınıf: "telefon" ve "sigara" panelde, kanıt
        # klasöründe ve webhook'ta AYRI görünür (evidence.telefon / evidence.sigara).
        o["snapshot"] = kanit_kaydet(self.cfg, kare, self.camera_id, o["sinif"],
                                     box=o["kutu"], etiket=_ascii(alarm_etiketi(o)))
        o["clip"] = klip_kaydet(self.cfg, list(self.halka), self.camera_id, o["sinif"],
                                fps=self.efektif_fps)
        self.sonuc.alarmlar.append(o)
        if self.on_alert is not None:
            self.on_alert(o)
        if self.store is not None:
            self.store.add_alert(o["sinif"], o["sinif"], o["sinif"], alarm_etiketi(o),
                                 self.camera_id, snapshot=o["snapshot"])


def _ciz(kare, tespitler) -> Any:
    import cv2
    img = kare.copy()
    k = max(1.0, img.shape[1] / 1280)
    renk = {"kisi": (160, 160, 160), "telefon?": (0, 200, 255), "telefon": (0, 120, 255),
            "sigara?": (0, 220, 180), "sigara": (40, 40, 255)}
    for et, x1, y1, x2, y2, _c in tespitler:
        c = renk.get(et, (200, 200, 200))
        cv2.rectangle(img, (int(x1), int(y1)), (int(x2), int(y2)), c, max(1, round(2 * k)))
        if et != "kisi":
            cv2.putText(img, _ascii(et), (int(x1), max(12, int(y1) - 4)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55 * k, c, max(1, round(2 * k)))
    return img


def run_davranis(source: str, cfg, store=None, camera_id: str = "",
                 on_event=None, on_alert=None, on_frame=None,
                 should_stop: Callable[[], bool] | None = None,
                 siniflar=SINIFLAR) -> DavranisResult:
    """Dosya/RTSP kaynağında davranış tespiti koşar (CLI + Test ekranı).

    `siniflar`: ('telefon',), ('sigara',) veya ikisi — görev anahtarlarıyla aynı.
    """
    siniflar = tuple(s for s in SINIFLAR if s in siniflar) or SINIFLAR
    import cv2
    from . import akis

    vid_stride = max(1, int(cfg.get("davranis.vid_stride", cfg.get("detect.vid_stride", 3))))
    camera_id = camera_id or Path(source).stem
    cap = akis.ac(source, cfg)
    if not cap.isOpened():
        raise FileNotFoundError(f"Video açılamadı: {source}")
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    hat = DavranisHatti(cfg, w, h, camera_id, fps / vid_stride,
                        telefon=_telefon_kur(cfg) if "telefon" in siniflar else None,
                        sigara=_sigara_kur(cfg) if "sigara" in siniflar else None,
                        store=store, on_event=on_event, on_alert=on_alert,
                        siniflar=siniflar)
    ham_idx = 0
    try:
        while should_stop is None or not should_stop():
            okundu, kare = cap.read()
            if not okundu:
                break
            ham_idx += 1
            if ham_idx % vid_stride:
                continue
            ts = ham_idx / fps
            tespitler = hat.kare(kare, ts, ham_idx)
            if on_frame is not None:
                on_frame(_ciz(kare, tespitler))
    finally:
        cap.release()
        if store is not None:
            store.commit()
    return hat.sonuc
