from __future__ import annotations

import hashlib
import json
import stat
import zipfile

import pytest

from twinops.research.downloads import inspect_archive, safe_extract_archive, verify_archive
from twinops.research.metadata import load_metadata


def _zip(path, members: dict[str, bytes]) -> str:
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in members.items():
            archive.writestr(name, content)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_safe_archive_extraction_produces_hashed_inventory(tmp_path) -> None:
    archive = tmp_path / "dataset.zip"
    expected = _zip(archive, {"bearing/a.csv": b"x,y\n1,2\n", "bearing/b.csv": b"3,4\n"})

    assert verify_archive(archive, expected) == expected
    inspected = inspect_archive(archive)
    extracted = safe_extract_archive(archive, tmp_path / "raw")

    assert inspected.inventory_sha256 == extracted.inventory_sha256
    assert [item.relative_path for item in extracted.files] == ["bearing/a.csv", "bearing/b.csv"]
    assert all(len(item.sha256) == 64 for item in extracted.files)
    assert (tmp_path / "raw" / "bearing" / "a.csv").read_bytes() == b"x,y\n1,2\n"


def test_safe_archive_extraction_rechecks_expected_archive_hash_before_writing(tmp_path) -> None:
    archive = tmp_path / "dataset.zip"
    _zip(archive, {"bearing/a.csv": b"x,y\n1,2\n"})
    destination = tmp_path / "raw"

    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        safe_extract_archive(archive, destination, expected_sha256="0" * 64)

    assert not destination.exists()


@pytest.mark.parametrize(
    "member",
    ["../escape.csv", "/absolute.csv", "C:/drive.csv", "safe.csv:stream"],
)
def test_archive_rejects_traversal_and_absolute_paths(tmp_path, member) -> None:
    archive = tmp_path / "bad.zip"
    _zip(archive, {member: b"bad"})

    with pytest.raises(ValueError, match="unsafe archive member"):
        inspect_archive(archive)


def test_archive_rejects_symlink_collision_and_nonempty_destination(tmp_path) -> None:
    symlink_archive = tmp_path / "symlink.zip"
    with zipfile.ZipFile(symlink_archive, "w") as archive:
        info = zipfile.ZipInfo("link")
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(info, "target")
    with pytest.raises(ValueError, match="symlink"):
        inspect_archive(symlink_archive)

    collision_archive = tmp_path / "collision.zip"
    _zip(collision_archive, {"A.csv": b"1", "a.csv": b"2"})
    with pytest.raises(ValueError, match="collision"):
        inspect_archive(collision_archive)

    parent_collision = tmp_path / "parent-collision.zip"
    _zip(parent_collision, {"node/child.csv": b"1", "node": b"2"})
    with pytest.raises(ValueError, match="collision"):
        inspect_archive(parent_collision)

    safe_archive = tmp_path / "safe.zip"
    _zip(safe_archive, {"a.csv": b"1"})
    destination = tmp_path / "raw"
    destination.mkdir()
    (destination / "existing").write_text("do not overwrite", encoding="utf-8")
    with pytest.raises(ValueError, match="empty"):
        safe_extract_archive(safe_archive, destination)


def test_metadata_schema_hash_and_raw_inventory_are_bound(tmp_path) -> None:
    archive = tmp_path / "dataset.zip"
    _zip(archive, {"bearing/a.csv": b"Signal\n1\n"})
    inventory = safe_extract_archive(archive, tmp_path / "raw")
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "datasetId": "xjtu-sy",
                "metadataId": "fixture-xjtu-v1",
                "samplingHz": 25_600,
                "accelerationUnit": "g",
                "files": {
                    "bearing/a.csv": {
                        "bearingId": "b1",
                        "runId": "r1",
                        "sequenceIndex": 0,
                        "startedAt": None,
                        "timestampQuality": "unavailable",
                        "windowStateLabel": "normal",
                        "terminalFailureMode": None,
                        "columns": {"Signal": "radial"},
                        "hasHeader": True,
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    expected_hash = hashlib.sha256(metadata_path.read_bytes()).hexdigest()

    loaded = load_metadata(
        metadata_path,
        expected_sha256=expected_hash,
        dataset_id="xjtu-sy",
        raw_inventory=inventory,
    )

    assert loaded.metadata_sha256 == expected_hash
    assert loaded.metadata_id == "fixture-xjtu-v1"

    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    payload["files"] = {}
    metadata_path.write_text(json.dumps(payload), encoding="utf-8")
    changed_hash = hashlib.sha256(metadata_path.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="raw inventory"):
        load_metadata(
            metadata_path,
            expected_sha256=changed_hash,
            dataset_id="xjtu-sy",
            raw_inventory=inventory,
        )
