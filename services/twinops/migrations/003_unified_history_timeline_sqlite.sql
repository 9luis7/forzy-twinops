CREATE TABLE IF NOT EXISTS schema_migrations_v1 (
  migration_version TEXT PRIMARY KEY,
  sql_sha256 TEXT NOT NULL
    CHECK (
      length(sql_sha256) = 71
      AND substr(sql_sha256, 1, 7) = 'sha256:'
      AND substr(sql_sha256, 8) NOT GLOB '*[^0-9a-f]*'
    ),
  applied_at TEXT NOT NULL
    CHECK (length(applied_at) = 24 AND substr(applied_at, -1) = 'Z')
);

CREATE TABLE IF NOT EXISTS deployment_identity_v1 (
  identity_key TEXT PRIMARY KEY CHECK (identity_key = 'primary'),
  environment TEXT NOT NULL
    CHECK (environment IN ('local', 'preview', 'production')),
  label TEXT NOT NULL CHECK (length(label) > 0),
  target_fingerprint TEXT NOT NULL
    CHECK (
      length(target_fingerprint) = 71
      AND substr(target_fingerprint, 1, 7) = 'sha256:'
      AND substr(target_fingerprint, 8) NOT GLOB '*[^0-9a-f]*'
    ),
  schema_version TEXT NOT NULL CHECK (length(schema_version) > 0)
);

