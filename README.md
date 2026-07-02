# AurasVision — Görüntü Analitiği POC

Açık kaynak görüntü işleme: **kişi sayma**, **plaka okuma (ALPR)**, **yüz tespit + anonim demografi**.
Tek videoda hepsi. Geliştirme: MacBook M4 (MPS). Üretim hedefi: Jetson / NVIDIA edge.

## Kurulum

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
```

Modeller ilk çalıştırmada otomatik iner (YOLO ~5MB, fast-alpr, InsightFace buffalo_l ~280MB).

## Kullanım

```bash
# Kişi sayma + çizgi geçişi (annotated video kaydet)
python -m src.cli count   --source data/videos/people-detection.mp4 --save

# Plaka okuma
python -m src.cli plate   --source data/videos/person-bicycle-car-detection.mp4

# Yüz + anonim demografi
python -m src.cli face    --source data/videos/people-detection.mp4

# Üçü birden
python -m src.cli analyze --source data/videos/scene.mp4 --save
```

Sonuçlar `output/videoai.db` (SQLite) içine yazılır; `--save` ile annotated video `output/` altına çıkar.

## Mimari

```
src/
  cli.py      tek giriş noktası (count | plate | face | analyze)
  config.py   config.yaml yükleyici (tüm eşikler burada — kodda magic number yok)
  device.py   cihaz seçimi: MPS > CUDA > CPU
  detect.py   YOLO yükleyici (singleton, model bir kez yüklenir)
  count.py    YOLO + ByteTrack + çizgi geçişi
  plate.py    fast-alpr (tespit + OCR); Apple Silicon'da CPU provider
  face.py     InsightFace (tespit + ArcFace + yaş/cinsiyet)
  store.py    SQLite (runs / count_events / plate_reads / face_events; synced bayrağı)
```

Tüm eşik/parametreler [config.yaml](config.yaml)'de. Çizgi konumu, model boyutu, güven eşikleri, `vid_stride` (kare atlama) oradan ayarlanır.

## Notlar (POC → üretim)

- **Cihaz:** M4'te YOLO MPS'te akıcı; fast-alpr & InsightFace onnxruntime-CPU (POC için yeterli). Üretimde NVIDIA + TensorRT/DeepStream.
- **Plaka OCR doğruluğu:** aynı araç farklı karelerde farklı okunabilir → çok-kareli oylama + TR plaka fine-tune (yapılacak).
- **KVKK:** yüz varsayılanı **anonim** (kimlik yok). İsimli tanıma açık rıza/aydınlatma kapısına bağlı — bkz `.agent-ofis/docs/kvkk-notlari.md`.
- **Donanım/dağıtım:** senaryo-bazlı tablo `.agent-ofis/docs/donanim-mimari.md`.

## Demo videolar

`data/videos/` (repoya girmez). Açık kaynak örnekler: [intel-iot-devkit/sample-videos](https://github.com/intel-iot-devkit/sample-videos).
