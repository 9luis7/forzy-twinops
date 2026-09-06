-- Additive, isolated replay store. Apply explicitly in PostgreSQL deployments.
CREATE TABLE IF NOT EXISTS demo_datasets (
    dataset_id TEXT PRIMARY KEY, metadata TEXT NOT NULL, pairs TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS demo_runs (
    run_id TEXT PRIMARY KEY, token_hash TEXT NOT NULL, expires_at TEXT NOT NULL,
    state TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS demo_commands (
    run_id TEXT NOT NULL REFERENCES demo_runs(run_id) ON DELETE CASCADE,
    command_id TEXT NOT NULL, fingerprint TEXT NOT NULL, revision INTEGER NOT NULL,
    response TEXT, PRIMARY KEY(run_id, command_id)
);
CREATE TABLE IF NOT EXISTS demo_events (
    event_id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES demo_runs(run_id) ON DELETE CASCADE,
    generation INTEGER NOT NULL, payload TEXT NOT NULL, context TEXT NOT NULL,
    owner TEXT, lease_until TEXT
);
CREATE INDEX IF NOT EXISTS demo_events_run ON demo_events(run_id, generation);
CREATE INDEX IF NOT EXISTS demo_commands_revision ON demo_commands(run_id, revision);
