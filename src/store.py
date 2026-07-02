"""SQLite çıktı katmanı.

Tasarım (manifest convention): her kayıtta source + timestamp; senkron için
`synced` bayrağı (offline saha → merkez store-and-forward'a hazır).
KVKK: ham görüntü saklanmaz; sadece anonim metrik / embedding özeti.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    kind        TEXT NOT NULL,            -- count | plate | face | analyze
    source      TEXT NOT NULL,            -- video yolu / kamera id
    started_at  TEXT NOT NULL,
    meta        TEXT                      -- JSON: model, eşikler vs.
);

-- Kişi sayımı: çizgi geçiş olayları + özet
CREATE TABLE IF NOT EXISTS count_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      INTEGER NOT NULL REFERENCES runs(id),
    track_id    INTEGER NOT NULL,
    direction   TEXT NOT NULL,            -- in | out
    frame_idx   INTEGER NOT NULL,
    ts_seconds  REAL NOT NULL,
    synced      INTEGER NOT NULL DEFAULT 0
);

-- Plaka okumaları
CREATE TABLE IF NOT EXISTS plate_reads (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      INTEGER NOT NULL REFERENCES runs(id),
    plate       TEXT NOT NULL,
    confidence  REAL,
    frame_idx   INTEGER NOT NULL,
    ts_seconds  REAL NOT NULL,
    synced      INTEGER NOT NULL DEFAULT 0
);

-- Yüz tespitleri (anonim: kimlik yok, demografi tahmini)
CREATE TABLE IF NOT EXISTS face_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      INTEGER NOT NULL REFERENCES runs(id),
    track_hint  INTEGER,                  -- varsa kaba grup
    age         INTEGER,
    gender      TEXT,                     -- M | F (anonim tahmin)
    det_score   REAL,
    frame_idx   INTEGER NOT NULL,
    ts_seconds  REAL NOT NULL,
    synced      INTEGER NOT NULL DEFAULT 0
);

-- Bölge/çizgi tanımları (kamera görüntüsü üzerine çizilen; normalize 0-1 koordinat)
CREATE TABLE IF NOT EXISTS zones (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    camera_id   TEXT NOT NULL,
    kind        TEXT NOT NULL,            -- line | zone | intrusion
    name        TEXT,
    points      TEXT NOT NULL,            -- JSON: [[x,y],...] normalize
    classes     TEXT,                     -- JSON: ["person","car"]
    direction   TEXT,                     -- line için: in yönü ipucu
    created_at  TEXT NOT NULL
);

-- İzleme listeleri (plaka)
CREATE TABLE IF NOT EXISTS watch_plates (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    plate       TEXT NOT NULL UNIQUE,
    label       TEXT,                     -- serbest etiket
    list_type   TEXT NOT NULL DEFAULT 'blacklist',  -- blacklist | vip | visitor
    created_at  TEXT NOT NULL
);

-- İzleme listeleri (yüz/personel) — KVKK: embedding opsiyonel, ham görüntü saklanmaz
CREATE TABLE IF NOT EXISTS watch_faces (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    label       TEXT,
    list_type   TEXT NOT NULL DEFAULT 'blacklist',  -- blacklist | allowed | vip
    embedding   TEXT,                     -- JSON: 512d (opsiyonel)
    created_at  TEXT NOT NULL
);

-- Kameralar (UI'dan eklenenler; config.yaml'daki sabitlere ek)
CREATE TABLE IF NOT EXISTS cameras (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    source      TEXT NOT NULL,
    created_at  TEXT NOT NULL
);

-- Uyarılar — izleme listesi eşleşmeleri (plaka/yüz kara listede yakalandı)
CREATE TABLE IF NOT EXISTS alerts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    kind        TEXT NOT NULL,            -- plate | face
    ref         TEXT NOT NULL,            -- eşleşen plaka metni / kişi adı
    list_type   TEXT NOT NULL,            -- blacklist | vip | ...
    label       TEXT,
    camera      TEXT,
    created_at  TEXT NOT NULL,
    seen        INTEGER NOT NULL DEFAULT 0
);
"""


