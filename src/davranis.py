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
# Tek "telefon" alarmı, iki tanım (kullanıcı kararı 2026-09-23): kulakta → konuşma,
# elde (mesajlaşma/bakma) → elde kullanım. alerts.kind aynı kalır, etiket ayrışır.
TELEFON_ALT_TUR = {"konusma": "telefonla konuşma", "elde": "elde telefon kullanımı"}
# Ön uyarıyı NE tetikledi — kanıt ekranındaki analiz zaman çizgisinde yazılır
_ON_UYARI_NOT = {"telefon": "el kulak/ağız hizasında, kol duruşu telefon pozu",
                 "sigara": "el ağza gitti — dokunuş sayılmaya başladı"}


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
    kol_dik = False     # kulaktaki elin önkolu dik mi (dirsek bilekten ≥ 1,0 baş aşağıda)
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
                # Ölçüm 2026-09-23: konuşmada dirsek−bilek +1,6…+2,2 baş (önkol dik);
                # başı eğik mesajlaşmada ≤ +0,8 (önkol yatay). Dirsek görünmüyorsa dik sayılır.
                if kc[d] <= esik or kp[d][1] - w[1] >= 1.0 * bas:
                    kol_dik = True
        if agiz_pt is not None and _uzak(w, agiz_pt) < agiz_oran * bas:
            agiz = True
    # Baş kutusu: doğrulayıcı dedektörlerin bakacağı bölge (burun merkezli)
    if burun_ok:
        cx, cy = kp[BURUN]
    else:
        cx, cy = (kutu[0] + kutu[2]) / 2, kutu[1] + bas
    r = 1.6 * bas
    bas_kutu = (cx - r, cy - r, cx + r, cy + 1.6 * r)
    return {"bas": bas, "kulak": kulak, "agiz": agiz, "bas_kutu": bas_kutu, "kol_dik": kol_dik}


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
                 "dokunus", "agiz_giris", "dogrulama", "bas_kutu", "son_dogrulama_ts",
                 "telefon_alt", "telefon_pay", "temas_onay", "onayli_dokunus", "agiz_cikis",
                 "son_telefon_ts", "dogdu", "dogrulama_kutu")

    def __init__(self, tid: int, kutu, ts: float) -> None:
        self.id = tid
        self.kutu = kutu
        self.son_ts = ts
        self.dogdu = ts                       # ilk görülme — kanıtta "N sn izlendi"
        self.gecmis: deque = deque()          # (ts, kulak, agiz)
        self.durum = {s: "izle" for s in SINIFLAR}
        self.baslangic = {s: None for s in SINIFLAR}   # on_uyari anı
        self.son_alarm = {s: -1e9 for s in SINIFLAR}
        self.dokunus: deque = deque()         # ağza gidiş anları (sigara)
        self.agiz_giris: float | None = None  # şu anki ağız temasının başlangıcı
        self.temas_onay = False               # süren temasta dedektör sigara gördü mü
        self.onayli_dokunus: deque = deque()  # dedektörün sigara gördüğü dokunuşların anları
        self.agiz_cikis: float | None = None  # son temasın bittiği an (kısa boşluk → aynı temas)
        self.son_telefon_ts = -1e9            # bu kişide en son telefon kutusu görülen an
        self.dogrulama = {s: None for s in SINIFLAR}   # (ts, kaynak) son pozitif doğrulama
        # (ts, kutu) — doğrulayıcının GÖRDÜĞÜ nesnenin tam kare koordinatı. Kanıt
        # karesine ve klibe çizilir: operatör "neyi yakaladı" sorusunu görüntüden
        # cevaplayabilsin (istek 2026-09-24).
        self.dogrulama_kutu = {s: None for s in SINIFLAR}
        self.bas_kutu = None
        self.son_dogrulama_ts = -1e9
        self.telefon_alt = "konusma"
        self.telefon_pay = (0.0, 0.0, 0)


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
                 siniflar=SINIFLAR, telefon_poz_kat: float = 3.0,
                 telefon_kip: str = "ikisi", alarm_konum_iou: float = 0.2,
                 sigara_onay_tekrar: int = 2, dokunus_bosluk_sn: float = 1.5,
                 telefon_bastirma_sn: float = 5.0) -> None:
        self.telefon_bastirma_sn = float(telefon_bastirma_sn)
        self.sigara_onay_tekrar = int(sigara_onay_tekrar)
        self.dokunus_bosluk_sn = float(dokunus_bosluk_sn)
        self._olum: dict[int, float] = {}            # iz id → kaybolma anı (konum hafızası için)
        self._temaslar: list[tuple[float, tuple, bool, int]] = []   # (ts, kutu, onaylı, iz id) biten dokunuşlar
        self.siniflar = tuple(s for s in SINIFLAR if s in siniflar)
        # konusma : yalnız kulakta telefon pozu (ilk istek: "telefonla konuşan insanlar")
        # kullanim: elde telefon görülmesi de yeter (mesajlaşma dâhil)
        # konusma : yalnız kulakta poz alarm olur
        # kullanim: yalnız elde telefon (mesajlaşma) alarm olur
        # ikisi   : her ikisi de alarm olur; etiket ayrışır (varsayılan)
        self.telefon_kip = telefon_kip if telefon_kip in ("konusma", "kullanim", "ikisi") else "ikisi"
        # Aynı kişi 30 sn'de bir yeniden alarm üretiyordu: iz kimliği kalabalıkta
        # kopup yeniden açılınca iz-başı cooldown sıfırlanıyor (ölçüm 2026-09-23:
        # mesajlaşan kadın 1,5 dk'da 3 alarm). Alarm KONUMU hatırlanır; cooldown
        # içinde aynı yerdeki (IoU ≥ eşik) aynı türden alarm bastırılır.
        self.alarm_konum_iou = float(alarm_konum_iou)
        self._son_alarmlar: list[tuple[float, str, tuple]] = []
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
            self._olum[tid] = self.izler.pop(tid).son_ts
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
            # İz DEVRALMA YOK: konumla devralma sigara içenin geçmişini yanından geçen
            # kişiye aktardı (klip kontrolü 2026-09-23). Kopan izin dokunuşları konum
            # hafızasından (_cevre_sayisi, ≤ 6 sn önce kaybolmuş iz) sayılır.
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
            elde_asagi = False      # telefon kutusu elde ve BAŞ BÖLGESİNİN DIŞINDA (göğüs hizası)
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
            if telefon_eller and kc[BURUN] > self.kp_esik:
                # 2B pozdan "konuşma" ile "başı eğik mesajlaşma" ayrılmıyor (ölçüm 2026-09-23:
                # bilekler aynı yerde). Ayrım telefon KUTUSUNUN yeri: yanak/kulak hizasında
                # (burundan ≤ 0,9 baş) → konuşma; burnun ≥ 1,0 baş altında (göğüs) → elde.
                for tk in telefon_kutular or ():
                    if not _kesisir(tk, kutu):
                        continue
                    cx, cy = (tk[0] + tk[2]) / 2, (tk[1] + tk[3]) / 2
                    dx, dy = (cx - kp[BURUN][0]) / oz["bas"], (cy - kp[BURUN][1]) / oz["bas"]
                    if dy >= 1.0 and not (abs(dx) <= 1.0 and abs(dy) <= 0.9):
                        elde_asagi = True
            elde_telefon = bool(telefon_eller) and self.telefon_kip in ("kullanim", "ikisi")
            kulakta = oz["kulak"] and self.telefon_kip in ("konusma", "ikisi")
            # gecmis: (ts, telefon_pozu, agiz, kulakta, elde)
            iz.gecmis.append((ts, kulakta or elde_telefon, oz["agiz"],
                              bool(oz["kulak"] and oz["kol_dik"]), elde_asagi))
            ufuk = ts - max(self.telefon_sn * 2.5, self.sigara_pencere_sn)
            while iz.gecmis and iz.gecmis[0][0] < ufuk:
                iz.gecmis.popleft()
            # doğrulayıcılar
            if telefon_kutular:
                if telefon_eller or any(_kesisir(tk, iz.bas_kutu) for tk in telefon_kutular):
                    iz.dogrulama["telefon"] = (ts, "telefon kutusu")
                    # Kanıta çizilecek kutu: önce başla kesişen (kulakta telefon),
                    # yoksa kişiyle kesişen ilk kutu (elde telefon).
                    esl = ([tk for tk in telefon_kutular if _kesisir(tk, iz.bas_kutu)]
                           or [tk for tk in telefon_kutular if _kesisir(tk, kutu)])
                    if esl:
                        iz.dogrulama_kutu["telefon"] = (ts, tuple(float(v) for v in esl[0]))
            # Telefon pozundaki el ağız yarıçapına da girer: o karede dokunuş sayılmaz
            sig_oz = ozellikler(kp, kc, kutu, self.kp_esik, self.kulak_oran,
                               self.agiz_oran, ignore_wrists=telefon_eller)
            # Kulak pozu DIŞLANMAZ: sigara içen de eli yanağında tutar (ölçüm 2026-09-23,
            # sokak klibi: nefeslerin çoğu kulak=True). Telefonla konuşmayı ayıran şey
            # SÜREdir: telefon tek uzun temas (> dokunus_max_sn → dokunuş değil), sigara
            # aralıklı kısa temaslar. Elde COCO telefon kutusu olan bilek yine dışlanır.
            if telefon_eller or any(_kesisir(tk, iz.bas_kutu) for tk in telefon_kutular or ()):
                iz.son_telefon_ts = ts
            # Telefonu görülen kişide 5 sn boyunca sigara teması sayılmaz: sigara dedektörü
            # CCTV ölçeğinde telefonu sigara sanıyor (ölçüm 2026-09-23, 8 örnekte 3).
            telefonlu = ts - iz.son_telefon_ts <= self.telefon_bastirma_sn
            self._sigara_dokunus(iz, sig_oz["agiz"] and not telefonlu, ts, sigara_kontrol)
            olaylar += self._degerlendir(iz, ts)
        return olaylar

    def _sigara_dokunus(self, iz: _Iz, agiz: bool, ts: float, kontrol) -> None:
        """Ağız temaslarını sayar. Saha incelemesi 2026-09-23 (140 alarm): süren tek temas
        (kulakta telefon, çeneye dayanan el) dokunuş sayılıp dedektör tek kırpmada
        "sigara" deyince alarm oluyordu. Artık yalnız BİTMİŞ ve süresi uygun temas
        dokunuştur; dedektör onayı dokunuş başına tutulur, alarm ≥2 AYRI onaylı
        dokunuş ister (sigara_onay_tekrar)."""
        if agiz:
            if iz.agiz_giris is None:
                iz.agiz_giris = ts
                iz.temas_onay = False
            # temas sırasında en fazla 0,5 sn'de bir doğrulayıcıya sor
            if kontrol is not None and not iz.temas_onay and ts - iz.son_dogrulama_ts >= 0.5:
                iz.son_dogrulama_ts = ts
                try:
                    if kontrol(iz):
                        iz.temas_onay = True
                except Exception:
                    pass
            iz.agiz_cikis = None
        elif iz.agiz_giris is not None:
            # Poz titreşimi temasları parçalıyor (ölçüm 2026-09-23: kulakta telefonla
            # konuşan kişide 0,3 sn aralıklı 4 "dokunuş"). El gerçekten inmeden
            # (dokunus_bosluk_sn) yeniden temas gelirse AYNI temas sayılır.
            if iz.agiz_cikis is None:
                iz.agiz_cikis = ts
                return
            if ts - iz.agiz_cikis < self.dokunus_bosluk_sn:
                return
            sure = iz.agiz_cikis - iz.agiz_giris
            iz.agiz_giris = None
            iz.agiz_cikis = None
            if self.dokunus_min_sn <= sure <= self.dokunus_max_sn:
                iz.dokunus.append(ts)
                # Kamera düzeyi konum hafızası: kalabalıkta iz 40 sn boyunca kopuyor
                # (ölçüm 2026-09-23: gerçek sigara içen 3 iz kimliği aldı, sayaç hep
                # sıfırlandı). Dokunuşlar KONUMLA tutulur; aynı çevredeki (2 kutu
                # genişliği) dokunuşlar aynı kişiye sayılır.
                self._temaslar.append((ts, tuple(iz.kutu), bool(iz.temas_onay), iz.id))
                if iz.temas_onay:
                    iz.onayli_dokunus.append(ts)
            iz.temas_onay = False
        while iz.dokunus and iz.dokunus[0] < ts - self.sigara_pencere_sn:
            iz.dokunus.popleft()
        while iz.onayli_dokunus and iz.onayli_dokunus[0] < ts - self.sigara_pencere_sn:
            iz.onayli_dokunus.popleft()
        self._temaslar = [t for t in self._temaslar if ts - t[0] < self.sigara_pencere_sn]
        if self._cevre_sayisi(iz, onayli=True) >= self.sigara_onay_tekrar:
            iz.dogrulama["sigara"] = (ts, "sigara dedektörü")
        else:
            iz.dogrulama["sigara"] = None

    def _cevre_sayisi(self, iz: _Iz, onayli: bool = False) -> int:
        """Bu izin kendi dokunuşları + çevresindeki KAYBOLMUŞ izlerin dokunuşları.

        Hâlâ takipte olan BAŞKA bir izin temasları sayılmaz: yan yana yürüyen iki
        kişide alarm yanlış kişiye yazılıyordu (ölçüm 2026-09-23, klip kontrolü).
        Konum devralma yalnız iz kopması içindir.
        """
        kutu = iz.kutu
        cx, cy = (kutu[0] + kutu[2]) / 2, (kutu[1] + kutu[3]) / 2
        r = 1.0 * max(kutu[2] - kutu[0], kutu[3] - kutu[1], 1.0)
        n = 0
        dogum = iz.gecmis[0][0] if iz.gecmis else iz.son_ts
        for ts, k, o, sahip in self._temaslar:
            if onayli and not o:
                continue
            if sahip == iz.id:
                n += 1
                continue
            if sahip in self.izler:
                continue        # canlı başka kişi
            # kopan iz: bu iz doğmadan en fazla 6 sn önce kaybolmuş ve aynı yerde olmalı
            if dogum - self._olum.get(sahip, -1e9) <= 6.0                     and _uzak(((k[0] + k[2]) / 2, (k[1] + k[3]) / 2), (cx, cy)) <= r:
                n += 1
        return n

    def _telefon_adayi(self, iz: _Iz, ts: float) -> tuple[bool, float]:
        pencere = [g for g in iz.gecmis if g[0] >= ts - self.telefon_sn]
        if len(pencere) < 3 or ts - pencere[0][0] < self.telefon_sn * 0.8:
            return False, 0.0
        oran = sum(1 for g in pencere if g[1]) / len(pencere)
        # Alt tür: telefon kutusu elde ve baş bölgesinin DIŞINDA (göğüs hizası) görülen
        # kareler çoğunluktaysa "elde" — başı eğik mesajlaşan kişide bilek kulak kuralına
        # da uyuyor (ölçüm 2026-09-23). Kutu baş bölgesindeyse (kulakta telefon) ya da
        # kulak pozu çoğunluktaysa "konuşma".
        pozlu = [g for g in pencere if g[1]]
        elde_pay = (sum(1 for g in pozlu if len(g) > 4 and g[4]) / len(pozlu)) if pozlu else 0.0
        kulak_pay = (sum(1 for g in pozlu if len(g) > 3 and g[3]) / len(pozlu)) if pozlu else 0.0
        # konuşma: kutu göğüste değil VE kulakta dik önkol çoğunlukta; aksi elde
        iz.telefon_alt = "konusma" if (elde_pay < 0.5 and kulak_pay >= 0.5) else "elde"
        iz.telefon_pay = (round(elde_pay, 2), round(kulak_pay, 2), len(pozlu))
        return oran >= self.telefon_oran, oran

    def _sigara_adayi(self, iz: _Iz, ts: float) -> tuple[bool, float]:
        # Yalnız BİTMİŞ temaslar (süren temas kulakta telefon olabilir), konum çevresiyle
        n = max(len(iz.dokunus), self._cevre_sayisi(iz))
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
                        n_dok = len(iz.dokunus)   # yalnız bitmiş temaslar
                        alarm = dogrulandi or n_dok >= self.sigara_tekrar + 1                             or sure >= self.sigara_pencere_sn * 0.5
                if alarm and self._ayni_yerde_yakin_alarm(sinif, iz.kutu, ts):
                    # Aynı kişi (iz kimliği değişmiş olsa da) cooldown içinde: sessiz kal
                    iz.durum[sinif] = "alarm"
                    iz.son_alarm[sinif] = ts
                    continue
                if alarm and ts - self.kamera_son_alarm[sinif] >= self.kamera_cooldown_sn:
                    iz.durum[sinif] = "alarm"
                    iz.son_alarm[sinif] = ts
                    self.kamera_son_alarm[sinif] = ts
                    self._son_alarmlar.append((ts, sinif, tuple(iz.kutu)))
                    olaylar.append(self._olay(iz, sinif, "alarm", ts, max(skor, 0.9 if dogrulandi else skor),
                                              d[1] if dogrulandi else "poz",
                                              sure=sure))
        return olaylar

    def _ayni_yerde_yakin_alarm(self, sinif: str, kutu, ts: float) -> bool:
        self._son_alarmlar = [a for a in self._son_alarmlar if ts - a[0] < self.cooldown_sn]
        return any(a[1] == sinif and _iou(a[2], kutu) >= self.alarm_konum_iou
                   for a in self._son_alarmlar)

    def _olay(self, iz: _Iz, sinif: str, durum: str, ts: float, skor: float,
              kaynak: str, sure: float = 0.0) -> dict:
        return {"sinif": sinif, "durum": durum, "conf": round(float(skor), 2),
                "alt_tur": iz.telefon_alt if sinif == "telefon" else "",
                "alt_pay": iz.telefon_pay if sinif == "telefon" else (),
                "kutu": tuple(float(v) for v in iz.kutu), "track_id": iz.id,
                # Doğrulayıcının gördüğü nesne kutusu (tam kare) — kanıta çizilir
                "dogrulama_kutu": (iz.dogrulama_kutu[sinif][1]
                                   if iz.dogrulama_kutu[sinif] is not None
                                   and ts - iz.dogrulama_kutu[sinif][0] <= self.dogrulama_taze_sn
                                   else None),
                "dogrulama": kaynak, "sure": round(float(sure), 1),
                "ts_seconds": round(ts, 2),
                "analiz": self._analiz(iz, sinif, durum, ts, kaynak, sure, skor)}

    def _analiz(self, iz: _Iz, sinif: str, durum: str, ts: float, kaynak: str,
                sure: float, skor: float) -> dict:
        """Kanıtta gösterilecek analiz özeti: ne yakalandı, hangi anda ne oldu.

        Operatör isteği 2026-09-24: "test ekranı gibi neyi yakaladı, hangi anda
        uyarı, hangi anda alarma döndü". Aşama zamanları ALARM ANINA GÖRE geriye
        saniye olarak verilir; alarmın veritabanı zamanı mutlak andır, UI ikisini
        toplayıp saat yazar — böylece kayıt/klip saatiyle birebir tutar.
        """
        izlendi = max(0.0, ts - iz.dogdu)
        basla = iz.baslangic[sinif]
        asamalar = [{"durum": "izle", "once_sn": round(izlendi, 1),
                     "not": "kişi izlenmeye başlandı"}]
        if basla is not None:
            asamalar.append({"durum": "on_uyari", "once_sn": round(max(0.0, ts - basla), 1),
                             "not": _ON_UYARI_NOT.get(sinif, "poz eşiği aşıldı")})
        if durum == "alarm":
            asamalar.append({"durum": "alarm", "once_sn": 0.0,
                             "not": ("doğrulayıcı onayladı: " + kaynak) if kaynak != "poz"
                             else "poz tek başına yeterli süre sürdü"})
        if sinif == "sigara":
            olcum = {"dokunus": len(iz.dokunus), "onayli_dokunus": len(iz.onayli_dokunus)}
        else:
            olcum = {"alt_tur": TELEFON_ALT_TUR.get(iz.telefon_alt, iz.telefon_alt)}
        return {"sinif": sinif, "durum": durum, "iz": iz.id,
                "izlendi_sn": round(izlendi, 1), "sure_sn": round(float(sure), 1),
                "guven": round(float(skor), 2), "dogrulama": kaynak,
                "asamalar": asamalar, "olcum": olcum}

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
    """İsteğe bağlı sigara dedektörü: (bgr_kirpma) → en iyi kutu ya da None.

    Eskiden yalnız bool dönüyordu; kanıt karesinde "neyi yakaladı" gösterilemiyordu
    (istek 2026-09-24). Kutu kırpma koordinatındadır, çağıran tam kareye taşır.
    Dönen değer yine doğruluk testine uygundur (kutu varsa doğru, yoksa None).
    """
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
            return None
        r = model.predict(bgr, imgsz=imgsz, conf=esik, device=device, verbose=False)[0]
        if r.boxes is None or len(r.boxes) == 0:
            return None
        xy = r.boxes.xyxy.cpu().numpy()
        gv = r.boxes.conf.cpu().numpy() if r.boxes.conf is not None else None
        i = int(gv.argmax()) if gv is not None and len(gv) else 0
        return tuple(float(v) for v in xy[i])
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
        telefon_kip=str(g("telefon_kip", "ikisi")),
        alarm_konum_iou=g("alarm_konum_iou", 0.2),
        telefon_sn=g("telefon_sn", 4.0), telefon_oran=g("telefon_oran", 0.7),
        sigara_tekrar=g("sigara_tekrar", 2), sigara_pencere_sn=g("sigara_pencere_sn", 40.0),
        dokunus_min_sn=g("dokunus_min_sn", 0.3), dokunus_max_sn=g("dokunus_max_sn", 6.0),
        telefon_dogrulama=str(g("telefon_dogrulama", "tercih")),
        sigara_dogrulama=str(g("sigara_dogrulama", "zorunlu")),
        sigara_onay_tekrar=g("sigara_onay_tekrar", 2),
        dokunus_bosluk_sn=g("dokunus_bosluk_sn", 1.5),
        telefon_bastirma_sn=g("telefon_bastirma_sn", 5.0),
        dogrulama_taze_sn=g("dogrulama_taze_sn", 5.0),
        cooldown_sn=g("cooldown_seconds", 120.0),
        kamera_cooldown_sn=g("camera_cooldown_seconds", 30.0),
        kayip_sn=g("kayip_sn", 2.0), min_bas_px=g("min_bas_px", 24.0),
        kp_esik=g("kp_conf", 0.3), kulak_oran=g("kulak_oran", 0.8), agiz_oran=g("agiz_oran", 1.4),
    )


