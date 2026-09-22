"""Yangın olayının store SQL parçaları ve expand-only PostgreSQL migration'ı."""

SQLITE_FIRE_SCHEMA = """
CREATE TABLE IF NOT EXISTS fire_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT, time TEXT NOT NULL DEFAULT (datetime('now')),
    camera_id TEXT NOT NULL, state TEXT NOT NULL, class TEXT NOT NULL, conf REAL,
    confirm_frames INTEGER NOT NULL, duration REAL NOT NULL, ts_seconds REAL,
    frame_idx INTEGER, snapshot TEXT, clip TEXT);
"""

SQLITE_RECENT_EVENTS = """
SELECT * FROM (
  SELECT time, 'count' AS type, camera_id,
         TRIM(COALESCE(zone,'')||' '||direction) AS detail, ts_seconds, frame_idx,
         NULL AS snapshot, NULL AS state, NULL AS clip FROM count_events
  UNION ALL
  SELECT time, 'plate', camera_id, plate, ts_seconds, frame_idx, snapshot,
         NULL, NULL FROM plate_events
  UNION ALL
  SELECT time, 'face', camera_id,
         COALESCE(gender,'?')||' ~'||COALESCE(age,0), ts_seconds, frame_idx, NULL,
         NULL AS state, NULL AS clip FROM face_events
  UNION ALL
  SELECT time, 'fire', camera_id, class||' · '||state, ts_seconds, frame_idx,
         snapshot, state, clip FROM fire_events
) WHERE (?='' OR type=?) AND (?='' OR camera_id=?)
ORDER BY time DESC, ts_seconds DESC LIMIT ?
"""

PG_RECENT_EVENTS = """
SELECT * FROM (
  SELECT time, 'count' AS type, camera_id,
         TRIM(COALESCE(zone,'')||' '||direction) AS detail, ts_seconds, frame_idx,
         NULL AS snapshot, NULL AS state, NULL AS clip FROM count_events
  UNION ALL
  SELECT time, 'plate', camera_id, plate, ts_seconds, frame_idx, snapshot,
         NULL, NULL FROM plate_events
  UNION ALL
  SELECT time, 'face', camera_id,
         COALESCE(gender, chr(63))||' ~'||COALESCE(age::text,'0'), ts_seconds, frame_idx,
         NULL, NULL AS state, NULL AS clip FROM face_events
  UNION ALL
  SELECT time, 'fire', camera_id, class||' · '||state, ts_seconds, frame_idx,
         snapshot, state, clip FROM fire_events
) ev WHERE (?='' OR type=?) AND (?='' OR camera_id=?)
ORDER BY time DESC, ts_seconds DESC NULLS LAST LIMIT ?
"""


def ensure_pg_fire(conn) -> None:
    """Kurulu PostgreSQL'e yangın tablosu, Timescale politikaları ve zone türleri ekler."""
    conn.execute("""CREATE TABLE IF NOT EXISTS fire_events (
        time TIMESTAMPTZ NOT NULL DEFAULT now(), camera_id TEXT NOT NULL,
        state TEXT NOT NULL, class TEXT NOT NULL, conf REAL,
        confirm_frames INTEGER NOT NULL, duration REAL NOT NULL,
        ts_seconds REAL, frame_idx INTEGER, snapshot TEXT, clip TEXT)""")
    conn.execute("""DO $$ BEGIN
      PERFORM create_hypertable('fire_events','time',
        if_not_exists => true, migrate_data => true);
    EXCEPTION WHEN OTHERS THEN
      RAISE NOTICE 'fire_events hypertable atlandi: %', SQLERRM;
    END $$""")
    conn.execute("""DO $$ BEGIN
      ALTER TABLE fire_events SET (
        timescaledb.compress, timescaledb.compress_segmentby='camera_id');
      PERFORM add_compression_policy('fire_events', INTERVAL '7 days', if_not_exists => true);
      PERFORM add_retention_policy('fire_events', INTERVAL '90 days', if_not_exists => true);
    EXCEPTION WHEN OTHERS THEN
      RAISE NOTICE 'fire_events politikalari atlandi: %', SQLERRM;
    END $$""")
    zone_check = conn.execute(
        "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
        "WHERE conrelid='zones'::regclass AND conname='zones_kind_check'").fetchone()
    if not zone_check or "firemask" not in str(zone_check[0]):
        conn.execute("ALTER TABLE zones DROP CONSTRAINT IF EXISTS zones_kind_check")
        conn.execute("ALTER TABLE zones ADD CONSTRAINT zones_kind_check "
                     "CHECK (kind IN ('line','zone','intrusion','fire','firemask'))")
