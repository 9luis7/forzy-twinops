from __future__ import annotations

import hashlib
import json

import numpy as np
import pytest

from twinops.research.datasets.xjtu import iter_xjtu
from twinops.research.downloads import verify_archive


def _write_metadata(root) -> None:
    (root / "metadata.json").write_text(
        json.dumps(
            {
                "samplingHz": 25_600,
                "accelerationUnit": "g",
                "bearings": {
                    "Bearing1_1": {
                        "faultLabel": "outer_race",
                        "rpm": 2_100,
                        "load": 12,
                    }
                },
            }
        ),
        encoding="utf-8",
    )


def test_xjtu_adapter_uses_metadata_and_natural_chronology(tmp_path) -> None:
    _write_metadata(tmp_path)
    bearing = tmp_path / "35Hz12kN" / "Bearing1_1"
    bearing.mkdir(parents=True)
    (bearing / "10.csv").write_text("Horizontal,Vertical\n10,20\n11,21\n", encoding="utf-8")
    (bearing / "2.csv").write_text("Horizontal,Vertical\n2,4\n3,5\n", encoding="utf-8")

    windows = list(iter_xjtu(tmp_path))

    assert [window.run_id for window in windows] == ["2", "10"]
    assert all(window.dataset_id == "xjtu-sy" for window in windows)
    assert all(window.bearing_id == "Bearing1_1" for window in windows)
    assert all(window.sampling_hz == 25_600 for window in windows)
    assert all(window.fault_label == "outer_race" for window in windows)
    assert windows[0].rpm == 2_100
    assert windows[0].load == 12
    np.testing.assert_allclose(windows[0].acceleration["horizontal"], [2, 3])
    np.testing.assert_allclose(windows[0].acceleration["vertical"], [4, 5])


def test_xjtu_adapter_never_guesses_label_from_filename(tmp_path) -> None:
    (tmp_path / "metadata.json").write_text(
        json.dumps({"samplingHz": 25_600, "bearings": {}}), encoding="utf-8"
    )
    bearing = tmp_path / "outer_race" / "Bearing1_1"
    bearing.mkdir(parents=True)
    (bearing / "1.csv").write_text("Horizontal,Vertical\n1,2\n", encoding="utf-8")

    with pytest.raises(ValueError, match="metadata"):
        list(iter_xjtu(tmp_path))


def test_verify_archive_returns_digest_and_rejects_mismatch(tmp_path) -> None:
    archive = tmp_path / "dataset.zip"
    archive.write_bytes(b"official-source-bytes")
    expected = hashlib.sha256(b"official-source-bytes").hexdigest()

    assert verify_archive(archive, expected) == expected
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        verify_archive(archive, "0" * 64)
