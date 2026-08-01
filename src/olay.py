"""Olay → DB yazım kuralları (uyarı üretimi dahil).

Tek yerde durur, iki yerden çağrılır:
  - ingestor.py      : Redis'ten tüketilen olaylar (çok makineli kurulum)
  - bus.YerelBus     : worker'ın doğrudan yazdığı olaylar (tek makine kurulumu)

İkisi de aynı kuralı uygulasın diye burada: eşiğin altındaki plaka okuması
alarm üretmez, eşleşen yüz alarm üretir. Bu mantık iki dosyaya kopyalanırsa
biri güncellenip diğeri unutulur; sahada "alarm gelmiyor" olarak görünür.
"""
from __future__ import annotations


def isle(store, alert_min_reads: int, type_: str, camera_id: str, p: dict) -> None:
    if type_ == "count":
        store.add_count_event(camera_id, p.get("track_id"), p["direction"],
                              p.get("zone", ""), p.get("ts_seconds", 0.0),
                              p.get("frame_idx", 0))
    elif type_ == "plate":
        store.add_plate_event(camera_id, p["plate"], p.get("conf"), p.get("reads", 1),
                              p.get("ts_seconds", 0.0), p.get("frame_idx", 0),
                              track_id=p.get("track_id"))
        # Tek kareden ibaret okuma alarm tetiklemesin: gerçek geçişte oylama
        # penceresi birden çok okuma üretir
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
        # Worker'da doğan alarm (ihlal alanı)
        store.add_alert(p.get("kind", "intrusion"), p.get("ref", ""),
                        p.get("list_type", ""), p.get("label", ""), camera_id)
    elif type_ == "health":
        store.add_camera_health(camera_id, p.get("fps"), p.get("dropped"),
                                p.get("status", "ok"))
