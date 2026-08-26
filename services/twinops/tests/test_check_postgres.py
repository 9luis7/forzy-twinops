from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import check_postgres


SERVICE_ROOT = Path(__file__).parents[1]
MIGRATION_002 = SERVICE_ROOT / "migrations" / "002_real_twin_v2.sql"
MIGRATION_003 = (
    SERVICE_ROOT / "migrations" / "003_unified_history_timeline_postgres.sql"
)
EFFECTIVE_FROM = "2026-08-22T00:00:00.000Z"
PROJECT_ID = "project-id-for-test"
BRANCH_ID = "branch-id-for-test"
DATABASE_NAME = "twinops_test"
SCHEMA_NAME = "public"
DATABASE_URL = "postgresql://user:secret@database.invalid/twinops"
LEGACY_V2_PUBLIC_RELATIONS = {
    ("collection_attempts_v2", "r"),
    ("latest_readings_v2", "r"),
    ("raw_readings_v2", "r"),
    ("refresh_cycles_v2", "r"),
    ("telemetry_samples_v2", "r"),
    ("collection_attempts_v2_pkey", "i"),
    ("latest_readings_v2_pkey", "i"),
    ("raw_readings_v2_pkey", "i"),
    ("refresh_cycles_v2_pkey", "i"),
    ("telemetry_samples_v2_pkey", "i"),
    ("ix_raw_readings_v2_slot", "i"),
    ("ix_telemetry_samples_v2_history", "i"),
}
REGISTERED_002_PLAN_SHA256 = {
    "preview": (
        "sha256:0d28b7d23416153cc6bd12fb93a3be51"
        "0cd0cf239ea4c3be19d14268e8ff47ad"
    ),
    "production": (
        "sha256:60d15d2518749344325d740f069d1f758"
        "a405257d7dff54d6bfc30e7270fa8e2"
    ),
}
LEGACY_002_PLAN_SHA256 = {
    "preview": (
        "sha256:fc4be49486435c53f867825f69f69c4a"
        "05c32aae5f6446a9d441a6adfc9ad0b0"
    ),
    "production": (
        "sha256:9de3daf5b59ab3bb2558a1b8b3e0af35"
        "a8c8dde6b2778ffa7fb9f5905c767b68"
    ),
}
_AUTO_PLAN = object()


class _Rows:
    def __init__(self, rows=()):
        self._rows = list(rows)

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None


