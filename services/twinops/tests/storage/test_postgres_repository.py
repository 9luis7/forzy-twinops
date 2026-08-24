import json
import os
from contextlib import contextmanager
from datetime import datetime, timezone

import psycopg
import pytest

from test_sqlite_v2_repository import repository_contract as assert_repository_contract
from twinops.storage import postgres_repository
from twinops.storage.schema_migrations import SchemaVerification


@pytest.fixture
def repository_contract():
    return assert_repository_contract


@pytest.fixture
def postgres_repo():
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("TEST_DATABASE_URL not configured")

    from twinops.storage.postgres_repository import PostgresTelemetryRepository

    repository = PostgresTelemetryRepository(database_url)
    repository.initialize()
    with psycopg.connect(database_url) as connection:
        connection.execute(
            "TRUNCATE TABLE refresh_cycles_v2, collection_attempts_v2, "
            "raw_readings_v2, latest_readings_v2, telemetry_samples_v2"
        )
    try:
        yield repository
    finally:
        with psycopg.connect(database_url) as connection:
            connection.execute(
                "TRUNCATE TABLE refresh_cycles_v2, collection_attempts_v2, "
                "raw_readings_v2, latest_readings_v2, telemetry_samples_v2"
            )


@pytest.mark.postgres
def test_postgres_repository_satisfies_shared_contract(
    postgres_repo, repository_contract
):
    repository_contract(postgres_repo)

    with psycopg.connect(postgres_repo.database_url) as connection:
        rows = connection.execute(
            "SELECT payload_json FROM raw_readings_v2 ORDER BY scheduled_at"
        ).fetchall()

    expected_payload = {
        "dados1": {
            "Velocidade": 0.12,
            "Aceleração": 0.0,
            "Temperatura": 34,
        }
    }
    assert len(rows) == 2
    assert [json.loads(row[0]) for row in rows] == [
        expected_payload,
        expected_payload,
    ]


class _NoRuntimeDdlConnection:
    def __init__(self):
        self.calls = []

    def execute(self, query, params=None, **kwargs):
        self.calls.append((query, params, kwargs))
        raise AssertionError("runtime initialization must not execute DDL or locks")


def _verification(*, current: bool) -> SchemaVerification:
    return SchemaVerification(
        expected_version="003",
        current_version="003" if current else "002",
        applied_migration_hashes={},
        is_current=current,
    )


def test_initialize_is_verification_only_and_never_reads_or_applies_sql(monkeypatch):
    connection = _NoRuntimeDdlConnection()
    repository = postgres_repository.PostgresTelemetryRepository("redacted")
    verification_calls = []

    @contextmanager
    def fake_connection():
        yield connection

    def verify(candidate, expected_version):
        verification_calls.append((candidate, expected_version))
        return _verification(current=True)

    monkeypatch.setattr(repository, "_connection", fake_connection)
    monkeypatch.setattr(postgres_repository, "verify_schema_version", verify)

    repository.initialize()

    assert verification_calls == [(connection, "003")]
    assert connection.calls == []


def test_initialize_fails_closed_when_schema_003_is_not_current(monkeypatch):
    connection = _NoRuntimeDdlConnection()
    repository = postgres_repository.PostgresTelemetryRepository("redacted")

    @contextmanager
    def fake_connection():
        yield connection

    monkeypatch.setattr(repository, "_connection", fake_connection)
    monkeypatch.setattr(
        postgres_repository,
        "verify_schema_version",
        lambda connection, expected_version: _verification(current=False),
    )

    with pytest.raises(RuntimeError, match="schema 003"):
        repository.initialize()

    assert connection.calls == []


def test_repository_policy_reads_delegate_without_writes(monkeypatch):
    connection = _NoRuntimeDdlConnection()
    repository = postgres_repository.PostgresTelemetryRepository("redacted")
    instant = datetime(2026, 8, 22, tzinfo=timezone.utc)
    expected_by_id = object()
    expected_effective = object()
    calls = []

    @contextmanager
    def fake_connection():
        yield connection

    monkeypatch.setattr(repository, "_connection", fake_connection)
    monkeypatch.setattr(
        postgres_repository,
        "read_collection_policy",
        lambda candidate, policy_id: calls.append((candidate, policy_id))
        or expected_by_id,
    )
    monkeypatch.setattr(
        postgres_repository,
        "read_effective_collection_policy",
        lambda candidate, asset_id, at: calls.append((candidate, asset_id, at))
        or expected_effective,
    )

    assert repository.collection_policy("forzy-live-window-v1") is expected_by_id
    assert (
        repository.effective_collection_policy("forzy-motor-01", instant)
        is expected_effective
    )
    assert calls == [
        (connection, "forzy-live-window-v1"),
        (connection, "forzy-motor-01", instant),
    ]
    assert connection.calls == []
