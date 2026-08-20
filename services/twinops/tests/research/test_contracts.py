from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest

from twinops.research.compatibility import compatibility
from twinops.research.contracts import FeaturePolicy, LabelMappingPolicy, SignalWindow
from .factories import make_window


def test_window_requires_explicit_unit_axes_and_provenance() -> None:
    with pytest.raises(TypeError, match="acceleration_unit"):
        SignalWindow(
            dataset_id="xjtu-sy",
            bearing_id="bearing-1",
            run_id="run-1",
            sampling_hz=25_600,
            acceleration={"radial": np.array([0.1, -0.1])},
            window_state_label="normal",
            sequence_index=0,
            timestamp_quality="unavailable",
            source_relative_path="condition/bearing-1/1.csv",
            metadata_sha256="a" * 64,
        )

    with pytest.raises(ValueError, match="axis mapping"):
        SignalWindow(
            dataset_id="xjtu-sy",
            bearing_id="bearing-1",
            run_id="run-1",
            sampling_hz=25_600,
            acceleration=np.array([0.1, -0.1]),
            acceleration_unit="g",
            window_state_label="normal",
            sequence_index=0,
            timestamp_quality="unavailable",
            source_relative_path="condition/bearing-1/1.csv",
            metadata_sha256="a" * 64,
        )


def test_window_rejects_non_finite_misaligned_or_unidentified_signal() -> None:
    with pytest.raises(ValueError, match="bearing_id"):
        make_window(bearing_id="", axes={"radial": np.array([0.0, np.nan])})
    with pytest.raises(ValueError, match="finite"):
        make_window(axes={"radial": np.array([0.0, np.nan])})
    with pytest.raises(ValueError, match="same number of samples"):
        make_window(axes={"radial": np.array([0.1, 0.2]), "axial": np.array([0.3])})


def test_window_separates_terminal_mode_from_per_window_state() -> None:
    window = make_window(
        window_state_label="normal",
        terminal_failure_mode="outer_race",
        life_fraction=0.25,
        sequence_index=3,
    )

    assert window.window_state_label == "normal"
    assert window.terminal_failure_mode == "outer_race"
    assert window.life_fraction == pytest.approx(0.25)
    assert window.sequence_index == 3

    with pytest.raises(ValueError, match="sequence_index"):
        make_window(life_fraction=0.5, sequence_index=None)


def test_source_labels_are_preserved_until_versioned_canonical_mapping() -> None:
    window = make_window(
        window_state_label="source-healthy",
        terminal_failure_mode="source-outer-ring",
    )
    policy = LabelMappingPolicy(
        version="source-taxonomy-v1",
        mapping={"source-healthy": "normal", "source-outer-ring": "outer_race"},
    )

    assert window.window_state_label == "source-healthy"
    assert window.terminal_failure_mode == "source-outer-ring"
    assert policy.mapping[window.window_state_label] == "normal"


def test_timestamp_quality_cannot_invent_timezone_or_time() -> None:
    with pytest.raises(ValueError, match="unavailable"):
        SignalWindow(
            dataset_id="ims",
            bearing_id="b1",
            run_id="r1",
            sampling_hz=20_000,
            acceleration={"radial": [0.1, -0.1]},
            acceleration_unit="g",
            window_state_label="normal",
            sequence_index=0,
            started_at=datetime(2003, 1, 1, tzinfo=timezone.utc),
            timestamp_quality="unavailable",
            source_relative_path="test/run.txt",
            metadata_sha256="a" * 64,
        )

    with pytest.raises(ValueError, match="started_at"):
        SignalWindow(
            dataset_id="ims",
            bearing_id="b1",
            run_id="r1",
            sampling_hz=20_000,
            acceleration={"radial": [0.1, -0.1]},
            acceleration_unit="g",
            window_state_label="normal",
            sequence_index=0,
            started_at=None,
            timestamp_quality="source_timezone_confirmed",
            source_relative_path="test/run.txt",
            metadata_sha256="a" * 64,
        )


def test_forzy_acceleration_is_blocked_until_audited_policy() -> None:
    window = make_window(temperature_c=42.5)
    unconfirmed = compatibility(window)

    assert not unconfirmed.forzy_features
    assert unconfirmed.missing_semantics["acceleration_rms_g"] == "unconfirmed_semantics"

    policy = FeaturePolicy(
        policy_id="synthetic-policy-v1",
        selected_acceleration_axis="radial",
        acceleration_rms_semantics_confirmed=True,
        temperature_semantics_confirmed=True,
        evidence="Synthetic fixture contract; not evidence for Forzy.",
    )
    confirmed = compatibility(window, policy=policy)

    assert confirmed.forzy_features == ("acceleration_rms_g__radial", "temperature_c")
    assert set(confirmed.forzy_features) <= set(confirmed.aggregate_features)
    assert set(confirmed.aggregate_features) <= set(confirmed.full_features)
