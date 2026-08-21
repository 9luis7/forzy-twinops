"""Apply and verify the TwinOps v2 PostgreSQL migration without leaking DSNs."""

import argparse
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
import os
from pathlib import Path
import sys
from uuid import uuid4

import psycopg

from twinops.storage.postgres_repository import (
    POSTGRES_SCHEMA_MIGRATION_LOCK_KEY,
    POSTGRES_V2_REQUIRED_INDEXES,
    POSTGRES_V2_REQUIRED_TABLES,
    ensure_postgres_schema,
)


_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_EXPECTED_MIGRATION = (
    _REPOSITORY_ROOT / "services" / "twinops" / "migrations" / "002_real_twin_v2.sql"
)
class PostgresCheckError(RuntimeError):
    def __init__(self, stage: str):
        super().__init__(stage)
        self.stage = stage


def _migration_path(argv: Sequence[str] | None) -> Path:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--migrate", required=True, type=Path)
    candidate = parser.parse_args(argv).migrate.resolve()
    if candidate != _EXPECTED_MIGRATION.resolve():
        raise ValueError("unexpected migration path")
    return candidate


def _verify_database(database_url: str, migration_path: Path, connect) -> None:
    probe_id = f"twinops-deploy-probe-{uuid4()}"
    now = datetime.now(timezone.utc)

    with connect(database_url) as connection:
        ensure_postgres_schema(
            connection,
            lambda: migration_path.read_text(encoding="utf-8"),
        )

        tables = {
            row[0]
            for row in connection.execute(
                "SELECT tablename FROM pg_catalog.pg_tables "
                "WHERE schemaname='public' AND tablename = ANY(%s)",
                (sorted(POSTGRES_V2_REQUIRED_TABLES),),
            ).fetchall()
        }
        if tables != POSTGRES_V2_REQUIRED_TABLES:
            raise PostgresCheckError("tables")

        indexes = {
            row[0]
            for row in connection.execute(
                "SELECT indexname FROM pg_catalog.pg_indexes "
                "WHERE schemaname='public' AND indexname = ANY(%s)",
                (sorted(POSTGRES_V2_REQUIRED_INDEXES),),
            ).fetchall()
        }
        if indexes != POSTGRES_V2_REQUIRED_INDEXES:
            raise PostgresCheckError("indexes")

        if connection.pgconn.ssl_in_use is not True:
            raise PostgresCheckError("tls")

        connection.execute(
            "INSERT INTO telemetry_samples_v2 "
            "(reading_id,asset_id,sensor_id,observed_at,received_at,"
            "payload_hash,canonical_json) VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (
                probe_id,
                "__twinops_deploy_probe__",
                "probe",
                now,
                now,
                "sha256:deploy-probe",
                "{}",
            ),
        )
        read_back = connection.execute(
            "SELECT reading_id FROM telemetry_samples_v2 WHERE reading_id=%s",
            (probe_id,),
        ).fetchone()
        if read_back != (probe_id,):
            raise PostgresCheckError("probe")

        connection.execute(
            "DELETE FROM telemetry_samples_v2 WHERE reading_id=%s",
            (probe_id,),
        )
        remaining = connection.execute(
            "SELECT COUNT(*) FROM telemetry_samples_v2 WHERE reading_id=%s",
            (probe_id,),
        ).fetchone()
        if remaining != (0,):
            raise PostgresCheckError("probe")


def main(
    argv: Sequence[str] | None = None,
    *,
    env: Mapping[str, str] | None = None,
    connect: Callable[..., object] = psycopg.connect,
) -> int:
    try:
        source_env = os.environ if env is None else env
        database_url = source_env.get("DATABASE_URL")
        if not database_url:
            raise ValueError("DATABASE_URL is required")
        migration_path = _migration_path(argv)
        _verify_database(database_url, migration_path, connect)
        print("postgres_check_ok tables=5 indexes=2 ssl=true probe=passed")
        return 0
    except Exception as exc:
        stage = f" stage={exc.stage}" if isinstance(exc, PostgresCheckError) else ""
        print(
            f"postgres_check_failed error_type={type(exc).__name__}{stage}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
