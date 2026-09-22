"""Kamera akışı açma — kamera bazlı HTTP başlıklarıyla.

Neden ayrı bir modül: bazı HTTP/HLS sağlayıcıları kendi Referer'ını şart koşar
ve YANLIŞ Referer 403 döndürür. Tek bir genel başlık ayarı olduğu sürece iki
farklı sağlayıcıdan kamera aynı anda çalışamıyordu (ölçüldü: EarthCam,
mobese Referer'ı ile açılmıyor, kendi Referer'ı ile açılıyor).

cv2, PyAV'ın aksine seçenek sözlüğü almaz; FFmpeg başlıklarını YALNIZ
OPENCV_FFMPEG_CAPTURE_OPTIONS ortam değişkeninden okur. Ortam değişkeni süreç
geneli olduğundan, çok kameralı worker'da iki thread aynı anda farklı başlıkla
açmaya kalkarsa biri diğerinin ayarını kapar. Bu yüzden ayar + açma tek kilit
altında yapılır. Açma seyrek bir işlemdir (kamera başına birkaç saniye), kare
okuma kilidin dışındadır — sürekli iş engellenmez.
"""
from __future__ import annotations

import os
import threading

# kaynak adresi → o kameraya ait ham başlık metni ("Referer: ...\nX-Y: ...")
_BASLIKLAR: dict[str, str] = {}
_KILIT = threading.RLock()


def kaydet(source: str, basliklar: str) -> None:
    """Bir kaynağın başlıklarını tanıtır. Worker/sunucu kamera listesini
    okurken çağırır; sonrasında ac() adresi görünce doğru başlığı kullanır."""
    if source and (basliklar or "").strip():
        _BASLIKLAR[source] = basliklar.strip()


def _secenek(source: str, cfg) -> str:
    """OPENCV_FFMPEG_CAPTURE_OPTIONS değeri. Kamera başlığı yoksa config'teki
    genel başlığa düşer (eski davranış korunur)."""
    if not str(source).startswith(("http://", "https://")):
        return ""
    ham = _BASLIKLAR.get(source) or (cfg.get("stream.http_headers", "") if cfg else "") or ""
    ham = ham.strip()
    if not ham:
        return ""
    hdr = "".join(f"{s.strip()}\r\n" for s in ham.splitlines() if s.strip())
    return f"headers;{hdr}"


def ac(source: str, cfg=None, timeout_ms: int = 15000):
    """cv2.VideoCapture açar; HTTP kaynağı ise kameraya ait başlıklarla.

    timeout_ms yalnız ağ kaynaklarına uygulanır — ölü bir kameranın çağrıyı
    süresiz kilitlemesi tüm hattı durdurur.
    """
    import cv2

    with _KILIT:
        onceki = os.environ.get("OPENCV_FFMPEG_CAPTURE_OPTIONS")
        opt = _secenek(source, cfg)
        if opt:
            os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = opt
        elif onceki is not None:
            # Başlık gerekmeyen kaynak, bir öncekinin başlığını miras almasın
            os.environ.pop("OPENCV_FFMPEG_CAPTURE_OPTIONS", None)
        try:
            if str(source).startswith(("rtsp://", "rtmp://", "http://", "https://")):
                cap = cv2.VideoCapture(source, cv2.CAP_FFMPEG,
                                       [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, timeout_ms,
                                        cv2.CAP_PROP_READ_TIMEOUT_MSEC, timeout_ms])
            else:
                # Dosya: sarılabilir sarmalayıcı (Test ekranı ileri sarma) —
                # cv2 arayüzü aynen korunur, yalnız read() öncesi bekleyen
                # sarma isteği uygulanır ve konum raporlanır.
                cap = _Sarilabilir(cv2.VideoCapture(source), source)
        finally:
            if onceki is None:
                os.environ.pop("OPENCV_FFMPEG_CAPTURE_OPTIONS", None)
            else:
                os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = onceki
    return cap


