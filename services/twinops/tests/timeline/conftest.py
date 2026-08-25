from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import sqlite3
from typing import Literal

import pytest

from twinops.ingestion.historical_import_v1 import (
    _prepare_historical_batch_for_profile,
)
from twinops.ingestion.live_adapter_v2 import adapt_live_payload_v2
from twinops.ingestion.history_profiles_v1 import (
    HistoryProfileV1,
    registered_profile,
)
from twinops.storage.schema_migrations import (
    apply_sqlite_migrations,
    registered_migration_specs,
)
from twinops.storage.sqlite_historical_repository_v1 import (
    SQLiteHistoricalRepositoryV1,
)
from twinops.storage.sqlite_v2_repository import SQLiteTelemetryRepositoryV2


_HEADER_RECORDS = registered_profile(
    "forzy-history-2026-05-19-v1"
).header_records
_ROWS_BY_VARIANT = {
    0: (
        "2026-05-19T11:46:10.921;AQID;BAUG;0.04;0;27;0.05;0.01;34",
        "2026-05-19T11:46:20.921;CQoL;DA0O;0.06;0.02;28;0.07;0.03;35",
    ),
    1: (
        "2026-05-19T11:46:10.921;AQID;BAUG;0.14;0;27;0.15;0.01;34",
        "2026-05-19T11:46:20.921;CQoL;DA0O;0.16;0.02;28;0.17;0.03;35",
    ),
}


def prepared_batch(variant: int):
    rows = _ROWS_BY_VARIANT[variant]
    source_bytes = b"".join(_HEADER_RECORDS) + b"".join(
        row.encode("utf-8") + b"\r\n" for row in rows
    )
    profile = HistoryProfileV1(
        profile_id=f"synthetic-vs1-v{variant}",
        source_size_bytes=len(source_bytes),
        source_sha256="sha256:" + sha256(source_bytes).hexdigest(),
        header_records=_HEADER_RECORDS,
        encoding="utf-8",
        delimiter=";",
        newline="CRLF",
        final_crlf_required=True,
        data_record_count=len(rows),
        sample_count=2 * len(rows),
        operating_cycle_count=1,
        timezone_name="America/Sao_Paulo",
        parser_version="forzy-history-parser-v1",
        contract_version="1.0",
        gap_seconds=15.0,
    )
    return _prepare_historical_batch_for_profile(
        source_bytes,
        profile=profile,
        asset_id="forzy-motor-01",
        ingested_at=datetime(2026, 8, 22, 12, tzinfo=timezone.utc),
    )


def live_reading(
    *,
    reading_id: str,
    sensor_id: Literal["s1", "s2"],
    scheduled_at: datetime,
    received_at: datetime,
    velocity: float,
):
    root = "dados1" if sensor_id == "s1" else "dados2"
    reading = adapt_live_payload_v2(
        sensor_id=sensor_id,
        payload={
            root: {
                "Velocidade": velocity,
                "Acelera\u00e7\u00e3o": 0.01,
                "Temperatura": 34,
            }
        },
        scheduled_at=scheduled_at,
        received_at=received_at,
    )
    payload = reading.model_dump(mode="json", by_alias=True)
    payload["readingId"] = reading_id
    return type(reading).model_validate(payload)


def store_live_reading(
    path: Path,
    reading,
    *,
    collection_policy_id: str | None,
) -> None:
    repository = SQLiteTelemetryRepositoryV2(path)
    result = repository.insert_distinct_sample(reading)
    assert result.stored is True
    scheduled = (
        datetime.fromisoformat(reading.scheduled_at.replace("Z", "+00:00"))
        .astimezone(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )
    with sqlite3.connect(path, timeout=5) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute(
            "INSERT OR IGNORE INTO refresh_cycles_v2 "
            "(asset_id,scheduled_at,owner_token,claimed_at,completed_at,"
            "outcomes_json,status) VALUES (?,?,?,?,?,?,?)",
            (
                reading.asset_id,
                scheduled,
                "test-owner",
                scheduled,
                scheduled,
                '{"s1":"stored","s2":"stored"}',
                "completed",
            ),
        )
        if collection_policy_id is not None:
            connection.execute(
                "INSERT OR IGNORE INTO refresh_cycle_policies_v1 "
                "(asset_id,scheduled_at,policy_id) VALUES (?,?,?)",
                (reading.asset_id, scheduled, collection_policy_id),
            )


@pytest.fixture
def sqlite_database_path(tmp_path: Path) -> Path:
    path = tmp_path / "timeline-vs1.sqlite3"
    connection = sqlite3.connect(path, timeout=5)
    try:
        apply_sqlite_migrations(
            connection,
            registered_migration_specs(),
            initial_policy_effective_from=datetime(
                2026, 8, 1, tzinfo=timezone.utc
            ),
        )
    finally:
        connection.close()
    return path


@pytest.fixture
def sqlite_timeline_repository(sqlite_database_path: Path):
    return SQLiteHistoricalRepositoryV1(sqlite_database_path)
