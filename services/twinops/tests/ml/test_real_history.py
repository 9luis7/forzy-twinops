from datetime import datetime, timezone

from twinops.ml.real_history import prepare_forzy_history_features


def test_prepares_both_real_history_sensor_streams_without_raw_fields(tmp_path):
    source = tmp_path / "history.csv"
    source.write_text(
        ";raw1;raw2;4;5;6;7;8;9\n"
        ";PDI;PDI;1.1. Velocidade;1.2. Aceleração;1.3. Temperatura;"
        "2.1. Velocidade;2.2. Aceleração;2.3. Temperatura\n"
        ";Byte[];Byte[];Double;Double;Double;Double;Double;Double\n"
        "2026-05-19T11:46:10.000;a;b;0.04;0;27;0.05;0.01;34\n"
        "2026-05-19T11:46:11.000;c;d;0.06;0;27;0.07;0.01;34\n"
        "2026-05-19T11:46:12.000;e;f;0.08;0;28;0.09;0.01;35\n",
        encoding="utf-8",
    )

    features = prepare_forzy_history_features(
        source,
        asset_tag="MTR-BMB-042",
        timezone_name="America/Sao_Paulo",
        received_at=datetime(2026, 8, 13, 18, 47, 2, tzinfo=timezone.utc),
    )

    assert len(features) == 6
    assert set(features["sensor_id"]) == {"s1", "s2"}
    assert features["feature_valid"].sum() == 2
    assert "raw" not in features.columns
    assert features["event_at"].min().isoformat().startswith("2026-05-19T14:46:10")
