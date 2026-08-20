from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import cadquery as cq


ASSET_ID = "forzy-motor-01"
MODEL_URL_PREFIX = "/models"
CONVERTER_VERSION = "1.0.0"
UNSAFE_NAME_SEPARATOR = re.compile(r"[\s/\\.\[\]:\x00-\x1f]+")
STEP_ENTITY = re.compile(r"(?m)^#(?P<id>\d+)\s*=\s*(?P<type>[A-Z_]+)\s*\((?P<body>[^;]*)\);\s*$")
STEP_STRING = re.compile(r"^\s*'((?:''|[^'])*)'")


@dataclass(frozen=True)
class NodeMapping:
    source_name: str
    node_name: str


@dataclass(frozen=True)
class Bounds:
    minimum: tuple[float, float, float]
    maximum: tuple[float, float, float]


@dataclass(frozen=True)
class ConversionReport:
    source_sha256: str
    glb_sha256: str
    glb_bytes: int
    solid_count: int
    node_names: tuple[str, ...]
    node_mappings: tuple[NodeMapping, ...]
    bounds: Bounds

    def to_json_dict(self) -> dict[str, object]:
        return {
            "sourceSha256": self.source_sha256,
            "glbSha256": self.glb_sha256,
            "glbBytes": self.glb_bytes,
            "solidCount": self.solid_count,
            "nodes": list(self.node_names),
            "nodeMappings": [
                {"sourceName": mapping.source_name, "nodeName": mapping.node_name}
                for mapping in self.node_mappings
            ],
            "bounds": {
                "min": list(self.bounds.minimum),
                "max": list(self.bounds.maximum),
            },
        }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalise_name(name: str) -> str:
    normalised = UNSAFE_NAME_SEPARATOR.sub("_", name)
    if not normalised:
        raise ValueError("STEP solid name is empty after removing unsafe separators")
    return normalised


def _step_entities(text: str) -> dict[str, tuple[str, str]]:
    return {
        match.group("id"): (match.group("type"), match.group("body"))
        for match in STEP_ENTITY.finditer(text)
    }


def _first_step_string(body: str) -> str | None:
    match = STEP_STRING.match(body)
    return match.group(1).replace("''", "'") if match else None


def _entity_references(body: str) -> list[str]:
    return re.findall(r"#(\d+)", body)


def _product_name_for_definition(
    product_definition_id: str,
    entities: dict[str, tuple[str, str]],
) -> str | None:
    definition = entities.get(product_definition_id)
    if not definition or definition[0] != "PRODUCT_DEFINITION":
        return None
    definition_refs = _entity_references(definition[1])
    if not definition_refs:
        return None
    formation = entities.get(definition_refs[0])
    if not formation or not formation[0].startswith("PRODUCT_DEFINITION_FORMATION"):
        return None
    formation_refs = _entity_references(formation[1])
    if not formation_refs:
        return None
    product = entities.get(formation_refs[-1])
    if not product or product[0] != "PRODUCT":
        return None
    return _first_step_string(product[1])


def _prepare_step_for_cadquery(source: Path, destination: Path) -> tuple[NodeMapping, ...]:
    """Fill blank occurrence names and make duplicate names safe for CadQuery.

    Some valid STEP exporters leave NEXT_ASSEMBLY_USAGE_OCCURRENCE names blank.
    CadQuery 2.8 cannot address those children after import. The source file remains
    untouched: this deterministic working copy borrows each referenced PRODUCT name,
    removes only separators unsafe for glTF/Three.js lookup, and suffixes
    repeated identities.
    """

    text = source.read_text(encoding="utf-8")
    entities = _step_entities(text)
    used_names: dict[str, int] = {}
    mappings: list[NodeMapping] = []

    occurrence_pattern = re.compile(
        r"(?m)^(#(?P<id>\d+)\s*=\s*NEXT_ASSEMBLY_USAGE_OCCURRENCE\s*\()"
        r"(?P<body>[^;]*)(\);\s*)$"
    )

    def replace_occurrence(match: re.Match[str]) -> str:
        body = match.group("body")
        references = _entity_references(body)
        if len(references) < 2:
            raise ValueError(f"STEP occurrence #{match.group('id')} has no child definition")
        source_name = _product_name_for_definition(references[-1], entities)
        if source_name is None:
            source_name = _first_step_string(body)
        if source_name is None or source_name == "":
            raise ValueError(f"STEP occurrence #{match.group('id')} has no traceable product name")

        base_name = _normalise_name(source_name)
        ordinal = used_names.get(base_name, 0) + 1
        used_names[base_name] = ordinal
        node_name = base_name if ordinal == 1 else f"{base_name}__{ordinal:02d}"
        mappings.append(NodeMapping(source_name=source_name, node_name=node_name))

        escaped = node_name.replace("'", "''")
        rewritten = re.sub(
            r"^\s*'(?:''|[^'])*'\s*,\s*'(?:''|[^'])*'\s*,\s*'(?:''|[^'])*'",
            f"'{escaped}', '{escaped}', ''",
            body,
            count=1,
        )
        if rewritten == body:
            raise ValueError(f"STEP occurrence #{match.group('id')} has unsupported name fields")
        return f"{match.group(1)}{rewritten}{match.group(4)}"

    prepared = occurrence_pattern.sub(replace_occurrence, text)
    if not mappings:
        raise ValueError("STEP file contains no assembly occurrences")
    destination.write_text(prepared, encoding="utf-8", newline="")
    return tuple(mappings)


def _leaf_nodes(assembly: cq.Assembly) -> list[cq.Assembly]:
    leaves: list[cq.Assembly] = []

    def visit(node: cq.Assembly) -> None:
        if node.obj is not None:
            leaves.append(node)
        for child in node.children:
            visit(child)

    visit(assembly)
    return leaves


