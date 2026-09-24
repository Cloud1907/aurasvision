"""Olay kanıt görüntüsü — "okundu" iddiasının denetlenebilir karşılığı.

Neden: plaka olayı metin olarak kaydediliyordu; okuma yanlışsa kimse fark edemezdi
ve ihtilafta gösterilecek bir şey yoktu. Kanıt görüntüsü olmadan doğruluk iddiası
denetlenemez.

KVKK dengesi — proje "ham görüntü saklanmaz" taahhüdü veriyordu, bu modül onu
TÜRE GÖRE gevşetir (config `evidence`):
  * plate      → varsayılan AÇIK. Plaka zaten metin olarak saklanıyor; kanıt kırpması
                 ALPR'ın asli işlevi ve orantılı sayılır.
  * intrusion  → varsayılan AÇIK. Alarm anının karesi güvenlik amacının kendisidir.
  * face       → varsayılan KAPALI. Yüz biyometrik veridir; mevcut tasarım yalnız
                 embedding saklar, bu modül onu değiştirmez.
Her durumda `evidence.keep_days` sonunda dosyalar otomatik silinir (veri minimizasyonu).

Dosyalar output/evidence/<GG-AA-YYYY>/ altına yazılır; UI onlara token korumalı
/media/evidence/... yolundan erişir.
"""
from __future__ import annotations

import shutil
import time
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_SON_TEMIZLIK = 0.0


def etkin(cfg, tur: str) -> bool:
    """Bu olay türü için kanıt görüntüsü açık mı."""
    if not cfg.get("evidence.enabled", True):
        return False
    return bool(cfg.get(f"evidence.{tur}", tur != "face"))


def _h264_yaz(yol, kareler, w: int, h: int, fps: float) -> bool:
    """BGR kareleri H.264/yuv420p mp4 olarak yazar (tarayıcıda oynar). Hata → False."""
    try:
        import av
        import cv2
        from fractions import Fraction
        # H.264 çift boyut ister; tek piksel varsa kırp
        w2, h2 = w - (w % 2), h - (h % 2)
        with av.open(str(yol), "w", options={"movflags": "+faststart"}) as out:
            vs = out.add_stream("libx264", rate=Fraction(fps).limit_denominator(1000))
            vs.width, vs.height = w2, h2
            vs.pix_fmt = "yuv420p"
            vs.options = {"preset": "veryfast", "crf": "26"}
            for k in kareler:
                if k.shape[:2] != (h, w):
                    k = cv2.resize(k, (w, h))
                fr = av.VideoFrame.from_ndarray(k[:h2, :w2], format="bgr24")
                for pkt in vs.encode(fr):
                    out.mux(pkt)
            for pkt in vs.encode(None):
                out.mux(pkt)
        return True
    except Exception as e:
        print(f"[evidence] H.264 klip yazılamadı ({e.__class__.__name__}: {e}) — mp4v yedeği", flush=True)
        try:
            Path(yol).unlink(missing_ok=True)
        except OSError:
            pass
        return False


def klip_kaydet(cfg, kareler, camera_id: str, tur: str, fps: float = 5.0) -> str:
    """Doğrulayan kareleri kısa MP4 olarak yazar, /media'ya göreli yolu döndürür.

    Neden tek kare yetmiyor: duman DURAĞAN karede insan gözüyle de ayırt
    edilemez — FIA/BRE ölçümünde video dedektörlerinin benzer renkli arka planda
    başarısı %52. Operatörün "gerçek mi" sorusuna cevap verebilmesi için
    dumanın HAREKETİNİ görmesi gerekir; kanıt bu yüzden karenin değil kısa
    dizinin kendisidir.
    """
    if not etkin(cfg, tur) or not kareler:
        return ""
    import cv2

    try:
        temizle(cfg)
        h, w = kareler[0].shape[:2]
        klasor = _kok(cfg) / date.today().isoformat()
        klasor.mkdir(parents=True, exist_ok=True)
        ad = f"{camera_id}_{tur}_{uuid.uuid4().hex[:10]}.mp4"
        # H.264 (avc1) + faststart: tarayıcı OpenCV'nin mp4v (MPEG-4 Part 2) çıktısını
        # OYNATMAZ — kanıt penceresinde klip siyah kalıyordu ("video oynamıyor",
        # 2026-09-24). PyAV libx264 bundle'lı; başarısızsa mp4v'ye düşülür (en azından
        # dosya olur, indirilebilir).
        if _h264_yaz(klasor / ad, kareler, w, h, max(1.0, float(fps))):
            return f"evidence/{klasor.name}/{ad}"
        yazici = cv2.VideoWriter(str(klasor / ad), cv2.VideoWriter_fourcc(*"mp4v"),
                                 max(1.0, float(fps)), (w, h))
        if not yazici.isOpened():
            return ""
        try:
            for k in kareler:
                # Boyutu tutmayan kare (çözünürlük değişimi) klibi bozmasın
                yazici.write(k if k.shape[:2] == (h, w) else cv2.resize(k, (w, h)))
        finally:
            yazici.release()
        return f"evidence/{klasor.name}/{ad}"
    except Exception:
        return ""   # kanıt yazımı ASLA analizi düşürmez (kaydet() ile aynı kural)


