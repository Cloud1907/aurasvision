"""Depolama katmanı — PostgreSQL (TimescaleDB + pgvector) veya SQLite (yerel demo).

Backend seçimi (open_store):
  1. DATABASE_URL ortam değişkeni  → PgStore
  2. config db.url                 → PgStore
  3. hiçbiri yoksa                 → SqliteStore (output/aurasvision.db)

Olaylar TRACK bazlıdır (kare bazlı değil) — bkz docs/mimari-100-kamera.md §4.
KVKK: ham görüntü saklanmaz; yüz için yalnız 512d embedding.
"""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent


# record: kameranın NVR kaydı (analiz değil arşiv). Varsayılan AÇIK — kayıt
# bilinçli kapatılır; sessizce kapalı başlayan kamera sahada "o gün kayıt yok"
# olarak patlar ve geri getirilemez.
DEFAULT_TASKS = {"count": True, "plate": False, "face": False, "record": True}


def open_store(cfg) -> "BaseStore":
    url = os.environ.get("DATABASE_URL") or (cfg.get("db.url", "") if cfg else "")
    if url:
        return PgStore(url)
    db_path = cfg.get("paths.db_path", "output/aurasvision.db") if cfg else "output/aurasvision.db"
    return SqliteStore(db_path)


def merged_cameras(cfg, store: "BaseStore") -> list[dict[str, Any]]:
    """config.yaml kameraları + UI'dan eklenenler (DB), görevlerle birlikte.

    DB'deki satır aynı id'li config kamerasının görev anahtarlarını override eder
    (config dosyası elle düzenlenmeden UI'dan görev açıp kapamak için).
    """
    by_id: dict[str, dict] = {}
    for c in (cfg.get("cameras", []) or []):
        c = dict(c)
        if not c.get("tasks"):     # setdefault yetmez: anahtar None olarak var olabilir
            c["tasks"] = dict(DEFAULT_TASKS)
        by_id[c["id"]] = c
    for c in store.list_cameras_db():
        if c["id"] in by_id:
            if c.get("tasks"):
                by_id[c["id"]]["tasks"] = c["tasks"]
            if c.get("detect_fps"):
                by_id[c["id"]]["detect_fps"] = c["detect_fps"]
            if c.get("url_sub"):
                by_id[c["id"]]["url_sub"] = c["url_sub"]
            if c.get("http_headers"):
                by_id[c["id"]]["http_headers"] = c["http_headers"]
        else:
            if not c.get("tasks"):
                c["tasks"] = dict(DEFAULT_TASKS)
            by_id[c["id"]] = c
    # Kameraya özgü HTTP başlıklarını akış katmanına tanıt — kamera listesini
    # okuyan her bileşen (worker, sunucu, kayıt) böylece doğru başlığı kullanır.
    # Tek genel başlık ayarı, farklı sağlayıcılardan iki HTTP kameranın aynı
    # anda çalışmasını engelliyordu (yanlış Referer → 403).
    from . import akis
    for c in by_id.values():
        if c.get("http_headers"):
            akis.kaydet(c.get("source") or "", c["http_headers"])
    return list(by_id.values())


