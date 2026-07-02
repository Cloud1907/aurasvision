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

`yolo export model=yolo11s.pt format=engine half=True` (32 sn sürdü);
config: `detect.model: yolo11s.engine`.

### Maksimum verim (dosya kaynak, 720p, vid_stride 3) — taban ile karşılaştırma

| akış | toplam işlenen FPS (TRT s) | taban (PyTorch n) | kazanım | GPU util % | CPU % |
|---|---|---|---|---|---|
| 1 | 125.4 | 109.7 | 1.14× | 18 | 9.6 |
| 8 | **268.0** | 124.1 | **2.16×** | 42 | 29.3 |
| 16 | 224.7 | 102.0 | 2.20× | 34 | 29.5 |

Not: TRT'de daha BÜYÜK model (s > n) çalışırken bile 2.2× verim. 8→16 thread'de
düşüş sürüyor → Python thread modeli tavanı; Faz 3 batch pipeline'ın gerekçesi.

### RTSP keep-up, 16 akış (TRT)

| akış | işlenen FPS ort/min | toplam | GPU util ort/maks % | CPU % |
|---|---|---|---|---|
| 16 | 1.6 / 1.1 | 26.0 | 5 / 22 | 3.3 |

### İkinci kademe: ONNX Runtime CUDA EP (onnxruntime-gpu 1.24, sbsa/cu130)

| model | CPU ms/kare | CUDA ms/kare | kazanım |
|---|---|---|---|
| InsightFace det_10g (640) | 65 | 14.2 | 4.6× |
| InsightFace tam pipeline (det+attrs) | — | 6.3 | — |
| fast-alpr (det+OCR) | 17.6 | 7.3 | 2.4× |

Kurulum notu: PyPI `onnxruntime` (CPU) ile GPU paketi aynı modül yolunu paylaşıyor —
önce `pip uninstall onnxruntime`, sonra `pip install onnxruntime-gpu
--index-url https://pypi.jetson-ai-lab.io/sbsa/cu130`. CUDA EP, cuDNN 9'u dlopen
yolunda arar; venv'deki pip `nvidia-cudnn-cu13` kütüphaneleri `src/device.py
_preload_cuda_libs()` ile RTLD_GLOBAL önden yüklenir.

### imgsz 640 vs 1280 (doğruluk/hız, videoya eşit dağılmış 80 kare)

| video | model@imgsz | ort. kişi/kare | maks | ms/kare |
|---|---|---|---|---|
| people-detection | yolo11n.pt@640 | 0.69 | 4 | 3.4 |
| people-detection | yolo11s.engine@640 | 0.70 | 4 | **2.2** |
| people-detection | yolo11s_1280.engine@1280 | 0.69 | 3 | 7.5 |
| store-aisle | yolo11n.pt@640 | 3.31 | 5 | 3.2 |
| store-aisle | yolo11s.engine@640 | 3.40 | 5 | **2.3** |
| store-aisle | yolo11s_1280.engine@1280 | 3.50 | 6 | 7.5 |

**Karar:** demo sahnelerinde (yakın/orta mesafe) 1280 kazandırmıyor (+%3 tespit,
3.4× GPU maliyeti). Varsayılan `imgsz: 640` kalır; uzak/kalabalık sahneler için
`yolo11s_1280.engine` üretilmiştir — kamera bazlı override (`cameras.tasks` JSONB)
ile seçilir. (Config'teki crowd_meydan notu — n@640=1 vs s@1280=10 — uzak plan
meydan sahnesi içindir; böyle kamera geldiğinde 1280 gerekir.)

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