# ───────────────────────── hat ─────────────────────────

def _ascii(s: str) -> str:
    return (s or "").translate(str.maketrans("çğıİöşüÇĞÖŞÜ", "cgiIosuCGOSU"))


def olay_adi(o: dict) -> str:
    """Panelde görünen ad: telefon için alt tür (konuşma / elde kullanım)."""
    if o.get("sinif") == "telefon":
        return TELEFON_ALT_TUR.get(o.get("alt_tur") or "", ETIKETLER["telefon"])
    return ETIKETLER.get(o.get("sinif", ""), o.get("sinif", ""))


def alarm_etiketi(o: dict) -> str:
    return (f"{olay_adi(o)} · {o.get('sure', 0)} sn · "
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
        # Kare başına çizim bilgisi (etiket, kutu) — klip ANALİZ KATMANIYLA yazılır:
        # operatör kanıtta "izle → ön uyarı → alarm" ilerleyişini görsün (istek 2026-09-23)
        self.halka_ciz: deque = deque(maxlen=self.halka.maxlen)
        # Kare kimliği + akış saniyesi: kanıttaki KARE DÖKÜMÜ bunlardan yazılır
        # (istek 2026-09-24: "olaylarda da Test ekranındaki kare/sn detayı olsun")
        self.halka_meta: deque = deque(maxlen=self.halka.maxlen)
        # Kare başına iz kimliği → (etiket, kutu). Döküm ve klip vurgusu bundan
        # okunur: kutu örtüşmesiyle eşleştirmek yürüyen kişide iz kopartıyordu
        # (canlı alarm #644'te 5 saniyelik tampondan yalnız 2 kare eşleşti).
        self.halka_iz: deque = deque(maxlen=self.halka.maxlen)
        self.sonuc = DavranisResult(fps=efektif_fps)
        self.store = store
        self.on_event = on_event
        self.on_alert = on_alert

    def _sigara_kontrol(self, bgr):
        if self.sigara is None:
            return None

        min_bas = float(self.cfg.get("davranis.sigara_min_bas_px", 24))

        def kontrol(iz) -> bool:
            # Küçük başta (< sigara_min_bas_px) dedektör halüsinasyon görüyor
            # (ölçüm 2026-09-23: 25 px başta telefon 0,8 güvenle "sigara")
            x1, y1, x2, y2 = iz.bas_kutu
            if (x2 - x1) / 3.2 < min_bas:      # bas_kutu genişliği = 3,2 × baş
                return False
            x1, y1 = max(0, int(x1)), max(0, int(y1))
            x2, y2 = min(self.w, int(x2)), min(self.h, int(y2))
            if x2 - x1 < 8 or y2 - y1 < 8:
                return False
            kutu = self.sigara(bgr[y1:y2, x1:x2])
            if not kutu:
                return False
            # Kırpma koordinatı → tam kare: kanıt karesine bu kutu çizilir.
            # (Kutu döndürmeyen bir dedektör verilmişse yalnız "gördü" bilgisi kalır.)
            try:
                a, b, c, d = (float(v) for v in kutu)
                iz.dogrulama_kutu["sigara"] = (iz.son_ts, (a + x1, b + y1, c + x1, d + y1))
            except (TypeError, ValueError):
                pass
            return True
        return kontrol

    def kare(self, bgr, ts: float, frame_idx: int, telefon_kutular=None) -> list[tuple]:
        """Bir kareyi işler; kişileri (etiket, x1, y1, x2, y2, conf) olarak döndürür.

        etiket: 'kisi' | 'telefon?' | 'telefon' | 'sigara?' | 'sigara'
        """
        self.sonuc.frames += 1
        self.halka.append(bgr.copy())
        self.halka_meta.append((frame_idx, ts))
        # Etiket yeri şimdi açılır, kare sonunda doldurulur: halka ile BİREBİR
        # hizalı kalsın. Önceden etiketler kare sonunda eklendiği için klipte
        # kutular bir kare geriden çiziliyordu ve alarm karesi etiketsiz kalıyordu.
        self.halka_ciz.append([])
        self.halka_iz.append({})
        kisiler = self.poz(bgr)
        # Tam karede kaybolan küçük telefonu kişi kırpmasında ara. Çağrı sayısı
        # kamera başına saniyede bir, en büyük altı kişiyle sınırlıdır.
        #
        # 2026-09-24 denendi ve GERİ ALINDI: "yalnız eli yukarıdaki kişiyi tara"
        # filtresi saha karelerinde taramayı yalnız %10 azaltıyordu (uzak kişide poz
        # bilekleri gövdenin üstünde topluyor) — tempo darboğazı burası değil,
        # sayım+yangın+davranışın aynı GPU'yu paylaşması. Tespit riski almaya değmez.
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
        olaylar = self.takip.guncelle(kisiler, ts, boxes, self._sigara_kontrol(bgr))
        # Etiketler olaylardan ÖNCE yazılır: alarm karesinin kendisi de kanıt
        # klibinde ve kare dökümünde etiketli görünsün.
        et = self.takip.etiketler()
        out = []
        izmap = {}
        for iz in self.takip.izler.values():
            if iz.son_ts != ts:
                continue
            etiket = et.get(iz.id, "kisi")
            out.append((etiket, *iz.kutu, 1.0))
            izmap[iz.id] = (etiket, tuple(float(v) for v in iz.kutu))
        self.halka_ciz[-1] = list(out)
        self.halka_iz[-1] = izmap
        for o in olaylar:
            o["camera_id"] = self.camera_id
            o["frame_idx"] = frame_idx
            self._yay(o, bgr)
        return out

    def _klip_kareleri(self, o: dict) -> list:
        """Halka tamponunu analiz katmanıyla döker: kişi kutuları + o karedeki aşama.

        Aşama etiketi hattın o andaki durumudur ('kisi' → izle, 'x?' → ön uyarı,
        'x' → alarm); son kare alarmın kendisidir. Alarm kişisi İZ KİMLİĞİNDEN
        bulunup vurgulanır — kalabalıkta hangi kişiye ait olduğu belli olsun ve
        kişi yürürken kutu örtüşmesi düşse de iz kopmasın.
        """
        import cv2
        kareler = list(self.halka)
        cizler = list(self.halka_ciz)     # halka ile birebir hizalı (bkz. kare())
        metalar = list(self.halka_meta)
        izler = list(self.halka_iz)
        tid = o.get("track_id")
        cikti = []
        n = len(kareler)
        for i, (kare, ciz) in enumerate(zip(kareler, cizler)):
            meta = metalar[i] if i < len(metalar) else (0, 0.0)
            img = _ciz(kare, ciz)
            k = max(1.0, img.shape[1] / 1280)
            # alarm kişisi: iz kimliğiyle bulunur, kalın kırmızı + aşama metni
            en = (izler[i] if i < len(izler) else {}).get(tid)
            if en is not None:
                et, kutu = en
                asama = "ALARM" if (i == n - 1 or et == o["sinif"]) else \
                        ("on uyari" if et.endswith("?") else "izle")
                renk = (40, 40, 255) if asama == "ALARM" else ((0, 200, 255) if asama == "on uyari" else (200, 200, 200))
                cv2.rectangle(img, (int(kutu[0]), int(kutu[1])), (int(kutu[2]), int(kutu[3])), renk, max(2, round(3 * k)))
                # Aşama metni kutunun İÇİNE yazılır: üstte _ciz'in kendi etiketiyle
                # üst üste biniyordu (klip kontrolünde görüldü).
                cv2.putText(img, f"{_ascii(o['sinif'])}: {asama}",
                            (int(kutu[0]) + 6, int(kutu[1]) + int(24 * k)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7 * k, renk, max(2, round(2 * k)))
            # Yakalanan nesne (sigara/telefon kutusu) son karelerde kırmızı çizilir:
            # klipte de "neyi yakaladı" görünsün. Kutu alarm anına aittir, bu yüzden
            # yalnız doğrulamanın tazeliği kadar geriye çizilir (son 3 kare).
            if o.get("dogrulama_kutu") and i >= n - 3:
                vk = o["dogrulama_kutu"]
                cv2.rectangle(img, (int(vk[0]), int(vk[1])), (int(vk[2]), int(vk[3])),
                              (40, 40, 255), max(2, round(2 * k)))
                cv2.putText(img, _ascii(o["sinif"]), (int(vk[0]), max(12, int(vk[1]) - 6)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6 * k, (40, 40, 255), max(2, round(2 * k)))
            # Bant: kare numarası ve akış saniyesi kanıttaki kare dökümüyle AYNI
            # değerlerdir — operatör klipteki anı listede bulabilsin.
            cv2.putText(img, f"{_ascii(alarm_etiketi(o))}  kare {meta[0]} ({i + 1}/{n})"
                             f"  {meta[1]:.2f} sn", (10, int(28 * k)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6 * k, (255, 255, 255), max(1, round(2 * k)))
            cikti.append(img)
        return cikti

    def _olculen_fps(self) -> float:
        """Klibin yazılacağı GERÇEK tempo (kare/sn).

        Hedef tempo (`davranis.fps`) ile gerçekleşen tempo sahada ayrışıyor: GPU
        doluyken kademe kare düşürüyor (ölçüm 2026-09-24, kamera-201/207: hedef 4,
        gerçekleşen 0,5–1,8). Hedef temposuyla yazılan klip gerçeğin 2–8 katı hızda
        oynuyordu — kanıt yanıltıcı olur. Halka tamponundaki zaman damgalarından
        ölçülür; tampon boşsa hedefe düşer.
        """
        m = list(self.halka_meta)
        if len(m) < 2:
            return self.efektif_fps
        sure = m[-1][1] - m[0][1]
        if sure <= 0:
            return self.efektif_fps
        return max(1.0, min(30.0, (len(m) - 1) / sure))

    def _kare_izi(self, o: dict) -> list[dict]:
        """Alarm kişisinin son karelerdeki tespit dökümü — Test ekranındaki satırların aynısı.

        Her kare için: kare numarası, akış saniyesi, o karede verilen etiket ve
        aşaması. Klip görsel kanıt, bu liste OKUNABİLİR kanıttır: "hangi karede
        izleme, hangi karede ön uyarı, hangi karede alarm" listeden görülür.
        Halka tamponu kadar (davranis.clip_seconds) geriye gider.
        """
        tid = o.get("track_id")
        cikti = []
        for (fi, fts), izmap in zip(self.halka_meta, self.halka_iz):
            kayit = izmap.get(tid)
            if kayit is None:
                continue          # kişi o karede sahnede değil (ya da iz kopmuş)
            et = kayit[0]
            asama = "izle" if et == "kisi" else ("on_uyari" if et.endswith("?") else "alarm")
            cikti.append({"kare": int(fi), "ts_sn": round(float(fts), 2),
                          "etiket": et, "asama": asama})
        return cikti

    def _yay(self, o: dict, kare) -> None:
        if o["durum"] == "on_uyari":
            self.sonuc.on_uyarilar.append(o)
            if self.on_event is not None:
                self.on_event(o)
            return
        from .evidence import kaydet as kanit_kaydet
        from .evidence import klip_kaydet
        # Analiz özetine kare düzeyi eklenir: hangi kare, kaçıncı saniye ve alarm
        # kişisinin kare kare tespit dökümü (kanıt ekranı bunu liste olarak gösterir).
        analiz = o.get("analiz")
        if isinstance(analiz, dict):
            analiz["kare"] = int(o.get("frame_idx") or 0)
            analiz["ts_sn"] = float(o.get("ts_seconds") or 0.0)
            analiz["kareler"] = self._kare_izi(o)
            # Gerçekleşen analiz temposu: hedefin altındaysa zamansal kurallar daha
            # az örnekle karar veriyor demektir — kanıtta görünsün.
            analiz["tempo_fps"] = round(self._olculen_fps(), 2)
            analiz["hedef_fps"] = round(float(self.efektif_fps), 2)
        # Kanıt türü ve uyarı türü = sınıf: "telefon" ve "sigara" panelde, kanıt
        # klasöründe ve webhook'ta AYRI görünür (evidence.telefon / evidence.sigara).
        vurgu = o.get("dogrulama_kutu")
        o["snapshot"] = kanit_kaydet(self.cfg, kare, self.camera_id, o["sinif"],
                                     box=o["kutu"], etiket=_ascii(alarm_etiketi(o)),
                                     vurgular=[(vurgu, _ascii(o["sinif"]))] if vurgu else None)
        o["clip"] = klip_kaydet(self.cfg, self._klip_kareleri(o), self.camera_id, o["sinif"],
                                fps=self._olculen_fps())
        self.sonuc.alarmlar.append(o)
        if self.on_alert is not None:
            self.on_alert(o)
        if self.store is not None:
            import json
            self.store.add_alert(o["sinif"], o["sinif"], o["sinif"], alarm_etiketi(o),
                                 self.camera_id, snapshot=o["snapshot"], clip=o.get("clip", ""),
                                 detay=json.dumps(o.get("analiz") or {}, ensure_ascii=False))


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
