"""VideoAI — açık kaynak görüntü analitiği POC.

Modüller:
  config  — config.yaml yükleyici
  device  — MPS > CUDA > CPU cihaz seçimi
  store   — SQLite çıktı katmanı
  detect  — YOLO model yükleyici (singleton)
  count   — kişi sayma + ByteTrack + çizgi geçişi
  plate   — plaka okuma (fast-alpr)
  face    — yüz tespit/embedding + anonim demografi (InsightFace)
  cli     — tek giriş noktası (count | face | plate | analyze)
"""

import os as _os

# RTSP'de UDP paket kaybı "Waiting for stream" ile sonuçlanır (go2rtc/NVR relay'lerde
# tipik) → OpenCV/Ultralytics yakalayıcıları TCP taşımaya zorlanır. Kullanıcı kendi
# değerini set ettiyse dokunulmaz.
_os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")

__version__ = "0.1.0"