class basliklarla:
    """Ultralytics gibi akışı KENDİ açan kütüphaneler için bağlam yöneticisi.

    yolo.track(source=...) çözmeyi ultralytics'e devreder; o da kendi
    VideoCapture'ını açar ve bizim ac() yolumuzdan geçmez. Tek yol, ortam
    değişkenini o çalışma boyunca ayarlı tutmak.

    SINIR: ortam değişkeni süreç genelidir. Aynı worker sürecinde FARKLI
    başlık isteyen iki HTTP kamera aynı anda koşarsa son ayarlayan kazanır.
    Kalıcı çözüm, HTTP kaynaklarını go2rtc üzerinden yerel RTSP'ye çevirmek —
    o zaman başlık işini go2rtc yapar ve analiz hattı başlık görmez.
    RTSP ve dosya kaynakları bundan etkilenmez.
    """

    def __init__(self, source: str, cfg=None) -> None:
        self.opt = _secenek(source, cfg)
        self.onceki = None

    def __enter__(self):
        if self.opt:
            self.onceki = os.environ.get("OPENCV_FFMPEG_CAPTURE_OPTIONS")
            os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = self.opt
        return self

    def __exit__(self, *_a) -> None:
        if not self.opt:
            return
        if self.onceki is None:
            os.environ.pop("OPENCV_FFMPEG_CAPTURE_OPTIONS", None)
        else:
            os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = self.onceki


def av_secenekleri(source: str, cfg=None) -> dict:
    """PyAV (kayıt/dışa aktarma) için aynı başlıklar — seçenek sözlüğü olarak."""
    opt = _secenek(source, cfg)
    return {"headers": opt[len("headers;"):]} if opt else {}


# ── Dosya kaynağında ileri sarma (Test ekranı) ──────────────────────────
# Kaynak yolu → {"hedef": sn | None, "konum": sn, "sure": sn}. Analiz modülleri
# (fire/plate/face) kaynağı KENDİ açıp cap.read() ile okur; sunucu bu kayıt
# üzerinden "bir sonraki karede şuraya atla" der, modül kodu değişmez.
# Sınır: count hattı akışı ultralytics'e devreder (yolo.track) — bizim cap'ten
# geçmez, orada sarma etkisizdir. Canlı (RTSP/HTTP) kaynakta sarma anlamsızdır.
_SAR: dict[str, dict] = {}


def dosya_mi(source) -> bool:
    return not str(source).lower().startswith(("rtsp://", "rtmp://", "http://", "https://"))


def sar(source, sn: float) -> None:
    """Kaynağın bir sonraki read()'inde `sn` saniyesine atlanmasını ister."""
    d = _SAR.setdefault(str(source), {"hedef": None, "konum": 0.0, "sure": 0.0})
    d["hedef"] = max(0.0, float(sn))


def sar_sifirla(source) -> None:
    """Yeni koşu öncesi eski hedef/konum kalıntısını temizler."""
    _SAR.pop(str(source), None)


def konum(source) -> tuple[float, float]:
    """(mevcut saniye, toplam saniye) — dosya açılmadıysa (0, 0)."""
    d = _SAR.get(str(source))
    return (d["konum"], d["sure"]) if d else (0.0, 0.0)


class _Sarilabilir:
    """cv2.VideoCapture sarmalayıcısı — dosya kaynağı için.

    read(): bekleyen sarma hedefi varsa önce CAP_PROP_POS_MSEC ile atlar, sonra
    okur; okunan karenin konumunu kayda yazar. Diğer her şey (get/set/isOpened/
    release/grab/retrieve) sarmalanan nesneye aynen gider.
    """

    def __init__(self, cap, source) -> None:
        import cv2
        self._cap = cap
        d = _SAR.setdefault(str(source), {"hedef": None, "konum": 0.0, "sure": 0.0})
        fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
        n = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0
        d["sure"] = (n / fps) if fps > 0 and n > 0 else 0.0
        d["konum"] = 0.0
        self._d = d

    def read(self):
        import cv2
        hedef = self._d.get("hedef")
        if hedef is not None:
            self._d["hedef"] = None
            self._cap.set(cv2.CAP_PROP_POS_MSEC, hedef * 1000.0)
        ok, kare = self._cap.read()
        if ok:
            self._d["konum"] = (self._cap.get(cv2.CAP_PROP_POS_MSEC) or 0.0) / 1000.0
        return ok, kare

    def __getattr__(self, ad):
        return getattr(self._cap, ad)