CREATE TABLE IF NOT EXISTS historical_import_batches_v1 (
  batch_id TEXT PRIMARY KEY
    CHECK (
      length(batch_id) = 71
      AND substr(batch_id, 1, 7) = 'sha256:'
      AND substr(batch_id, 8) NOT GLOB '*[^0-9a-f]*'
    ),
  asset_id TEXT NOT NULL CHECK (length(asset_id) > 0),
  source_name TEXT NOT NULL CHECK (length(source_name) > 0),
  source_sha256 TEXT NOT NULL
    CHECK (
      length(source_sha256) = 71
      AND substr(source_sha256, 1, 7) = 'sha256:'
      AND substr(source_sha256, 8) NOT GLOB '*[^0-9a-f]*'
    ),
  source_bytes BLOB NOT NULL,
  source_size_bytes INTEGER NOT NULL
    CHECK (source_size_bytes >= 0 AND source_size_bytes = length(source_bytes)),
  encoding TEXT NOT NULL DEFAULT 'utf-8' CHECK (encoding = 'utf-8'),
  delimiter TEXT NOT NULL DEFAULT ';' CHECK (delimiter = ';'),
  newline TEXT NOT NULL DEFAULT 'CRLF' CHECK (newline = 'CRLF'),
  raw_row_count INTEGER NOT NULL CHECK (raw_row_count >= 0),
  sample_count INTEGER NOT NULL CHECK (sample_count >= 0),
  operating_cycle_count INTEGER NOT NULL CHECK (operating_cycle_count >= 0),
  timezone_name TEXT NOT NULL CHECK (length(timezone_name) > 0),
  parser_version TEXT NOT NULL CHECK (length(parser_version) > 0),
  contract_version TEXT NOT NULL CHECK (length(contract_version) > 0),
  imported_at TEXT NOT NULL
    CHECK (length(imported_at) = 24 AND substr(imported_at, -1) = 'Z'),
  status TEXT NOT NULL CHECK (status IN ('staged', 'active', 'superseded')),
  manifest_json TEXT NOT NULL CHECK (length(manifest_json) > 0),
  manifest_sha256 TEXT NOT NULL
    CHECK (
      length(manifest_sha256) = 71
      AND substr(manifest_sha256, 1, 7) = 'sha256:'
      AND substr(manifest_sha256, 8) NOT GLOB '*[^0-9a-f]*'
    ),
  assessment_count INTEGER NOT NULL DEFAULT 0 CHECK (assessment_count >= 0),
  assessment_manifest_sha256 TEXT
    CHECK (
      assessment_manifest_sha256 IS NULL
      OR (
        length(assessment_manifest_sha256) = 71
        AND substr(assessment_manifest_sha256, 1, 7) = 'sha256:'
        AND substr(assessment_manifest_sha256, 8) NOT GLOB '*[^0-9a-f]*'
      )
    ),
  staged_at TEXT NOT NULL
    CHECK (length(staged_at) = 24 AND substr(staged_at, -1) = 'Z'),
  activated_at TEXT
    CHECK (
      activated_at IS NULL
      OR (length(activated_at) = 24 AND substr(activated_at, -1) = 'Z')
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_historical_import_batches_v1_active_asset
ON historical_import_batches_v1(asset_id) WHERE status = 'active';

CREATE TABLE IF NOT EXISTS historical_raw_rows_v1 (
  batch_id TEXT NOT NULL,
  record_ordinal INTEGER NOT NULL CHECK (record_ordinal > 0),
  source_line_number INTEGER NOT NULL CHECK (source_line_number > 0),
  byte_start INTEGER NOT NULL CHECK (byte_start >= 0),
  byte_end INTEGER NOT NULL CHECK (byte_end > byte_start),
  source_timestamp_text TEXT NOT NULL CHECK (length(source_timestamp_text) > 0),
  canonical_values_json TEXT NOT NULL CHECK (length(canonical_values_json) > 0),
  row_sha256 TEXT NOT NULL
    CHECK (
      length(row_sha256) = 71
      AND substr(row_sha256, 1, 7) = 'sha256:'
      AND substr(row_sha256, 8) NOT GLOB '*[^0-9a-f]*'
    ),
  PRIMARY KEY (batch_id, record_ordinal),
  FOREIGN KEY (batch_id) REFERENCES historical_import_batches_v1(batch_id)
    ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS historical_samples_v1 (
  reading_id TEXT PRIMARY KEY CHECK (length(reading_id) > 0),
  batch_id TEXT NOT NULL,
  record_ordinal INTEGER NOT NULL CHECK (record_ordinal > 0),
  source_line_number INTEGER NOT NULL CHECK (source_line_number > 0),
  sample_pair_id TEXT NOT NULL CHECK (length(sample_pair_id) > 0),
  operating_cycle_id TEXT NOT NULL CHECK (length(operating_cycle_id) > 0),
  asset_id TEXT NOT NULL CHECK (length(asset_id) > 0),
  sensor_id TEXT NOT NULL CHECK (sensor_id IN ('s1', 's2')),
  observed_at TEXT NOT NULL
    CHECK (length(observed_at) = 24 AND substr(observed_at, -1) = 'Z'),
  vibration_velocity_rms REAL NOT NULL,
  vibration_acceleration REAL NOT NULL,
  temperature REAL NOT NULL,
  quality_flags_json TEXT NOT NULL CHECK (length(quality_flags_json) > 0),
  payload_sha256 TEXT NOT NULL
    CHECK (
      length(payload_sha256) = 71
      AND substr(payload_sha256, 1, 7) = 'sha256:'
      AND substr(payload_sha256, 8) NOT GLOB '*[^0-9a-f]*'
    ),
  canonical_json TEXT NOT NULL CHECK (length(canonical_json) > 0),
  UNIQUE (batch_id, reading_id),
  FOREIGN KEY (batch_id, record_ordinal)
    REFERENCES historical_raw_rows_v1(batch_id, record_ordinal)
    ON DELETE RESTRICT
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_historical_samples_v1_source_sensor
ON historical_samples_v1(batch_id, record_ordinal, sensor_id);

CREATE INDEX IF NOT EXISTS ix_historical_samples_v1_timeline
ON historical_samples_v1(
  asset_id, observed_at, sample_pair_id, sensor_id, reading_id
);

CREATE TABLE IF NOT EXISTS historical_assessments_v1 (
  assessment_id TEXT PRIMARY KEY CHECK (length(assessment_id) > 0),
  batch_id TEXT NOT NULL,
  fold_id TEXT NOT NULL CHECK (length(fold_id) > 0),
  sensor_id TEXT NOT NULL CHECK (sensor_id IN ('s1', 's2')),
  operating_cycle_id TEXT NOT NULL CHECK (length(operating_cycle_id) > 0),
  training_window_start TEXT NOT NULL
    CHECK (length(training_window_start) = 24 AND substr(training_window_start, -1) = 'Z'),
  training_window_end TEXT NOT NULL
    CHECK (length(training_window_end) = 24 AND substr(training_window_end, -1) = 'Z'),
  window_start TEXT NOT NULL
    CHECK (length(window_start) = 24 AND substr(window_start, -1) = 'Z'),
  window_end TEXT NOT NULL
    CHECK (length(window_end) = 24 AND substr(window_end, -1) = 'Z'),
  assessment_at TEXT NOT NULL
    CHECK (length(assessment_at) = 24 AND substr(assessment_at, -1) = 'Z'),
  anchor_point_id TEXT NOT NULL,
  status TEXT NOT NULL
    CHECK (status IN ('normal', 'watch', 'alert', 'insufficient_data')),
  anomaly_score REAL,
  deterioration_score REAL,
  model_family TEXT NOT NULL CHECK (length(model_family) > 0),
  model_version TEXT NOT NULL CHECK (length(model_version) > 0),
  model_hash TEXT NOT NULL
    CHECK (
      length(model_hash) = 71
      AND substr(model_hash, 1, 7) = 'sha256:'
      AND substr(model_hash, 8) NOT GLOB '*[^0-9a-f]*'
    ),
  fold_hash TEXT NOT NULL
    CHECK (
      length(fold_hash) = 71
      AND substr(fold_hash, 1, 7) = 'sha256:'
      AND substr(fold_hash, 8) NOT GLOB '*[^0-9a-f]*'
    ),
  report_hash TEXT NOT NULL
    CHECK (
      length(report_hash) = 71
      AND substr(report_hash, 1, 7) = 'sha256:'
      AND substr(report_hash, 8) NOT GLOB '*[^0-9a-f]*'
    ),
  canonical_json TEXT NOT NULL CHECK (length(canonical_json) > 0),
  UNIQUE (batch_id, assessment_id),
  FOREIGN KEY (batch_id) REFERENCES historical_import_batches_v1(batch_id)
    ON DELETE RESTRICT,
  FOREIGN KEY (anchor_point_id) REFERENCES historical_samples_v1(reading_id)
    ON DELETE RESTRICT,
  CHECK (training_window_start <= training_window_end),
  CHECK (window_start <= window_end),
  CHECK (window_end <= assessment_at)
);

CREATE INDEX IF NOT EXISTS ix_historical_assessments_v1_anchor
ON historical_assessments_v1(
  batch_id, anchor_point_id, sensor_id, assessment_at
);

CREATE TABLE IF NOT EXISTS collection_policies_v1 (
  schema_version TEXT NOT NULL CHECK (schema_version = '1.0'),
  policy_id TEXT PRIMARY KEY CHECK (length(policy_id) > 0),
  asset_id TEXT NOT NULL CHECK (asset_id = 'forzy-motor-01'),
  timezone_name TEXT NOT NULL CHECK (timezone_name = 'America/Sao_Paulo'),
  active_weekdays_json TEXT NOT NULL
    CHECK (active_weekdays_json = '["monday","tuesday","wednesday"]'),
  window_start_local TEXT NOT NULL,
  window_end_local TEXT NOT NULL,
  poll_interval_seconds INTEGER NOT NULL CHECK (poll_interval_seconds > 0),
  gap_threshold_seconds INTEGER NOT NULL CHECK (gap_threshold_seconds > 0),
  effective_from TEXT NOT NULL
    CHECK (length(effective_from) = 24 AND substr(effective_from, -1) = 'Z'),
  effective_to TEXT
    CHECK (
      effective_to IS NULL
      OR (
        length(effective_to) = 24
        AND substr(effective_to, -1) = 'Z'
        AND effective_to > effective_from
      )
    ),
  configuration_hash TEXT NOT NULL
    CHECK (
      length(configuration_hash) = 71
      AND substr(configuration_hash, 1, 7) = 'sha256:'
      AND substr(configuration_hash, 8) NOT GLOB '*[^0-9a-f]*'
    ),
  CHECK (window_start_local < window_end_local)
);

CREATE INDEX IF NOT EXISTS ix_collection_policies_v1_effective
ON collection_policies_v1(asset_id, effective_from, effective_to, policy_id);

CREATE TABLE IF NOT EXISTS refresh_cycle_policies_v1 (
  asset_id TEXT NOT NULL,
  scheduled_at TEXT NOT NULL,
  policy_id TEXT NOT NULL,
  PRIMARY KEY (asset_id, scheduled_at),
  FOREIGN KEY (asset_id, scheduled_at)
    REFERENCES refresh_cycles_v2(asset_id, scheduled_at)
    ON DELETE RESTRICT,
  FOREIGN KEY (policy_id) REFERENCES collection_policies_v1(policy_id)
    ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS ix_telemetry_samples_v2_timeline
ON telemetry_samples_v2(asset_id, observed_at, reading_id);
