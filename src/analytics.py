"""Analiz raporları için limitsiz, veritabanı tarafında toplama sorguları."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any


class AnalyticsMixin:
    """BaseStore'un iki backend tarafından paylaşılan raporlama davranışı."""

    def dashboard_alerts(self, start, end, excluded=()):
        params = list(excluded)
        camera_filter = "camera_id NOT IN (" + ','.join('?' for _ in excluded) + ")" if excluded else "1=1"
        period = "time >= ? AND time < ? AND " + camera_filter
        totals = self._all(
            "SELECT COUNT(*) AS total, SUM(CASE WHEN acked_at IS NULL THEN 1 ELSE 0 END) AS pending "
            "FROM alerts WHERE " + period, (start, end, *params))[0]
        backlog = self._all("SELECT COUNT(*) AS total FROM alerts WHERE acked_at IS NULL AND " + camera_filter, tuple(params))[0]
        bucket = "strftime('%Y-%m-%d %H:00:00',time)" if self._ph == '?' else "date_trunc('hour',time)"
        series = self._all(f"SELECT {bucket} AS bucket, COUNT(*) AS total FROM alerts WHERE " + period +
                           " GROUP BY bucket ORDER BY bucket", (start, end, *params))
        kinds = self._all("SELECT kind, COUNT(*) AS total FROM alerts WHERE " + period +
                          " GROUP BY kind ORDER BY total DESC", (start, end, *params))
        total, pending = int(totals['total']), int(totals['pending'] or 0)
        return {'total': total, 'pending': pending, 'acknowledged': total - pending,
                'pending_all': int(backlog['total']), 'kinds': kinds,
                'series': [{'bucket': str(r['bucket']), 'total': int(r['total'])} for r in series]}

    def alert_feed(self, after_id, limit=100):
        if after_id is None:
            row = self._all('SELECT COALESCE(MAX(id),0) AS cursor FROM alerts')[0]
            return {'cursor': int(row['cursor']), 'alerts': [], 'has_more': False}
        rows = self._all('SELECT id, camera_id, kind, ref, label, time, snapshot, acked_at '
                         'FROM alerts WHERE id > ? ORDER BY id LIMIT ?', (after_id, limit + 1))
        visible = rows[:limit]
        for row in visible:
            row['time'] = str(row['time'])
            if row.get('acked_at') is not None:
                row['acked_at'] = str(row['acked_at'])
        return {'cursor': int(visible[-1]['id']) if visible else after_id,
                'alerts': visible, 'has_more': len(rows) > limit}

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

    def count_trend(self, since, bucket_minutes: int = 15) -> list[dict[str, Any]]:
        """Çizgi geçişlerini taşınabilir zaman kovalarında toplar."""
        minutes = max(1, min(int(bucket_minutes), 1440))
        if self._ph == "?":
            seconds = minutes * 60
            sql = """
                SELECT datetime((CAST(strftime('%s', time) AS INTEGER) / ?) * ?,
                                'unixepoch') AS bucket,
                       SUM(CASE WHEN direction='in' THEN 1 ELSE 0 END) AS in_count,
                       SUM(CASE WHEN direction='out' THEN 1 ELSE 0 END) AS out_count
                  FROM count_events WHERE time >= ?
                 GROUP BY bucket ORDER BY bucket
            """
            rows = self._all(sql, (seconds, seconds, since))
        else:
            sql = f"""
                SELECT date_bin(INTERVAL '{minutes} minutes', time,
                                TIMESTAMPTZ '1970-01-01') AS bucket,
                       COUNT(*) FILTER (WHERE direction='in') AS in_count,
                       COUNT(*) FILTER (WHERE direction='out') AS out_count
                  FROM count_events WHERE time >= ?
                 GROUP BY bucket ORDER BY bucket
            """
            rows = self._all(self._q(sql), (since,))
        for row in rows:
            row["bucket"] = str(row["bucket"])
            row["in_count"] = int(row.get("in_count") or 0)
            row["out_count"] = int(row.get("out_count") or 0)
        return rows


def build_event_summary(store_factory, hours: int) -> dict:
    """API özetini depolama ayrıntılarını sunucu modülüne taşımadan kurar."""
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    store = store_factory()
    try:
        events = store.event_summary(since.strftime("%Y-%m-%d %H:%M:%S"))
        alerts = store.pending_alert_summary()
    finally:
        store.close()
    summary = {}
    for event in events:
        camera_id = event["camera_id"]
        summary[camera_id] = {
            "camera_id": camera_id, "count": int(event.get("count") or 0),
            "count_events": int(event.get("count_events") or 0),
            "plate": int(event.get("plate") or 0), "face": int(event.get("face") or 0),
            "alerts": 0, "last": str(event["last"]) if event.get("last") is not None else None,
        }
    for alert in alerts:
        camera_id = alert["camera_id"] or "?"
        row = summary.setdefault(camera_id, {
            "camera_id": camera_id, "count": 0, "count_events": 0,
            "plate": 0, "face": 0, "alerts": 0, "last": None,
        })
        row["alerts"] += int(alert.get("alerts") or 0)
    return {"hours": hours,
            "cameras": sorted(summary.values(), key=lambda row: (-row["alerts"], -row["count"]))}


def build_count_trend(store_factory, hours: int) -> dict:
    """API için son N saatin 15 dakikalık geçiş serisini kurar."""
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    store = store_factory()
    try:
        series = store.count_trend(since.strftime("%Y-%m-%d %H:%M:%S"), 15)
    finally:
        store.close()
    return {"hours": hours, "bucket_minutes": 15, "series": series}
