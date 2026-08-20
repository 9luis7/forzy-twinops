import hashlib
import json
from pathlib import Path
import struct

import cadquery as cq

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
