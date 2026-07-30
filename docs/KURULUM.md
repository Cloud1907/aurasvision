# AurasVision — Client Kurulum Kılavuzu

> Hedef: müşteri sahasında (edge kutu / GPU'lu mini PC) sıfırdan çalışır kurulum.
> Her adım bu repodaki gerçek dosyalara dayanır; sürüm: main @ 2026-07.

## 0. Donanım ve ön koşullar

| Bileşen | Asgari | Önerilen |
|---|---|---|
| GPU | — (CPU'da çalışır, yavaş) | NVIDIA (RTX / Jetson Orin / GB10 sınıfı) |
| RAM | 8 GB | 16 GB+ |
| Disk | 30 GB | SSD, kayıt saklanacaksa +kamera başına plan |
| OS | Ubuntu 22.04+ | Ubuntu 24.04 |
| Yazılım | Python 3.11, git, Docker + compose plugin | + NVIDIA sürücü & container toolkit |

```bash
sudo apt update && sudo apt install -y python3.11 python3.11-venv git docker.io docker-compose-v2
```

## 1. Kod

```bash
sudo mkdir -p /opt/aurasvision && sudo chown $USER /opt/aurasvision
git clone https://github.com/Cloud1907/aurasvision.git /opt/aurasvision
cd /opt/aurasvision
python3.11 -m venv .venv
.venv/bin/pip install -U pip
.venv/bin/pip install -r requirements.txt
```

GPU makinede (GB10/DGX Spark, aarch64 SBSA) onnxruntime'ı GPU sürümüyle değiştir
(requirements.txt içindeki nota bak):

```bash
.venv/bin/pip uninstall -y onnxruntime
.venv/bin/pip install onnxruntime-gpu --index-url https://pypi.jetson-ai-lab.io/sbsa/cu130
.venv/bin/pip install tensorrt            # detect.model: *.engine kullanılacaksa
```

## 2. Modeller (git'te YOK — ayrı taşınır)

Model ağırlıkları bilinçli olarak repoya girmez (`.gitignore` + manifest yasağı):

- `yolo11s.pt` → scp/USB ile repo köküne kopyala (ya da `ultralytics` ilk koşuda indirir).
- **TensorRT `.engine` dosyası karta özeldir** — başka makineden kopyalama, client GPU'sunda üret:
  ```bash
  .venv/bin/yolo export model=yolo11s.pt format=engine half=True dynamic=True batch=32
  ```
- InsightFace `buffalo_l` paketi ilk çalıştırmada `~/.insightface/` altına kendisi iner (internet gerekir; kapalı ağda klasörü elle taşı).
- GPU yoksa `config.yaml` → `detect.model: yolo11n.pt` yap.

## 3. Yapılandırma (kod değil, iki dosya)

### 3a. `.env` — gizli bilgiler (repoya asla girmez)

```bash
cp .env.example .env && nano .env
```

- `AURAS_TOKEN` — **client kurulumunda ZORUNLU**: set edilince tüm `/api` ve `/media` bearer-token ister, arayüz ilk açılışta anahtarı sorar. Boş bırakılırsa panel şifresizdir.
- `DATABASE_URL` — üretimde Postgres/Timescale (aşağıda). Boş = SQLite (yalnız demo; yedeği yoktur, dosya bozulursa çizgiler/olaylar gider — yaşandı).
- `REDIS_URL` — worker/ingestor hattı için (7/24 sürekli analiz). Yalnız Test ekranı kullanılacaksa boş kalabilir.

### 3b. `config.yaml` — kameralar ve eşikler

- `cameras:` bloğuna client'ın gerçek kameralarını yaz:
  ```yaml
  - id: kasa-1
    name: "Kasa 1"
    source: rtsp://KULLANICI:SIFRE@10.0.0.21:554/Streaming/Channels/102   # substream öner
    tasks: {count: true, plate: false, face: true}
  ```
  (Kamerayı arayüzden de ekleyebilirsin; DB'de saklanır.)
- `server.host: 0.0.0.0` yap (yerel ağdan erişim için) — varsayılan 127.0.0.1'dir.
- Demo video kameralarını sil.
- Eşikler (`detect.conf`, `face.*`, `count.*`) kalibrasyon adımından sonra dokunulur (adım 7).

## 4. Altyapı servisleri (Docker)

```bash
docker compose up -d db redis go2rtc
```

- `db` — Postgres 16 + TimescaleDB (host portu **5433**), şema `db/schema.sql`'den otomatik yüklenir.
  Üretimde `POSTGRES_PASSWORD`'ü compose'da değiştir ve `.env`'deki `DATABASE_URL`'i eşle.
- `redis` — olay veri yolu (worker → ingestor).
- `go2rtc` — canlı izleme fan-out'u. `go2rtc/go2rtc.yaml`'ı elle düzenleme; sunucu kamera listesinden otomatik üretir.
  API'si (1984) **yalnız localhost'a** bağlanır: kimlik doğrulaması yoktur ve tarayıcı ona doğrudan
  bağlanmaz — canlı görüntü uygulama sunucusundaki token korumalı `/api/stream` ucundan vekillenir.
  Operatörlerin ağa açması gereken tek port uygulamanın kendisidir (8000).

## 5. İlk çalıştırma (elle duman testi)

```bash
cd /opt/aurasvision
set -a; source .env; set +a
.venv/bin/python -m src.server        # http://<makine-ip>:8000
```

Tarayıcıdan aç → token'ı gir → **Test ve çalıştır** → kamera seç → **Çalıştır**.
Canlı annotated görüntü + sayaçlar akıyorsa çekirdek çalışıyor demektir. Ctrl-C ile kapat, servisleştirmeye geç.

## 6. Servisleştirme (systemd — kalıcı çalışma)

Hazır unit dosyaları `deploy/` altında:

```bash
sudo cp deploy/aurasvision-server.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now aurasvision-server
systemctl status aurasvision-server     # active (running) görmelisin
```

7/24 sürekli analiz (RTSP kameraları kesintisiz izleme) isteniyorsa worker + ingestor da açılır
(`REDIS_URL` şart):

```bash
sudo cp deploy/aurasvision-worker.service deploy/aurasvision-ingestor.service \
        deploy/aurasvision-recorder.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now aurasvision-worker aurasvision-ingestor aurasvision-recorder
```

> **Kayıt servisi (`aurasvision-recorder`) opsiyonel değildir.** Kamera kaydı saklama
> süresi mevzuat gereği zorunludur (§8); bu servis çalışmıyorsa yükümlülük karşılanmaz.
> Kurulumdan sonra `systemctl is-active aurasvision-recorder` ile doğrula ve izlemeye al.
> Kayıt yolu `output/rec/`, saklama süresi `config.yaml` → `record.keep_days`.

> Unit dosyaları `/opt/aurasvision` yolunu varsayar; farklı yere kurduysan `WorkingDirectory`
> ve `ExecStart` yollarını düzelt. Kod güncellemesinden sonra **daima**
> `sudo systemctl restart aurasvision-server` — eski süreç eski kodu koşturur (klasik tuzak).

## 7. Kamera başına kalibrasyon (KRİTİK — atlama)

Her kamera farklı açı/ışık/zemin demektir. Kurulum günü, kamera başına:

1. **Yüz sayımı doğrulaması:** kameradan 1-2 dakikalık kayıt al, teşhis scriptini koştur:
   ```bash
   .venv/bin/python scripts/face_calib.py /yol/kayit.mp4 output/calib_kamera1
   ```
   Çıktıdaki kırpıntılara bak: taş/duvar/desen "yüz" sayılıyorsa `face.det_min_score` /
   `min_calm_frac` eşiklerini yükselt; aynı kişi bölünüyorsa pairwise matristen
   `face.reid_threshold`'u kalibre et (yorumlarda yöntem yazılı). **İş bitince calib
   klasörlerini sil (KVKK).**
2. **Sayım çizgileri:** arayüz → **Bölgeler** → çizgiyi çiz, A→B yönünü kontrol et, kaydet.
   Bir gün gerçek trafiğe karşı sayıyı elle doğrula (`count.min_track_frames`, `imgsz` ayarı
   config yorumlarında).
3. Kalabalık/uzak sahnede `detect.imgsz: 1280` (GPU maliyeti ~4x — yorumdaki ölçüme bak).

## 8. Güvenlik + KVKK (client sözleşmesi öncesi zorunlu)

- `AURAS_TOKEN` set edilmeden paneli ağa açma.
- Dış ağdan erişim gerekiyorsa doğrudan port açma — reverse proxy + TLS koy (Caddy örneği):
  `caddy reverse-proxy --from auras.client.com --to localhost:8000`
- **KVKK:** yüz analizi biyometrik veri işler. Sistem varsayılanı anonimdir
  (`face.identify: false` — yaş/cinsiyet + sayı, kimliklendirme YOK); isimli tanıma (watchlist)
  ancak client'ın açık rıza/aydınlatma süreciyle açılır. Kare/video KVKK gereği minimum tutulur:
  canlı önizleme yalnız bellekte, analiz videoları `output/`'ta — saklama süresini client
  politikasına bağla ve eski çıktıları temizleyen bir cron ekle.
- **Kanıt görüntüsü (`evidence`, config):** olayın denetlenebilir karşılığı. Bu, "ham görüntü
  saklanmaz" ilkesinden BİLİNÇLİ bir sapmadır; aydınlatma metninde yer almalı. Tür bazında:

  | Tür | Varsayılan | Ne saklanır | Gerekçe |
  |-----|-----------|-------------|---------|
  | `plate` | **açık** | plaka kırpması + bağlam karesi | plaka zaten metin olarak işleniyor; kanıt ALPR'ın asli işlevi ve yanlış okumanın tek denetim yolu |
  | `intrusion` | **açık** | alarm anının karesi | alarmın doğru olup olmadığı ancak görüntüyle teyit edilir |
  | `face` | **kapalı** | — | biyometrik veri; yalnız 512d embedding saklanır, görüntü saklanmaz |

  Dosyalar `output/evidence/<tarih>/` altında tutulur ve `evidence.keep_days` (varsayılan **30 gün**)
  sonunda **otomatik silinir** — ayrıca cron gerekmez. Client daha kısa süre isterse bu değeri düşür;
  kanıt hiç istenmiyorsa `evidence.enabled: false` yap (özellik tamamen kapanır).
  Kanıt görüntülerine erişim `AURAS_TOKEN` ile korunur (`/media/evidence/...`).
- **Üçüncü taraf akış kaynakları (`stream.http_headers`):** bazı CDN/HLS kaynakları Referer gibi
  başlık ister. Bu ayarı yalnız **erişim hakkına sahip olduğun** kaynaklar için kullan; başkasının
  akışını korumasını aşarak kullanmak sözleşme ve mevzuat riski yaratır.
- Postgres yedeği: `pg_dump` cron'u kur (SQLite kullanılıyorsa dosya yedeği — ama üretimde SQLite kullanma).

## 9. Güncelleme

```bash
cd /opt/aurasvision && git pull
.venv/bin/pip install -r requirements.txt      # bağımlılık değiştiyse
.venv/bin/python -m pytest -q                  # yeşil olmadan restart etme
sudo systemctl restart aurasvision-server aurasvision-worker aurasvision-ingestor aurasvision-recorder
```

## 10. Sorun giderme (sahada yaşananlardan)

| Belirti | Sebep / çözüm |
|---|---|
| "Değişiklik görünmüyor" | Eski süreç çalışıyor — `systemctl restart`; sürecin yaşına bak |
| Analiz videosu "kısa" | Kaynak kayıt hasarlı olabilir (NVR AVI'lerinde yaşandı) — gerçek okunabilir kare sayısını ölç, NVR'dan yeniden export et |
| Sahte "yüz"ler (duvar/taş) | Adım 7.1 — `det_min_score` / doku filtreleri kamera bazlı kalibre |
| Aynı kişi 2-3 kez sayılıyor | `face.reid_threshold` kalibrasyonu (matris yöntemi config yorumunda) |
| `database is locked` | SQLite'tasın — Postgres'e geç (adım 4) |
| GPU kullanılmıyor | `onnxruntime-gpu` kurulumu (adım 1) + `nvidia-smi` ile doğrula |
| Panel 401 istiyor | Doğru davranış — `AURAS_TOKEN`'ı gir; token'ı kaybettiysen `.env`'e bak |