class Store:
    """POC için ince SQLite sarmalayıcı."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        # WAL + busy_timeout: eşzamanlı okuma/yazma kilitlenmesini önler
        self.conn = sqlite3.connect(self.db_path, timeout=30, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=30000")
        self.conn.executescript(_SCHEMA)
        # Hafif migration: count_events.line_name (eski DB'lerde yoksa ekle)
        try:
            self.conn.execute("ALTER TABLE count_events ADD COLUMN line_name TEXT")
        except sqlite3.OperationalError:
            pass  # zaten var
        self.conn.commit()

    def start_run(self, kind: str, source: str, started_at: str, meta: str = "") -> int:
        cur = self.conn.execute(
            "INSERT INTO runs (kind, source, started_at, meta) VALUES (?, ?, ?, ?)",
            (kind, source, started_at, meta),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def add_count_event(self, run_id: int, track_id: int, direction: str,
                        frame_idx: int, ts_seconds: float, line_name: str = "") -> None:
        self.conn.execute(
            "INSERT INTO count_events (run_id, track_id, direction, frame_idx, ts_seconds, line_name)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (run_id, track_id, direction, frame_idx, ts_seconds, line_name),
        )

    def add_plate_read(self, run_id: int, plate: str, confidence: float | None,
                       frame_idx: int, ts_seconds: float) -> None:
        self.conn.execute(
            "INSERT INTO plate_reads (run_id, plate, confidence, frame_idx, ts_seconds)"
            " VALUES (?, ?, ?, ?, ?)",
            (run_id, plate, confidence, frame_idx, ts_seconds),
        )

    def add_face_event(self, run_id: int, age: int | None, gender: str | None,
                       det_score: float | None, frame_idx: int, ts_seconds: float,
                       track_hint: int | None = None) -> None:
        self.conn.execute(
            "INSERT INTO face_events (run_id, track_hint, age, gender, det_score, frame_idx, ts_seconds)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (run_id, track_hint, age, gender, det_score, frame_idx, ts_seconds),
        )

    # --- Bölgeler ---
    def list_zones(self, camera_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT id, camera_id, kind, name, points, classes, direction"
            " FROM zones WHERE camera_id=? ORDER BY id", (camera_id,)).fetchall()
        cols = ["id", "camera_id", "kind", "name", "points", "classes", "direction"]
        return [dict(zip(cols, r)) for r in rows]

    def add_zone(self, camera_id: str, kind: str, name: str, points: str,
                 classes: str, direction: str, created_at: str) -> int:
        cur = self.conn.execute(
            "INSERT INTO zones (camera_id, kind, name, points, classes, direction, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (camera_id, kind, name, points, classes, direction, created_at))
        self.conn.commit()
        return int(cur.lastrowid)

    def clear_zones(self, camera_id: str) -> None:
        self.conn.execute("DELETE FROM zones WHERE camera_id=?", (camera_id,))
        self.conn.commit()

    # --- İzleme listeleri ---
    def list_watch(self, kind: str) -> list[dict[str, Any]]:
        table = "watch_plates" if kind == "plate" else "watch_faces"
        rows = self.conn.execute(f"SELECT * FROM {table} ORDER BY id DESC").fetchall()
        cols = [c[0] for c in self.conn.execute(f"SELECT * FROM {table} LIMIT 0").description]
        return [dict(zip(cols, r)) for r in rows]

    def add_watch_plate(self, plate: str, label: str, list_type: str, created_at: str) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO watch_plates (plate, label, list_type, created_at)"
            " VALUES (?, ?, ?, ?)", (plate.replace(" ", "").upper(), label, list_type, created_at))
        self.conn.commit()

    def add_watch_face(self, name: str, label: str, list_type: str, created_at: str,
                       embedding: str | None = None) -> None:
        self.conn.execute(
            "INSERT INTO watch_faces (name, label, list_type, embedding, created_at)"
            " VALUES (?, ?, ?, ?, ?)", (name, label, list_type, embedding, created_at))
        self.conn.commit()

    def faces_with_embedding(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT name, label, list_type, embedding FROM watch_faces"
            " WHERE embedding IS NOT NULL AND embedding != ''").fetchall()
        cols = ["name", "label", "list_type", "embedding"]
        return [dict(zip(cols, r)) for r in rows]

    # --- Kameralar (DB) ---
    def list_cameras_db(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT id, name, source FROM cameras ORDER BY created_at").fetchall()
        return [{"id": r[0], "name": r[1], "source": r[2]} for r in rows]

    def add_camera(self, cid: str, name: str, source: str, created_at: str) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO cameras (id, name, source, created_at)"
            " VALUES (?, ?, ?, ?)", (cid, name, source, created_at))
        self.conn.commit()

    def delete_camera(self, cid: str) -> None:
        self.conn.execute("DELETE FROM cameras WHERE id=?", (cid,))
        self.conn.commit()

    def delete_watch(self, kind: str, row_id: int) -> None:
        table = "watch_plates" if kind == "plate" else "watch_faces"
        self.conn.execute(f"DELETE FROM {table} WHERE id=?", (row_id,))
        self.conn.commit()

    # --- Plaka izleme eşleşmesi ---
    def match_plates(self, plates: list[str]) -> list[dict[str, Any]]:
        """Okunan plakaları watch_plates ile karşılaştırır; eşleşenleri döndürür."""
        out: list[dict[str, Any]] = []
        for p in {x.replace(" ", "").upper() for x in plates}:
            row = self.conn.execute(
                "SELECT plate, label, list_type FROM watch_plates WHERE plate=?", (p,)).fetchone()
            if row:
                out.append({"plate": row[0], "label": row[1], "list_type": row[2]})
        return out

    # --- Uyarılar ---
    def add_alert(self, kind: str, ref: str, list_type: str, label: str,
                  camera: str, created_at: str) -> None:
        self.conn.execute(
            "INSERT INTO alerts (kind, ref, list_type, label, camera, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)", (kind, ref, list_type, label, camera, created_at))
        self.conn.commit()

    def recent_alerts(self, limit: int = 20) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT kind, ref, list_type, label, camera, created_at FROM alerts"
            " ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        cols = ["kind", "ref", "list_type", "label", "camera", "created_at"]
        return [dict(zip(cols, r)) for r in rows]

    def clear_analysis(self) -> None:
        """Önceki analiz çıktılarını siler (her test koşusu temiz başlasın).

        SİLİNİR: runs, count_events, plate_reads, face_events, alerts.
        KORUNUR: cameras, zones, watch_plates, watch_faces (kullanıcı ayarı).
        """
        for t in ("count_events", "plate_reads", "face_events", "alerts", "runs"):
            self.conn.execute(f"DELETE FROM {t}")
        self.conn.commit()

    def recent_events(self, limit: int = 50) -> list[dict[str, Any]]:
        """count/plate/face olaylarını tek akışta birleştirir (en yeni önce)."""
        q = """
        SELECT 'count' AS type, TRIM(COALESCE(line_name,'')||' '||direction) AS detail, ts_seconds, frame_idx, run_id FROM count_events
        UNION ALL
        SELECT 'plate' AS type, plate AS detail, ts_seconds, frame_idx, run_id FROM plate_reads
        UNION ALL
        SELECT 'face' AS type, COALESCE(gender,'?')||' ~'||COALESCE(age,0) AS detail, ts_seconds, frame_idx, run_id FROM face_events
        ORDER BY run_id DESC, ts_seconds DESC LIMIT ?
        """
        rows = self.conn.execute(q, (limit,)).fetchall()
        cols = ["type", "detail", "ts_seconds", "frame_idx", "run_id"]
        return [dict(zip(cols, r)) for r in rows]

    def commit(self) -> None:
        self.conn.commit()

    def summary(self, run_id: int) -> dict[str, Any]:
        c = self.conn
        return {
            "in": c.execute("SELECT COUNT(*) FROM count_events WHERE run_id=? AND direction='in'", (run_id,)).fetchone()[0],
            "out": c.execute("SELECT COUNT(*) FROM count_events WHERE run_id=? AND direction='out'", (run_id,)).fetchone()[0],
            "plates": c.execute("SELECT COUNT(DISTINCT plate) FROM plate_reads WHERE run_id=?", (run_id,)).fetchone()[0],
            "faces": c.execute("SELECT COUNT(*) FROM face_events WHERE run_id=?", (run_id,)).fetchone()[0],
        }

    def close(self) -> None:
        self.conn.commit()
        self.conn.close()
