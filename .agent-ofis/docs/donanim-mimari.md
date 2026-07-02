---
title: "Donanım & Dağıtım Mimarisi"
type: reference
updated: 2026-06-29
topics: [donanım, reid, retail, poc]
tags: [donanım, deploy, edge]
---

# Donanım & Dağıtım Mimarisi

## Senaryo → Donanım Tablosu
| Senaryo | İşlem birimi | Yaklaşık fiyat | Not |
|---|---|---|---|
| Erişim kontrolü, kapı başı | Jetson Orin Nano 8GB | $300–450 | Tanıma edge'de, merkez sadece DB/panel/log |
| Offline saha, 2 kamera, ara sıra internet | Jetson Orin Nano + 256-512GB NVMe + 4G modem | ~$450–650/saha | store-and-forward senkron, yerel SQLite |
| Çok-kameralı takip (5 kamera) | NVIDIA sunucu RTX 4070/4080 (16GB) | ~$1.800+ | sürekli tespit+takip+embedding, DeepStream verimli |
| Retail mağaza, 10 kamera | 1× RTX 4080 (ideal 4090 24GB) makine **veya** Jetson AGX Orin 64GB | ~$1.800–3.000 | FPS 5-10 yeter, DeepStream batch |
| Geliştirme / POC (hepsi) | MacBook M4 16GB (MPS) | mevcut | 1-2 kamera, küçük (n/s) modeller |

## Apple M4 Notları (geliştirme makinesi)
- CUDA YOK → DeepStream/TensorRT koşmaz. PyTorch `device="mps"` veya CoreML export kullan.
- YOLOv8/11 n-s modelleri MPS'te ~30-60 FPS (tek akış gerçek zamanlı sorunsuz).
- InsightFace/fast-alpr → onnxruntime (CPU), POC için yeterli.
- 16GB RAM sınırda; modelleri küçük tut, `yolo export format=coreml` ile Neural Engine'i kullan.
- Eğitim/fine-tune gerekirse: Mac'te eğitme → bulut GPU kirala (Colab/RunPod/Lambda), modeli indir.

## Üretim Optimizasyon Kuralları
1. DeepStream ile çok akışı batch'le (ham OpenCV ile N ayrı akış GPU'yu boğar).
2. Retail/analitik için FPS'i 5-10'a düşür → GPU yükü 3-4× azalır.
3. Model boyutu: YOLOv8/11 s veya m yeter, x'e gerek yok.
4. Demografi/kıyafet'i her karede değil, track boyunca seyrek örnekle → ortalama.
5. Görüntü saklama yok → sadece anonim metrik (hem ucuz hem KVKK uyumlu).

## Senkron (offline saha)
İnternet yokken: kamera → tanı → yerel SQLite'a yaz (`synced=false`), tanıma yerel listeyle çalışır.
İnternet gelince: `synced=false` kayıtları merkeze gönder → onayda `synced=true`; merkezden güncel kişi/plaka
listesi iner. Bağlantı koparsa kuyruk korunur, veri kaybı yok.
