---
title: "ADR-0003 — GB10 GPU motoru: Savant yerine PyNvVideoCodec+TensorRT pipeline"
type: decision
status: accepted
date: 2026-07-02
topics: [gb10, dgx-spark, savant, deepstream, nvdec, tensorrt, sbsa, faz3]
tags: [decision/accepted]
aliases: [adr-0003, gb10-gpu-motoru, nvdec-pipeline]
provenance:
  root: external_doc   # WebSearch/WebFetch: Savant/DeepStream SBSA uyumluluk taraması (2026-07-02)
---

# ADR-0003 — GB10 GPU motoru: Savant yerine PyNvVideoCodec + TensorRT pipeline

## Bağlam

Faz 3 planı (ADR-0002) worker motorunu **Savant (DeepStream)** ile değiştirmekti.
Hedef makine FusionXpark GB10 (NVIDIA DGX Spark OEM): aarch64 **SBSA** (Jetson/L4T
DEĞİL), Blackwell sm_121, CUDA 13.0, 128 GB birleşik bellek, **1× NVDEC / 1× NVENC**.

Araştırma bulguları (birincil kaynaklar; 2026-07-02):

1. **Savant GB10'da çalışmıyor.** Yayınlanan imajlar yalnız `linux/amd64` ve
   `-l4t` (Jetson, CUDA 12.6 + sm_87 + JetPack host-mount bağımlı). SBSA varyantı
   yok; GitHub'da "DGX Spark/GB10/SBSA/sm_121" için 0 sonuç; maintainer DS 8+
   geçişine taahhüt vermedi (issue #1156). Son sürüm v0.6.0 = DeepStream 7.1
   (7.1'in SBSA desteği yalnız GH200 sınıfı, Blackwell yok).
2. **DeepStream tarafında resmî yol var ama maliyetli:** `nvcr.io/nvidia/
   deepstream:9.0-triton-sbsa-dgx-spark` (native kurulum desteklenmiyor,
   yalnız konteyner). Bilinen Spark sürtünmeleri: pyds'in `-DIS_SBSA=on` ile
   yeniden derlenmesi, VIC yok (`compute-hw=1` zorunlu), nvinfer ön-işleme
   sorunları, appsrc/CUDA `createTexture` hatası. Python iş mantığımızı
   (BusStore, çizgi/bölge, oylama) DS eklenti modeline taşımak büyük iş.
3. **PyNvVideoCodec + TensorRT rotası bu makinede ÖLÇÜMLE doğrulandı:**
   - NVDEC decode: tek akış 2751 kare/sn, paralel toplam **~3900 kare/sn @720p**
     (100 kam × 5 fps = 500 kare/sn ihtiyacın 7.8 katı); 32 eşzamanlı decoder
     oturumu sorunsuz; DLPack ile sıfır-kopya torch tensörü.
   - TensorRT YOLO11s FP16: thread modelinde bile 268 infer/sn (bkz.
     `docs/olcumler-gb10.md`); batch ile üstü açık.
   - onnxruntime-gpu 1.24 CUDA EP (sbsa/cu130) plaka/yüz için çalışıyor.
   - Kısıt: PyNvVideoCodec demuxer'ı RTSP'de TCP transport'a düşemiyor
     (`461 Unsupported transport` → segfault). Çözüm: akışlar go2rtc'den
     **HTTP MPEG-TS** (`/api/stream.ts?src=...`) olarak alınır — go2rtc zaten
     mimarinin ingest katmanı, kamera başına tek bağlantı korunur.

## Karar

Faz 3 motoru **Savant değil**, worker içinde yaşayan **özel GPU pipeline**:

```
go2rtc HTTP-TS → PyNvVideoCodec (NVDEC, kamera başına oturum, son-kare-kazanır)
  → hareket ön-filtresi (GPU, Y-düzlemi fark)
  → NV12→RGB + letterbox (torch, sıfır-kopya)
  → TEK batch TensorRT YOLO11s FP16 (tüm kameraların kareleri)
  → kamera başına BoT-SORT + çizgi/bölge mantığı
  → BusStore (Redis Streams — sözleşme AYNEN korunur)
plaka/yüz: olay-tetikli ikinci kademe (ORT CUDA EP), her karede değil
```

- Config anahtarı: `worker.engine: ultralytics | nvdec` — eski motor fallback
  olarak kalır (Mac/CPU geliştirme + arıza durumu).
- `add_count_event / add_plate_event / add_face_event` imzaları ve
  `db/schema.sql` değişmez; UI/API'ye dokunulmaz.

## Alternatifler (neden değil)

- **Savant:** bu donanımda hiçbir yayınlanmış imajı çalışmıyor; SBSA yol
  haritası yok. Çıkarsa yeniden değerlendirilir (motor değişimi BusStore
  sözleşmesi sayesinde lokal kalır).
- **Çıplak DeepStream 9.0 SBSA konteyneri:** resmî ve en olgun çoklu-akış
  altyapısı; ama iş mantığı taşıma maliyeti + pyds/SBSA sürtünmeleri +
  konteyner-içi worker dağıtım karmaşası, kazanılacak verime değmiyor —
  ölçümler mevcut ihtiyacın (100 kam) özel pipeline ile karşılandığını
  gösteriyor. 500+ kamera / çoklu-GPU gündeme gelirse yeniden aday.
- **CPU decode (mevcut):** çalışıyor (~800 kare/sn) ama Grace çekirdeklerini
  yiyor; NVDEC varken israf. cv2 tabanlı decode, nvdec motorunda dosya/uyumsuz
  kaynak fallback'i olarak kalır.

## Kapasite notu

Tek NVDEC ölçülen tavan ~3900 kare/sn @720p → substream 720p/5fps ile ~780 kamera
decode tavanı; gerçek sınır YOLO inference bütçesi (batch ölçümleri Aşama 3.3'te,
`docs/olcumler-gb10.md`). 1080p main-stream analizi bu tavanı ~2.5× düşürür —
ADR-0002'deki "substream zorunlu" kuralı geçerli.

## İlgili

`docs/mimari-100-kamera.md` · `docs/olcumler-gb10.md` · [[decisions/0002-100-kamera-uretim-mimarisi]]
