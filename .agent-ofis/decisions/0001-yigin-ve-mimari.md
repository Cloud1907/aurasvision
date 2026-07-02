---
title: "ADR-0001 — Açık kaynak yığın & senaryo-bazlı dağıtım mimarisi"
type: decision
status: accepted
date: 2026-06-29
topics: [yüz, plaka, sayma, reid, retail, donanım, kvkk, poc]
tags: [decision/accepted]
related_runs: [[runs/2026-06-29T18-15-11-9c58]]
aliases: [adr-0001, yigin-karari, mimari-karari]
provenance:
  root: external_doc          # WebSearch ile doğrulanmış araç/vendor karşılaştırması (2026-06)
---

# ADR-0001 — Açık kaynak yığın & senaryo-bazlı dağıtım mimarisi

## Bağlam
Görüntü işleme platformu kurulacak: yüz tanıma, plaka okuma, kişi sayma ve retail analitiği.
Geliştirme makinesi MacBook M4 (16GB, arm64, MPS; CUDA yok). Üretim çoğunlukla edge.

## Karar — Açık Kaynak Yığın
| İş | Seçilen araç | Gerekçe |
|---|---|---|
| Tespit + takip + sayma | **Ultralytics YOLO + ByteTrack** | Tek çatı; MPS/CoreML + CUDA + TensorRT export. |
| Yüz tanıma | **InsightFace (ArcFace)** üretim · **CompreFace** hızlı başlangıç | ArcFace endüstri std (LFW ~%99.86). CompreFace = Docker+REST kolay POC. |
| Plaka (ALPR) | **fast-alpr** · alternatif Plate Recognizer / YOLO+EasyOCR | Modern, detektör+OCR değiştirilebilir; TR için fine-tune. |
| Ölçek/üretim runtime | **NVIDIA DeepStream + TensorRT** | Çok-kameralı IVA standardı (GStreamer pipeline). NVIDIA-only. |

## Karar — Senaryo-Bazlı Dağıtım Mimarisi
1. **Erişim kontrolü (10 kapı, <500 kişi, kendi yazılımı):** kapı başına **edge cihaz** (Jetson Orin Nano),
   tanıma edge'de; merkez yalnız kullanıcı DB + panel + log. Eşleştirme cosine/pgvector. **Liveness şart.**
2. **Çok-kameralı takip/rota (Re-ID):** yüz=embedding benzerliği · plaka=düz metin eşitliği · vücut=Person Re-ID.
   Global ID + kamera_id + timestamp → rota. Zorluk: kör nokta, ID switch, eşik kalibrasyonu.
3. **Offline saha (2 kamera, ara sıra internet):** saha başına **Jetson Orin Nano + SSD + 4G**,
   yerel SQLite, **store-and-forward** senkron (synced bayrağı). Tanıma internete bağımsız.
4. **Retail mağaza (10 kamera):** **1× RTX 4080 makine** veya **Jetson AGX Orin**.
   Isı haritası + footfall + **anonim demografi** + kıyafet analizi. DeepStream batch, FPS 5-10, görüntü saklama yok.

Tüm senaryolarda **geliştirme/POC = MacBook M4** (küçük modeller, MPS). Üretim = Jetson/NVIDIA.

## Sonuçlar (consequences)
- DeepStream/TensorRT Mac'te koşmaz → POC'ta PyTorch-MPS / onnxruntime-CPU; prod'da CUDA'ya geçiş planlı.
- Plaka eşleştirme metin tabanlı olduğu için yüz Re-ID'den daha kesin; risk OCR doğruluğunda.
- KVKK: edge-first + görüntü saklamama tasarımı hem maliyet hem uyum kazandırır → bkz [[docs/kvkk-notlari]].

## Alternatifler (neden değil)
- Hazır ticari (Hikvision/Genetec/Verkada): hızlı ama kendi yazılım hedefiyle çelişir; Hikvision/Dahua'da
  ihracat/uyum riski (Section 889). Kendi açık-kaynak yığını seçildi.
- Merkezi-tek-sunucu (tüm akış buraya): tek hata noktası + pahalı GPU + ağ yükü → edge-first tercih edildi.

## İlgili
Donanım/maliyet tam tablo: [[docs/donanim-mimari]] · KVKK: [[docs/kvkk-notlari]]
