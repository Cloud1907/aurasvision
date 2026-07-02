---
title: "ADR-0002 — 100 kameralık tek-GPU üretim mimarisi ve veri katmanı"
type: decision
status: accepted
date: 2026-07-02
topics: [ölçek, gpu, deepstream, savant, go2rtc, timescaledb, pgvector, redis, kvkk]
tags: [decision/accepted]
aliases: [adr-0002, 100-kamera, uretim-mimarisi]
provenance:
  root: external_doc          # WebSearch: Frigate/DeepStream/Savant/Timescale karşılaştırması (2026-07)
---

# ADR-0002 — 100 kameralık tek-GPU üretim mimarisi ve veri katmanı

## Bağlam
POC (ADR-0001 yığını) tek video + SQLite ile çalışıyor. Yeni hedef: **tek güçlü GPU'lu makinede
~100 kamera**, sonuçlar veritabanında kalıcı, ayarlar basit. Global çözümler incelendi:
Frigate (NVR/işletme deseni), go2rtc (ingest), NVIDIA DeepStream + Savant (GPU pipeline),
TimescaleDB vs ClickHouse (olay saklama). Tam belge: `docs/mimari-100-kamera.md`.

## Karar
| Katman | Seçim | Gerekçe |
|---|---|---|
| Ingest | **go2rtc** | Kamera başına tek bağlantı; analiz + WebRTC canlı izleme aynı akıştan |
| Analiz | **vision-worker**: substream 720p@5fps, hareket ön-filtresi, YOLO **TensorRT batch**; ALPR/yüz **olay-tetikli ikinci kademe**; Faz 3'te motor = **Savant (DeepStream)** | 100 kam × 5fps = ~500 infer/s → tek modern GPU'nun FPS bütçesine sığar; NVDEC nedeniyle substream zorunlu |
| Olay yolu | **Redis Streams** | Worker→DB ayrışması; worker çökse de olay kaybolmaz; ek broker yok |
| Veritabanı | **PostgreSQL 16 + TimescaleDB + pgvector** (tek DB) | İlişkisel yapı + zaman serisi (hypertable, sıkıştırma, retention, continuous aggregate) + yüz embedding araması aynı yerde; işletmesi basit. ClickHouse ancak 1000+ kamera ölçeğinde |
| Veri modeli | **Track-bazlı olay** (kare-bazlı değil); `direction` uygulanır; ham 90 gün + 15dk özet 2 yıl | Hacim ~50× düşer, sayılar kişi/araç anlamı kazanır |
| Medya | Ham akış saklanmaz; olay snapshot/klip + retention job | KVKK + disk maliyeti; NVR gerekirse yanına Frigate |
| Ayar | `config.yaml` = yalnız sistem varsayılanları (<15 satır); geri kalan her şey UI→DB | Frigate dersi: kullanıcı tek dosya bilir |
| Dağıtım | Tek makine **docker-compose** (go2rtc, worker, redis, db, api, retention) | `docker compose up -d` ile kurulum |

## Yol haritası
Faz 1: SQLite→Timescale + track-bazlı olay + auth/XSS düzeltmeleri →
Faz 2: go2rtc + worker/Redis ayrımı (10-25 kam) →
Faz 3: Savant/TensorRT ile 100 kam →
Faz 4: dashboard + uyarı ack + operasyon.

## Alternatifler (neden değil)
- **ClickHouse**: aggregasyonda hızlı ama ikinci sistem; bu hacimde gereksiz karmaşıklık.
- **MQTT/Kafka**: Kafka bu ölçek için ağır; MQTT yalnız ev-otomasyon entegrasyonu istenirse eklenir.
- **Frigate'i doğrudan kullanmak**: NVR odaklı; ANPR/yüz/izleme-listesi iş mantığımızı ve TR/KVKK
  gereksinimlerini taşımıyor — desenleri alındı, ürünü alınmadı.
- **Çıplak DeepStream**: GStreamer mühendislik maliyeti yüksek; Savant aynı performansı Python-first verir.

## İlgili
Tam mimari + şema SQL: `docs/mimari-100-kamera.md` · Önceki yığın kararı: [[decisions/0001-yigin-ve-mimari]]
