-- AurasVision — PostgreSQL şeması (TimescaleDB + pgvector)
-- Kaynak tasarım: docs/mimari-100-kamera.md §4
-- Notlar:
--  * pgvector ZORUNLU (yüz embedding). TimescaleDB OPSİYONEL — yoksa düz tablo
--    olarak çalışır (DO blokları hatayı yutar), sıkıştırma/retention devre dışı kalır.
--  * Dosya idempotent: tekrar çalıştırmak güvenlidir.
--  * `-- #split` satırları PgStore'un otomatik kurulumunda parça sınırıdır
--    (continuous aggregate transaction içinde oluşturulamaz).

CREATE EXTENSION IF NOT EXISTS vector;
DO $$ BEGIN
  CREATE EXTENSION IF NOT EXISTS timescaledb;
EXCEPTION WHEN OTHERS THEN
  RAISE NOTICE 'timescaledb bulunamadi — duz tablolarla devam';
END $$;

-- ── Yapı tabloları ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS runs (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    kind        TEXT NOT NULL,
    source      TEXT NOT NULL,
    started_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    meta        JSONB
);

CREATE TABLE IF NOT EXISTS cameras (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    source      TEXT NOT NULL,               -- rtsp://... veya dosya yolu
    url_sub     TEXT,                        -- analiz substream'i (varsa)
    http_headers TEXT,                       -- kameraya özgü HTTP başlıkları (bazı HLS sağlayıcıları Referer şart koşar)
    enabled     BOOLEAN NOT NULL DEFAULT true,
    tasks       JSONB NOT NULL DEFAULT '{"count":true,"plate":false,"face":false}',
    detect_fps  SMALLINT NOT NULL DEFAULT 5,
    retention_days SMALLINT NOT NULL DEFAULT 90,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS zones (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    camera_id   TEXT NOT NULL,
    kind        TEXT NOT NULL CHECK (kind IN ('line','zone','intrusion')),
    name        TEXT NOT NULL DEFAULT '',
    points      JSONB NOT NULL,              -- [[x,y],...] normalize 0-1
    classes     TEXT[] NOT NULL DEFAULT '{person}',
    direction   TEXT NOT NULL DEFAULT 'AtoB',-- AtoB | BtoA (A→B geçişi 'in' sayılır / tersi)
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS zones_cam_idx ON zones(camera_id);

CREATE TABLE IF NOT EXISTS watch_plates (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    plate       TEXT NOT NULL UNIQUE,        -- normalize: boşluksuz, büyük harf
    label       TEXT,
    list_type   TEXT NOT NULL DEFAULT 'blacklist',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS watch_faces (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name        TEXT NOT NULL,
    label       TEXT,
    list_type   TEXT NOT NULL DEFAULT 'blacklist',
    embedding   VECTOR(512),                 -- ArcFace; ham görüntü YOK (KVKK)
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
DO $$ BEGIN
  CREATE INDEX watch_faces_emb_idx ON watch_faces USING hnsw (embedding vector_cosine_ops);
EXCEPTION WHEN duplicate_table THEN NULL; WHEN OTHERS THEN NULL; END $$;

-- ── Olay tabloları (TRACK bazlı — kare bazlı değil) ────────────────
CREATE TABLE IF NOT EXISTS count_events (
    time        TIMESTAMPTZ NOT NULL DEFAULT now(),
    camera_id   TEXT NOT NULL,
    zone        TEXT,                        -- çizgi/bölge adı
    track_id    BIGINT,
    direction   TEXT NOT NULL,               -- in | out
    class       TEXT NOT NULL DEFAULT 'person',
    ts_seconds  REAL,                        -- video-içi zaman (dosya analizi)
    frame_idx   INTEGER
);

CREATE TABLE IF NOT EXISTS plate_events (
    time        TIMESTAMPTZ NOT NULL DEFAULT now(),
    camera_id   TEXT NOT NULL,
    track_id    BIGINT,
    plate       TEXT NOT NULL,
    conf        REAL,
    reads       SMALLINT,                    -- oylamaya giren kare sayısı
    ts_seconds  REAL,
    frame_idx   INTEGER,
    snapshot    TEXT                         -- kanıt görüntüsü yolu (evidence.keep_days sonra silinir)
);

CREATE TABLE IF NOT EXISTS face_events (
    time        TIMESTAMPTZ NOT NULL DEFAULT now(),
    camera_id   TEXT NOT NULL,
    track_id    BIGINT,
    age         SMALLINT,
    gender      CHAR(1),                     -- M | F
    conf        REAL,
    match_name  TEXT,                        -- izleme listesi eşleşmesi (varsa)
    match_score REAL,
    ts_seconds  REAL,
    frame_idx   INTEGER
);

CREATE TABLE IF NOT EXISTS alerts (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    time        TIMESTAMPTZ NOT NULL DEFAULT now(),
    camera_id   TEXT,
    kind        TEXT NOT NULL,               -- plate | face | intrusion
    ref         TEXT NOT NULL,
    list_type   TEXT,
    label       TEXT,
    acked_by    TEXT,
    acked_at    TIMESTAMPTZ,
    snapshot    TEXT                         -- alarm anının kanıt karesi (evidence modülü)
);

CREATE TABLE IF NOT EXISTS recordings (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    camera_id   TEXT NOT NULL,
    path        TEXT NOT NULL UNIQUE,        -- record kökine göreli
    start_time  TIMESTAMPTZ NOT NULL,
    end_time    TIMESTAMPTZ NOT NULL,
    duration    REAL NOT NULL,               -- ffprobe ile ÖLÇÜLMÜŞ (nominal değil)
    size_bytes  BIGINT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_rec_cam_time ON recordings (camera_id, start_time DESC);

CREATE TABLE IF NOT EXISTS camera_health (
    time        TIMESTAMPTZ NOT NULL DEFAULT now(),
    camera_id   TEXT NOT NULL,
    fps         REAL,
    dropped     BIGINT,
    status      TEXT                         -- ok | no_signal | decode_err
);

-- ── Timescale: hypertable + sıkıştırma + retention (varsa) ─────────
DO $$ BEGIN
  PERFORM create_hypertable('count_events','time',  if_not_exists => true, migrate_data => true);
  PERFORM create_hypertable('plate_events','time',  if_not_exists => true, migrate_data => true);
  PERFORM create_hypertable('face_events','time',   if_not_exists => true, migrate_data => true);
  PERFORM create_hypertable('camera_health','time', if_not_exists => true, migrate_data => true);
EXCEPTION WHEN OTHERS THEN RAISE NOTICE 'hypertable atlandi: %', SQLERRM; END $$;

DO $$ BEGIN
  ALTER TABLE count_events  SET (timescaledb.compress, timescaledb.compress_segmentby='camera_id');
  ALTER TABLE plate_events  SET (timescaledb.compress, timescaledb.compress_segmentby='camera_id');
  ALTER TABLE face_events   SET (timescaledb.compress, timescaledb.compress_segmentby='camera_id');
  ALTER TABLE camera_health SET (timescaledb.compress, timescaledb.compress_segmentby='camera_id');
  PERFORM add_compression_policy('count_events',  INTERVAL '7 days', if_not_exists => true);
  PERFORM add_compression_policy('plate_events',  INTERVAL '7 days', if_not_exists => true);
  PERFORM add_compression_policy('face_events',   INTERVAL '7 days', if_not_exists => true);
  PERFORM add_compression_policy('camera_health', INTERVAL '2 days', if_not_exists => true);
  PERFORM add_retention_policy('count_events',  INTERVAL '90 days', if_not_exists => true);
  PERFORM add_retention_policy('plate_events',  INTERVAL '90 days', if_not_exists => true);
  PERFORM add_retention_policy('face_events',   INTERVAL '90 days', if_not_exists => true);
  PERFORM add_retention_policy('camera_health', INTERVAL '14 days', if_not_exists => true);
EXCEPTION WHEN OTHERS THEN RAISE NOTICE 'politikalar atlandi: %', SQLERRM; END $$;

-- #split
-- ── Rapor: 15 dakikalık doluluk özeti (dashboard buradan okur) ─────
CREATE MATERIALIZED VIEW IF NOT EXISTS occupancy_15m
WITH (timescaledb.continuous) AS
SELECT time_bucket('15 minutes', time) AS bucket,
       camera_id,
       count(*) FILTER (WHERE direction='in')  AS in_count,
       count(*) FILTER (WHERE direction='out') AS out_count
FROM count_events GROUP BY bucket, camera_id
WITH NO DATA;

-- #split
DO $$ BEGIN
  PERFORM add_continuous_aggregate_policy('occupancy_15m',
      start_offset => INTERVAL '1 hour', end_offset => INTERVAL '1 minute',
      schedule_interval => INTERVAL '5 minutes', if_not_exists => true);
EXCEPTION WHEN OTHERS THEN RAISE NOTICE 'aggregate politikasi atlandi: %', SQLERRM; END $$;
