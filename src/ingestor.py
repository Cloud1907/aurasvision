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
        if type_ == "count":
            store.add_count_event(camera_id, p.get("track_id"), p["direction"],
                                  p.get("zone", ""), p.get("ts_seconds", 0.0),
                                  p.get("frame_idx", 0))
        elif type_ == "plate":
            store.add_plate_event(camera_id, p["plate"], p.get("conf"), p.get("reads", 1),
                                  p.get("ts_seconds", 0.0), p.get("frame_idx", 0),
                                  track_id=p.get("track_id"))
            if int(p.get("reads") or 1) >= alert_min_reads:
                for m in store.match_plates([p["plate"]]):
                    store.add_alert("plate", m["plate"], m["list_type"],
                                    m.get("label") or "", camera_id)
        elif type_ == "face":
            store.add_face_event(camera_id, p.get("age"), p.get("gender"), p.get("conf"),
                                 p.get("ts_seconds", 0.0), p.get("frame_idx", 0),
                                 track_id=p.get("track_id"),
                                 match_name=p.get("match_name"),
                                 match_score=p.get("match_score"))
            if p.get("match_name"):
                store.add_alert("face", p["match_name"], p.get("list_type") or "watch",
                                "", camera_id)
        elif type_ == "alert":
            # Worker'da doğan alarm (ihlal alanı) — DB yazımı burada
            store.add_alert(p.get("kind", "intrusion"), p.get("ref", ""),
                            p.get("list_type", ""), p.get("label", ""), camera_id)
        elif type_ == "health":
            store.add_camera_health(camera_id, p.get("fps"), p.get("dropped"),
                                    p.get("status", "ok"))

    consume(bus, handle, on_batch=store.commit)


if __name__ == "__main__":
    main()
