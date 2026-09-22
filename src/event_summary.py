"""Kamera olaylarını panel özetine indirgeyen saf dönüşüm."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone


def _bos(camera_id: str) -> dict:
    return {"camera_id": camera_id, "count": 0, "count_events": 0,
            "plate": 0, "face": 0, "fire": 0, "alerts": 0, "last": None}


def summarize(olaylar: list[dict], bekleyen: list[dict], hours: int,
              now: datetime | None = None) -> dict:
    """Toplam olay ile `count` olay türünü ayrı sayaçlarda tutar."""
    sinir = (now or datetime.now(timezone.utc)) - timedelta(hours=hours)
    ozet: dict[str, dict] = {}
    for event in olaylar:
        try:
            event_time = datetime.fromisoformat(str(event["time"]).replace(" ", "T"))
            if event_time.tzinfo is None:
                event_time = event_time.replace(tzinfo=timezone.utc)
            if event_time < sinir:
                continue
        except ValueError:
            pass
        row = ozet.setdefault(event["camera_id"], _bos(event["camera_id"]))
        row["count"] += 1
        if event["type"] == "count":
            row["count_events"] += 1
        elif event["type"] in row:
            row[event["type"]] += 1
        if row["last"] is None:
            row["last"] = str(event["time"])
    for alert in bekleyen:
        camera_id = alert["camera_id"] or "?"
        ozet.setdefault(camera_id, _bos(camera_id))["alerts"] += 1
    return {"hours": hours,
            "cameras": sorted(ozet.values(), key=lambda x: (-x["alerts"], -x["count"]))}

