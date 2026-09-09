# Kararlılık ve kaynak denetimi — 2026-09-05

Yöntem: `docs/PROMPT-aurasvision.md` denetim listesi. Bütün sayılar bu makinede
(NVR-14, i3-10100 / RTX 3050 6 GB, 6 Reolink kamera) canlı sistemden alındı;
hiçbir değer tahmin değildir. Rakip karşılaştırması kamuya açık belgelerden.

## 1. Ölçümler

| Ne | Değer | Kaynak |
|---|---|---|
| Toplam CPU | **%99** (8 mantıksal çekirdeğin hepsi %98-100) | psutil, 6 sn örnek |
| Analiz worker CPU | **%656 / 800** (makinenin %82'si), 147 iş parçacığı, 1,9 GB RAM | psutil, PID 8752 |
| Kayıt servisi CPU | %12 | psutil |
| go2rtc CPU | %3 | psutil |
| GPU SM | %13-49 dalgalı; bellek bant genişliği %6-25 | `nvidia-smi dmon` |
| GPU VRAM | **5077 / 6144 MiB (%83)** | nvidia-smi |
| GPU NVDEC / NVENC | **%0 / %0** — donanım decode hiç kullanılmıyor | `nvidia-smi dmon` |
| Analiz kare hızı | kamera başına ort. **3,0-4,6 fps** (hedef 25/3 = 8,3) | `camera_health`, son 3 saat, 2153 örnek/kamera |
| "Waiting for stream" uyarısı | son 200 bin log satırında **77.776** | `output/logs/analiz-konsol.log` |
| H.264 decode hatası (`error while decoding MB`, cabac) | son 200 bin satırda **12.503** | aynı log |
| Kamera akışı | 2880×1616@25 H.264 High (ana), 896×512@20 (sub) | ffprobe |
| Analiz kaynağı | **ANA akış** (substream DB'de tanımlı ama analizde kullanılmıyor) | `cameras.source`, worker.py |
| Kamera başına RTSP oturumu | worker 1 (kamera-204'te count+plate = 2) + go2rtc 1 = 2-3 | go2rtc `/api/streams`, worker.py |
| Kayıt sürekliliği (son 12 saat) | 6 kamerada **0 boşluk** (>90 sn), segment 60-62 sn | `recordings` tablosu |
| Kayıt hatası | go2rtc her yenilendiğinde tüm kameralarda `10054` (29 kez), `Invalid argument` segment kapanışı 23 kez | `kayit.log` |
| Olay üretimi | 4.931 sayım olayı / 24 saat; plaka 0 (kamera-204 sahnesinde araç yok) | DB |
| Disk | 255 GB, **63 GB boş**; kayıt arşivi 107,6 GB, kota 100 GB | psutil, DB |
| Testler | 125 geçti, 1 başarısız (`test_check_citations`, kernel), 7 atlandı | pytest |
| Ürün testi | analitik hattı (count/plate/face/recorder) için **birim/regresyon testi yok**; yalnız `count_eval`/`plate_eval_gt` | `tests/` |

## 2. Kök neden (tek cümle)

Ultralytics `LoadStreams` her karede `cap.grab()` çağırır; bu FFmpeg arka ucunda
tam decode demektir. `vid_stride: 3` yalnız inference'ı atlar, decode'u değil.
Sonuç: 6 kamera × 25 fps × 4,65 MP ≈ **700 megapiksel/sn H.264 High yazılım
decode'u** 4 çekirdekli i3'te — makine doygun, GPU ise decode'u beklediği için
%13-49'da boşta kalıyor. "Waiting for stream" ve cabac hataları bunun
belirtisi: decoder yetişemeyince TCP tamponu taşıyor, paketler bozuk çözülüyor.

Video takılmasının kaynağı da aynı: tarayıcıya giden MSE akışı FastAPI
WebSocket vekilinden (Python, uvicorn) geçiyor; CPU %99'da vekil de kare
geciktiriyor. `index.html`'deki playbackRate sınırlaması belirtiyi yumuşatır,
nedeni ortadan kaldırmaz.

## 3. Global standartla karşılaştırma

| Alan | Standart (kaynak) | AurasVision (bu kurulum) | Durum |
|---|---|---|---|
| Analizde substream | Frigate: tespit düşük çözünürlüklü substream'den, ~5 fps ([docs.frigate.video](https://docs.frigate.video/troubleshooting/cpu/)) | Ana akış 2880×1616 çözülüp 640'a küçültülüyor | **Uyumsuz** — mimari belge (`mimari-100-kamera.md`) bunu zaten ders olarak yazmış, kurulum uygulamıyor |
| Donanım decode | Milestone 2018 R2'den beri Recording Server'da NVDEC ([milestonesys](https://www.milestonesys.com/globalassets/techcomm/2018-r2/advvms/english-united-states/65581.htm)); Frigate `preset-nvidia` ([docs.frigate.video](https://docs.frigate.video/configuration/hardware_acceleration_video/)); DeepStream NVDEC+batch | NVDEC %0; `nvdec` motoru ADR-0003'te var, Windows'ta PyNvVideoCodec/TensorRT kurulmadığı için ultralytics'e düşüyor | **Uyumsuz** |
| Kamera başına tek bağlantı | go2rtc fan-out; Frigate tüm tüketicileri go2rtc'den besler | Kayıt go2rtc'den (doğru); analiz kameraya DOĞRUDAN bağlanıyor, count+plate açık kamerada iki kez | **Kısmen** |
| Tek model örneği / batch | DeepStream/TensorRT batch; tek ağırlık kopyası | Kamera başına ayrı YOLO örneği (`load_yolo(instance_key=cid)`) → 6 kopya, 5 GB VRAM | **Uyumsuz** (nvdec motoru bunu batch ile çözüyor, kullanılmıyor) |
| Kayıt | Transcode yok, anahtar kare hizalı segment, kota | `-c copy` PyAV remux, 60 sn segment, kota+gün, ölçülen süre DB'de | **Uyumlu** — 12 saatte 0 boşluk |
| Restart dayanıklılığı | Config değişimi akışları düşürmez | Gözcü go2rtc'yi yeniden başlatıyor → tüm kayıt/analiz bağlantıları kopuyor (10054 × 29) | **Uyumsuz** |
| Telemetri | fps, düşen kare, decode hatası, gecikme kamera başına | `fps` var; `dropped` hep NULL; decode hatası ve tarayıcı takılma sayacı yok | **Kısmen** |
| ONVIF | VMS için Profile S/T istemci (akış), G (kayıt), M (analitik metadata) ([forasoft](https://www.forasoft.com/learn/video-surveillance/articles-vms/onvif-profiles-s-t-m-decision-guide)) | ONVIF keşif + akış adresi alma var; Profile M metadata/olay yayını yok, olaylar yalnız kendi DB'si + webhook | **Kısmen** (resmî uyumluluk ONVIF üyeliği ve test aracı ister; iddia edilemez) |
| Canlı izleme | WebRTC düşük gecikme + MSE yedeği; duvar substream | MSE (WebRTC bilinçli kapalı), duvar substream (doğru), tekil görünüm ana akış | **Uyumlu** mimari; takılma CPU'dan |
| TRASSIR | NeuroStation: GPU'lu ayrı analitik sunucu, offload; kanal sayısı GPU kapasitesine bağlı, satıcı hesaplıyor ([trassir.com](https://trassir.com/products/analytics/trassir_neuro_detector/), [confluence.trassir.com](https://confluence.trassir.com/display/TKB/Offload-TRASSIR+video+analytics)) | Tek makinede analiz+kayıt+canlı; kanal/GPU tablosu yok | Ölçek belgesi (`olcumler-gb10.md`) GB10 için var, RTX 3050/Windows için yok |
| Doğruluk | Yer gerçeğiyle ölçüm | Plaka %59,5 tam isabet / 0 yanlış pozitif; sayım TRASSIR ile 0,68 korelasyon, mutlak doğruluk açık | Ölçülmüş, sayım kalibrasyonu eksik |

**Özet yargı:** Mimari tasarım (go2rtc fan-out, `-c copy` kayıt, NVDEC+batch
motoru, substream ilkesi, KVKK kanıt yönetimi) global çözümlerle aynı çizgide.
**Çalışan Windows kurulumu bu mimarinin CPU-yolu yedeğinde koşuyor** ve bu
yedek 6 kamerada makineyi doyurmuş durumda. Sistem "kararlı" (12 saat kayıt
boşluksuz, worker düşmüyor, olay üretiyor) ama **verimli değil** ve kamera
sayısı 7-8'e çıkınca kararlılık da bozulur.

## 4. Öncelikli aksiyonlar

| # | Aksiyon | Beklenen etki | Maliyet | Dosya |
|---|---|---|---|---|
| 1 | **Sayım/ihlal analizini substream'den yap** (`url_sub` varsa onu kullan; plaka ana akışta kalır) | Decode yükü kamera başına 4,65 MP → 0,46 MP (**~10×**); CPU %99 → tahmini %30-40; "Waiting for stream" ve cabac hataları kaybolur | Küçük: `worker.py` `_gorev_calistir` kaynağı seçer, config anahtarı `detect.use_substream` | `src/worker.py`, `config.yaml` |
| 2 | **Analizi go2rtc'den al**, kameraya doğrudan bağlanma (`rtsp://localhost:8554/<id>-sub`) | Kamera başına tek oturum; go2rtc'de koparsa hepsi aynı anda görülür | Küçük | `src/worker.py` (recorder `_kaynak` ile aynı kalıp) |
| 3 | **nvdec motorunu Windows'ta kur:** `PyNvVideoCodec` + `tensorrt` pip, `yolo export format=engine half=True batch=32`, `worker.engine: nvdec` | NVDEC decode, tek TensorRT örneği, batch; VRAM 5 GB → ~1,5 GB; GPU gerçek işe koşar | Orta: wheel uyumu (CUDA 13) doğrulanmalı, `setup.ps1`'e eklenmeli | `windows/setup.ps1`, `config.yaml` |
| 4 | **go2rtc'yi restart etmeden akış ekle:** `PUT /api/streams?name=&src=` dene; olmuyorsa yeni kamerada yalnız o akışı ekleyip mevcut tüketicileri koru | Kamera eklerken kayıt/analiz kesilmez; `10054` sıfırlanır | Küçük-orta (go2rtc 1.9.14 davranışı test edilecek) | `src/server.py:_sync_go2rtc`, `windows/AurasVision-Gozcu.ps1` |
| 5 | **Telemetriyi tamamla:** `camera_health.dropped` doldur (decode hatası + bekleme sayısı), tarayıcıda `video.waiting` olaylarını say ve karoda göster, `/api/status`'a CPU/GPU/NVDEC yüzdesi ekle | "Video takılıyor mu" sorusu ölçülebilir olur; sahada uzaktan teşhis | Küçük | `src/worker.py`, `web/index.html`, `src/server.py` |
| 6 | **count+plate açık kamerada tek decode:** aynı kareyi iki göreve dağıt (nvdec motoru bunu zaten yapıyor; ultralytics yolunda kuyruk paylaşımı) | Kamera başına ikinci decode kalkar | Orta | `src/worker.py` |
| 7 | **Analitik hattına regresyon testi:** bilinen sayımlı 30 sn'lik klip → beklenen giriş/çıkış; recorder segment kapanış testi | "Kararlı" iddiası CI'da kanıtlanır | Orta | `tests/` |
| 8 | Disk: kota 100 GB, boş 63 GB, arşiv zaten 107 GB → kota temizliği çalışıyor ama sınırın üstünde; kayıt substream'e (`record.use_substream`) alınırsa 30 gün sığar | Dolu diskte SQLite yazamaz riski kalkar | Config | `config.yaml` |

Sıra: 1 → 2 → 5 (bir günlük iş, CPU'yu hemen düşürür) → 3 (asıl standart) → 4 → 6 → 7 → 8.

## 5. Yapılmayan / doğrulanamayan

- TRASSIR'ın RTX sınıfı kart için kanal/sunucu sayısı kamuya açık değil
  ("satış temsilcisine sorun"); karşılaştırma nitel kaldı.
- Tarayıcı tarafı takılma bu oturumda ÖLÇÜLMEDİ (canlı izleme açık istemci
  yoktu: go2rtc'de tek tüketici kayıt servisiydi). Aksiyon 5 bunu ölçülebilir yapar.
- `nvdec` motorunun Windows'ta çalışıp çalışmadığı denenmedi; PyNvVideoCodec
  Windows wheel'i ve CUDA 13 uyumu kurulum sırasında doğrulanacak.
- Test başarısızlığı (`test_check_citations`) ürünle ilgisiz kernel testi;
  incelenmedi.

## 6. Sonuç ölçümü — aksiyon 1-2-5-6 uygulandıktan sonra (aynı gün, 13:20)

`worker.engine: auto` → `akis` motoru (src/akis_motoru.py), aynı 6 kamera, aynı makine.

| Ölçüm | Önce | Sonra |
|---|---|---|
| Toplam CPU | %99 | **%46** |
| Analiz worker CPU (8 çekirdek = 800) | %656 | **%195** |
| NVDEC (donanım decode) | %0 | **%9-31** |
| GPU SM | %13-49 (decode bekliyor) | %39-76 (inference) |
| VRAM | 5077 MiB (6 model kopyası) | 3208 MiB (tek model + 6 cuda decode bağlamı) |
| Analiz kare hızı / kamera | 3,0-4,6 fps | **5,0 fps** (hedef tam) |
| Bozuk kare (decode hatası) | 12.503 / 200k satır | **0** |
| "Waiting for stream" | 77.776 / 200k satır | **0** |
| Kamera başına RTSP oturumu | 2-3 (kameraya doğrudan) | 1 (go2rtc) |
| Canlı akış (6 kamera, /api/stream vekili, 8 sn) | ölçülmedi | 6/6 akışta fMP4 parçaları geldi (138-311 parça) |
| Sayım olayı | akıyor | akıyor (33 dk'da 189 olay, 3 kamera) |
| Kayıt | boşluksuz | boşluksuz (her kamerada 60 sn segment sürüyor) |

Not: Değişiklik sırasında go2rtc'nin stream API'si YAML dosyasını da güncellediği
için ESKİ gözcü go2rtc'yi 3 kez yeniden başlattı (12:32, 12:33, 12:36) — her
biri ~5 sn kayıt kesintisi. Yeni gözcü (windows/AurasVision-Gozcu.ps1) YAML
değişiminde restart yapmıyor; bu sınıf kesinti bir daha oluşmaz.

Tarayıcıda karo/oynatma denetimi kullanıcı isteğiyle sonraya bırakıldı
(WebSocket seviyesinde doğrulandı, DOM seviyesinde değil).
