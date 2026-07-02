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


DEFAULT_TASKS = {"count": True, "plate": False, "face": False}


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
        else:
            if not c.get("tasks"):
                c["tasks"] = dict(DEFAULT_TASKS)
            by_id[c["id"]] = c
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
                        ts_seconds: float, frame_idx: int, track_id: int | None = None) -> None:
        self._x("INSERT INTO plate_events (camera_id, plate, conf, reads, ts_seconds, frame_idx, track_id)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (camera_id, plate, conf, reads, round(ts_seconds, 2), frame_idx, track_id))

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

    def add_camera(self, cid: str, name: str, source: str) -> None:
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
        self.commit()

    # --- Uyarılar ---
    def add_alert(self, kind: str, ref: str, list_type: str, label: str, camera_id: str) -> None:
        self._x("INSERT INTO alerts (kind, ref, list_type, label, camera_id)"
                " VALUES (?, ?, ?, ?, ?)", (kind, ref, list_type, label, camera_id))
        self.commit()

    def recent_alerts(self, limit: int = 20) -> list[dict[str, Any]]:
        return self._all("SELECT kind, ref, list_type, label, camera_id, time FROM alerts"
                         " ORDER BY time DESC LIMIT ?", (limit,))

    def clear_analysis(self) -> None:
        """Önceki analiz çıktılarını siler. KORUNUR: cameras, zones, izleme listeleri."""
        for t in ("count_events", "plate_events", "face_events", "alerts", "runs"):
            self._x(f"DELETE FROM {t}")
        self.commit()

    def recent_events(self, limit: int = 50) -> list[dict[str, Any]]:
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
    tasks TEXT, created_at TEXT NOT NULL DEFAULT (datetime('now')));
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
    camera_id TEXT NOT NULL, track_id INTEGER, plate TEXT NOT NULL, conf REAL,
    reads INTEGER, ts_seconds REAL, frame_idx INTEGER);
CREATE TABLE IF NOT EXISTS face_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT, time TEXT NOT NULL DEFAULT (datetime('now')),
    camera_id TEXT NOT NULL, track_id INTEGER, age INTEGER, gender TEXT, conf REAL,
    match_name TEXT, match_score REAL, ts_seconds REAL, frame_idx INTEGER);
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT, time TEXT NOT NULL DEFAULT (datetime('now')),
    camera_id TEXT, kind TEXT NOT NULL, ref TEXT NOT NULL, list_type TEXT, label TEXT,
    acked_by TEXT, acked_at TEXT);
"""


class SqliteStore(BaseStore):
    """Yerel demo backend'i — Docker/Postgres olmayan makinede aynı arayüz."""

    _ph = "?"

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path, timeout=30, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=30000")
        self.conn.executescript(_SQLITE_SCHEMA)
        try:   # hafif migration: eski DB'lerde cameras.tasks yoksa ekle
            self.conn.execute("ALTER TABLE cameras ADD COLUMN tasks TEXT")
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
        rows = self._all("SELECT id, name, source, tasks FROM cameras ORDER BY created_at")
        for r in rows:
            r["tasks"] = json.loads(r["tasks"]) if r.get("tasks") else None
        return rows

    def add_camera(self, cid, name, source) -> None:
        self._x("INSERT INTO cameras (id, name, source) VALUES (?, ?, ?)"
                " ON CONFLICT(id) DO UPDATE SET name=excluded.name, source=excluded.source",
                (cid, name, source))
        self.commit()

    def set_camera_tasks(self, cid, tasks) -> None:
        self._x("UPDATE cameras SET tasks=? WHERE id=?", (json.dumps(tasks), cid))
        self.commit()

    def latest_health(self) -> list[dict[str, Any]]:
        # MAX(time) saniye çözünürlüğünde eşitlik yapar → en son satırı id ile seç
        return self._all(
            "SELECT camera_id, time, status, fps FROM camera_health"
            " WHERE id IN (SELECT MAX(id) FROM camera_health GROUP BY camera_id)")

    def recent_events(self, limit: int = 50) -> list[dict[str, Any]]:
        q = """
        SELECT * FROM (
          SELECT time, 'count' AS type, camera_id,
                 TRIM(COALESCE(zone,'')||' '||direction) AS detail, ts_seconds, frame_idx
            FROM count_events
          UNION ALL
          SELECT time, 'plate', camera_id, plate, ts_seconds, frame_idx FROM plate_events
          UNION ALL
          SELECT time, 'face', camera_id,
                 COALESCE(gender,'?')||' ~'||COALESCE(age,0), ts_seconds, frame_idx
            FROM face_events
        ) ORDER BY time DESC, ts_seconds DESC LIMIT ?
        """
        return self._all(q, (limit,))

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
        rows = self._all("SELECT id, name, source, tasks::text AS tasks"
                         " FROM cameras ORDER BY created_at")
        for r in rows:
            r["tasks"] = json.loads(r["tasks"]) if r.get("tasks") else None
        return rows

    def add_camera(self, cid, name, source) -> None:
        self._x("INSERT INTO cameras (id, name, source) VALUES (?, ?, ?)"
                " ON CONFLICT (id) DO UPDATE SET name=EXCLUDED.name, source=EXCLUDED.source",
                (cid, name, source))

    def set_camera_tasks(self, cid, tasks) -> None:
        self._x("UPDATE cameras SET tasks=?::jsonb WHERE id=?", (json.dumps(tasks), cid))

    def latest_health(self) -> list[dict[str, Any]]:
        rows = self._all(
            "SELECT DISTINCT ON (camera_id) camera_id, time, status, fps"
            " FROM camera_health ORDER BY camera_id, time DESC")
        for r in rows:
            r["time"] = str(r["time"])
        return rows

    def recent_events(self, limit: int = 50) -> list[dict[str, Any]]:
        q = """
        SELECT * FROM (
          SELECT time, 'count' AS type, camera_id,
                 TRIM(COALESCE(zone,'')||' '||direction) AS detail, ts_seconds, frame_idx
            FROM count_events
          UNION ALL
          SELECT time, 'plate', camera_id, plate, ts_seconds, frame_idx FROM plate_events
          UNION ALL
          SELECT time, 'face', camera_id,
                 COALESCE(gender, chr(63))||' ~'||COALESCE(age::text,'0'), ts_seconds, frame_idx
            FROM face_events
        ) ev ORDER BY time DESC, ts_seconds DESC NULLS LAST LIMIT ?
        """
        rows = self._all(q, (limit,))
        for r in rows:
            r["time"] = str(r["time"])
        return rows

    def recent_alerts(self, limit: int = 20) -> list[dict[str, Any]]:
        rows = super().recent_alerts(limit)
        for r in rows:
            r["time"] = str(r["time"])
        return rows

    def close(self) -> None:
        self.conn.close()
