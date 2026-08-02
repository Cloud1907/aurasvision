"""Ingestor — Redis Streams'ten olayları tüketip DB'ye yazar.

Worker'ların tek DB müşterisi budur (yazma yolunda). Uyarı üretimi de burada:
  plaka olayı → watch_plates eşleşmesi → alert
  yüz olayı   → match_name doluysa → alert

Çalıştırma:
  export REDIS_URL=redis://localhost:6379/0
  python -m src.ingestor
"""
from __future__ import annotations

from .bus import consume, open_bus
from .config import load_config
from .olay import isle
from .store import open_store


def main() -> None:
    cfg = load_config()
    from .gunluk import kur as gunluk_kur
    gunluk_kur("ingestor", cfg)
    bus = open_bus(cfg)
    if bus is None:
        raise SystemExit("REDIS_URL (veya config redis.url) gerekli")
    store = open_store(cfg)
    # Tek kareden ibaret okuma alarm tetiklemesin: gerçek geçişte oylama penceresi
    # birden çok okuma üretir; count'u eşiğin altındaki eşleşme alarm olmaz (olay yine yazılır)
    alert_min_reads = int(cfg.get("plate.alert_min_reads", 2))
    print("[ingest] dinleniyor — stream: events", flush=True)

    def handle(type_: str, camera_id: str, p: dict) -> None:
        isle(store, alert_min_reads, type_, camera_id, p, cfg=cfg)

    consume(bus, handle, on_batch=store.commit)


if __name__ == "__main__":
    main()
