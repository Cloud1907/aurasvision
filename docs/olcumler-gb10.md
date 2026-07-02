# GB10 Ölçümleri — Faz 3 taban çizgisi ve GPU kazanımları

> Makine: FusionXpark GB10 (NVIDIA DGX Spark OEM) — GB10 Grace Blackwell Superchip,
> 20 çekirdek ARM Grace CPU (aarch64/SBSA), Blackwell GPU (sm_121), 128 GB birleşik bellek.
> Yazılım: DGX OS (Ubuntu 24.04.4), sürücü 580.159.03, CUDA 13.0, Python 3.12.3,
> torch 2.12.1+cu130 (PyPI aarch64 wheel'i CUDA'lı geliyor), ultralytics 8.4.84,
> TensorRT 11.1.0 (pip, cu13), onnxruntime 1.27 (CPU).
> Not: python3.11 Ubuntu 24.04'te yok; sistem 3.12 ile kuruldu (tüm bağımlılıklar uyumlu).

## Ölçüm yöntemi

- `scripts/bench_fps.py`: akış başına ayrı thread + ayrı YOLO örneği + kendi
  `cv2.VideoCapture` döngüsü; `config.yaml` ile aynı parametreler
  (conf 0.35, iou 0.5, imgsz 640, vid_stride 3, BoT-SORT).
- **RTSP keep-up:** go2rtc `exec:ffmpeg -re -stream_loop -1` ile döngülü akışlar
  (`bench0..bench15`), kaynak = 1280×720 @ 5 fps (mimarideki substream hedefi).
  Beklenen işlenen FPS ≈ 5/vid_stride ≈ 1.7/akış; düşükse yetişemiyor demektir.
- **Maksimum verim:** aynı iş parçacığı yapısı, kaynak = yerel dosya (`-re` yok),
  decode+inference tam gaz — kapasite ekstrapolasyonu buradan.
- GPU util: NVML (`nvidia-ml-py`); GB10 birleşik bellekte ayrı VRAM sayacı yok.
- Her tur 60 sn, warmup ölçüm dışı.

## Aşama 1 — Taban çizgisi (Ultralytics-PyTorch CUDA, yolo11n.pt @640)

### RTSP keep-up (720p/5fps kaynak, vid_stride 3 → hedef ~1.7 FPS/akış)

| akış | işlenen FPS ort/min | toplam işlenen | toplam decode | GPU util ort/maks % | CPU % |
|---|---|---|---|---|---|
| 1 | 1.7 / 1.7 | 1.7 | 5.2 | 1 / 2 | 0.9 |
| 4 | 1.4 / 1.2 | 5.5 | 16.6 | 1 / 27 | 2.1 |
| 8 | 1.5 / 1.1 | 12.1 | 36.3 | 3 / 28 | 2.6 |
| 16 | 1.6 / 1.1 | 25.5 | 76.6 | 8 / 31 | 4.2 |

**Yorum:** 16 eşzamanlı 720p/5fps akışta bile mevcut motor gerçek zamanı korur
(işlenen ≈ decode/3, kayıp yok). Ortalamanın 1.7 altında kalması kaynak tarafı:
`ffmpeg -stream_loop` döngü sınırında kısa boşluk veriyor (248 karelik dosya ~50 sn'de
bir sarıyor). GPU %8 ortalama → birinci kademede bolca yer var; asıl maliyet CPU
decode (Grace çekirdekleri, akış başına ~%0.3).

### Maksimum verim (dosya kaynak, 720p, vid_stride 3)

| akış | işlenen FPS ort/min | toplam işlenen | toplam decode | GPU util ort/maks % | CPU % |
|---|---|---|---|---|---|
| 1 | 109.7 | 109.7 | 329.0 | 23 / 28 | 9.8 |
| 8 | 15.5 / 15.2 | 124.1 | 372.2 | 29 / 35 | 19.9 |
| 16 | 6.4 / 6.3 | 102.0 | 306.1 | 25 / 30 | 19.4 |

**Yorum:** Tepe verim ~124 inference/sn + ~372 kare/sn CPU decode (8 thread'de).
16 thread'de toplam DÜŞÜYOR (Python GIL + thread çekişmesi) — thread-başına-kamera
modeli 100 kameraya ölçeklenmez; Faz 3'ün batch pipeline gerekçesi ölçümle doğrulandı.
Kaba kapasite (mevcut motor): 100 kam × 5 fps ÷ stride 3 ≈ 167 infer/sn gerekir →
~%35 açık var; decode tarafı 500 kare/sn gerekir → ~%25 kapasite açığı.

## Aşama 2 — TensorRT engine (yolo11s.engine, FP16 @640)

Smoke test: tek akış `predict` 279 FPS (PyTorch yolo11s.pt: ~180 FPS).

(tablolar eklenecek)

## Notlar / bulgular

- **PyPI torch aarch64 wheel'i CUDA 13 ile geliyor** (`2.12.1+cu130`), ayrı index gerekmedi;
  `torch.cuda.is_available()=True`, GB10 sm_121 tanınıyor, matmul doğrulandı.
- **onnxruntime-gpu PyPI'da aarch64 için YOK**; NVIDIA'nın `pypi.jetson-ai-lab.io/sbsa/cu130`
  indeksinde `onnxruntime_gpu-1.24.0-cp312-linux_aarch64.whl` mevcut (Aşama 2.2'de kullanılacak).
- **`load_yolo` lru_cache yarışı:** iki kamera thread'i aynı YOLO örneğini paylaşınca
  BoT-SORT GMC'ye farklı çözünürlükte kareler karışıyor
  (`prevPyr.size() == nextPyr.size()` assert'i, worker logunda). Aşama 2'de düzeltildi.
- go2rtc, demo dosyaları `exec:ffmpeg -re -stream_loop -1 ... -c copy` ile RTSP'ye çevirir;
  16 eşzamanlı producer CPU'da sorunsuz (yalnız kopya, re-encode yok).
