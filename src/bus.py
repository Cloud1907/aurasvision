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
import threading

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


class YerelBus:
    """Redis'in yerine geçen tek-makine yolu — olayı doğrudan DB'ye yazar.

    Redis + ingestor, olayları çok worker/çok makine arasında dağıtmak için var.
    Tek kutuya kurulan sistemde bu ayrım net bir maliyet: müşteri makinesine
    Docker Desktop kurmak, yeniden başlatma istemek ve lisans sorunu doğurmak.
    Bu sınıf `xadd` arayüzünü taklit eder; `publish()` ve `BusStore` hiç
    değişmeden çalışır, yalnız hedef değişir.

    İş parçacığı güvenliği: worker her kamera için ayrı thread açar, bu nesne
    paylaşılır. SqliteStore `check_same_thread=False` ile açılır, yazımlar
    burada kilitle sıraya sokulur.
    """

    def __init__(self, cfg) -> None:
        from .store import open_store
        self.store = open_store(cfg)
        self.cfg = cfg
        self.alert_min_reads = int(cfg.get("plate.alert_min_reads", 2))
        self._lock = threading.Lock()

    def xadd(self, _stream, fields, **_kw) -> None:
        from .olay import isle
        payload = json.loads(fields.get("payload") or "{}")
        with self._lock:
            try:
                isle(self.store, self.alert_min_reads, fields.get("type", ""),
                     fields.get("camera_id", ""), payload, cfg=self.cfg)
                self.store.commit()
            except Exception as e:
                # Tek olayın yazılamaması analizi durdurmasın (Redis yolunda da
                # zehirli mesaj ack'lenip geçiliyor)
                print(f"[bus] olay yazılamadı ({fields.get('type')}): {e}", flush=True)

    def close(self) -> None:
        self.store.close()


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

    def add_alert(self, kind, ref, list_type, label, camera_id) -> None:
        # İhlal alanı alarmı worker'da doğar; DB yazımı ingestor'ın işi (ADR-0002)
        publish(self.r, "alert", camera_id,
                {"kind": kind, "ref": ref, "list_type": list_type, "label": label})

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

    def _sahipsizleri_al() -> list:
        """Ölü tüketicilerin üstünde kalan mesajları devralır (XAUTOCLAIM).

        xreadgroup '>' yalnız HİÇ teslim edilmemiş mesajı verir. Eski bir
        ingestor mesajı alıp ack'lemeden ölürse o mesaj sonsuza dek askıda
        kalıyordu — sahada 11k+ olay böyle kaybolmuştu (worker yeniden
        başlatılınca görüldü). 60 sn'den uzun süredir sahipsiz olanları al.
        """
        try:
            _, msgs, _ = r.xautoclaim(STREAM, GROUP, consumer,
                                      min_idle_time=60_000, count=200)
            return msgs
        except (_redis.ResponseError, _redis.ConnectionError):
            return []

    while True:
        sahipsiz = _sahipsizleri_al()
        if sahipsiz:
            for mid, fields in sahipsiz:
                if fields is None:      # silinmiş mesajın hayaleti
                    continue
                try:
                    handler(fields.get("type", ""), fields.get("camera_id", ""),
                            json.loads(fields.get("payload") or "{}"))
                except Exception as e:
                    print(f"[ingest] devralınan mesaj hatası ({mid}): {e}", flush=True)
                r.xack(STREAM, GROUP, mid)
            if on_batch:
                on_batch()
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
