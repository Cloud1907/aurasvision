# AurasVision — Görüntü Analitiği POC

Açık kaynak görüntü işleme: **kişi sayma**, **plaka okuma (ALPR)**, **yüz tespit + anonim demografi**.
Tek videoda hepsi. Geliştirme: MacBook M4 (MPS). Üretim hedefi: Jetson / NVIDIA edge.

## Kurulum

Tek komut: bağımlılıklar, `.env` (rastgele erişim anahtarı), Docker altyapısı,
duman testi ve servisler.

```bash
git clone https://github.com/Cloud1907/aurasvision.git /opt/aurasvision
cd /opt/aurasvision
./setup.sh --systemd
```

Betik bitince **panel adresini ve erişim anahtarını** yazdırır. Anahtarı kaydet —
panele ilk girişte sorulur.

| Seçenek | Ne yapar |
|---|---|
| _(yok)_ | Kurar ve test eder, servisleştirmez (geliştirme) |
| `--systemd` | Servisleri de kurup başlatır — **sahada bunu kullan** |
| `--no-docker` | db/redis/go2rtc başka makinedeyse altyapıyı atlar |
| `--check` | Hiçbir şey kurmaz, mevcut kurulumu denetler |

Betik **tekrar çalıştırılabilir**: var olanı bozmaz, eksik olanı tamamlar.
`.env` varsa dokunmaz (anahtar yeniden üretilseydi tüm istemciler düşerdi).

**Ön koşullar:** Python 3.11+, Docker + compose eklentisi. GPU'lu makinede
NVIDIA sürücüsü. Betik eksikleri baştan söyler.

### Kurulumdan sonra: ilk kamera

Panel → **Kameralar → Kamera ekle** → IP, kullanıcı ve şifreyi gir →
**IP ile sorgula**. ONVIF açıksa kameranın kendi bildirdiği ana akış ve
substream gelir. Olmazsa **Ağı tara** veya **RTSP yolunu dene** (10 marka için
bilinen yollar denenir, yalnız gerçekten açılanlar listelenir).
Kaydetmeden önce **Bağlantıyı test et** — çözünürlük, fps ve canlı kare görmelisin.

> 🏢 **Ayrıntılı saha kılavuzu:** [docs/KURULUM.md](docs/KURULUM.md) — donanım seçimi,
> modeller, kamera kalibrasyonu, kayıt saklama süresi ve KVKK yükümlülükleri.

### Elle kurulum (betiği kullanmadan)

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

Sonuçlar veritabanına yazılır; `--save` ile annotated video `output/` altına çıkar.

**Veritabanı:** `DATABASE_URL` set ise PostgreSQL (TimescaleDB + pgvector), değilse
SQLite (`output/aurasvision.db`) kullanılır. Postgres'i başlatmak için:

```bash
docker compose up -d db redis
export DATABASE_URL=postgresql://auras:auras@localhost:5433/auras
```

**Web arayüzü:** `python -m src.server` → http://127.0.0.1:8000
Erişim anahtarı için `AURAS_TOKEN=gizli` ortam değişkeni set edilir (UI ilk açılışta sorar).

## Sürekli çalışma (Faz 2 — worker mimarisi)

Test ekranı tek seferlik analiz içindir; sürekli izleme worker'la çalışır:

```bash
docker compose up -d db redis go2rtc      # altyapı (go2rtc = canlı izleme)
export DATABASE_URL=postgresql://auras:auras@localhost:5433/auras
export REDIS_URL=redis://localhost:6379/0

python -m src.server     # UI + API (go2rtc config'ini otomatik üretir)
python -m src.ingestor   # Redis → DB yazıcı
python -m src.worker     # analiz — olayları Redis'e yayınlar
```

- Kamera başına görevler (Sayım/Plaka/Yüz) **Kameralar** ekranından açılıp kapanır;
  worker bir sonraki turda otomatik uygular.
- Ölçekleme: `AURAS_CAMERAS=giris,otopark python -m src.worker` ile kameralar
  worker süreçlerine bölünür.
- Kamera sağlığı (heartbeat) Kameralar ekranındaki durum çipinde görünür.

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

## Üretim mimarisi (100 kamera)

Tek GPU'lu makinede ~100 kameraya ölçekleme mimarisi (go2rtc + TensorRT/Savant worker +
Redis Streams + PostgreSQL/TimescaleDB/pgvector), tablo şeması ve faz planı:
**[docs/mimari-100-kamera.md](docs/mimari-100-kamera.md)** (karar özeti: `.agent-ofis/decisions/0002`).

## Notlar (POC → üretim)

- **Cihaz:** M4'te YOLO MPS'te akıcı; fast-alpr & InsightFace onnxruntime-CPU (POC için yeterli). Üretimde NVIDIA + TensorRT/DeepStream.
- **Plaka OCR doğruluğu:** aynı araç farklı karelerde farklı okunabilir → çok-kareli oylama + TR plaka fine-tune (yapılacak).
- **KVKK:** yüz varsayılanı **anonim** (kimlik yok). İsimli tanıma açık rıza/aydınlatma kapısına bağlı — bkz `.agent-ofis/docs/kvkk-notlari.md`.
- **Kanıt görüntüsü:** plaka ve ihlal olayları kanıt karesiyle saklanır (`evidence` config), yüz için KAPALI; dosyalar `evidence.keep_days` (30 gün) sonunda otomatik silinir. Ayrıntı: [docs/KURULUM.md §8](docs/KURULUM.md).
- **Donanım/dağıtım:** senaryo-bazlı tablo `.agent-ofis/docs/donanim-mimari.md`.

## Demo videolar

`data/videos/` (repoya girmez). Açık kaynak örnekler: [intel-iot-devkit/sample-videos](https://github.com/intel-iot-devkit/sample-videos).
