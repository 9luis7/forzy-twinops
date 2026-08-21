from __future__ import annotations

import hashlib
import json
import zipfile

import numpy as np
import pytest

from twinops.research.datasets.xjtu import iter_xjtu
from twinops.research.downloads import safe_extract_archive
from twinops.research.metadata import load_metadata


_HORIZONTAL_HEADER = "Horizontal_vibration_signals"
_VERTICAL_HEADER = "Vertical_vibration_signals"


def _fixture(tmp_path, *, columns=None):
    archive = tmp_path / "xjtu.zip"
    members = {
        "Introduction_to_XJTU-SY_Bearing_Dataset.pdf": b"%PDF-1.4 fixture",
        "misleading/outer_race/10.csv": (
            b"Horizontal_vibration_signals,Vertical_vibration_signals\n"
            b"10,20\n11,21\n"
        ),
        "misleading/normal/2.csv": (
            b"Horizontal_vibration_signals,Vertical_vibration_signals\n"
            b"2,4\n3,5\n"
        ),
    }
    with zipfile.ZipFile(archive, "w") as container:
        for name, content in members.items():
            container.writestr(name, content)
    inventory = safe_extract_archive(archive, tmp_path / "raw")
    metadata_path = tmp_path / "xjtu.metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "datasetId": "xjtu-sy",
                "metadataId": "fixture-xjtu-v1",
                "samplingHz": 25_600,
                "samplesPerWindow": 2,
                "accelerationUnit": "g",
                "files": {
                    "Introduction_to_XJTU-SY_Bearing_Dataset.pdf": {
                        "kind": "source_document",
                        "mediaType": "application/pdf",
                    },
                    "misleading/outer_race/10.csv": {
                        "kind": "signal_window",
                        "bearingId": "explicit-bearing-a",
                        "runId": "explicit-run-10",
                        "sequenceIndex": 1,
                        "startedAt": None,
                        "timestampQuality": "unavailable",
                        "windowStateLabel": "normal",
                        "terminalFailureMode": "outer_race",
                        "lifeFraction": 0.5,
                        "columns": columns
                        or {
                            _HORIZONTAL_HEADER: "horizontal",
                            _VERTICAL_HEADER: "vertical",
                        },
                        "hasHeader": True,
                        "rpm": 2_100,
                        "load": 12,
                    },
                    "misleading/normal/2.csv": {
                        "kind": "signal_window",
                        "bearingId": "explicit-bearing-a",
                        "runId": "explicit-run-2",
                        "sequenceIndex": 0,
                        "startedAt": None,
                        "timestampQuality": "unavailable",
                        "windowStateLabel": "normal",
                        "terminalFailureMode": "outer_race",
                        "lifeFraction": 0.0,
                        "columns": {
                            _HORIZONTAL_HEADER: "horizontal",
                            _VERTICAL_HEADER: "vertical",
                        },
                        "hasHeader": True,
                        "rpm": 2_100,
                        "load": 12,
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
        dataset_id="xjtu-sy",
        raw_inventory=inventory,
    )
    return tmp_path / "raw", metadata


def test_xjtu_adapter_skips_official_header_and_preserves_window_identity_and_count(
    tmp_path,
) -> None:
    raw, metadata = _fixture(tmp_path)

    windows = list(iter_xjtu(raw, metadata))

    assert [window.sequence_index for window in windows] == [0, 1]
    assert [window.run_id for window in windows] == ["explicit-run-2", "explicit-run-10"]
    assert all(window.bearing_id == "explicit-bearing-a" for window in windows)
    assert all(window.window_state_label == "normal" for window in windows)
    assert all(window.terminal_failure_mode == "outer_race" for window in windows)
    assert all(window.started_at is None for window in windows)
    assert all(window.timestamp_quality == "unavailable" for window in windows)
    assert all(window.acceleration_unit == "g" for window in windows)
    assert all(window.metadata_sha256 == metadata.metadata_sha256 for window in windows)
    assert len(windows) == 2
    assert [
        (window.run_id, window.bearing_id, window.sequence_index)
        for window in windows
    ] == [
        ("explicit-run-2", "explicit-bearing-a", 0),
        ("explicit-run-10", "explicit-bearing-a", 1),
    ]
    np.testing.assert_allclose(windows[0].acceleration["horizontal"], [2, 3])
    np.testing.assert_allclose(windows[0].acceleration["vertical"], [4, 5])


def test_xjtu_adapter_rejects_unmapped_column_instead_of_fallback(tmp_path) -> None:
    raw, metadata = _fixture(
        tmp_path,
        columns={"horizontal-ish": "horizontal", _VERTICAL_HEADER: "vertical"},
    )

    with pytest.raises(ValueError, match="column"):
        list(iter_xjtu(raw, metadata))


def test_xjtu_adapter_rejects_non_string_axis_instead_of_stringifying_it(tmp_path) -> None:
    raw, metadata = _fixture(
        tmp_path,
        columns={_HORIZONTAL_HEADER: None, _VERTICAL_HEADER: "vertical"},
    )

    with pytest.raises(ValueError, match="axis"):
        list(iter_xjtu(raw, metadata))


def test_xjtu_adapter_skips_only_explicit_source_document_entries(tmp_path) -> None:
    raw, metadata = _fixture(tmp_path)

    windows = list(iter_xjtu(raw, metadata))

    assert len(windows) == 2
    assert all(window.source_relative_path.endswith(".csv") for window in windows)


def test_xjtu_adapter_rejects_unknown_file_kind_before_signal_fields(tmp_path) -> None:
    raw, metadata = _fixture(tmp_path)
    metadata.payload["files"]["Introduction_to_XJTU-SY_Bearing_Dataset.pdf"][
        "kind"
    ] = "mystery"

    with pytest.raises(ValueError, match="unknown kind"):
        list(iter_xjtu(raw, metadata))


def test_xjtu_adapter_rejects_window_length_that_differs_from_metadata(tmp_path) -> None:
    raw, metadata = _fixture(tmp_path)
    metadata.payload["samplesPerWindow"] = 3

    with pytest.raises(ValueError, match="samplesPerWindow|row count"):
        list(iter_xjtu(raw, metadata))


def test_xjtu_adapter_rejects_duplicate_global_window_identity(tmp_path) -> None:
    raw, metadata = _fixture(tmp_path)
    files = metadata.payload["files"]
    first = files["misleading/normal/2.csv"]
    second = files["misleading/outer_race/10.csv"]
    second["runId"] = first["runId"]
    second["sequenceIndex"] = first["sequenceIndex"]

    with pytest.raises(ValueError, match="duplicate.*runId.*bearingId.*sequenceIndex"):
        list(iter_xjtu(raw, metadata))
