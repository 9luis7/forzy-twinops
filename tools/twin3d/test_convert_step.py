import hashlib
import json
from pathlib import Path

import cadquery as cq

from convert_step import convert_step


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
