from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sqlite3

import pytest


SERVICE_ROOT = Path(__file__).parents[2]
SURFACE_READY = all(
    path.is_file()
    for path in (
        SERVICE_ROOT / "migrations" / "003_unified_history_timeline_sqlite.sql",
        SERVICE_ROOT / "migrations" / "003_unified_history_timeline_postgres.sql",
        SERVICE_ROOT / "src" / "twinops" / "storage" / "schema_migrations.py",
        SERVICE_ROOT / "src" / "twinops" / "storage" / "collection_policy_v1.py",
    )
)
pytestmark = pytest.mark.skipif(
    not SURFACE_READY,
    reason="migration surface has not been implemented",
)

UTC = timezone.utc
INITIAL_EFFECTIVE_FROM = datetime(2026, 8, 22, tzinfo=UTC)


@pytest.fixture
def connection():
    from twinops.storage.schema_migrations import (
        apply_sqlite_migrations,
        registered_migration_specs,
    )

    database = sqlite3.connect(":memory:")
    database.row_factory = sqlite3.Row
    database.execute("PRAGMA foreign_keys=ON")
    apply_sqlite_migrations(
        database,
        registered_migration_specs(),
        initial_policy_effective_from=INITIAL_EFFECTIVE_FROM,
    )
    try:
        yield database
    finally:
        database.close()


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def _policy(
    *,
    policy_id: str,
    effective_from: datetime,
    effective_to: datetime | None,
):
    from twinops.contracts.timeline_v1_models import CollectionPolicyV1

    payload = {
        "schemaVersion": "1.0",
        "collectionPolicyId": policy_id,
        "assetId": "forzy-motor-01",
        "timezone": "America/Sao_Paulo",
        "activeWeekdays": ["monday", "tuesday", "wednesday"],
        "windowStartLocal": "12:00:00",
        "windowEndLocal": "14:00:00",
        "pollIntervalSeconds": 5,
        "gapThresholdSeconds": 15,
        "effectiveFrom": _timestamp(effective_from),
        "effectiveTo": _timestamp(effective_to) if effective_to else None,
    }
    selected = {
        key: payload[key]
        for key in (
            "schemaVersion",
            "collectionPolicyId",
            "assetId",
            "timezone",
            "activeWeekdays",
            "windowStartLocal",
            "windowEndLocal",
            "pollIntervalSeconds",
            "gapThresholdSeconds",
        )
    }
    canonical = json.dumps(selected, sort_keys=True, separators=(",", ":")).encode()
    payload["configurationHash"] = "sha256:" + hashlib.sha256(canonical).hexdigest()
    return CollectionPolicyV1.model_validate(payload)


def _insert_raw(connection: sqlite3.Connection, policy) -> None:
    body = policy.model_dump(mode="json", by_alias=True)
    connection.execute(
        "INSERT INTO collection_policies_v1 ("
        "schema_version,policy_id,asset_id,timezone_name,active_weekdays_json,"
        "window_start_local,window_end_local,poll_interval_seconds,"
        "gap_threshold_seconds,effective_from,effective_to,configuration_hash"
        ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            body["schemaVersion"],
            body["collectionPolicyId"],
            body["assetId"],
            body["timezone"],
            json.dumps(body["activeWeekdays"], separators=(",", ":")),
            body["windowStartLocal"],
            body["windowEndLocal"],
            body["pollIntervalSeconds"],
            body["gapThresholdSeconds"],
            body["effectiveFrom"],
            body["effectiveTo"],
            body["configurationHash"],
        ),
    )


def test_administrative_migrator_seeds_and_reads_pinned_policy(connection):
    from twinops.storage.collection_policy_v1 import (
        INITIAL_COLLECTION_POLICY_CONFIGURATION_HASH,
        INITIAL_COLLECTION_POLICY_ID,
        read_collection_policy,
    )

    policy = read_collection_policy(connection, INITIAL_COLLECTION_POLICY_ID)

    assert policy is not None
    assert policy.collection_policy_id == "forzy-live-window-v1"
    assert policy.configuration_hash == INITIAL_COLLECTION_POLICY_CONFIGURATION_HASH
    assert policy.effective_from == INITIAL_EFFECTIVE_FROM
    assert policy.effective_to is None


