from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

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
        self.migrations = {
            "002": specs[0].postgres_sha256,
        }
        if current_version == "003":
            self.migrations["003"] = specs[1].postgres_sha256
        self.policy = None
        self.identity = None
        self.migration_003 = MIGRATION_003.read_text(encoding="utf-8")
        if current_version == "003":
            self._store_policy(EFFECTIVE_FROM)
            self.identity = {
                "environment": "preview",
                "label": "forzy-twinops-preview",
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
        if normalized.startswith("SELECT current_database()"):
            return _Rows([(DATABASE_NAME, SCHEMA_NAME)])
        if "to_regclass('public.schema_migrations_v1')" in normalized:
            return _Rows([{"relation": "schema_migrations_v1"}])
        if normalized.startswith("SELECT migration_version, sql_sha256"):
            return _Rows(
                {
                    "migration_version": version,
                    "sql_sha256": digest,
                }
                for version, digest in sorted(self.migrations.items())
            )
        if "pg_advisory_xact_lock" in normalized:
            return _Rows()
        if query == self.migration_003:
            return _Rows()
        if normalized.startswith("CREATE TABLE IF NOT EXISTS schema_migrations_v1"):
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
            self.identity = {
                "environment": params[1],
                "label": params[2],
                "target_fingerprint": params[3],
                "schema_version": params[4],
            }
            return _Rows()
        if "FROM pg_catalog.pg_tables" in normalized:
            if "AS tables_current" in normalized:
                return _Rows([{"tables_current": True, "indexes_current": True}])
            return _Rows((name,) for name in check_postgres.POSTGRES_V3_REQUIRED_TABLES)
        if "FROM pg_catalog.pg_indexes" in normalized:
            return _Rows((name,) for name in check_postgres.POSTGRES_V3_REQUIRED_INDEXES)
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


def _args(*, expected_current_version="002", fingerprint=None):
    return [
        "--migrate",
        str(MIGRATION_002),
        "--migrate",
        str(MIGRATION_003),
        "--environment",
        "preview",
        "--expected-target-label",
        "forzy-twinops-preview",
        "--expected-target-fingerprint",
        fingerprint or _target_fingerprint(),
        "--expected-current-version",
        expected_current_version,
        "--initial-policy-effective-from",
        EFFECTIVE_FROM,
    ]


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
        "label": "forzy-twinops-preview",
        "target_fingerprint": _target_fingerprint(),
        "schema_version": "003",
    }
    assert captured.err == ""
    assert captured.out.strip() == (
        "postgres_check_ok schema_version=003 tables=13 indexes=8 policies=1 "
        "policy_id=forzy-live-window-v1 "
        "policy_hash=sha256:89bde17193c7a34c80d48828f4e61fc"
        "5802caa92169d83f8a9fd8e4c282b1bce"
    )
    for secret in (
        DATABASE_URL,
        "user",
        "secret",
        "database.invalid",
        str(MIGRATION_002),
        str(MIGRATION_003),
        PROJECT_ID,
        BRANCH_ID,
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
    assert not any("pg_advisory_xact_lock" in query for query, _, _ in connection.calls)
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