class BaseStore:
    """Ortak sorgular. Alt sınıf: _x (execute), _all (fetch dict listesi), _ph (placeholder)."""

    _ph = "?"

    def _q(self, sql: str) -> str:
        return sql if self._ph == "?" else sql.replace("?", self._ph)

    def _x(self, sql: str, params: tuple = ()) -> Any:
        raise NotImplementedError

    def _all(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        raise NotImplementedError

    # --- Koşu günlüğü (lineage; olaylar camera_id üzerinden bağımsız) ---
    def start_run(self, kind: str, source: str, meta: dict | None = None) -> None:
        self._x("INSERT INTO runs (kind, source, meta) VALUES (?, ?, ?)",
                (kind, source, json.dumps(meta or {})))

    # --- Olaylar (track bazlı) ---
    def add_count_event(self, camera_id: str, track_id: int, direction: str,
                        zone: str, ts_seconds: float, frame_idx: int) -> None:
        self._x("INSERT INTO count_events (camera_id, track_id, direction, zone, ts_seconds, frame_idx)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (camera_id, track_id, direction, zone, round(ts_seconds, 2), frame_idx))

    def add_plate_event(self, camera_id: str, plate: str, conf: float | None, reads: int,
                        ts_seconds: float, frame_idx: int, track_id: int | None = None,
                        snapshot: str = "") -> None:
        self._x("INSERT INTO plate_events (camera_id, plate, conf, reads, ts_seconds, frame_idx,"
                " track_id, snapshot) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (camera_id, plate, conf, reads, round(ts_seconds, 2), frame_idx, track_id,
                 snapshot or None))

    def add_face_event(self, camera_id: str, age: int | None, gender: str | None, conf: float | None,
                       ts_seconds: float, frame_idx: int, track_id: int | None = None,
                       match_name: str | None = None, match_score: float | None = None) -> None:
        self._x("INSERT INTO face_events (camera_id, age, gender, conf, ts_seconds, frame_idx,"
                " track_id, match_name, match_score) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (camera_id, age, gender, conf, round(ts_seconds, 2), frame_idx,
                 track_id, match_name, match_score))

    # --- Bölgeler ---
    def list_zones(self, camera_id: str) -> list[dict[str, Any]]:
        raise NotImplementedError

    def add_zone(self, camera_id: str, kind: str, name: str,
                 points: list, classes: list, direction: str) -> None:
        raise NotImplementedError

    def clear_zones(self, camera_id: str) -> None:
        self._x("DELETE FROM zones WHERE camera_id=?", (camera_id,))
        self.commit()

    # --- İzleme listeleri ---
    def list_watch(self, kind: str) -> list[dict[str, Any]]:
        if kind == "plate":
            return self._all("SELECT id, plate, label, list_type FROM watch_plates ORDER BY id DESC")
        rows = self._all("SELECT id, name, label, list_type,"
                         " (embedding IS NOT NULL) AS enrolled FROM watch_faces ORDER BY id DESC")
        for r in rows:
            r["enrolled"] = bool(r["enrolled"])
        return rows

    def add_watch_plate(self, plate: str, label: str, list_type: str) -> None:
        raise NotImplementedError

    def add_watch_face(self, name: str, label: str, list_type: str,
                       embedding: list | None = None) -> None:
        raise NotImplementedError

    def faces_with_embedding(self) -> list[dict[str, Any]]:
        """[{name,label,list_type,embedding:list[float]}] — embedding parse edilmiş döner."""
        raise NotImplementedError

    def delete_watch(self, kind: str, row_id: int) -> None:
        table = "watch_plates" if kind == "plate" else "watch_faces"
        self._x(f"DELETE FROM {table} WHERE id=?", (row_id,))  # tablo adı koddan, kullanıcıdan değil
        self.commit()

    def match_plates(self, plates: list[str]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for p in {x.replace(" ", "").upper() for x in plates}:
            rows = self._all("SELECT plate, label, list_type FROM watch_plates WHERE plate=?", (p,))
            out.extend(rows)
        return out

    # --- Kameralar (UI'dan eklenenler) ---
    def list_cameras_db(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    def add_camera(self, cid: str, name: str, source: str, url_sub: str = "",
                   http_headers: str = "") -> None:
        raise NotImplementedError

    def set_camera_tasks(self, cid: str, tasks: dict) -> None:
        raise NotImplementedError

    # --- Kamera sağlığı (worker heartbeat) ---
    def add_camera_health(self, camera_id: str, fps: float | None,
                          dropped: int | None, status: str) -> None:
        self._x("INSERT INTO camera_health (camera_id, fps, dropped, status)"
                " VALUES (?, ?, ?, ?)", (camera_id, fps, dropped, status))

    def latest_health(self) -> list[dict[str, Any]]:
        """Kamera başına en son heartbeat."""
        raise NotImplementedError

    def delete_camera(self, cid: str) -> None:
        self._x("DELETE FROM cameras WHERE id=?", (cid,))
        # Sağlık izi de gitmeli: latest_health() kamera tablosuna bakmadığı için
        # silinen kamera panelde "hatalı" olarak görünmeye devam ediyordu.
        # Olay/kayıt satırları KALIR — geçmiş kanıt, kamera silindi diye silinmez.
        self._x("DELETE FROM camera_health WHERE camera_id=?", (cid,))
        self.commit()

    # --- Kayıtlar (NVR segmentleri) ---
    def add_recording(self, camera_id: str, path: str, start, end,
                      duration: float, size_bytes: int) -> None:
        """Kapanmış segmenti kaydeder. duration ÖLÇÜLMÜŞ değerdir (nominal değil)."""
        self._x("INSERT INTO recordings (camera_id, path, start_time, end_time,"
                " duration, size_bytes) VALUES (?, ?, ?, ?, ?, ?)"
                " ON CONFLICT (path) DO NOTHING",
                (camera_id, path, start, end, round(duration, 3), size_bytes))

    def list_recordings(self, camera_id: str = "", start=None, end=None,
                        limit: int = 2000) -> list[dict[str, Any]]:
        sql = "SELECT camera_id, path, start_time, end_time, duration, size_bytes FROM recordings WHERE 1=1"
        par: list[Any] = []
        if camera_id:
            sql += " AND camera_id=?"; par.append(camera_id)
        if start is not None:
            sql += " AND end_time >= ?"; par.append(start)
        if end is not None:
            sql += " AND start_time <= ?"; par.append(end)
        sql += " ORDER BY start_time LIMIT ?"; par.append(limit)
        rows = self._all(sql, tuple(par))
        for r in rows:
            r["start_time"] = str(r["start_time"]); r["end_time"] = str(r["end_time"])
        return rows

    def recordings_before(self, ts, limit: int = 500) -> list[dict[str, Any]]:
        return self._all("SELECT path, size_bytes FROM recordings WHERE end_time < ?"
                         " ORDER BY start_time LIMIT ?", (ts, limit))

    def recordings_oldest(self, limit: int = 500) -> list[dict[str, Any]]:
        return self._all("SELECT path, size_bytes FROM recordings"
                         " ORDER BY start_time LIMIT ?", (limit,))

    def recordings_size(self) -> int:
        r = self._all("SELECT COALESCE(SUM(size_bytes),0) AS t FROM recordings")
        return int(r[0]["t"]) if r else 0

    def recordings_stats(self) -> list[dict[str, Any]]:
        """Kamera başına: segment sayısı, toplam boyut, en eski/yeni kayıt."""
        return self._all("SELECT camera_id, COUNT(*) AS segments,"
                         " COALESCE(SUM(size_bytes),0) AS bytes,"
                         " MIN(start_time) AS oldest, MAX(end_time) AS newest"
                         " FROM recordings GROUP BY camera_id")

    def delete_recording(self, path: str) -> None:
        self._x("DELETE FROM recordings WHERE path=?", (path,))

    # --- Uyarılar ---
    def add_alert(self, kind: str, ref: str, list_type: str, label: str, camera_id: str,
                  snapshot: str = "") -> None:
        self._x("INSERT INTO alerts (kind, ref, list_type, label, camera_id, snapshot)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (kind, ref, list_type, label, camera_id, snapshot or None))
        self.commit()

    def recent_alerts(self, limit: int = 20, pending_only: bool = False) -> list[dict[str, Any]]:
        kosul = " WHERE acked_at IS NULL" if pending_only else ""
        return self._all("SELECT id, kind, ref, list_type, label, camera_id, time,"
                         " acked_by, acked_at, snapshot FROM alerts"
                         f"{kosul} ORDER BY time DESC LIMIT ?", (limit,))

    def ack_alert(self, alert_id: int, by: str = "operatör") -> bool:
        """Uyarıyı kabul eder (kim/ne zaman). Zaten kabul edilmişse dokunmaz."""
        cur = self._x("UPDATE alerts SET acked_by=?, acked_at=CURRENT_TIMESTAMP"
                      " WHERE id=? AND acked_at IS NULL", (by, alert_id))
        self.commit()
        return bool(getattr(cur, "rowcount", 0))

    def count_totals(self) -> list[dict[str, Any]]:
        return self._all("SELECT camera_id, "
                         "SUM(CASE WHEN direction='in' THEN 1 ELSE 0 END) AS in_count, "
                         "SUM(CASE WHEN direction='out' THEN 1 ELSE 0 END) AS out_count "
                         "FROM count_events GROUP BY camera_id")

    def clear_analysis(self) -> None:
        """Önceki analiz çıktılarını siler. KORUNUR: cameras, zones, izleme listeleri."""
        for t in ("count_events", "plate_events", "face_events", "alerts", "runs"):
            self._x(f"DELETE FROM {t}")
        self.commit()

    def recent_events(self, limit: int = 50, tur: str = "",
                      kamera: str = "") -> list[dict[str, Any]]:
        """Birleşik olay akışı. tur: count|plate|face (boş = hepsi)."""
        raise NotImplementedError

    def commit(self) -> None:
        pass

    def close(self) -> None:
        pass


# ─────────────────────────── SQLite ────────────────────────────────

_SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, source TEXT NOT NULL,
    started_at TEXT NOT NULL DEFAULT (datetime('now')), meta TEXT);
CREATE TABLE IF NOT EXISTS cameras (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, source TEXT NOT NULL,
    url_sub TEXT,   -- düşük çözünürlüklü substream (kamera duvarı); boşsa ana akış
    http_headers TEXT,  -- bu kameraya özgü HTTP başlıkları (bazı HLS sağlayıcıları Referer şart koşar)
    tasks TEXT, created_at TEXT NOT NULL DEFAULT (datetime('now')));
CREATE TABLE IF NOT EXISTS recordings (
    id INTEGER PRIMARY KEY AUTOINCREMENT, camera_id TEXT NOT NULL,
    path TEXT NOT NULL UNIQUE, start_time TEXT NOT NULL, end_time TEXT NOT NULL,
    duration REAL NOT NULL, size_bytes INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS ix_rec_cam_time ON recordings (camera_id, start_time);
CREATE TABLE IF NOT EXISTS camera_health (
    id INTEGER PRIMARY KEY AUTOINCREMENT, time TEXT NOT NULL DEFAULT (datetime('now')),
    camera_id TEXT NOT NULL, fps REAL, dropped INTEGER, status TEXT);
CREATE TABLE IF NOT EXISTS zones (
    id INTEGER PRIMARY KEY AUTOINCREMENT, camera_id TEXT NOT NULL, kind TEXT NOT NULL,
    name TEXT NOT NULL DEFAULT '', points TEXT NOT NULL, classes TEXT,
    direction TEXT NOT NULL DEFAULT 'AtoB', created_at TEXT NOT NULL DEFAULT (datetime('now')));
CREATE TABLE IF NOT EXISTS watch_plates (
    id INTEGER PRIMARY KEY AUTOINCREMENT, plate TEXT NOT NULL UNIQUE, label TEXT,
    list_type TEXT NOT NULL DEFAULT 'blacklist', created_at TEXT NOT NULL DEFAULT (datetime('now')));
CREATE TABLE IF NOT EXISTS watch_faces (
    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, label TEXT,
    list_type TEXT NOT NULL DEFAULT 'blacklist', embedding TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')));
CREATE TABLE IF NOT EXISTS count_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT, time TEXT NOT NULL DEFAULT (datetime('now')),
    camera_id TEXT NOT NULL, zone TEXT, track_id INTEGER, direction TEXT NOT NULL,
    class TEXT DEFAULT 'person', ts_seconds REAL, frame_idx INTEGER);
CREATE TABLE IF NOT EXISTS plate_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT, time TEXT NOT NULL DEFAULT (datetime('now')),
    camera_id TEXT NOT NULL, track_id INTEGER, plate TEXT NOT NULL, conf REAL, snapshot TEXT,
    reads INTEGER, ts_seconds REAL, frame_idx INTEGER);
CREATE TABLE IF NOT EXISTS face_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT, time TEXT NOT NULL DEFAULT (datetime('now')),
    camera_id TEXT NOT NULL, track_id INTEGER, age INTEGER, gender TEXT, conf REAL,
    match_name TEXT, match_score REAL, ts_seconds REAL, frame_idx INTEGER);
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT, time TEXT NOT NULL DEFAULT (datetime('now')),
    camera_id TEXT, kind TEXT NOT NULL, ref TEXT NOT NULL, list_type TEXT, label TEXT,
    acked_by TEXT, acked_at TEXT, snapshot TEXT);
