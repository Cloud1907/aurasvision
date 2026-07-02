---
title: "VideoAI — Hafıza İndeksi"
type: memory-index
updated: 2026-06-29T23:06
topics: [yüz, plaka, sayma, reid, retail, donanım, kvkk, poc, ui]
aliases: [videoai-memory, hafıza-index]
---

# 📚 VideoAI — Topic İndeksi

> Tech Lead her run başında **yalnızca bu dosyayı** okur, eşleşen topic'in pointer'larından girer.
> Bu dosya **kanonik index** — runs/decisions/sprints granular kalıt; bu sadece pointer haritası.

Proje özeti: Açık kaynak görüntü analitiği. **Yüz tanıma + plaka okuma + kişi sayma/Re-ID + retail analitiği.** Geliştirme: MacBook M4 (16GB, MPS). Üretim: Jetson/NVIDIA edge. KVKK-bilinçli, edge-first.

## Yığın & Genel Mimari
Kanonik karar: [[decisions/0001-yigin-ve-mimari]]
Geçmiş runs:
- [[runs/2026-06-29T18-15-11-9c58]] — proje Agent Ofis'e bağlandı, kararlar hafızaya alındı

## yüz
Araç: InsightFace (ArcFace) üretim, CompreFace hızlı başlangıç. Embedding=512d, cosine eşik ~0.5-0.6 (kalibre et). Liveness/anti-spoof üretimde zorunlu.
Kararlar: [[decisions/0001-yigin-ve-mimari]]
Not: İsimli tanıma = biyometrik veri → [[docs/kvkk-notlari]]. Retail'de **anonim demografi** (yaş/cinsiyet) tercih.

