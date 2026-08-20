from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest

from twinops.research.compatibility import compatibility
from twinops.research.contracts import SignalWindow


def window_without_temperature_or_rpm() -> SignalWindow:
    return SignalWindow(
        dataset_id="xjtu-sy",
        bearing_id="Bearing1_1",
        run_id="001",
        started_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        sampling_hz=25_600,
        acceleration=np.array([0.1, -0.2, 0.3]),
        fault_label="normal",
    )


def test_window_rejects_missing_identity_and_non_finite_signal() -> None:
    with pytest.raises(ValueError, match="bearing_id"):
        SignalWindow(
            dataset_id="xjtu-sy",
            bearing_id="",
            run_id="1",
            sampling_hz=25_600,
            acceleration=np.array([0.0, np.nan]),
            fault_label="normal",
        )

    with pytest.raises(ValueError, match="finite"):
        SignalWindow(
            dataset_id="xjtu-sy",
            bearing_id="Bearing1_1",
            run_id="1",
            sampling_hz=25_600,
            acceleration=np.array([0.0, np.nan]),
            fault_label="normal",
        )


def test_window_accepts_axis_mapping_and_validates_each_axis() -> None:
    window = SignalWindow(
        dataset_id="xjtu-sy",
        bearing_id="Bearing1_1",
        run_id="001",
        sampling_hz=25_600,
        acceleration={"horizontal": [0.1, -0.1], "vertical": [0.2, -0.2]},
        fault_label="outer_race",
    )

    assert set(window.acceleration) == {"horizontal", "vertical"}
    assert all(isinstance(axis, np.ndarray) for axis in window.acceleration.values())

    with pytest.raises(ValueError, match="one-dimensional"):
        SignalWindow(
            dataset_id="xjtu-sy",
            bearing_id="Bearing1_1",
            run_id="002",
            sampling_hz=25_600,
            acceleration={"horizontal": [[0.1], [0.2]]},
            fault_label="normal",
        )


@pytest.mark.parametrize("field,value", [("sampling_hz", 0), ("temperature_c", np.inf), ("rpm", -1)])
def test_window_rejects_invalid_numeric_metadata(field: str, value: float) -> None:
    kwargs = {
        "dataset_id": "ims",
        "bearing_id": "test-1-bearing-1",
        "run_id": "001",
        "sampling_hz": 20_000,
        "acceleration": np.array([0.0, 0.1]),
        "fault_label": "normal",
    }
    kwargs[field] = value

    with pytest.raises(ValueError, match=field):
        SignalWindow(**kwargs)


def test_window_rejects_unknown_label_and_out_of_range_life_fraction() -> None:
    with pytest.raises(ValueError, match="fault_label"):
        SignalWindow(
            dataset_id="ims",
            bearing_id="b1",
            run_id="001",
            sampling_hz=20_000,
            acceleration=np.array([0.0, 0.1]),
            fault_label="guessed_from_filename",
        )

    with pytest.raises(ValueError, match="life_fraction"):
        SignalWindow(
            dataset_id="ims",
            bearing_id="b1",
            run_id="001",
            sampling_hz=20_000,
            acceleration=np.array([0.0, 0.1]),
            fault_label="unknown",
            life_fraction=1.1,
        )


def test_forzy_view_does_not_invent_temperature_rpm_or_velocity() -> None:
    report = compatibility(window_without_temperature_or_rpm())

    assert "temperature_c" not in report.forzy_features
    assert "velocity_rms_mm_s" not in report.forzy_features
    assert "rpm" in report.missing_semantics
    assert "temperature_c" in report.missing_semantics
    assert "velocity_rms_mm_s" in report.missing_semantics


def test_forzy_view_includes_only_measured_compatible_aggregates() -> None:
    window = SignalWindow(
        dataset_id="pronostia",
        bearing_id="Bearing1_1",
        run_id="001",
        sampling_hz=25_600,
        acceleration=np.array([0.1, -0.1]),
        temperature_c=42.5,
        rpm=1_800,
        fault_label="normal",
    )

    report = compatibility(window)

    assert report.forzy_features == ("acceleration_rms_g", "temperature_c")
    assert "rpm" not in report.forzy_features
    assert "rpm" in report.aggregate_features