class _SuccessfulConnection:
    def __init__(self, specs, *, current_version="002", tls=True):
        self.specs = specs
        self.calls = []
        self.pgconn = SimpleNamespace(ssl_in_use=tls)
        self.migration_table_exists = current_version in {"002", "003"}
        self.migrations = {}
        if current_version in {"002", "003"}:
            self.migrations["002"] = specs[0].postgres_sha256
        if current_version == "003":
            self.migrations["003"] = specs[1].postgres_sha256
        self.policy = None
        self.identity = None
        self.identity_table_exists = current_version == "003"
        self.extra_public_relations = set()
        self.relation_on_lock = None
        self.legacy_v2_schema_current = current_version == "legacy002"
        self.invalidate_legacy_v2_on_lock = False
        self.record_002_on_lock = False
        self.migration_002 = MIGRATION_002.read_text(encoding="utf-8")
        self.migration_003 = MIGRATION_003.read_text(encoding="utf-8")
        if current_version == "003":
            self._store_policy(EFFECTIVE_FROM)
            self.identity = {
                "environment": "preview",
                "label": f"{PROJECT_ID}/{BRANCH_ID}",
                "target_fingerprint": _target_fingerprint(),
                "schema_version": "003",
            }

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def _store_policy(self, effective_from):
        self.policy = {
            "schema_version": "1.0",
            "policy_id": "forzy-live-window-v1",
            "asset_id": "forzy-motor-01",
            "timezone_name": "America/Sao_Paulo",
            "active_weekdays_json": '["monday","tuesday","wednesday"]',
            "window_start_local": "12:00:00",
            "window_end_local": "14:00:00",
            "poll_interval_seconds": 5,
            "gap_threshold_seconds": 15,
            "effective_from": effective_from,
            "effective_to": None,
            "configuration_hash": (
                "sha256:89bde17193c7a34c80d48828f4e61fc"
                "5802caa92169d83f8a9fd8e4c282b1bce"
            ),
        }

    def execute(self, query, params=None, **kwargs):
        self.calls.append((query, params, kwargs))
        normalized = " ".join(query.split())
        if normalized == "SET TRANSACTION READ ONLY":
            return _Rows()
        if normalized.startswith("SELECT current_database()"):
            return _Rows([(DATABASE_NAME, SCHEMA_NAME)])
        if "to_regclass('public.deployment_identity_v1')" in normalized:
            relation = (
                "deployment_identity_v1" if self.identity_table_exists else None
            )
            return _Rows([{"relation": relation}])
        if "to_regclass('public.schema_migrations_v1')" in normalized:
            relation = "schema_migrations_v1" if self.migration_table_exists else None
            return _Rows([{"relation": relation}])
        if normalized.startswith("SELECT migration_version, sql_sha256"):
            return _Rows(
                {
                    "migration_version": version,
                    "sql_sha256": digest,
                }
                for version, digest in sorted(self.migrations.items())
            )
        if "pg_advisory_xact_lock" in normalized:
            if self.relation_on_lock is not None:
                self.extra_public_relations.add(self.relation_on_lock)
                self.relation_on_lock = None
            if self.invalidate_legacy_v2_on_lock:
                self.legacy_v2_schema_current = False
                self.invalidate_legacy_v2_on_lock = False
            if self.record_002_on_lock:
                self.migration_table_exists = True
                self.migrations["002"] = self.specs[0].postgres_sha256
                self.record_002_on_lock = False
            return _Rows()
        if query == self.migration_002:
            return _Rows()
        if query == self.migration_003:
            self.identity_table_exists = True
            return _Rows()
        if normalized.startswith("CREATE TABLE IF NOT EXISTS schema_migrations_v1"):
            self.migration_table_exists = True
            return _Rows()
        if normalized.startswith("INSERT INTO schema_migrations_v1"):
            self.migrations[params[0]] = params[1]
            return _Rows()
        if normalized.startswith("SELECT schema_version,policy_id"):
            if "WHERE policy_id=" in normalized:
                rows = [self.policy] if self.policy and self.policy["policy_id"] == params[0] else []
            else:
                rows = [self.policy] if self.policy and self.policy["asset_id"] == params[0] else []
            return _Rows(rows)
        if normalized.startswith("INSERT INTO collection_policies_v1"):
            self.policy = dict(
                zip(
                    (
                        "schema_version",
                        "policy_id",
                        "asset_id",
                        "timezone_name",
                        "active_weekdays_json",
                        "window_start_local",
                        "window_end_local",
                        "poll_interval_seconds",
                        "gap_threshold_seconds",
                        "effective_from",
                        "effective_to",
                        "configuration_hash",
                    ),
                    params,
                    strict=True,
                )
            )
            return _Rows()
        if normalized.startswith("SELECT environment,label,target_fingerprint"):
            return _Rows([self.identity] if self.identity else [])
        if normalized.startswith("INSERT INTO deployment_identity_v1"):
            self.identity_table_exists = True
            self.identity = {
                "environment": params[1],
                "label": params[2],
                "target_fingerprint": params[3],
                "schema_version": params[4],
            }
            return _Rows()
        if "FROM pg_catalog.pg_tables" in normalized:
            if "AS tables_current" in normalized:
                current = bool(self.migrations) or self.legacy_v2_schema_current
                return _Rows(
                    [{"tables_current": current, "indexes_current": current}]
                )
            if not self.migrations:
                return _Rows()
            return _Rows((name,) for name in check_postgres.POSTGRES_V3_REQUIRED_TABLES)
        if "FROM pg_catalog.pg_indexes" in normalized:
            if not self.migrations:
                return _Rows()
            return _Rows((name,) for name in check_postgres.POSTGRES_V3_REQUIRED_INDEXES)
        if "FROM pg_catalog.pg_class" in normalized:
            relations = set(self.extra_public_relations)
            if self.legacy_v2_schema_current:
                relations.update(LEGACY_V2_PUBLIC_RELATIONS)
            if "relkind IN" in normalized:
                relations = {
                    row
                    for row in relations
                    if row[1] in {"r", "p", "v", "m", "S", "f", "i", "I"}
                }
            return _Rows(sorted(relations))
        if normalized == "SELECT COUNT(*) FROM collection_policies_v1":
            return _Rows([(1 if self.policy else 0,)])
        raise AssertionError(f"unexpected query boundary: {query}")