"""


class SqliteStore(BaseStore):
    """Yerel demo backend'i — Docker/Postgres olmayan makinede aynı arayüz."""

    _ph = "?"

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        # isolation_level=None (autocommit): her INSERT kendi kısa kilidiyle biter.
        # Aksi hâlde analiz bağlantısı ilk olaydan analiz sonuna dek TEK yazma
        # transaction'ı tutar → eşzamanlı zone/kamera kaydı "database is locked" (500).
        self.conn = sqlite3.connect(self.db_path, timeout=30, check_same_thread=False,
                                    isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=30000")
        self.conn.executescript(_SQLITE_SCHEMA)
        for tablo, sutun, tip in (("cameras", "tasks", "TEXT"), ("cameras", "url_sub", "TEXT"),
                                  ("cameras", "http_headers", "TEXT"),
                                  ("plate_events", "snapshot", "TEXT"),
                                  ("alerts", "snapshot", "TEXT")):
            try:   # hafif migration: eski DB'lerde eksik sütunları ekle
                self.conn.execute(f"ALTER TABLE {tablo} ADD COLUMN {sutun} {tip}")
            except sqlite3.OperationalError:
                pass
        self.conn.commit()

    def _x(self, sql: str, params: tuple = ()) -> Any:
        return self.conn.execute(sql, params)

    def _all(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        return [dict(r) for r in self.conn.execute(sql, params).fetchall()]

    def list_zones(self, camera_id: str) -> list[dict[str, Any]]:
        rows = self._all("SELECT id, camera_id, kind, name, points, classes, direction"
                         " FROM zones WHERE camera_id=? ORDER BY id", (camera_id,))
        for r in rows:
            r["points"] = json.loads(r["points"] or "[]")
            r["classes"] = json.loads(r["classes"] or "[]")
        return rows

    def add_zone(self, camera_id, kind, name, points, classes, direction) -> None:
        self._x("INSERT INTO zones (camera_id, kind, name, points, classes, direction)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (camera_id, kind, name, json.dumps(points), json.dumps(classes),
                 direction or "AtoB"))
        self.commit()

    def add_watch_plate(self, plate, label, list_type) -> None:
        self._x("INSERT OR REPLACE INTO watch_plates (plate, label, list_type) VALUES (?, ?, ?)",
                (plate.replace(" ", "").upper(), label, list_type))
        self.commit()

    def add_watch_face(self, name, label, list_type, embedding=None) -> None:
        self._x("INSERT INTO watch_faces (name, label, list_type, embedding) VALUES (?, ?, ?, ?)",
                (name, label, list_type, json.dumps(embedding) if embedding else None))
        self.commit()

    def faces_with_embedding(self) -> list[dict[str, Any]]:
        rows = self._all("SELECT name, label, list_type, embedding FROM watch_faces"
                         " WHERE embedding IS NOT NULL AND embedding != ''")
        for r in rows:
            r["embedding"] = json.loads(r["embedding"])
        return rows

    def list_cameras_db(self) -> list[dict[str, Any]]:
        rows = self._all("SELECT id, name, source, url_sub, http_headers, tasks"
                         " FROM cameras ORDER BY created_at")
        for r in rows:
            r["tasks"] = json.loads(r["tasks"]) if r.get("tasks") else None
        return rows

    def add_camera(self, cid, name, source, url_sub: str = "",
                   http_headers: str = "") -> None:
        self._x("INSERT INTO cameras (id, name, source, url_sub, http_headers)"
                " VALUES (?, ?, ?, ?, ?)"
                " ON CONFLICT(id) DO UPDATE SET name=excluded.name, source=excluded.source,"
                " url_sub=excluded.url_sub, http_headers=excluded.http_headers",
                (cid, name, source, url_sub or None, http_headers or None))
        self.commit()

    def set_camera_tasks(self, cid, tasks) -> None:
        self._x("UPDATE cameras SET tasks=? WHERE id=?", (json.dumps(tasks), cid))
        self.commit()

    def latest_health(self) -> list[dict[str, Any]]:
        # MAX(time) saniye çözünürlüğünde eşitlik yapar → en son satırı id ile seç
        return self._all(
            "SELECT camera_id, time, status, fps FROM camera_health"
            " WHERE id IN (SELECT MAX(id) FROM camera_health GROUP BY camera_id)")

    def recent_events(self, limit: int = 50, tur: str = "",
                      kamera: str = "") -> list[dict[str, Any]]:
        q = """
        SELECT * FROM (
          SELECT time, 'count' AS type, camera_id,
                 TRIM(COALESCE(zone,'')||' '||direction) AS detail, ts_seconds, frame_idx,
                 NULL AS snapshot
            FROM count_events
          UNION ALL
          SELECT time, 'plate', camera_id, plate, ts_seconds, frame_idx, snapshot FROM plate_events
          UNION ALL
          SELECT time, 'face', camera_id,
                 COALESCE(gender,'?')||' ~'||COALESCE(age,0), ts_seconds, frame_idx, NULL
            FROM face_events
        ) WHERE (?='' OR type=?) AND (?='' OR camera_id=?)
        ORDER BY time DESC, ts_seconds DESC LIMIT ?
        """
        return self._all(q, (tur, tur, kamera, kamera, limit))

    def commit(self) -> None:
        self.conn.commit()

    def close(self) -> None:
        self.conn.commit()
        self.conn.close()


# ─────────────────────────── PostgreSQL ────────────────────────────

class PgStore(BaseStore):
    """Üretim backend'i — PostgreSQL 16 + TimescaleDB + pgvector (bkz db/schema.sql)."""

    _ph = "%s"

    def __init__(self, url: str) -> None:
        try:
            import psycopg
        except ImportError as e:
            raise RuntimeError("PostgreSQL için 'psycopg[binary]' gerekli: pip install 'psycopg[binary]'") from e
        self.conn = psycopg.connect(url, autocommit=True)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        """Tablolar yoksa db/schema.sql'i uygular (compose initdb zaten yükler; bu emniyet)."""
        exists = self.conn.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_name='cameras'").fetchone()
        if exists:
            # Hafif migration: kurulu DB'lerde sonradan eklenen sütunlar
            for tablo, sutun in (("plate_events", "snapshot"), ("alerts", "snapshot"),
                                 ("cameras", "http_headers")):
                self.conn.execute(
                    f"ALTER TABLE {tablo} ADD COLUMN IF NOT EXISTS {sutun} TEXT")
            self.conn.execute("""CREATE TABLE IF NOT EXISTS recordings (
                id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY, camera_id TEXT NOT NULL,
                path TEXT NOT NULL UNIQUE, start_time TIMESTAMPTZ NOT NULL,
                end_time TIMESTAMPTZ NOT NULL, duration REAL NOT NULL,
                size_bytes BIGINT NOT NULL)""")
            self.conn.execute("CREATE INDEX IF NOT EXISTS ix_rec_cam_time"
                              " ON recordings (camera_id, start_time DESC)")
            self.conn.commit()
            return
        schema_path = _ROOT / "db" / "schema.sql"
        if not schema_path.exists():
            raise RuntimeError(f"Şema yok ve {schema_path} bulunamadı")
        sql = schema_path.read_text(encoding="utf-8")
        # continuous aggregate transaction içinde oluşturulamaz → parçalar ayrı yürütülür
        for chunk in sql.split("-- #split"):
            chunk = chunk.strip()
            if chunk:
                self.conn.execute(chunk)

    def _x(self, sql: str, params: tuple = ()) -> Any:
        return self.conn.execute(self._q(sql), params)

    def start_run(self, kind: str, source: str, meta: dict | None = None) -> None:
        self._x("INSERT INTO runs (kind, source, meta) VALUES (?, ?, ?::jsonb)",
                (kind, source, json.dumps(meta or {})))

    def _all(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        cur = self.conn.execute(self._q(sql), params)
        cols = [d.name for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    def list_zones(self, camera_id: str) -> list[dict[str, Any]]:
        rows = self._all("SELECT id, camera_id, kind, name, points::text AS points,"
                         " classes, direction FROM zones WHERE camera_id=? ORDER BY id",
                         (camera_id,))
        for r in rows:
            r["points"] = json.loads(r["points"] or "[]")
            r["classes"] = list(r["classes"] or [])
        return rows

    def add_zone(self, camera_id, kind, name, points, classes, direction) -> None:
        self._x("INSERT INTO zones (camera_id, kind, name, points, classes, direction)"
                " VALUES (?, ?, ?, ?::jsonb, ?, ?)",
                (camera_id, kind, name, json.dumps(points), list(classes or []),
                 direction or "AtoB"))

    def add_watch_plate(self, plate, label, list_type) -> None:
        self._x("INSERT INTO watch_plates (plate, label, list_type) VALUES (?, ?, ?)"
                " ON CONFLICT (plate) DO UPDATE SET label=EXCLUDED.label, list_type=EXCLUDED.list_type",
                (plate.replace(" ", "").upper(), label, list_type))

    def add_watch_face(self, name, label, list_type, embedding=None) -> None:
        emb = json.dumps(embedding) if embedding else None
        self._x("INSERT INTO watch_faces (name, label, list_type, embedding)"
                " VALUES (?, ?, ?, ?::vector)", (name, label, list_type, emb))

    def faces_with_embedding(self) -> list[dict[str, Any]]:
        rows = self._all("SELECT name, label, list_type, embedding::text AS embedding"
                         " FROM watch_faces WHERE embedding IS NOT NULL")
        for r in rows:
            r["embedding"] = json.loads(r["embedding"])
        return rows

    def list_cameras_db(self) -> list[dict[str, Any]]:
        rows = self._all("SELECT id, name, source, url_sub, http_headers,"
                         " tasks::text AS tasks, detect_fps"
                         " FROM cameras ORDER BY created_at")
        for r in rows:
            r["tasks"] = json.loads(r["tasks"]) if r.get("tasks") else None
        return rows

    def add_camera(self, cid, name, source, url_sub: str = "",
                   http_headers: str = "") -> None:
        self._x("INSERT INTO cameras (id, name, source, url_sub, http_headers)"
                " VALUES (?, ?, ?, ?, ?)"
                " ON CONFLICT (id) DO UPDATE SET name=EXCLUDED.name, source=EXCLUDED.source,"
                " url_sub=EXCLUDED.url_sub, http_headers=EXCLUDED.http_headers",
                (cid, name, source, url_sub or None, http_headers or None))

    def set_camera_tasks(self, cid, tasks) -> None:
        self._x("UPDATE cameras SET tasks=?::jsonb WHERE id=?", (json.dumps(tasks), cid))

    def latest_health(self) -> list[dict[str, Any]]:
        rows = self._all(
            "SELECT DISTINCT ON (camera_id) camera_id, time, status, fps"
            " FROM camera_health ORDER BY camera_id, time DESC")
        for r in rows:
            r["time"] = str(r["time"])
        return rows

    def recent_events(self, limit: int = 50, tur: str = "",
                      kamera: str = "") -> list[dict[str, Any]]:
        q = """
        SELECT * FROM (
          SELECT time, 'count' AS type, camera_id,
                 TRIM(COALESCE(zone,'')||' '||direction) AS detail, ts_seconds, frame_idx,
                 NULL AS snapshot
            FROM count_events
          UNION ALL
          SELECT time, 'plate', camera_id, plate, ts_seconds, frame_idx, snapshot FROM plate_events
          UNION ALL
          SELECT time, 'face', camera_id,
                 COALESCE(gender, chr(63))||' ~'||COALESCE(age::text,'0'), ts_seconds, frame_idx,
                 NULL
            FROM face_events
        ) ev WHERE (?='' OR type=?) AND (?='' OR camera_id=?)
        ORDER BY time DESC, ts_seconds DESC NULLS LAST LIMIT ?
        """
        rows = self._all(q, (tur, tur, kamera, kamera, limit))
        for r in rows:
            r["time"] = str(r["time"])
        return rows

    def recent_alerts(self, limit: int = 20, pending_only: bool = False) -> list[dict[str, Any]]:
        rows = super().recent_alerts(limit, pending_only)
        for r in rows:
            r["time"] = str(r["time"])
            if r.get("acked_at"):
                r["acked_at"] = str(r["acked_at"])
        return rows

    def close(self) -> None:
        self.conn.close()
