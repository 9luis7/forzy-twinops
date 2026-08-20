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


def _fixture(tmp_path, *, channel_index=0):
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
                "accelerationUnit": "g",
                "files": {
                    "misleading/2099.01.01.00.00.00": {
                        "runId": "explicit-run-10",
                        "sequenceIndex": 1,
                        "startedAt": "2003-10-22T12:10:00-04:00",
                        "timestampQuality": "source_timezone_confirmed",
                        "channels": [
                            {
                                "columnIndex": channel_index,
                                "bearingId": "explicit-bearing-1",
                                "axis": "radial",
                                "windowStateLabel": "outer_race",
                                "terminalFailureMode": "outer_race",
                                "lifeFraction": 1.0,
                            },
                            {
                                "columnIndex": 1,
                                "bearingId": "explicit-bearing-2",
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
                                "bearingId": "explicit-bearing-1",
                                "axis": "radial",
                                "windowStateLabel": "normal",
                                "terminalFailureMode": "outer_race",
                                "lifeFraction": 0.0,
                            },
                            {
                                "columnIndex": 1,
                                "bearingId": "explicit-bearing-2",
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
        (0, "explicit-bearing-1"),
        (0, "explicit-bearing-2"),
        (1, "explicit-bearing-1"),
        (1, "explicit-bearing-2"),
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