def _target_fingerprint() -> str:
    payload = {
        "branchId": BRANCH_ID,
        "database": DATABASE_NAME,
        "kind": "remote-postgres",
        "projectId": PROJECT_ID,
        "schema": SCHEMA_NAME,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


def _args(
    *,
    expected_current_version="002",
    fingerprint=None,
    mode="--apply",
    environment="preview",
    label=f"{PROJECT_ID}/{BRANCH_ID}",
    expected_plan_sha256=_AUTO_PLAN,
):
    args = [
        "--migrate",
        str(MIGRATION_002),
        "--migrate",
        str(MIGRATION_003),
        "--environment",
        environment,
        "--expected-target-label",
        label,
        "--expected-target-fingerprint",
        fingerprint or _target_fingerprint(),
        "--expected-current-version",
        expected_current_version,
        "--initial-policy-effective-from",
        EFFECTIVE_FROM,
    ]
    if mode is not None:
        args.append(mode)
    if (
        expected_plan_sha256 is _AUTO_PLAN
        and mode == "--apply"
        and expected_current_version == "002"
    ):
        expected_plan_sha256 = REGISTERED_002_PLAN_SHA256[environment]
    if expected_plan_sha256 is not _AUTO_PLAN and expected_plan_sha256 is not None:
        args.extend(["--expected-plan-sha256", expected_plan_sha256])
    return args


def _env():
    return {
        "DATABASE_URL": DATABASE_URL,
        "TWINOPS_TARGET_PROJECT_ID": PROJECT_ID,
        "TWINOPS_TARGET_BRANCH_ID": BRANCH_ID,
    }


def test_check_postgres_requires_database_url_without_connecting(capsys):
    def forbidden_connect(*args, **kwargs):
        raise AssertionError("database connect must not run without DATABASE_URL")

    result = check_postgres.main(_args(), env={}, connect=forbidden_connect)

    captured = capsys.readouterr()
    assert result == 1
    assert captured.out == ""
    assert captured.err.strip() == "postgres_check_failed error_type=ValueError"


def test_check_postgres_rejects_non_allowlisted_paths_before_connecting(
    capsys,
):
    unexpected = Path(check_postgres.__file__)
    args = _args()
    args[1] = str(unexpected)

    result = check_postgres.main(
        args,
        env=_env(),
        connect=lambda dsn: (_ for _ in ()).throw(
            AssertionError("unexpected connect")
        ),
    )

    captured = capsys.readouterr()
    assert result == 1
    assert captured.out == ""
    assert captured.err.strip() == "postgres_check_failed error_type=ValueError"
    assert str(unexpected) not in captured.err


def test_target_fingerprint_and_current_version_fail_before_ddl(capsys):
    specs = check_postgres.registered_migration_specs()
    connection = _SuccessfulConnection(specs)

    wrong_target = check_postgres.main(
        _args(fingerprint="sha256:" + "0" * 64),
        env=_env(),
        connect=lambda dsn: connection,
    )
    assert wrong_target == 1
    assert not any(query == connection.migration_003 for query, _, _ in connection.calls)
    first_capture = capsys.readouterr()
    assert first_capture.out == ""
    assert "stage=target_identity" in first_capture.err
    assert DATABASE_URL not in first_capture.err

    connection = _SuccessfulConnection(specs)
    wrong_version = check_postgres.main(
        _args(expected_current_version="003"),
        env=_env(),
        connect=lambda dsn: connection,
    )
    assert wrong_version == 1
    assert not any(query == connection.migration_003 for query, _, _ in connection.calls)
    second_capture = capsys.readouterr()
    assert second_capture.out == ""
    assert "stage=schema_version" in second_capture.err
    assert DATABASE_URL not in second_capture.err


def test_expected_002_rejects_partial_identity_before_ddl_or_migration_write(
    capsys,
):
    specs = check_postgres.registered_migration_specs()
    connection = _SuccessfulConnection(specs)
    connection.identity_table_exists = True
    connection.identity = None

    result = check_postgres.main(
        _args(expected_current_version="002"),
        env=_env(),
        connect=lambda dsn: connection,
    )

    captured = capsys.readouterr()
    normalized_queries = [
        " ".join(query.split()) for query, _, _ in connection.calls
    ]
    assert result == 1
    assert not any(query == connection.migration_003 for query, _, _ in connection.calls)
    assert not any(
        query.startswith("INSERT INTO schema_migrations_v1")
        for query in normalized_queries
    )
    assert not any(
        query.startswith("CREATE TABLE IF NOT EXISTS schema_migrations_v1")
        for query in normalized_queries
    )
    assert captured.out == ""
    assert captured.err.strip() == (
        "postgres_check_failed error_type=PostgresCheckError "
        "stage=target_identity"
    )
    for sensitive in (
        DATABASE_URL,
        PROJECT_ID,
        BRANCH_ID,
        DATABASE_NAME,
        SCHEMA_NAME,
        str(MIGRATION_002),
        str(MIGRATION_003),
    ):
        assert sensitive not in captured.err


def test_check_postgres_applies_exact_migration_after_preflight_and_reports_safe_facts(
    capsys,
):
    specs = check_postgres.registered_migration_specs()
    connection = _SuccessfulConnection(specs)
    connected_with = []

    def connect(dsn):
        connected_with.append(dsn)
        return connection

    result = check_postgres.main(_args(), env=_env(), connect=connect)

    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert result == 0
    assert connected_with == [DATABASE_URL]
    assert any(query == connection.migration_003 for query, _, _ in connection.calls)
    target_index = next(
        index
        for index, (query, _, _) in enumerate(connection.calls)
        if query.startswith("SELECT current_database()")
    )
    ddl_index = next(
        index
        for index, (query, _, _) in enumerate(connection.calls)
        if query == connection.migration_003
    )
    assert target_index < ddl_index
    assert connection.identity == {
        "environment": "preview",
        "label": f"{PROJECT_ID}/{BRANCH_ID}",
        "target_fingerprint": _target_fingerprint(),
        "schema_version": "003",
    }
    assert captured.err == ""
    payload = json.loads(captured.out)
    assert payload["mode"] == "apply"
    assert payload["schemaVersion"] == "003"
    assert payload["pendingMigrationVersions"] == ["003"]
    assert payload["plannedAdministrativeWriteCount"] == 3
    assert payload["writesPerformed"] == 3
    assert payload["verified"] is True
    for secret in (
        DATABASE_URL,
        "user",
        "secret",
        "database.invalid",
        str(MIGRATION_002),
        str(MIGRATION_003),
        DATABASE_NAME,
        SCHEMA_NAME,
    ):
        assert secret not in combined


def test_current_003_retry_is_noop_and_retains_policy_effective_from(capsys):
    specs = check_postgres.registered_migration_specs()
    connection = _SuccessfulConnection(specs, current_version="003")
    before_policy = dict(connection.policy)

    result = check_postgres.main(
        _args(expected_current_version="003"),
        env=_env(),
        connect=lambda dsn: connection,
    )

    assert result == 0
    assert connection.policy == before_policy
    assert not any(query == connection.migration_003 for query, _, _ in connection.calls)
    normalized_queries = [
        " ".join(query.split()) for query, _, _ in connection.calls
    ]
    assert "SELECT pg_advisory_xact_lock(%s)" not in normalized_queries
    assert any("hashtextextended" in query for query in normalized_queries)
    assert capsys.readouterr().err == ""


def test_checker_sanitizes_catalog_and_tls_failures(capsys):
    specs = check_postgres.registered_migration_specs()
    connection = _SuccessfulConnection(specs, current_version="003", tls=False)

    result = check_postgres.main(
        _args(expected_current_version="003"),
        env=_env(),
        connect=lambda dsn: connection,
    )

    captured = capsys.readouterr()
    assert result == 1
    assert captured.out == ""
    assert captured.err.strip() == (
        "postgres_check_failed error_type=PostgresCheckError stage=tls"
    )
    assert DATABASE_URL not in captured.err


def test_empty_production_dry_run_is_read_only_and_reports_closed_plan(capsys):
    specs = check_postgres.registered_migration_specs()
    connection = _SuccessfulConnection(specs, current_version="empty")

    result = check_postgres.main(
        _args(
            expected_current_version="empty",
            mode="--dry-run",
            environment="production",
            label=f"{PROJECT_ID}/{BRANCH_ID}",
        ),
        env=_env(),
        connect=lambda dsn: connection,
    )

    captured = capsys.readouterr()
    assert result == 0
    assert captured.err == ""
    payload = json.loads(captured.out)
    assert set(payload) == {
        "beforeSchemaVersion",
        "command",
        "environment",
        "expectedCurrentVersion",
        "initialPolicyEffectiveFrom",
        "migrationSha256s",
        "mode",
        "operation",
        "pendingMigrationVersions",
        "planSha256",
        "plannedAdministrativeWriteCount",
        "policyConfigurationHash",
        "policyId",
        "schemaVersion",
        "targetFingerprint",
        "targetIndexCount",
        "targetSchemaVersion",
        "targetTableCount",
        "verified",
        "writesPerformed",
    }
    assert payload == {
        "beforeSchemaVersion": None,
        "command": "migrate-postgres",
        "environment": "production",
        "expectedCurrentVersion": "empty",
        "initialPolicyEffectiveFrom": EFFECTIVE_FROM,
        "migrationSha256s": {
            spec.version: spec.postgres_sha256 for spec in specs
        },
        "mode": "dry-run",
        "operation": "bootstrap-empty",
        "pendingMigrationVersions": ["002", "003"],
        "planSha256": payload["planSha256"],
        "plannedAdministrativeWriteCount": 4,
        "policyConfigurationHash": (
            "sha256:89bde17193c7a34c80d48828f4e61fc"
            "5802caa92169d83f8a9fd8e4c282b1bce"
        ),
        "policyId": "forzy-live-window-v1",
        "schemaVersion": None,
        "targetFingerprint": _target_fingerprint(),
        "targetIndexCount": 8,
        "targetSchemaVersion": "003",
        "targetTableCount": 13,
        "verified": True,
        "writesPerformed": 0,
    }
    assert payload["planSha256"] == (
        "sha256:c788a0c4a87363b2bf1927375b04dadb"
        "5e547354ffbbbda0266cde7ea62387ed"
    )
    normalized = [" ".join(query.split()) for query, _, _ in connection.calls]
    assert normalized[0] == "SET TRANSACTION READ ONLY"
    assert not any(query == connection.migration_003 for query, _, _ in connection.calls)
    assert not any(query.startswith("CREATE ") for query in normalized)
    assert not any(query.startswith("INSERT ") for query in normalized)

    changed_args = _args(
        expected_current_version="empty",
        mode="--dry-run",
        environment="production",
        label=f"{PROJECT_ID}/{BRANCH_ID}",
    )
    effective_index = changed_args.index("--initial-policy-effective-from")
    changed_args[effective_index + 1] = "2026-08-23T00:00:00.000Z"
    changed_connection = _SuccessfulConnection(specs, current_version="empty")
    assert check_postgres.main(
        changed_args,
        env=_env(),
        connect=lambda dsn: changed_connection,
    ) == 0
    changed_payload = json.loads(capsys.readouterr().out)
    assert changed_payload["planSha256"] != payload["planSha256"]


def test_mode_is_required_and_wrong_target_label_fails_before_database_query(
    capsys,
):
    specs = check_postgres.registered_migration_specs()
    connection = _SuccessfulConnection(specs, current_version="empty")

    missing_mode = check_postgres.main(
        _args(mode=None),
        env=_env(),
        connect=lambda dsn: (_ for _ in ()).throw(
            AssertionError("mode validation must precede connect")
        ),
    )
    assert missing_mode == 1
    assert connection.calls == []
    first = capsys.readouterr()
    assert first.out == ""
    assert first.err.strip() == "postgres_check_failed error_type=ValueError"

    wrong_label = check_postgres.main(
        _args(
            expected_current_version="empty",
            mode="--dry-run",
            environment="production",
            label="wrong-project/wrong-branch",
        ),
        env=_env(),
        connect=lambda dsn: connection,
    )
    assert wrong_label == 1
    assert connection.calls == []
    second = capsys.readouterr()
    assert second.out == ""
    assert second.err.strip() == (
        "postgres_check_failed error_type=PostgresCheckError "
        "stage=target_identity"
    )


def test_empty_production_apply_bootstraps_exact_migrations_after_preflight(capsys):
    specs = check_postgres.registered_migration_specs()
    dry_run_connection = _SuccessfulConnection(specs, current_version="empty")
    dry_run = check_postgres.main(
        _args(
            expected_current_version="empty",
            mode="--dry-run",
            environment="production",
            label=f"{PROJECT_ID}/{BRANCH_ID}",
        ),
        env=_env(),
        connect=lambda dsn: dry_run_connection,
    )
    assert dry_run == 0
    approved_plan = json.loads(capsys.readouterr().out)["planSha256"]
    connection = _SuccessfulConnection(specs, current_version="empty")

    result = check_postgres.main(
        _args(
            expected_current_version="empty",
            environment="production",
            label=f"{PROJECT_ID}/{BRANCH_ID}",
            expected_plan_sha256=approved_plan,
        ),
        env=_env(),
        connect=lambda dsn: connection,
    )

    captured = capsys.readouterr()
    assert result == 0
    assert captured.err == ""
    payload = json.loads(captured.out)
    assert payload["mode"] == "apply"
    assert payload["operation"] == "bootstrap-empty"
    assert payload["planSha256"] == approved_plan
    assert payload["pendingMigrationVersions"] == ["002", "003"]
    assert payload["plannedAdministrativeWriteCount"] == 4
    assert payload["writesPerformed"] == 4
    assert connection.migrations == {
        spec.version: spec.postgres_sha256 for spec in specs
    }
    assert connection.identity == {
        "environment": "production",
        "label": f"{PROJECT_ID}/{BRANCH_ID}",
        "target_fingerprint": _target_fingerprint(),
        "schema_version": "003",
    }
    assert connection.policy is not None
    assert connection.calls[0][0].startswith("SELECT current_database()")
    first_ddl = next(
        index
        for index, (query, _, _) in enumerate(connection.calls)
        if query in {connection.migration_002, connection.migration_003}
    )
    identity_check = next(
        index
        for index, (query, _, _) in enumerate(connection.calls)
        if "to_regclass('public.deployment_identity_v1')" in query
    )
    assert identity_check < first_ddl
    lock_index = next(
        index
        for index, (query, _, _) in enumerate(connection.calls)
        if "pg_advisory_xact_lock" in query
    )
    assert identity_check < lock_index < first_ddl
    assert sum(
        query.startswith("SELECT current_database()")
        for query, _, _ in connection.calls
    ) >= 2


@pytest.mark.parametrize(
    "relation",
    [
        ("unexpected_demo_table", "r"),
        ("unexpected_demo_composite_type", "c"),
    ],
)
def test_empty_preflight_rejects_any_unknown_public_relation(capsys, relation):
    specs = check_postgres.registered_migration_specs()
    connection = _SuccessfulConnection(specs, current_version="empty")
    connection.extra_public_relations.add(relation)

    result = check_postgres.main(
        _args(
            expected_current_version="empty",
            mode="--dry-run",
            environment="production",
            label=f"{PROJECT_ID}/{BRANCH_ID}",
        ),
        env=_env(),
        connect=lambda dsn: connection,
    )

    captured = capsys.readouterr()
    assert result == 1
    assert captured.out == ""
    assert captured.err.strip() == (
        "postgres_check_failed error_type=PostgresCheckError "
        "stage=schema_version"
    )
    assert not any(query == connection.migration_002 for query, _, _ in connection.calls)
    assert not any(query == connection.migration_003 for query, _, _ in connection.calls)


def test_empty_apply_requires_approved_dry_run_plan_before_connecting(capsys):
    specs = check_postgres.registered_migration_specs()

    result = check_postgres.main(
        _args(
            expected_current_version="empty",
            environment="production",
            label=f"{PROJECT_ID}/{BRANCH_ID}",
        ),
        env=_env(),
        connect=lambda dsn: (_ for _ in ()).throw(
            AssertionError("missing approved plan must fail before connect")
        ),
    )

    captured = capsys.readouterr()
    assert result == 1
    assert captured.out == ""
    assert captured.err.strip() == "postgres_check_failed error_type=ValueError"


def test_empty_apply_rejects_wrong_plan_and_lock_time_catalog_race(capsys):
    specs = check_postgres.registered_migration_specs()
    dry_run_connection = _SuccessfulConnection(specs, current_version="empty")
    assert check_postgres.main(
        _args(
            expected_current_version="empty",
            mode="--dry-run",
            environment="production",
            label=f"{PROJECT_ID}/{BRANCH_ID}",
        ),
        env=_env(),
        connect=lambda dsn: dry_run_connection,
    ) == 0
    approved_plan = json.loads(capsys.readouterr().out)["planSha256"]

    wrong_plan_connection = _SuccessfulConnection(specs, current_version="empty")
    wrong_plan = check_postgres.main(
        _args(
            expected_current_version="empty",
            environment="production",
            label=f"{PROJECT_ID}/{BRANCH_ID}",
            expected_plan_sha256="sha256:" + "0" * 64,
        ),
        env=_env(),
        connect=lambda dsn: wrong_plan_connection,
    )
    wrong_capture = capsys.readouterr()
    assert wrong_plan == 1
    assert wrong_capture.out == ""
    assert wrong_capture.err.strip().endswith("stage=plan_identity")
    assert not any(
        "pg_advisory_xact_lock" in query
        for query, _, _ in wrong_plan_connection.calls
    )
    assert not any(
        query in {wrong_plan_connection.migration_002, wrong_plan_connection.migration_003}
        for query, _, _ in wrong_plan_connection.calls
    )

    race_connection = _SuccessfulConnection(specs, current_version="empty")
    race_connection.relation_on_lock = ("concurrent_relation", "r")
    raced = check_postgres.main(
        _args(
            expected_current_version="empty",
            environment="production",
            label=f"{PROJECT_ID}/{BRANCH_ID}",
            expected_plan_sha256=approved_plan,
        ),
        env=_env(),
        connect=lambda dsn: race_connection,
    )
    race_capture = capsys.readouterr()
    assert raced == 1
    assert race_capture.out == ""
    assert race_capture.err.strip().endswith("stage=schema_version")
    assert not any(
        query in {race_connection.migration_002, race_connection.migration_003}
        for query, _, _ in race_connection.calls
    )

def test_legacy_002_apply_requires_approved_plan_and_rechecks_under_lock(capsys):
    specs = check_postgres.registered_migration_specs()

    missing_plan = check_postgres.main(
        _args(
            expected_current_version="002",
            environment="production",
            label=f"{PROJECT_ID}/{BRANCH_ID}",
            expected_plan_sha256=None,
        ),
        env=_env(),
        connect=lambda dsn: (_ for _ in ()).throw(
            AssertionError("missing approved plan must fail before connect")
        ),
    )
    missing_capture = capsys.readouterr()
    assert missing_plan == 1
    assert missing_capture.out == ""
    assert missing_capture.err.strip() == (
        "postgres_check_failed error_type=ValueError"
    )

    dry_connection = _SuccessfulConnection(specs, current_version="legacy002")
    assert dry_connection.migration_table_exists is False
    dry_run = check_postgres.main(
        _args(
            expected_current_version="002",
            mode="--dry-run",
            environment="production",
            label=f"{PROJECT_ID}/{BRANCH_ID}",
        ),
        env=_env(),
        connect=lambda dsn: dry_connection,
    )
    assert dry_run == 0
    dry_payload = json.loads(capsys.readouterr().out)
    assert dry_payload["operation"] == "upgrade-002"
    assert dry_payload["planSha256"] == LEGACY_002_PLAN_SHA256["production"]
    assert dry_payload["pendingMigrationVersions"] == ["003"]
    assert dry_payload["writesPerformed"] == 0
    assert " ".join(dry_connection.calls[0][0].split()) == (
        "SET TRANSACTION READ ONLY"
    )

    registered_connection = _SuccessfulConnection(specs, current_version="002")
    registered_dry_run = check_postgres.main(
        _args(
            expected_current_version="002",
            mode="--dry-run",
            environment="production",
            label=f"{PROJECT_ID}/{BRANCH_ID}",
        ),
        env=_env(),
        connect=lambda dsn: registered_connection,
    )
    assert registered_dry_run == 0
    registered_payload = json.loads(capsys.readouterr().out)
    assert registered_payload["plannedAdministrativeWriteCount"] == 3
    assert dry_payload["plannedAdministrativeWriteCount"] == 4
    assert registered_payload["planSha256"] != dry_payload["planSha256"]

    extra_relation_connection = _SuccessfulConnection(
        specs, current_version="legacy002"
    )
    extra_relation_connection.extra_public_relations.add(
        ("unexpected_legacy_relation", "r")
    )
    extra_relation = check_postgres.main(
        _args(
            expected_current_version="002",
            mode="--dry-run",
            environment="production",
            label=f"{PROJECT_ID}/{BRANCH_ID}",
        ),
        env=_env(),
        connect=lambda dsn: extra_relation_connection,
    )
    extra_capture = capsys.readouterr()
    assert extra_relation == 1
    assert extra_capture.out == ""
    assert extra_capture.err.strip().endswith("stage=schema_version")

    wrong_plan_connection = _SuccessfulConnection(
        specs, current_version="legacy002"
    )
    wrong_plan = check_postgres.main(
        _args(
            expected_current_version="002",
            environment="production",
            label=f"{PROJECT_ID}/{BRANCH_ID}",
            expected_plan_sha256="sha256:" + "0" * 64,
        ),
        env=_env(),
        connect=lambda dsn: wrong_plan_connection,
    )
    wrong_capture = capsys.readouterr()
    assert wrong_plan == 1
    assert wrong_capture.out == ""
    assert wrong_capture.err.strip().endswith("stage=plan_identity")
    assert not any(
        "pg_advisory_xact_lock" in query
        for query, _, _ in wrong_plan_connection.calls
    )

    inventory_race_connection = _SuccessfulConnection(
        specs, current_version="legacy002"
    )
    inventory_race_connection.record_002_on_lock = True
    inventory_race = check_postgres.main(
        _args(
            expected_current_version="002",
            environment="production",
            label=f"{PROJECT_ID}/{BRANCH_ID}",
            expected_plan_sha256=LEGACY_002_PLAN_SHA256["production"],
        ),
        env=_env(),
        connect=lambda dsn: inventory_race_connection,
    )
    inventory_capture = capsys.readouterr()
    assert inventory_race == 1
    assert inventory_capture.out == ""
    assert inventory_capture.err.strip().endswith("stage=plan_identity")
    assert not any(
        query in {
            inventory_race_connection.migration_002,
            inventory_race_connection.migration_003,
        }
        for query, _, _ in inventory_race_connection.calls
    )

    race_connection = _SuccessfulConnection(specs, current_version="legacy002")
    race_connection.invalidate_legacy_v2_on_lock = True
    raced = check_postgres.main(
        _args(
            expected_current_version="002",
            environment="production",
            label=f"{PROJECT_ID}/{BRANCH_ID}",
            expected_plan_sha256=LEGACY_002_PLAN_SHA256["production"],
        ),
        env=_env(),
        connect=lambda dsn: race_connection,
    )
    race_capture = capsys.readouterr()
    assert raced == 1
    assert race_capture.out == ""
    assert race_capture.err.strip().endswith("stage=schema_version")
    assert not any(
        query in {race_connection.migration_002, race_connection.migration_003}
        for query, _, _ in race_connection.calls
    )

    apply_connection = _SuccessfulConnection(specs, current_version="legacy002")
    applied = check_postgres.main(
        _args(
            expected_current_version="002",
            environment="production",
            label=f"{PROJECT_ID}/{BRANCH_ID}",
            expected_plan_sha256=LEGACY_002_PLAN_SHA256["production"],
        ),
        env=_env(),
        connect=lambda dsn: apply_connection,
    )
    apply_capture = capsys.readouterr()
    assert applied == 0
    assert apply_capture.err == ""
    apply_payload = json.loads(apply_capture.out)
    assert apply_payload["planSha256"] == LEGACY_002_PLAN_SHA256["production"]
    assert apply_payload["pendingMigrationVersions"] == ["003"]
    assert apply_payload["plannedAdministrativeWriteCount"] == 4
    assert apply_payload["writesPerformed"] == 4
    assert apply_connection.migrations == {
        spec.version: spec.postgres_sha256 for spec in specs
    }
    assert not any(
        query == apply_connection.migration_002
        for query, _, _ in apply_connection.calls
    )
    assert any(
        query == apply_connection.migration_003
        for query, _, _ in apply_connection.calls
    )


def test_remote_migrator_prefers_non_pooling_dsn_without_echoing_it(capsys):
    specs = check_postgres.registered_migration_specs()
    connection = _SuccessfulConnection(specs, current_version="003")
    direct_url = "postgresql://user:secret@direct.invalid/twinops"
    source_env = {**_env(), "POSTGRES_URL_NON_POOLING": direct_url}
    connected_with = []

    result = check_postgres.main(
        _args(expected_current_version="003"),
        env=source_env,
        connect=lambda dsn: connected_with.append(dsn) or connection,
    )

    captured = capsys.readouterr()
    assert result == 0
    assert connected_with == [direct_url]
    assert direct_url not in captured.out + captured.err
