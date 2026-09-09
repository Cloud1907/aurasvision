# Sprint planı — taşınabilir, akışkan, kararlı AurasVision (Eylül 2026)

Bağlam: sistem GB10/Linux için yazıldı; artık **Windows veya Linux'ta, farklı
CPU/GPU'larda** kurulacak. Ölçüm tabanı: `docs/denetim-2026-09-05-kararlilik-kaynak.md`
(CPU %99, NVDEC %0, analiz 3-4 fps, "Waiting for stream" 77k). Standart
referansı: `docs/PROMPT-aurasvision.md` denetim listesi (Frigate / Milestone /
TRASSIR / DeepStream).

## 1. Majör düzeltmeler (ürünü taşınabilir ve kararlı yapanlar)

| # | Sorun | Neden majör | Çözüm | Durum |
|---|---|---|---|---|
| M1 | Analiz her kareyi CPU'da ana akıştan (2880×1616) çözüyor; vid_stride decode'u atlamıyor | 6 kamerada makine doygun; 7. kamerada kararlılık biter; video takılır | **Taşınabilir motor** `src/akis_motoru.py`: PyAV donanım decode (cuda/d3d11va/dxva2/qsv/vaapi/videotoolbox, yoksa yazılım) + substream + hedef fps'te örnekleme | **Yapıldı** (Sprint 1) |
| M2 | Kamera başına ayrı YOLO kopyası (6 kopya, 5 GB VRAM) | Küçük GPU'da 7-8 kamerada VRAM biter | Tek model, kameralar tek batch'te; kamera başına yalnız takipçi | **Yapıldı** (akis motoru) |
| M3 | Motor seçimi elle (`engine: ultralytics`/`nvdec`); Windows'ta GB10 yolu sessizce eski yola düşüyordu | Yeni sahada "GPU var ama kullanılmıyor" fark edilmiyor | `src/donanim.py` profil + `engine: auto` (nvdec > akis); panel "Donanım" kartı ve bileşeni | **Yapıldı** |
| M4 | Kamera eklenince go2rtc yeniden başlıyor → tüm kayıt/analiz bağlantıları kopuyor (10054 × 29) | Kayıt kesintisi mevzuat riski | go2rtc stream API ile fark uygulama (PUT/DELETE), YAML yalnız açılış; gözcü restart etmiyor | **Yapıldı** |
| M5 | Telemetri eksik: `dropped` NULL, decode hatası/takılma sayılmıyor | "Video takılıyor" ölçülemez, uzaktan teşhis yok | Heartbeat: dropped, decode_err, reconnects, hwaccel; karoda takılma sayacı; `/api/donanim`; CPU %95+ kırmızı bileşen | **Yapıldı** |
| M6 | count+plate açık kamerada iki RTSP oturumu, iki decode | Plakalı kameralarda yük iki kat | Kamera başına tek decoder; plaka ana akıştan, ikinci kademe olay tetikli | **Yapıldı** (akis motoru) |
| M7 | Analitik hattının ürün testi yok (yalnız kernel testleri) | "Kararlı" iddiası kanıtsız | `tests/test_akis_motoru.py`: sahte decoder + sahte dedektör ile uçtan uca geçiş olayı, kaynak seçimi, donanım profili | **Yapıldı** (ilk katman) |
| M8 | nvdec/TensorRT motoru Windows'ta kurulmuyor | NVIDIA Windows sahalarında en verimli yol kapalı | `setup.ps1`'e isteğe bağlı PyNvVideoCodec + tensorrt + engine export adımı; başarısızsa akis'e düş | Sprint 2 |
| M9 | Kayıt ana akıştan; 6 kamera × 30 gün diske sığmıyor (kota 100 GB, boş 63 GB) | Dolu diskte SQLite yazamaz | `record.use_substream` sahaya göre; kota uyarısı panelde; disk %5 altı kırmızı zaten var | Sprint 2 (config kararı müşteriye ait) |
| M10 | Canlı izleme yalnız MSE; WebRTC kapalı | Yerel ağda gecikme 1-3 sn, MSE tampon salınımı | go2rtc WebRTC'yi aynı-origin vekil üzerinden dene (ICE yerel), MSE yedek kalsın | Sprint 3 |