def _world_location(node: cq.Assembly) -> cq.Location:
    location = node.loc
    parent = node.parent
    while parent is not None:
        location = parent.loc * location
        parent = parent.parent
    return location


def _metre_assembly(assembly: cq.Assembly, leaves: Iterable[cq.Assembly]) -> cq.Assembly:
    output = cq.Assembly(name=ASSET_ID)
    for leaf in leaves:
        solids = leaf.obj.Solids()
        if len(solids) != 1:
            raise ValueError(f"STEP node {leaf.name} does not contain exactly one solid")
        world_solid = solids[0].moved(_world_location(leaf))
        output.add(world_solid.scale(0.001), name=leaf.name, color=leaf.color)
    return output


def _assembly_bounds_m(assembly: cq.Assembly) -> Bounds:
    bounding_box = assembly.toCompound().BoundingBox()
    # CadQuery exports glTF as metres and rotates its native Z-up coordinates
    # -90 degrees around X: (x, y, z) -> (x, z, -y).
    corners = (
        (x, z, -y)
        for x in (bounding_box.xmin, bounding_box.xmax)
        for y in (bounding_box.ymin, bounding_box.ymax)
        for z in (bounding_box.zmin, bounding_box.zmax)
    )
    points = list(corners)
    minimum = tuple(min(point[index] for point in points) for index in range(3))
    maximum = tuple(max(point[index] for point in points) for index in range(3))
    if not all(math.isfinite(value) for value in (*minimum, *maximum)):
        raise ValueError("STEP model has non-finite bounds")
    return Bounds(minimum=minimum, maximum=maximum)


def _groups(node_names: Iterable[str]) -> dict[str, dict[str, list[str]]]:
    groups: dict[str, dict[str, list[str]]] = {
        "motor": {"nodeNames": []},
        "pump": {"nodeNames": []},
        "base": {"nodeNames": []},
        "coupling": {"nodeNames": []},
    }
    for node_name in node_names:
        upper = node_name.upper()
        if "ME22A" in upper:
            group = "motor"
        elif "BOMBA" in upper:
            group = "pump"
        elif re.search(r"B01A[_-]BASE(?:[_-]|$)", upper):
            group = "base"
        elif re.search(r"B01A[_-][ABC](?:__\d+)?$", upper):
            group = "coupling"
        else:
            raise ValueError(f"STEP node has no evidence-backed group: {node_name}")
        groups[group]["nodeNames"].append(node_name)
    return groups


def _manifest(glb: Path, source_hash: str, node_names: tuple[str, ...]) -> dict[str, object]:
    return {
        "schemaVersion": "1.0",
        "assetId": ASSET_ID,
        "modelUrl": f"{MODEL_URL_PREFIX}/{glb.name}",
        "sourceSha256": source_hash,
        "generatedBy": {
            "tool": "tools/twin3d/convert_step.py",
            "version": CONVERTER_VERSION,
            "cadqueryVersion": cq.__version__,
        },
        "solidCount": len(node_names),
        "units": "m",
        "upAxis": "Y",
        "nodes": list(node_names),
        "groups": _groups(node_names),
        "sensors": [
            {"sensorId": "s1", "placement": "unvalidated"},
            {"sensorId": "s2", "placement": "unvalidated"},
        ],
    }


def convert_step(source: Path, glb: Path, manifest: Path) -> ConversionReport:
    source = Path(source).resolve(strict=True)
    glb = Path(glb)
    manifest = Path(manifest)
    source_hash = _sha256(source)

    glb.parent.mkdir(parents=True, exist_ok=True)
    manifest.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="twin3d-") as temporary_directory:
        prepared_step = Path(temporary_directory) / "prepared.step"
        mappings = _prepare_step_for_cadquery(source, prepared_step)
        assembly = cq.Assembly.load(str(prepared_step), importType="STEP", unit="MM")

    leaves = _leaf_nodes(assembly)
    solid_count = sum(len(leaf.obj.Solids()) for leaf in leaves)
    node_names = tuple(leaf.name for leaf in leaves)
    if solid_count != len(mappings) or len(leaves) != len(mappings):
        raise ValueError(
            "CadQuery did not preserve one traceable node per STEP solid: "
            f"source={len(mappings)}, leaves={len(leaves)}, solids={solid_count}"
        )
    if node_names != tuple(mapping.node_name for mapping in mappings):
        raise ValueError("CadQuery changed prepared STEP node names")

    metre_assembly = _metre_assembly(assembly, leaves)

    temporary_glb = glb.with_suffix(f"{glb.suffix}.tmp")
    if not metre_assembly.save(
        str(temporary_glb),
        exportType="GLTF",
        tolerance=0.1,
        angularTolerance=0.1,
        binary=True,
    ):
        raise RuntimeError("CadQuery/OpenCascade failed to export GLB")
    if temporary_glb.read_bytes()[:4] != b"glTF":
        raise RuntimeError("CadQuery output is not a binary glTF file")
    temporary_glb.replace(glb)

    manifest_value = _manifest(glb, source_hash, node_names)
    manifest.write_text(
        json.dumps(manifest_value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    return ConversionReport(
        source_sha256=f"sha256:{source_hash}",
        glb_sha256=f"sha256:{_sha256(glb)}",
        glb_bytes=glb.stat().st_size,
        solid_count=solid_count,
        node_names=node_names,
        node_mappings=mappings,
        bounds=_assembly_bounds_m(metre_assembly),
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert a named STEP assembly to a traceable GLB")
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--glb", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--report", type=Path)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    report = convert_step(args.source, args.glb, args.manifest)
    report_value = report.to_json_dict()
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(report_value, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    print(json.dumps(report_value, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
