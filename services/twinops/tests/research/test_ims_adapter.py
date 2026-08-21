from __future__ import annotations

import hashlib
import json
import zipfile
from datetime import timedelta

import numpy as np
import pytest

from twinops.research.datasets.ims import iter_ims
from twinops.research.downloads import safe_extract_archive
from twinops.research.metadata import load_metadata


def _fixture(
    tmp_path,
    *,
    channel_index=0,
    samples_per_window=2,
    same_sequence=False,
    globally_unique_bearings=True,
):
    archive = tmp_path / "ims.zip"
    members = {
        "misleading/2099.01.01.00.00.00": b"10 20\n11 21\n",
        "misleading/not-a-timestamp": b"1 2\n3 4\n",
    }
    with zipfile.ZipFile(archive, "w") as container:
        for name, content in members.items():
            container.writestr(name, content)
    inventory = safe_extract_archive(archive, tmp_path / "raw")
    metadata_path = tmp_path / "ims.metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "datasetId": "nasa-ims",
                "metadataId": "fixture-ims-v1",
                "samplingHz": 20_000,
                "samplesPerWindow": samples_per_window,
                "accelerationUnit": "g",
                "files": {
                    "misleading/2099.01.01.00.00.00": {
                        "runId": "explicit-run-10",
                        "sequenceIndex": 0 if same_sequence else 1,
                        "startedAt": "2003-10-22T12:10:00-04:00",
                        "timestampQuality": "source_timezone_confirmed",
                        "channels": [
                            {
                                "columnIndex": channel_index,
                                "bearingId": (
                                    "ims-run-10-bearing-1"
                                    if globally_unique_bearings
                                    else "reused-bearing-1"
                                ),
                                "axis": "radial",
                                "windowStateLabel": "outer_race",
                                "terminalFailureMode": "outer_race",
                                "lifeFraction": 1.0,
                            },
                            {
                                "columnIndex": 1,
                                "bearingId": (
                                    "ims-run-10-bearing-2"
                                    if globally_unique_bearings
                                    else "reused-bearing-2"
                                ),
                                "axis": "radial",
                                "windowStateLabel": "normal",
                                "terminalFailureMode": None,
                                "lifeFraction": 1.0,
                            },
                        ],
                    },
                    "misleading/not-a-timestamp": {
                        "runId": "explicit-run-2",
                        "sequenceIndex": 0,
                        "startedAt": None,
                        "timestampQuality": "unavailable",
                        "channels": [
                            {
                                "columnIndex": 0,
                                "bearingId": (
                                    "ims-run-2-bearing-1"
                                    if globally_unique_bearings
                                    else "reused-bearing-1"
                                ),
                                "axis": "radial",
                                "windowStateLabel": "normal",
                                "terminalFailureMode": "outer_race",
                                "lifeFraction": 0.0,
                            },
                            {
                                "columnIndex": 1,
                                "bearingId": (
                                    "ims-run-2-bearing-2"
                                    if globally_unique_bearings
                                    else "reused-bearing-2"
                                ),
                                "axis": "radial",
                                "windowStateLabel": "normal",
                                "terminalFailureMode": None,
                                "lifeFraction": 0.0,
                            },
                        ],
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    digest = hashlib.sha256(metadata_path.read_bytes()).hexdigest()
    metadata = load_metadata(
        metadata_path,
        expected_sha256=digest,
        dataset_id="nasa-ims",
        raw_inventory=inventory,
    )
    return tmp_path / "raw", metadata


def test_ims_adapter_uses_explicit_channels_sequence_and_timezone(tmp_path) -> None:
    raw, metadata = _fixture(tmp_path)

    windows = list(iter_ims(raw, metadata))

    assert [(window.sequence_index, window.bearing_id) for window in windows] == [
        (0, "ims-run-2-bearing-1"),
        (0, "ims-run-2-bearing-2"),
        (1, "ims-run-10-bearing-1"),
        (1, "ims-run-10-bearing-2"),
    ]
    first = windows[0]
    assert first.run_id == "explicit-run-2"
    assert first.started_at is None
    assert first.timestamp_quality == "unavailable"
    later = windows[2]
    assert later.started_at.utcoffset() == timedelta(hours=-4)
    assert later.window_state_label == "outer_race"
    assert later.terminal_failure_mode == "outer_race"
    np.testing.assert_allclose(first.acceleration["radial"], [1, 3])


def test_ims_adapter_rejects_duplicate_or_unmapped_channel_position(tmp_path) -> None:
    raw, metadata = _fixture(tmp_path, channel_index=1)

    with pytest.raises(ValueError, match="columnIndex"):
        list(iter_ims(raw, metadata))


@pytest.mark.parametrize("samples_per_window", [None, True, 0, -1, 2.0])
def test_ims_adapter_requires_positive_integer_samples_per_window(
    tmp_path, samples_per_window
) -> None:
    raw, metadata = _fixture(tmp_path, samples_per_window=samples_per_window)

    with pytest.raises(ValueError, match="samplesPerWindow"):
        list(iter_ims(raw, metadata))


def test_ims_adapter_rejects_a_matrix_with_the_wrong_row_count(tmp_path) -> None:
    raw, metadata = _fixture(tmp_path, samples_per_window=3)

    with pytest.raises(ValueError, match="row count"):
        list(iter_ims(raw, metadata))


def test_ims_adapter_allows_equal_sequences_in_different_runs(tmp_path) -> None:
    raw, metadata = _fixture(tmp_path, same_sequence=True)

    windows = list(iter_ims(raw, metadata))

    assert {(window.run_id, window.sequence_index) for window in windows} == {
        ("explicit-run-2", 0),
        ("explicit-run-10", 0),
    }


def test_ims_adapter_requires_bearing_ids_to_be_globally_unique_across_runs(
    tmp_path,
) -> None:
    raw, metadata = _fixture(tmp_path, globally_unique_bearings=False)

    with pytest.raises(ValueError, match="globally unique"):
        list(iter_ims(raw, metadata))