## 2. Minör düzeltmeler

| # | Sorun | Çözüm | Durum |
|---|---|---|---|
| m1 | Arayüz 11 sekme; operatör 6'sını kullanıyor | Basit görünüm varsayılan (Panel, Canlı, Olaylar, Kayıtlar, Kameralar, Sistem); "Gelişmiş…" ile diğerleri | **Yapıldı** |
| m2 | Panel kamera satırında yalnız fps | düşen kare de gösterilir | **Yapıldı** |
| m3 | `requirements.txt`'te psutil/nvidia-ml-py yok (donanım kartı çalışmaz) | eklendi | **Yapıldı** |
| m4 | go2rtc YAML'da H.264 kaynaklara da ffmpeg yedeği yazılıyor | Zararsız (tetiklenmiyor); sadeleştirme isteğe bağlı | Sprint 3 |
| m5 | `kayit.log` "Invalid argument … returned 22" (segment kapanışı) 23 kez | go2rtc restart kaynaklı; M4 ile büyük ölçüde kalkar; 1 hafta izle | Sprint 2 (izleme) |
| m6 | Test `test_check_citations` (kernel) kırmızı | Ürünle ilgisiz; ayrı ele alınır | Sprint 2 |
| m7 | `AurasVision-Baslat.bat` içine erişim anahtarı gömülü | .env'den okunmalı | Sprint 2 |
| m8 | Windows'ta açılışta otomatik başlatma kurulu değil | Kullanıcı yönetici PowerShell'de `schtasks` — belgelendi | Sprint 2 (doküman) |
| m9 | Sayım doğruluğu TRASSIR ile 0,68 korelasyon; elle sayım yok | 1 saatlik elle etiketli pencere ile kalibrasyon | Sprint 3 |
| m10 | ONVIF Profile M metadata/olay yayını yok | MQTT/ONVIF event köprüsü (webhook zaten var) | Sprint 3 |

## 3. Sprintler

### Sprint 1 — "Makine ne ise o" (bu sprint, uygulandı)
Hedef: aynı kodun Windows/Linux, GPU'lu/GPU'suz makinede kendi kendine doğru
motoru seçmesi; 6 kamerada CPU'nun doygunluktan çıkması; kararlılık sayaçları.

Teslimatlar: M1-M7, m1-m3. Kabul ölçütü: aynı 6 kamerada CPU < %60, NVDEC > %0
veya hwaccel etkin, analiz fps ≥ hedef (5), "Waiting for stream" sıfır, kayıtta
boşluk yok, testler yeşil.

### Sprint 2 — Kurulum ve işletme (1 hafta)
- M8 nvdec/TensorRT isteğe bağlı kurulum (Windows + Linux) ve `setup.sh`/`setup.ps1`
  ortak "donanım kontrolü" adımı (`python -m src.donanim`).
- M9 kayıt kotası/substream kararı ve panelde disk projeksiyonu ("bu hızla N gün").
- m5 izleme, m6 kernel testi, m7 anahtar gömme, m8 açılış belgesi.
- Linux'ta akis motoru vaapi/cuda doğrulaması (bir Linux makinede `hwdevices_available`
  + 30 dk koşu).

### Sprint 3 — Canlı izleme ve standartlar (1-2 hafta)
- M10 WebRTC; karoda gecikme göstergesi.
- m9 sayım kalibrasyonu (elle etiketli 1 saat) ve `docs/olcumler-sayim.md` güncellemesi.
- m10 olay köprüsü (MQTT) — TRASSIR/Milestone'a olay verme.
- m4 YAML sadeleştirme.

## 4. Bu sprintte değişen dosyalar
`src/akis_motoru.py` (yeni), `src/donanim.py` (yeni), `src/worker.py`,
`src/server.py`, `src/store.py`, `config.yaml`, `requirements.txt`,
`windows/AurasVision-Gozcu.ps1`, `web/index.html`, `tests/test_akis_motoru.py`
(yeni), `docs/PROMPT-aurasvision.md`, `docs/denetim-2026-09-05-kararlilik-kaynak.md`.