def _kok(cfg) -> Path:
    return _ROOT / cfg.get("paths.output_dir", "output") / "evidence"


def temizle(cfg) -> int:
    """Saklama süresi dolmuş gün klasörlerini siler. Günde bir kez koşar."""
    global _SON_TEMIZLIK
    if time.monotonic() - _SON_TEMIZLIK < 86400:
        return 0
    _SON_TEMIZLIK = time.monotonic()
    gun = int(cfg.get("evidence.keep_days", 30))
    kok = _kok(cfg)
    if gun <= 0 or not kok.is_dir():
        return 0
    sinir = date.today() - timedelta(days=gun)
    silinen = 0
    for d in kok.iterdir():
        if not d.is_dir():
            continue
        try:
            if datetime.strptime(d.name, "%Y-%m-%d").date() < sinir:
                shutil.rmtree(d, ignore_errors=True)
                silinen += 1
        except ValueError:
            continue   # klasör adı tarih değil → dokunma
    return silinen


def _kose(w: int, h: int, kw: int, kh: int, kacin) -> tuple[int, int]:
    """Büyütülmüş kırpma için, `kacin` dikdörtgeniyle en az örtüşen köşe.

    Kırpma sol üste sabitlenince konunun kendisini kapatabiliyordu (yakalanan
    telefon kutusu kırpmanın altında kaldı, ölçüm 2026-09-24).
    """
    bx1, by1, bx2, by2 = kacin

    def ortusme(oy_ox):
        ox, oy = oy_ox
        return (max(0, min(ox + kw, bx2) - max(ox, bx1))
                * max(0, min(oy + kh, by2) - max(oy, by1)))
    return min(((0, 0), (w - kw, 0), (0, h - kh), (w - kw, h - kh)), key=ortusme)


