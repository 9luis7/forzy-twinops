from datetime import datetime, timezone

from twinops.ingestion.forzy_history import import_forzy_history, read_forzy_history
from twinops.storage.sqlite_repository import SQLiteTelemetryRepository


def test_reads_real_forzy_multiline_header_into_two_canonical_streams(tmp_path):
    source = tmp_path / "history.csv"
    source.write_text(
        ";raw1;raw2;4;5;6;7;8;9\n"
        ";PDI;PDI;1.1. Velocidade;1.2. Aceleração;1.3. Temperatura;"
        "2.1. Velocidade;2.2. Aceleração;2.3. Temperatura\n"
        ";Byte[];Byte[];Double;Double;Double;Double;Double;Double\n"
        "2026-05-19T11:46:10.921;a;b;0.04;0;27;0.05;0.01;34\n",
        encoding="utf-8",
    )

    samples = read_forzy_history(
        source,
        asset_tag="MTR-BMB-042",
        timezone_name="America/Sao_Paulo",
        received_at=datetime(2026, 8, 13, 12, 0, tzinfo=timezone.utc),
    )

    assert [sample.sensor_id for sample in samples] == ["s1", "s2"]
    assert samples[0].observed_at == "2026-05-19T14:46:10.921000Z"
    assert samples[0].measurements.vibration_velocity_rms.value == 0.04
    assert samples[1].measurements.vibration_acceleration.value == 0.01
    assert samples[1].measurements.temperature.value == 34
    assert "observed_timezone_assumed:America/Sao_Paulo" in samples[0].quality_flags
    assert samples[0].raw["pdiByteArray"] == "a"


def test_rejects_wrong_header_or_non_finite_measurement(tmp_path):
    wrong_header = tmp_path / "wrong.csv"
    wrong_header.write_text("a;b\n", encoding="utf-8")

    try:
        read_forzy_history(
            wrong_header,
            asset_tag="MTR-BMB-042",
            timezone_name="America/Sao_Paulo",
            received_at=datetime.now(timezone.utc),
        )
    except ValueError as error:
        assert "header" in str(error).lower()
    else:
        raise AssertionError("wrong history header should be rejected")


def test_reading_identity_is_deterministic(tmp_path):
    source = tmp_path / "history.csv"
    source.write_text(
        ";r1;r2;4;5;6;7;8;9\n"
        ";PDI;PDI;1.1. Velocidade;1.2. Aceleração;1.3. Temperatura;"
        "2.1. Velocidade;2.2. Aceleração;2.3. Temperatura\n"
        ";Byte[];Byte[];Double;Double;Double;Double;Double;Double\n"
        "2026-05-19T11:46:10.921;a;b;0.04;0;27;0.05;0.01;34\n",
        encoding="utf-8",
    )
    received_at = datetime(2026, 8, 13, 12, 0, tzinfo=timezone.utc)

    first = read_forzy_history(source, "MTR", "America/Sao_Paulo", received_at)
    second = read_forzy_history(source, "MTR", "America/Sao_Paulo", received_at)

    assert [item.reading_id for item in first] == [item.reading_id for item in second]
    assert [item.payload_hash for item in first] == [item.payload_hash for item in second]


def test_native_history_import_is_idempotent(tmp_path):
    source = tmp_path / "history.csv"
    source.write_text(
        ";r1;r2;4;5;6;7;8;9\n"
        ";PDI;PDI;1.1. Velocidade;1.2. Aceleração;1.3. Temperatura;"
        "2.1. Velocidade;2.2. Aceleração;2.3. Temperatura\n"
        ";Byte[];Byte[];Double;Double;Double;Double;Double;Double\n"
        "2026-05-19T11:46:10.921;a;b;0.04;0;27;0.05;0.01;34\n",
        encoding="utf-8",
    )
    repository = SQLiteTelemetryRepository(tmp_path / "telemetry.db")
    repository.initialize()
    received_at = datetime(2026, 8, 13, 12, 0, tzinfo=timezone.utc)

    first = import_forzy_history(
        source,
        repository,
        asset_tag="MTR-BMB-042",
        timezone_name="America/Sao_Paulo",
        received_at=received_at,
    )
    second = import_forzy_history(
        source,
        repository,
        asset_tag="MTR-BMB-042",
        timezone_name="America/Sao_Paulo",
        received_at=received_at,
    )

    assert first.rows_read == 1
    assert first.samples_inserted == 2
    assert first.duplicates == 0
    assert second.samples_inserted == 0
    assert second.duplicates == 2
