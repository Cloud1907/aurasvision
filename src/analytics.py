"""Analiz raporları için limitsiz, veritabanı tarafında toplama sorguları."""
from __future__ import annotations

from typing import Any


class AnalyticsMixin:
    """BaseStore'un iki backend tarafından paylaşılan raporlama davranışı."""

    def count_totals(self) -> list[dict[str, Any]]:
        return self._all("SELECT camera_id, "
                         "SUM(CASE WHEN direction='in' THEN 1 ELSE 0 END) AS in_count, "
                         "SUM(CASE WHEN direction='out' THEN 1 ELSE 0 END) AS out_count "
                         "FROM count_events GROUP BY camera_id")

    def event_summary(self, since) -> list[dict[str, Any]]:
        """Seçili zaman aralığını limitsiz, kamera bazında veritabanında toplar.

        ``recent_events`` operatör akışı içindir ve bilinçli olarak limitlidir;
        raporlamada kullanılması yoğun kameralarda sessiz eksik sayım üretir.
        ``count`` geriye uyum için tüm olayların toplamı, ``count_events`` ise
        yalnız çizgi geçişlerinin sayısıdır.
        """
        rows = self._all(self._q("""
            SELECT camera_id,
                   SUM(total_count) AS count,
                   SUM(count_events) AS count_events,
                   SUM(plate_events) AS plate,
                   SUM(face_events) AS face,
                   MAX(last_time) AS last
              FROM (
                    SELECT camera_id, COUNT(*) AS total_count,
                           COUNT(*) AS count_events, 0 AS plate_events,
                           0 AS face_events, MAX(time) AS last_time
                      FROM count_events WHERE time >= ? GROUP BY camera_id
                    UNION ALL
                    SELECT camera_id, COUNT(*), 0, COUNT(*), 0, MAX(time)
                      FROM plate_events WHERE time >= ? GROUP BY camera_id
                    UNION ALL
                    SELECT camera_id, COUNT(*), 0, 0, COUNT(*), MAX(time)
                      FROM face_events WHERE time >= ? GROUP BY camera_id
                   ) AS events
             GROUP BY camera_id
        """), (since, since, since))
        for row in rows:
            for key in ("count", "count_events", "plate", "face"):
                row[key] = int(row.get(key) or 0)
            row["last"] = str(row["last"]) if row.get("last") is not None else None
        return rows

    def pending_alert_summary(self) -> list[dict[str, Any]]:
        """Bekleyen uyarıları limit uygulamadan kamera bazında toplar."""
        rows = self._all("SELECT COALESCE(camera_id, '?') AS camera_id,"
                         " COUNT(*) AS alerts FROM alerts"
                         " WHERE acked_at IS NULL GROUP BY COALESCE(camera_id, '?')")
        for row in rows:
            row["alerts"] = int(row.get("alerts") or 0)
        return rows