def _vurgu_ciz(img, kutu, etiket: str) -> None:
    """Yakalanan nesneyi kırmızı kutu + etiketle çizer (tam kare koordinatı)."""
    import cv2
    x1, y1, x2, y2 = (int(round(v)) for v in kutu)
    if x2 <= x1 or y2 <= y1:
        return
    # Küçük nesnede ince kutu kaybolur: en az 18 px'lik bir çerçeve çiz
    if x2 - x1 < 18 or y2 - y1 < 18:
        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
        x1, y1, x2, y2 = cx - 9, cy - 9, cx + 9, cy + 9
    cv2.rectangle(img, (x1, y1), (x2, y2), (40, 40, 255), 2)
    if etiket:
        cv2.putText(img, etiket, (x1, max(12, y1 - 5)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (40, 40, 255), 2)


def kaydet(cfg, frame, camera_id: str, tur: str, box=None, etiket: str = "",
           vurgular=None) -> str:
    """Kanıt karesi yazar, /media'ya göreli yolu döndürür (kapalıysa boş string).

    box verilirse (x1,y1,x2,y2) o bölge hem çerçevelenir hem sol üste BÜYÜTÜLMÜŞ
    olarak yapıştırılır: tek dosyada hem bağlam hem okunur plaka olur.

    vurgular: [(kutu, etiket)] — analizin YAKALADIĞI nesne (sigara/telefon kutusu).
    Hem tam karede hem büyütülmüş kırpmada kırmızı çizilir. Operatör isteği
    2026-09-24: "analizi çizsin, hangisini yakaladığını göstersin" — kişi kutusu
    tek başına "neden alarm verdi" sorusunu cevaplamıyordu.
    """
    if not etkin(cfg, tur) or frame is None:
        return ""
    import cv2

    try:
        temizle(cfg)
        img = frame.copy()
        h, w = img.shape[:2]
        # 1) Çizimler ÖNCE tam kareye: kişi kutusu (sarı) + yakalanan nesne (kırmızı)
        if box is not None:
            x1, y1, x2, y2 = (max(0, int(v)) for v in box)
            x2, y2 = min(w, x2), min(h, y2)
            if x2 > x1 and y2 > y1:
                cv2.rectangle(img, (x1, y1), (x2, y2), (0, 220, 255), 3)
        for vk, vet in (vurgular or ()):
            _vurgu_ciz(img, vk, vet)
        # 2) Büyütülmüş kırpma ÇİZİMLİ kareden alınır: nesne kutusu büyütmede de
        #    görünür, ayrı ölçek hesabı gerekmez. Kırpma, kişiyi VE yakalanan nesneyi
        #    birlikte kapsar — nesne kişi kutusunun dışına taşabiliyor (elde telefon).
        if box is not None:
            kx1, ky1, kx2, ky2 = (max(0, int(v)) for v in box)
            for vk, _ in (vurgular or ()):
                kx1, ky1 = min(kx1, int(vk[0]) - 6), min(ky1, int(vk[1]) - 6)
                kx2, ky2 = max(kx2, int(vk[2]) + 6), max(ky2, int(vk[3]) + 6)
            kx1, ky1 = max(0, kx1), max(0, ky1)
            kx2, ky2 = min(w, kx2), min(h, ky2)
            if kx2 > kx1 and ky2 > ky1:
                kirp = img[ky1:ky2, kx1:kx2].copy()
                # Büyütme oranı HEM genişliğe HEM yüksekliğe sığmalı. Yalnız genişliğe
                # bakınca ayakta duran kişinin (dar ve uzun kutu) büyütmesi kareden
                # taşıyor ve aşağıdaki "sığıyor mu" kontrolünde sessizce atlanıyordu:
                # 2880×1616 saha karesinde kişi kutusu 216×559 → 4× büyütme 864×2236,
                # kareye sığmıyor, kırpma HİÇ basılmıyordu (ölçüm 2026-09-24, #751).
                # En çok ihtiyaç duyulan yerde (uzaktaki küçük kişi) kayboluyordu.
                oran = min(4.0, (w * 0.45) / max(1, kx2 - kx1),
                           (h * 0.85) / max(1, ky2 - ky1))
                if oran > 1.05:
                    kirp = cv2.resize(kirp, None, fx=oran, fy=oran,
                                      interpolation=cv2.INTER_CUBIC)
                kh, kw = kirp.shape[:2]
                if kh < h and kw < w:
                    # Kırpma, konuyu ÖRTMEYEN köşeye yapıştırılır: sol üste sabitken
                    # büyütme kişinin kendisini kapatıyordu (ölçüm 2026-09-24).
                    ox, oy = _kose(w, h, kw, kh, (kx1, ky1, kx2, ky2))
                    img[oy:oy + kh, ox:ox + kw] = kirp
                    cv2.rectangle(img, (ox, oy), (ox + kw, oy + kh), (0, 220, 255), 2)
        if etiket:
            cv2.rectangle(img, (0, h - 34), (w, h), (24, 20, 16), -1)
            cv2.putText(img, etiket[:120], (10, h - 11),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

        klasor = _kok(cfg) / date.today().isoformat()
        klasor.mkdir(parents=True, exist_ok=True)
        ad = f"{camera_id}_{tur}_{uuid.uuid4().hex[:10]}.jpg"
        if not cv2.imwrite(str(klasor / ad), img, [int(cv2.IMWRITE_JPEG_QUALITY), 85]):
            return ""
        return f"evidence/{klasor.name}/{ad}"
    except Exception:
        return ""   # kanıt yazımı ASLA analizi düşürmez