def test_first_seed_inserts_once_and_second_seed_is_exact_noop(connection):
    from twinops.storage.collection_policy_v1 import (
        INITIAL_COLLECTION_POLICY_ID,
        ensure_initial_collection_policy,
        read_collection_policy,
    )

    connection.execute(
        "DELETE FROM collection_policies_v1 WHERE policy_id=?",
        (INITIAL_COLLECTION_POLICY_ID,),
    )
    connection.commit()

    first = ensure_initial_collection_policy(
        connection,
        effective_from=INITIAL_EFFECTIVE_FROM,
    )
    before_changes = connection.total_changes
    second = ensure_initial_collection_policy(
        connection,
        effective_from=INITIAL_EFFECTIVE_FROM,
    )
    stored = read_collection_policy(connection, INITIAL_COLLECTION_POLICY_ID)

    assert first.inserted is True
    assert first.writes_performed == 1
    assert second.inserted is False
    assert second.writes_performed == 0
    assert connection.total_changes == before_changes
    assert stored is not None
    assert stored.effective_from == INITIAL_EFFECTIVE_FROM
    assert stored.effective_to is None


def test_seed_rejects_wrong_pinned_hash_and_same_id_with_divergent_fields(connection):
    from twinops.storage.collection_policy_v1 import (
        INITIAL_COLLECTION_POLICY_ID,
        ensure_initial_collection_policy,
        read_collection_policy,
    )

    connection.execute(
        "UPDATE collection_policies_v1 SET configuration_hash=? "
        "WHERE policy_id=?",
        ("sha256:" + "0" * 64, INITIAL_COLLECTION_POLICY_ID),
    )
    with pytest.raises(ValueError):
        read_collection_policy(connection, INITIAL_COLLECTION_POLICY_ID)
    with pytest.raises(ValueError):
        ensure_initial_collection_policy(
            connection,
            effective_from=INITIAL_EFFECTIVE_FROM,
        )

    connection.rollback()
    connection.execute(
        "DELETE FROM collection_policies_v1 WHERE policy_id=?",
        (INITIAL_COLLECTION_POLICY_ID,),
    )
    divergent = _policy(
        policy_id=INITIAL_COLLECTION_POLICY_ID,
        effective_from=INITIAL_EFFECTIVE_FROM - timedelta(days=1),
        effective_to=None,
    )
    _insert_raw(connection, divergent)

    with pytest.raises(ValueError, match="conflict"):
        ensure_initial_collection_policy(
            connection,
            effective_from=INITIAL_EFFECTIVE_FROM,
        )


def test_touching_policy_validity_is_accepted_but_overlap_is_rejected(connection):
    from twinops.storage.collection_policy_v1 import (
        INITIAL_COLLECTION_POLICY_ID,
        ensure_initial_collection_policy,
        insert_collection_policy,
    )

    connection.execute(
        "DELETE FROM collection_policies_v1 WHERE policy_id=?",
        (INITIAL_COLLECTION_POLICY_ID,),
    )
    touching = _policy(
        policy_id="forzy-live-window-v0",
        effective_from=INITIAL_EFFECTIVE_FROM - timedelta(days=30),
        effective_to=INITIAL_EFFECTIVE_FROM,
    )
    assert insert_collection_policy(connection, touching) is True
    assert ensure_initial_collection_policy(
        connection,
        effective_from=INITIAL_EFFECTIVE_FROM,
    ).inserted is True

    connection.rollback()
    connection.execute(
        "DELETE FROM collection_policies_v1 WHERE policy_id=?",
        (INITIAL_COLLECTION_POLICY_ID,),
    )
    connection.execute(
        "DELETE FROM collection_policies_v1 WHERE policy_id=?",
        ("forzy-live-window-v0",),
    )
    overlapping = _policy(
        policy_id="forzy-live-window-overlap-v0",
        effective_from=INITIAL_EFFECTIVE_FROM - timedelta(days=30),
        effective_to=INITIAL_EFFECTIVE_FROM + timedelta(seconds=1),
    )
    assert insert_collection_policy(connection, overlapping) is True

    with pytest.raises(ValueError, match="overlap"):
        ensure_initial_collection_policy(
            connection,
            effective_from=INITIAL_EFFECTIVE_FROM,
        )


def test_effective_lookup_returns_none_and_fails_closed_on_multiple_matches(connection):
    from twinops.storage.collection_policy_v1 import (
        INITIAL_COLLECTION_POLICY_ID,
        read_effective_collection_policy,
    )

    connection.execute(
        "DELETE FROM collection_policies_v1 WHERE policy_id=?",
        (INITIAL_COLLECTION_POLICY_ID,),
    )
    at = datetime(2026, 9, 1, tzinfo=UTC)
    assert read_effective_collection_policy(
        connection, "forzy-motor-01", at
    ) is None

    _insert_raw(
        connection,
        _policy(
            policy_id="overlap-a",
            effective_from=at - timedelta(days=1),
            effective_to=None,
        ),
    )
    _insert_raw(
        connection,
        _policy(
            policy_id="overlap-b",
            effective_from=at - timedelta(hours=1),
            effective_to=at + timedelta(hours=1),
        ),
    )

    with pytest.raises(RuntimeError, match="multiple"):
        read_effective_collection_policy(connection, "forzy-motor-01", at)


