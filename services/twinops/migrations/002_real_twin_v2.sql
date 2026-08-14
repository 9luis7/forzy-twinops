CREATE TABLE IF NOT EXISTS telemetry_samples_v2 (
  reading_id TEXT PRIMARY KEY,
  asset_id TEXT NOT NULL,
  sensor_id TEXT NOT NULL,
  observed_at TIMESTAMPTZ NOT NULL,
  received_at TIMESTAMPTZ NOT NULL,
  payload_hash TEXT NOT NULL,
  canonical_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_telemetry_samples_v2_history
ON telemetry_samples_v2(asset_id, sensor_id, observed_at DESC);

CREATE TABLE IF NOT EXISTS latest_readings_v2 (
  asset_id TEXT NOT NULL,
  sensor_id TEXT NOT NULL,
  reading_id TEXT NOT NULL,
  received_at TIMESTAMPTZ NOT NULL,
  canonical_json TEXT NOT NULL,
  PRIMARY KEY (asset_id, sensor_id)
);

INSERT INTO latest_readings_v2 (
  asset_id, sensor_id, reading_id, received_at, canonical_json
)
SELECT asset_id, sensor_id, reading_id, received_at, canonical_json
FROM (
  SELECT
    asset_id,
    sensor_id,
    reading_id,
    received_at,
    canonical_json,
    ROW_NUMBER() OVER (
      PARTITION BY asset_id, sensor_id
      ORDER BY received_at DESC, observed_at DESC, reading_id DESC
    ) AS position
  FROM telemetry_samples_v2
) AS ranked
WHERE position = 1
ON CONFLICT (asset_id, sensor_id) DO UPDATE SET
  reading_id = excluded.reading_id,
  received_at = excluded.received_at,
  canonical_json = excluded.canonical_json
WHERE excluded.received_at >= latest_readings_v2.received_at;

CREATE TABLE IF NOT EXISTS raw_readings_v2 (
  raw_id TEXT PRIMARY KEY,
  sensor_id TEXT NOT NULL,
  scheduled_at TIMESTAMPTZ NOT NULL,
  received_at TIMESTAMPTZ NOT NULL,
  payload_hash TEXT NOT NULL,
  payload_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_raw_readings_v2_slot
ON raw_readings_v2(sensor_id, scheduled_at);

CREATE TABLE IF NOT EXISTS collection_attempts_v2 (
  attempt_id TEXT PRIMARY KEY,
  sensor_id TEXT NOT NULL,
  scheduled_at TIMESTAMPTZ NOT NULL,
  attempted_at TIMESTAMPTZ NOT NULL,
  succeeded BOOLEAN NOT NULL,
  latency_ms INTEGER,
  error_code TEXT
);

CREATE TABLE IF NOT EXISTS refresh_cycles_v2 (
  asset_id TEXT NOT NULL,
  scheduled_at TIMESTAMPTZ NOT NULL,
  owner_token TEXT NOT NULL,
  claimed_at TIMESTAMPTZ NOT NULL,
  completed_at TIMESTAMPTZ,
  outcomes_json TEXT,
  status TEXT NOT NULL CHECK (status IN ('in_progress', 'completed')),
  PRIMARY KEY (asset_id, scheduled_at)
);
