CREATE TABLE IF NOT EXISTS telemetry_samples_v2 (
  reading_id TEXT PRIMARY KEY,
  asset_id TEXT NOT NULL,
  sensor_id TEXT NOT NULL,
  observed_at TEXT NOT NULL,
  received_at TEXT NOT NULL,
  payload_hash TEXT NOT NULL,
  canonical_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_telemetry_samples_v2_history
ON telemetry_samples_v2(asset_id, sensor_id, observed_at DESC);

CREATE TABLE IF NOT EXISTS raw_readings_v2 (
  raw_id TEXT PRIMARY KEY,
  sensor_id TEXT NOT NULL,
  scheduled_at TEXT NOT NULL,
  received_at TEXT NOT NULL,
  payload_hash TEXT NOT NULL,
  payload_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_raw_readings_v2_slot
ON raw_readings_v2(sensor_id, scheduled_at);

CREATE TABLE IF NOT EXISTS collection_attempts_v2 (
  attempt_id TEXT PRIMARY KEY,
  sensor_id TEXT NOT NULL,
  scheduled_at TEXT NOT NULL,
  attempted_at TEXT NOT NULL,
  succeeded BOOLEAN NOT NULL,
  latency_ms INTEGER,
  error_code TEXT
);
