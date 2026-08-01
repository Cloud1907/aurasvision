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
                cap = cv2.VideoCapture(source)
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
