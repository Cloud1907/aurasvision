"""İhlal alanı (intrusion) değerlendirmesi — poligon içi kalış tespiti.

Bölgeler UI'da çizilir (kind='intrusion'), burada karara dönüşür. Tasarım kararları:

* **Ayak noktası** kullanılır (kutu merkezi değil): kişi eğildiğinde/oturduğunda kutu
  merkezi kayar, ayak sabit kalır — alan sınırında titreşimi azaltır.
* **Bekleme süresi (dwell):** alana giren nesne, eşiği aşacak kadar KALMADAN alarm
  üretmez. Sınıra değip geçen kişi/araç yanlış alarm üretmesin diye.
* **Soğuma (cooldown):** aynı track aynı alanda tekrar tekrar alarm üretmez.

Alarmlar `alerts` tablosuna kind='intrusion' ile yazılır → uyarı kabul (ack) akışı
ve menü rozeti bedavaya gelir.
"""
from __future__ import annotations

from typing import Any

# YOLO COCO sınıf id → UI'daki nesne seçimi ("İnsan" / "Araç")
PERSON_IDS = {0}
VEHICLE_IDS = {1, 2, 3, 5, 7}   # bisiklet, otomobil, motosiklet, otobüs, kamyon


def point_in_poly(x: float, y: float, poly: list) -> bool:
    """Ray-casting: nokta poligonun içinde mi (kenarda olması garanti değil)."""
    icinde = False
    n = len(poly)
    if n < 3:
        return False
    j = n - 1
    for i in range(n):
        xi, yi = poly[i][0], poly[i][1]
        xj, yj = poly[j][0], poly[j][1]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi:
            icinde = not icinde
        j = i
    return icinde


def wanted_classes(classes: list | None) -> set[int]:
    """UI'daki sınıf seçimini YOLO id kümesine çevirir (boş = hepsi)."""
    if not classes:
        return set()
    ids: set[int] = set()
    for c in classes:
        c = str(c).lower()
        if c in ("person", "insan"):
            ids |= PERSON_IDS
        elif c in ("car", "arac", "araç", "vehicle"):
            ids |= VEHICLE_IDS
    return ids


class IntrusionWatcher:
    """Track'lerin ihlal alanlarında kalışını izler, alarm olaylarını üretir."""

    def __init__(self, zones: list[dict], w: int, h: int,
                 dwell_seconds: float = 1.0, cooldown_seconds: float = 30.0) -> None:
        self.dwell = float(dwell_seconds)
        self.cooldown = float(cooldown_seconds)
        self.zones: list[dict] = []
        for z in zones:
            pts = z.get("points") or []
            if len(pts) < 3:
                continue   # poligon değil
            self.zones.append({
                "name": z.get("name") or "İhlal alanı",
                "poly": [(p[0] * w, p[1] * h) for p in pts],
                "classes": wanted_classes(z.get("classes")),
                "giris": {},      # track_id → alana ilk giriş zamanı
                "son_alarm": {},  # track_id → son alarm zamanı
            })

    def __bool__(self) -> bool:
        return bool(self.zones)

    def update(self, tracks: list[tuple[int, float, float, int]], ts: float) -> list[dict]:
        """tracks: [(track_id, ayak_x, ayak_y, sinif_id)] piksel. Yeni ihlalleri döner."""
        alarmlar: list[dict[str, Any]] = []
        for z in self.zones:
            gorulen = set()
            for tid, x, y, cls in tracks:
                if z["classes"] and int(cls) not in z["classes"]:
                    continue
                gorulen.add(tid)
                if not point_in_poly(x, y, z["poly"]):
                    z["giris"].pop(tid, None)     # alandan çıktı → sayaç sıfırlanır
                    continue
                t0 = z["giris"].setdefault(tid, ts)
                if (ts - t0 >= self.dwell
                        and ts - z["son_alarm"].get(tid, -1e9) >= self.cooldown):
                    z["son_alarm"][tid] = ts
                    alarmlar.append({"zone": z["name"], "track_id": tid,
                                     "ts_seconds": round(ts, 2),
                                     "dwell": round(ts - t0, 2)})
            # Sahneden kaybolan track'lerin durumu birikmesin
            for tid in [t for t in z["giris"] if t not in gorulen]:
                z["giris"].pop(tid, None)
        return alarmlar
