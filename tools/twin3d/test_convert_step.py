import hashlib
import json
from pathlib import Path
import struct
import threading
import time

import cadquery as cq
import pytest

import convert_step as converter
from convert_step import convert_step


def glb_position_extents(glb: Path) -> tuple[float, float]:
    binary = glb.read_bytes()
    json_length, json_type = struct.unpack_from("<II", binary, 12)
    assert json_type == 0x4E4F534A
    document = json.loads(binary[20 : 20 + json_length].decode("utf-8"))
    accessors = [
        document["accessors"][primitive["attributes"]["POSITION"]]
        for mesh in document["meshes"]
        for primitive in mesh["primitives"]
    ]
    return (
        min(min(accessor["min"]) for accessor in accessors),
        max(max(accessor["max"]) for accessor in accessors),
    )


def write_two_body_step(tmp_path: Path, names: tuple[str, str]) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    source = tmp_path / "named-solids.step"
    assembly = cq.Assembly(name="synthetic")
    assembly.add(cq.Workplane("XY").box(20, 10, 8), name=names[0])
    assembly.add(
        cq.Workplane("XY").box(8, 8, 12),
        name=names[1],
        loc=cq.Location(cq.Vector(30, 0, 0)),
    )
    assembly.save(str(source), exportType="STEP")
    return source


def test_conversion_preserves_named_solids_and_source_hash(tmp_path):
    source = write_two_body_step(tmp_path, names=("ME22A_001", "BOMBA_008"))
    glb = tmp_path / "out.glb"
    manifest_path = tmp_path / "out.json"

    report = convert_step(source, glb, manifest_path)

    assert report.solid_count == 2
    assert report.node_names == ("ME22A_001", "BOMBA_008")
    assert report.source_sha256.startswith("sha256:")
    assert report.source_sha256 == f"sha256:{hashlib.sha256(source.read_bytes()).hexdigest()}"
    assert glb.read_bytes()[:4] == b"glTF"
    position_min, position_max = glb_position_extents(glb)
    assert -0.1 < position_min < position_max < 0.1

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["sourceSha256"] == report.source_sha256.removeprefix("sha256:")
    assert manifest["solidCount"] == 2
    assert manifest["nodes"] == ["ME22A_001", "BOMBA_008"]
    assert manifest["units"] == "m"
    assert manifest["upAxis"] == "Y"
    assert manifest["sensors"] == [
        {"sensorId": "s1", "placement": "unvalidated"},
        {"sensorId": "s2", "placement": "unvalidated"},
    ]


def test_conversion_normalises_threejs_unsafe_node_separators(tmp_path):
    source = write_two_body_step(
        tmp_path,
        names=("R11.06-ME22A/001", "R11.06-BOMBA/008"),
    )

    report = convert_step(source, tmp_path / "out.glb", tmp_path / "out.json")

    assert report.node_names == (
        "R11_06-ME22A_001",
        "R11_06-BOMBA_008",
    )


def test_conversion_publishes_manifest_and_report_for_the_same_glb(tmp_path):
    source = write_two_body_step(tmp_path, names=("ME22A_001", "BOMBA_008"))
    glb = tmp_path / "published" / "out.glb"
    manifest_path = tmp_path / "published" / "out.json"
    report_path = tmp_path / "audit" / "report.json"

    report = convert_step(source, glb, manifest_path, report_path)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    persisted_report = json.loads(report_path.read_text(encoding="utf-8"))
    assert persisted_report == report.to_json_dict()
    assert manifest["sourceSha256"] == persisted_report["sourceSha256"].removeprefix("sha256:")
    assert persisted_report["glbSha256"] == f"sha256:{hashlib.sha256(glb.read_bytes()).hexdigest()}"
    assert not glb.with_suffix(".glb.tmp").exists()


def test_conversion_rolls_back_the_whole_output_set_when_publication_fails(tmp_path, monkeypatch):
    original_source = write_two_body_step(tmp_path / "original", names=("ME22A_001", "BOMBA_008"))
    replacement_source = write_two_body_step(tmp_path / "replacement", names=("ME22A_002", "BOMBA_009"))
    glb = tmp_path / "published" / "out.glb"
    manifest_path = tmp_path / "published" / "out.json"
    report_path = tmp_path / "audit" / "report.json"
    convert_step(original_source, glb, manifest_path, report_path)
    original_outputs = {
        path: path.read_bytes()
        for path in (glb, manifest_path, report_path)
    }

    actual_replace = converter._replace_file
    replace_calls = 0

    def fail_second_publication(source, target):
        nonlocal replace_calls
        replace_calls += 1
        if replace_calls == 2:
            raise OSError("injected publication failure")
        actual_replace(source, target)

    monkeypatch.setattr(converter, "_replace_file", fail_second_publication)

    with pytest.raises(OSError, match="injected publication failure"):
        converter.convert_step(replacement_source, glb, manifest_path, report_path)

    assert {path: path.read_bytes() for path in original_outputs} == original_outputs
    assert not manifest_path.with_suffix(f"{manifest_path.suffix}.publish.lock").exists()
    assert not list(glb.parent.glob(".twin3d-stage-*"))
    assert not list(report_path.parent.glob(".twin3d-stage-*"))


def test_publication_lock_serialises_concurrent_output_sets(tmp_path, monkeypatch):
    targets = [tmp_path / "model.glb", tmp_path / "report.json", tmp_path / "manifest.json"]
    events: list[str] = []
    actual_replace = converter._replace_file

    def observed_replace(source, target):
        marker = source.read_text(encoding="utf-8")
        events.append(marker)
        time.sleep(0.02)
        actual_replace(source, target)

    monkeypatch.setattr(converter, "_replace_file", observed_replace)
    barrier = threading.Barrier(2)
    errors: list[Exception] = []

    def publish(marker: str):
        try:
            stage = tmp_path / f"stage-{marker}"
            stage.mkdir()
            publications = []
            for target in targets:
                staged = stage / target.name
                staged.write_text(marker, encoding="utf-8")
                publications.append((staged, target))
            barrier.wait()
            converter._publish_output_set(publications, targets[-1])
        except Exception as error:  # pragma: no cover - asserted below
            errors.append(error)

    threads = [threading.Thread(target=publish, args=(marker,)) for marker in ("A", "B")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert events in (["A", "A", "A", "B", "B", "B"], ["B", "B", "B", "A", "A", "A"])
    assert len({target.read_text(encoding="utf-8") for target in targets}) == 1