def test_effective_lookup_uses_half_open_validity_boundaries(connection):
    from twinops.storage.collection_policy_v1 import (
        INITIAL_COLLECTION_POLICY_ID,
        insert_collection_policy,
        read_effective_collection_policy,
    )

    connection.execute(
        "DELETE FROM collection_policies_v1 WHERE policy_id=?",
        (INITIAL_COLLECTION_POLICY_ID,),
    )
    first_from = datetime(2026, 8, 1, tzinfo=UTC)
    boundary = datetime(2026, 9, 1, tzinfo=UTC)
    first = _policy(
        policy_id="boundary-a",
        effective_from=first_from,
        effective_to=boundary,
    )
    second = _policy(
        policy_id="boundary-b",
        effective_from=boundary,
        effective_to=None,
    )
    assert insert_collection_policy(connection, first) is True
    assert insert_collection_policy(connection, second) is True

    assert read_effective_collection_policy(
        connection, "forzy-motor-01", first_from - timedelta(milliseconds=1)
    ) is None
    assert read_effective_collection_policy(
        connection, "forzy-motor-01", first_from
    ).collection_policy_id == "boundary-a"
    assert read_effective_collection_policy(
        connection, "forzy-motor-01", boundary - timedelta(milliseconds=1)
    ).collection_policy_id == "boundary-a"
    assert read_effective_collection_policy(
        connection, "forzy-motor-01", boundary
    ).collection_policy_id == "boundary-b"


def test_every_policy_read_revalidates_canonical_json_and_closed_model(connection):
    from twinops.storage.collection_policy_v1 import (
        INITIAL_COLLECTION_POLICY_ID,
        read_collection_policy,
    )

    connection.execute("PRAGMA ignore_check_constraints=ON")
    try:
        connection.execute(
            "UPDATE collection_policies_v1 SET active_weekdays_json=? "
            "WHERE policy_id=?",
            (
                '["monday", "tuesday", "wednesday"]',
                INITIAL_COLLECTION_POLICY_ID,
            ),
        )
    finally:
        connection.execute("PRAGMA ignore_check_constraints=OFF")

    with pytest.raises(ValueError, match="canonical"):
        read_collection_policy(connection, INITIAL_COLLECTION_POLICY_ID)


@pytest.mark.parametrize(
    "effective_from",
    [
        datetime(2026, 8, 22),
        datetime(2026, 8, 22, 0, 0, 0, 1, tzinfo=UTC),
    ],
)
def test_seed_rejects_non_utc_millisecond_effective_time(connection, effective_from):
    from twinops.storage.collection_policy_v1 import ensure_initial_collection_policy

    with pytest.raises(ValueError):
        ensure_initial_collection_policy(connection, effective_from=effective_from)


def test_sqlite_runtime_repository_verifies_and_reads_only_after_admin_migration(
    connection,
    monkeypatch,
):
    from contextlib import contextmanager

    from twinops.storage.sqlite_v2_repository import SQLiteTelemetryRepositoryV2

    repository = SQLiteTelemetryRepositoryV2(Path("unused-by-test.sqlite3"))

    @contextmanager
    def fake_connection():
        yield connection

    monkeypatch.setattr(repository, "_connection", fake_connection)

    assert repository.verify_schema("003").is_current is True
    assert (
        repository.collection_policy("forzy-live-window-v1").collection_policy_id
        == "forzy-live-window-v1"
    )
    assert (
        repository.effective_collection_policy(
            "forzy-motor-01",
            INITIAL_EFFECTIVE_FROM,
        ).collection_policy_id
        == "forzy-live-window-v1"
    )


def test_sqlite_runtime_initialize_does_not_apply_migration_003(monkeypatch):
    from contextlib import contextmanager

    from twinops.storage.sqlite_v2_repository import SQLiteTelemetryRepositoryV2

    database = sqlite3.connect(":memory:")
    repository = SQLiteTelemetryRepositoryV2(Path("unused-by-test.sqlite3"))

    @contextmanager
    def fake_connection():
        yield database

    monkeypatch.setattr(repository, "_connection", fake_connection)
    try:
        repository.initialize()
        tables = {
            row[0]
            for row in database.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "telemetry_samples_v2" in tables
        assert "schema_migrations_v1" not in tables
        assert "collection_policies_v1" not in tables
    finally:
        database.close()
