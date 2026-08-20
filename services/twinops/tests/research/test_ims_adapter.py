from __future__ import annotations

import json
from datetime import datetime, timezone

import numpy as np
import pytest

from twinops.research.datasets.ims import iter_ims


def _write_metadata(root) -> None:
    (root / "metadata.json").write_text(
        json.dumps(
            {
                "samplingHz": 20_000,
                "accelerationUnit": "g",
                "tests": {
                    "1st_test": {
                        "channels": [
                            {"bearingId": "test-1-bearing-1", "axis": "x"},
                            {"bearingId": "test-1-bearing-1", "axis": "y"},
                            {"bearingId": "test-1-bearing-2", "axis": "x"},
                            {"bearingId": "test-1-bearing-2", "axis": "y"},
                        ],
                        "faultLabels": {
                            "test-1-bearing-1": "inner_race",
                            "test-1-bearing-2": "normal",
                        },
                    }
                },
            }
        ),
        encoding="utf-8",
    )


def test_ims_adapter_uses_channel_map_and_timestamp_order(tmp_path) -> None:
    _write_metadata(tmp_path)
    test_dir = tmp_path / "1st_test"
    test_dir.mkdir()
    (test_dir / "2003.10.22.12.10.00").write_text("10 11 20 21\n12 13 22 23\n", encoding="utf-8")
    (test_dir / "2003.10.22.12.00.00").write_text("1 2 3 4\n5 6 7 8\n", encoding="utf-8")

    windows = list(iter_ims(tmp_path))

    assert [(window.run_id, window.bearing_id) for window in windows] == [
        ("2003.10.22.12.00.00", "test-1-bearing-1"),
        ("2003.10.22.12.00.00", "test-1-bearing-2"),
        ("2003.10.22.12.10.00", "test-1-bearing-1"),
        ("2003.10.22.12.10.00", "test-1-bearing-2"),
    ]
    first = windows[0]
    assert first.dataset_id == "nasa-ims"
    assert first.sampling_hz == 20_000
    assert first.fault_label == "inner_race"
    assert first.started_at == datetime(2003, 10, 22, 12, tzinfo=timezone.utc)
    np.testing.assert_allclose(first.acceleration["x"], [1, 5])
    np.testing.assert_allclose(first.acceleration["y"], [2, 6])


def test_ims_adapter_rejects_unmapped_or_malformed_channels(tmp_path) -> None:
    _write_metadata(tmp_path)
    test_dir = tmp_path / "1st_test"
    test_dir.mkdir()
    (test_dir / "2003.10.22.12.00.00").write_text("1 2 3\n", encoding="utf-8")

    with pytest.raises(ValueError, match="channel"):
        list(iter_ims(tmp_path))

    metadata = json.loads((tmp_path / "metadata.json").read_text(encoding="utf-8"))
    del metadata["tests"]["1st_test"]["faultLabels"]["test-1-bearing-1"]
    (tmp_path / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    (test_dir / "2003.10.22.12.00.00").write_text("1 2 3 4\n", encoding="utf-8")

    with pytest.raises(ValueError, match="fault label metadata"):
        list(iter_ims(tmp_path))
