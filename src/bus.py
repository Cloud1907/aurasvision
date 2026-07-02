"""Redis Streams olay veri yolu — worker → ingestor → DB.

Worker olayları DB'ye DEĞİL buraya yazar; ingestor tüketip DB'ye basar.
Worker çökse de stream'de bekleyen olay kaybolmaz (consumer group + ack).

Mesaj formatı (stream 'events'):
  {type: count|plate|face|health, camera_id, payload: JSON}
"""
from __future__ import annotations

import json
import os
import socket

STREAM = "events"
GROUP = "ingest"
MAXLEN = 100_000   # stream tavanı (yaklaşık) — ingestor uzun süre ölürse eski olaylar düşer


def open_bus(cfg=None):
    """REDIS_URL env / config redis.url → Redis bağlantısı; yoksa None."""
    url = os.environ.get("REDIS_URL") or (cfg.get("redis.url", "") if cfg else "")
    if not url:
        return None
    import redis
    return redis.Redis.from_url(url, decode_responses=True)


def publish(r, type_: str, camera_id: str, payload: dict) -> None:
    r.xadd(STREAM, {"type": type_, "camera_id": camera_id,
                    "payload": json.dumps(payload)},
           maxlen=MAXLEN, approximate=True)


class BusStore:
    """Store arayüzünün olay-yazma alt kümesi — Redis'e yayınlar.

    run_count/run_plate/run_face 'store' parametresi olarak bunu alır;
    analiz modülleri DB'nin varlığından habersiz kalır (Faz 3'te motor
    değişse de bu sözleşme sabit).
    """

    def __init__(self, r) -> None:
        self.r = r

    def add_count_event(self, camera_id, track_id, direction, zone, ts_seconds, frame_idx):
        publish(self.r, "count", camera_id,
                {"track_id": track_id, "direction": direction, "zone": zone,
                 "ts_seconds": round(ts_seconds, 2), "frame_idx": frame_idx})

    def add_plate_event(self, camera_id, plate, conf, reads, ts_seconds, frame_idx, track_id=None):
        publish(self.r, "plate", camera_id,
                {"plate": plate, "conf": conf, "reads": reads,
                 "ts_seconds": round(ts_seconds, 2), "frame_idx": frame_idx, "track_id": track_id})

    def add_face_event(self, camera_id, age, gender, conf, ts_seconds, frame_idx,
                       track_id=None, match_name=None, match_score=None):
        publish(self.r, "face", camera_id,
                {"age": age, "gender": gender, "conf": conf,
                 "ts_seconds": round(ts_seconds, 2), "frame_idx": frame_idx,
                 "track_id": track_id, "match_name": match_name, "match_score": match_score})

    def commit(self) -> None:
        pass

    def close(self) -> None:
        pass


def consume(r, handler, on_batch=None, block_ms: int = 5000) -> None:
    """Consumer-group döngüsü: her mesaj için handler(type, camera_id, payload).

    Mesaj işlenince ack'lenir; handler istisnası mesajı ack'lemez (yeniden denenir).
    on_batch: parti sonunda çağrılır (DB commit için).
    """
    import time

    import redis as _redis

    try:
        r.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
    except _redis.ResponseError:
        pass  # grup zaten var
    consumer = f"{socket.gethostname()}-{os.getpid()}"
    while True:
        try:
            resp = r.xreadgroup(GROUP, consumer, {STREAM: ">"}, count=200, block=block_ms)
        except (_redis.TimeoutError, TimeoutError):
            continue   # bloklu okuma zaman aşımı normaldir — beklemeye devam
        except _redis.ConnectionError as e:
            print(f"[ingest] redis bağlantısı koptu, yeniden denenecek: {e}", flush=True)
            time.sleep(3)
            continue
        if not resp:
            continue
        for _stream, msgs in resp:
            for mid, fields in msgs:
                try:
                    handler(fields.get("type", ""), fields.get("camera_id", ""),
                            json.loads(fields.get("payload") or "{}"))
                    r.xack(STREAM, GROUP, mid)
                except Exception as e:   # tek bozuk mesaj akışı durdurmasın
                    print(f"[ingest] mesaj hatası ({mid}): {e}", flush=True)
                    r.xack(STREAM, GROUP, mid)   # zehirli mesajı da düşür (log'landı)
        if on_batch:
            on_batch()