## plaka
Araç: fast-alpr (tespit+OCR), alternatif Plate Recognizer / YOLO+EasyOCR. TR plaka için fine-tune.
Kararlar: [[decisions/0001-yigin-ve-mimari]]
Not: Plaka = METİN → eşleştirme düz string eşitliği (yüz embedding'inden kolay). Asıl zorluk OCR doğruluğu (çok kareli oylama).

## sayma
Araç: Ultralytics YOLO + ByteTrack. Çizgi geçişi (footfall) + anlık doluluk. Retail'de 5-10 FPS yeter.
**Çoklu çizgi**: `run_count(lines=[{name,pts}])`; `_saved_lines` tüm line zone'ları çeker; her çizgi ayrı sayılır (CountResult.lines=[{name,in,out}]). Annotated videoda A/B perpendiküler yan + çizgi adı + per-line sayaç; özet/kart per-line döküm. count_events.line_name.
Kararlar: [[decisions/0001-yigin-ve-mimari]]
Geçmiş runs: [[runs/2026-06-29T23-05-29-3718]] — çoklu çizgi + video A/B yan + isim + per-line + (exe vs web cevabı: web/servis standart)

## reid
Çok-kameralı takip: yüz=embedding benzerliği, plaka=metin eşitliği, vücut=Person Re-ID (OSNet/FastReID). Global ID + kamera + zaman → rota. Zorluk: kör nokta, ID switch, eşik kalibrasyonu.
Kararlar: [[decisions/0001-yigin-ve-mimari]]

## retail
Mağaza analitiği: ısı haritası + footfall + anonim demografi + kıyafet analizi. 10 kamera → 1× RTX 4080 makine veya Jetson AGX Orin. DeepStream batch, FPS düşür, görüntü saklama.
Kararlar: [[decisions/0001-yigin-ve-mimari]]

## donanım
Senaryo-donanım eşlemesi tam tabloyla: [[docs/donanim-mimari]]
Özet: kapı/edge başına Jetson Orin Nano (~$300-450); offline saha 2 kamera = Jetson Nano+SSD+4G; retail 10 kamera = RTX 4080 makine; geliştirme = M4. Üretim ölçek = DeepStream+TensorRT (NVIDIA-only, Mac'te çalışmaz).
Kararlar: [[decisions/0001-yigin-ve-mimari]]

## kvkk
Tam not: [[docs/kvkk-notlari]]
Özet: Yüz/plaka = kişisel/biyometrik veri. İsimli tanıma açık rıza+aydınlatma ister. Edge'de işle, görüntü saklama, sadece anonim metrik üret. Retail'de anonim demografi default.

## poc
Hedef: M4'te tek video üzerinden yüz+plaka+sayma yapan modüler CLI (src/cli.py · count|face|plate|analyze).
Yığın: Python 3.11 venv, Ultralytics+OpenCV (MPS), InsightFace (CPU), fast-alpr (CPU), SQLite çıktı.
Durum: **✅ ÜÇ MODÜL DE ÇALIŞIYOR.** Sayım MPS, plaka+yüz onnxruntime-CPU. Demo: intel-iot-devkit videoları (data/videos, repoya girmez).
Kanonik kod: src/cli.py, src/count.py, src/plate.py, src/face.py, src/store.py · [[README.md]] · config.yaml
Tuzaklar: fast-alpr Apple Silicon'da CoreML EP patlar → CPU provider zorunlu; OCR confidence liste olabilir; `lap` ByteTrack için gerekli; onnxruntime ayrı kurulur.
Geçmiş runs:
- [[runs/2026-06-29T18-15-11-9c58]] — proje bağlama
- [[runs/2026-06-29T18-29-15-e3c1]] — POC iskeleti + 3 modül çalışır (sayım IN2/OUT1, plaka 19 okuma, yüz+demografi)

## ui
Web arayüzü: **FastAPI + vanilla SPA, 5 ekran çalışıyor** (Canlı/Kameralar/Bölgeler/Olaylar/Listeler).
Kanonik kod: src/server.py, web/index.html · config.yaml (cameras + server) · .claude/launch.json (preview)
Endpoint: /api/cameras, /api/snapshot (anlık JPEG, diske yazmaz=KVKK), /api/zones (GET+POST clear-then-add), /api/events (birleşik), /api/lists (plate/face CRUD).
Canvas bölge editörü: gerçek snapshot üzerine çizgi (2 nokta) / poligon (bölge/ihlal), normalize 0-1 koordinat → zones tablosu.
İzleme listesi: watch_plates + watch_faces tabloları (blacklist/vip/visitor/allowed).
Watchlist alarmı: `/api/run` okunanları watch ile eşleştirir → `alerts` → `/api/alerts` → Olaylar kırmızı band + Test kartı. Plaka=metin eşitliği. **Yüz=embedding cosine≥eşik** (watch_faces.embedding; enroll: Listeler'de kamera seç → `embed_largest_face` 12 kare tarar; KVKK: ham görüntü değil sadece vektör).
Plaka çok-kareli oylama: `plate.run_plate` → `voted=[{plate,count,conf}]` (Levenshtein≤2 kümeleme); watchlist/summary oylanmış plakayı kullanır.
Annotated video: OpenCV mp4v tarayıcıda oynamaz → server._webify ffmpeg ile H.264'e çevirir (libx264+yuv420p+faststart).
Arka plan job: `/api/run` thread+`job_id` → `GET /api/run/{job_id}` (status/stage); UI ilerleme poll eder. **Analizler global RUN_LOCK ile sıraya alınır** (aynı anda tek yazıcı; "sırada bekliyor"). SQLite **WAL+busy_timeout(30s)** → "database is locked" çözüldü. Her koşu başında `clear_analysis()` (config/listeler korunur).
Plaka **canlı akış**: `run_plate(on_read=cb)` → `job['live']` → UI 500ms poll ile aşağı akıtır (`renderLive`). Bitince oylanmış özet+video.
Video web-uyumu: OpenCV mp4v tarayıcıda oynamaz → `server._webify` ffmpeg ile H.264.
Kameralar: `cameras` DB tablosu, config+DB merge, UI'dan ekle/sil (`POST/DELETE /api/cameras`); `_slug` TR çevirili. Canlı auto-refresh 5sn.
Demo videolar: intel-iot-devkit. **Yüz için en iyi: head-pose-face-detection (342 tespit/171 kare, frontal) → "Yüz Demo" kamerası.** Yüz CPU'da yavaş → büyük vid_stride önerilir.
Veri DEPO: tek SQLite `output/videoai.db` (runs/count_events/plate_reads/face_events/zones/watch_plates/watch_faces/alerts; timestamp + synced bayrağı). Ham görüntü saklanmaz (KVKK); annotated video output/ (repoya girmez) → /media. Üretim: saha SQLite → merkez Postgres/pgvector senkron. GÖSTERİM: web UI (Canlı/Test/Olaylar/Listeler/Bölgeler).
Veri doğruluğu kanıtı: yön semantiği unit-test (A→B=in); line_override farklı çizgi=farklı sonuç; olay=giriş+çıkış, track tekil. Gerçek doğruluk = çizgi konumu+conf+model kalibrasyonu (backlog).
Çalıştır: `python -m src.server` → http://127.0.0.1:8000 · preview: launch.json "videoai".
Test ekranı: `POST /api/run {camera,kind}` analizi çalıştırır (save_video), `/media/<file>` annotated videoyu sunar, UI'da `<video>` oynatır. kind: count|plate|face|analyze.
Çizgi A→B yönlü: editörde A/B etiket+ok; kayıtlı çizgi (zones tablosu) → `count.run_count(line_override=...)` → A→B=giriş, B→A=çıkış. **çiz-kaydet-say halkası kapalı.**
Editör UX (onDown/onMove/onUp): çizgi **bas-çek**, uç tutamaçları **sürüklenir**, **✕ rozeti** siler, her çizime **isim** (zlist), A/B çizginin **iki yanında** (perpendiküler; B=pozitif taraf=count "in"). points=[A_uç,B_uç] sözleşmesi sabit.
Premium tema: CSS token sistemi (light+dark), `<head>` anti-FOUC + localStorage toggle, dark sidebar rail (her zaman dark), inline SVG ikon (web font YOK=perf), kamera tile fade-in+skeleton shimmer+hover-lift, segment kontrol, içerik fade. Perf: `/api/snapshot` TTL cache (4sn)+Cache-Control → ~37× hızlı.
Tuzaklar: chrome-devtools MCP profile kilitli → Claude_Preview kullan (reload: preview_eval location.reload()); IMG/ZONES module-scope (window'da değil); içerik fade animasyonu screenshot'ta yarı-saydam görünebilir (kozmetik).
Geçmiş runs:
- [[runs/2026-06-29T21-26-23-fc10]] — web arayüzü (FastAPI + canvas editör) çalışır
- [[runs/2026-06-29T21-41-06-5477]] — A→B çizgi sayıma bağlandı + UI Test ekranı (çalıştır+video oynat)
- [[runs/2026-06-29T21-50-44-222e]] — editör UX: bas-çek, sürükle-düzelt, ✕ sil, isim, A/B yanlarda
- [[runs/2026-06-29T21-58-33-6a68]] — premium tema (dark mode, dark rail, skeleton) + snapshot cache perf
- [[runs/2026-06-29T22-08-41-f9fe]] — veri doğruluğu kanıtı + watchlist eşleşme alarmı
- [[runs/2026-06-29T22-22-54-5d99]] — backlog tamamı: plaka oylama, UI kamera ekle, arka plan job, canlı yenileme, yüz watchlist
Sonraki: uzun video için /api/run arka plan job · watchlist eşleşme alarmı · UI'dan kamera ekleme · canlı snapshot yenileme

Genel sonraki: çok-kareli plaka oylama + TR fine-tune · Re-ID/rota · retail ısı haritası
