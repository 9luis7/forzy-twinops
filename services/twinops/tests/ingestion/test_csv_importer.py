from datetime import datetime, timezone

from twinops.ingestion.csv_importer import import_csv
from twinops.storage.repository import HistoryQuery
from twinops.storage.sqlite_repository import SQLiteTelemetryRepository


HEADER = (
    "sensor_id,observed_at,vibration_velocity_rms,"
    "vibration_acceleration,temperature\n"
)


def test_csv_import_is_idempotent_and_keeps_source_and_timestamp(tmp_path):
    csv_fixture_path = tmp_path / "telemetry.csv"
    csv_fixture_path.write_text(
        HEADER
        + "s1,2026-08-10T15:00:00Z,0.04,0.0,34\n"
        + "s2,2026-08-10T15:00:00Z,0.05,0.0,35\n",
        encoding="utf-8",
    )
    repo = SQLiteTelemetryRepository(tmp_path / "telemetry.db")
    repo.initialize()
    now = datetime(2026, 8, 12, 15, 0, tzinfo=timezone.utc)

    first = import_csv(csv_fixture_path, repo, "MTR-BMB-042", now)
    second = import_csv(csv_fixture_path, repo, "MTR-BMB-042", now)

    assert (first.rows_read, first.samples_inserted, first.rejected) == (2, 2, 0)
    assert (second.samples_inserted, second.duplicates) == (0, 2)
    samples = repo.history(
        HistoryQuery(asset_tag="MTR-BMB-042", source="forzy-csv")
    )
    assert {reading.source for reading in samples} == {"forzy-csv"}
    assert all(reading.scheduled_at is None for reading in samples)
    assert {reading.observed_at for reading in samples} == {
        "2026-08-10T15:00:00Z"
    }
    assert all(
        reading.provenance.source_system == "forzy-csv-import"
        for reading in samples
    )


def test_invalid_csv_row_is_rejected_without_becoming_zero(tmp_path):
    csv_fixture_path = tmp_path / "telemetry.csv"
    csv_fixture_path.write_text(
        HEADER
        + "s1,2026-08-10T15:00:00Z,,0.0,34\n"
        + "s2,2026-08-10T15:00:00Z,0,0,0\n",
        encoding="utf-8",
    )
    repo = SQLiteTelemetryRepository(tmp_path / "telemetry.db")
    repo.initialize()

    report = import_csv(
        csv_fixture_path,
        repo,
        "MTR-BMB-042",
        datetime(2026, 8, 12, 15, 0, tzinfo=timezone.utc),
    )

    assert (report.rows_read, report.samples_inserted, report.rejected) == (2, 1, 1)
    only = repo.history(HistoryQuery(asset_tag="MTR-BMB-042"))[0]
    assert only.sensor_id == "s2"
    assert only.measurements.vibration_velocity_rms.value == 0.0


def test_csv_rows_with_missing_identity_or_timestamp_are_counted_as_rejected(tmp_path):
    csv_fixture_path = tmp_path / "telemetry.csv"
    csv_fixture_path.write_text(
        HEADER
        + ",2026-08-10T15:00:00Z,0.04,0.0,34\n"
        + "s1\n",
        encoding="utf-8",
    )
    repo = SQLiteTelemetryRepository(tmp_path / "telemetry.db")
    repo.initialize()

    report = import_csv(
        csv_fixture_path,
        repo,
        "MTR-BMB-042",
        datetime(2026, 8, 12, 15, 0, tzinfo=timezone.utc),
    )

    assert (report.rows_read, report.samples_inserted, report.rejected) == (2, 0, 2)
