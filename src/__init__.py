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

__version__ = "0.1.0"
