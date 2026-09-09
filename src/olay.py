"""Olay → DB yazım kuralları (uyarı üretimi dahil).

Tek yerde durur, iki yerden çağrılır:
  - ingestor.py      : Redis'ten tüketilen olaylar (çok makineli kurulum)
  - bus.YerelBus     : worker'ın doğrudan yazdığı olaylar (tek makine kurulumu)

İkisi de aynı kuralı uygulasın diye burada: eşiğin altındaki plaka okuması
alarm üretmez, eşleşen yüz alarm üretir. Bu mantık iki dosyaya kopyalanırsa
biri güncellenip diğeri unutulur; sahada "alarm gelmiyor" olarak görünür.
"""
from __future__ import annotations


def _web(cfg, alarm: dict) -> None:
    if cfg is None:
        return
    from .bildirim import gonder
    gonder(cfg, alarm)



def isle(store, alert_min_reads: int, type_: str, camera_id: str, p: dict,
         cfg=None) -> None:
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
                _web(cfg, {"tur": "plate", "ref": m["plate"], "liste": m["list_type"],
                           "etiket": m.get("label") or "", "kamera": camera_id})
    elif type_ == "face":
        store.add_face_event(camera_id, p.get("age"), p.get("gender"), p.get("conf"),
                             p.get("ts_seconds", 0.0), p.get("frame_idx", 0),
                             track_id=p.get("track_id"),
                             match_name=p.get("match_name"),
                             match_score=p.get("match_score"))
        if p.get("match_name"):
            store.add_alert("face", p["match_name"], p.get("list_type") or "watch",
                            "", camera_id)
            _web(cfg, {"tur": "face", "ref": p["match_name"], "kamera": camera_id})
    elif type_ == "alert":
        # Worker'da doğan alarm (ihlal alanı) — snapshot (kanıt karesi) count.py'de
        # zaten üretiliyordu ama buradan geçerken düşüyordu (bkz. bus.py:BusStore.add_alert)
        store.add_alert(p.get("kind", "intrusion"), p.get("ref", ""),
                        p.get("list_type", ""), p.get("label", ""), camera_id,
                        snapshot=p.get("snapshot") or "")
        _web(cfg, {"tur": p.get("kind", "intrusion"), "ref": p.get("ref", ""),
                   "etiket": p.get("label", ""), "kamera": camera_id})
    elif type_ == "fire":
        # Yangın ERKEN UYARISI (sertifikalı alarm değil — src/fire.py). Ön uyarı
        # panelde kalır, webhook YALNIZ alarmda gider: her ön uyarıyı santrale
        # basmak alarmı değersizleştirir, gerçek alarmda kimse bakmaz olur.
        from .fire import FERAGAT
        if p.get("durum") == "alarm":
            etiket = (f"{p.get('dogrulama', 0)} kare / {p.get('sure', 0)} sn"
                      f" · {FERAGAT}")
            store.add_alert("fire_warning", p.get("sinif", "duman"), "fire",
                            etiket, camera_id, snapshot=p.get("snapshot", ""))
            _web(cfg, {"tur": "fire_warning", "ref": p.get("sinif", "duman"),
                       "etiket": etiket, "kamera": camera_id,
                       "kanit": p.get("snapshot", ""), "klip": p.get("clip", "")})
    elif type_ == "vektor":
        # Görünüm araması örneği (base64 float16, arama.BOYUT boyutlu)
        import base64
        import numpy as np
        v = np.frombuffer(base64.b64decode(p["vec"]), dtype="float16").astype("float32")
        try:
            store.add_nesne_vektor(camera_id, p.get("sinif"), p.get("kutu", ""),
                                   p.get("kucuk", ""), v)
        except NotImplementedError:
            # Görünüm araması pgvector ister; SQLite (tek makine) profilinde tablo
            # yok. Her örnekte "[bus] olay yazılamadı (vektor)" basmak logu
            # gerçek hatalar görünmez olana dek dolduruyordu — sessizce atlanır.
            pass
    elif type_ == "health":
        store.add_camera_health(camera_id, p.get("fps"), p.get("dropped"),
                                p.get("status", "ok"))
