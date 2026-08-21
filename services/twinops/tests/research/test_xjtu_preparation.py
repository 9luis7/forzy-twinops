from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

from twinops.research.downloads import ArchivePart, RarExtractionLimits, RawFile, RawInventory
from twinops.research.datasets import xjtu_preparation
from twinops.research.datasets.xjtu import iter_xjtu
from twinops.research.datasets.xjtu_preparation import (
    XjtuSyPreparationConfig,
    XjtuSyPreparationResult,
    prepare_xjtu_sy,
)
from twinops.research.metadata import load_metadata


_OFFICIAL_PARTS = (
    (
        "XJTU-SY_Bearing_Datasets.part01.rar",
        744_488_960,
        "c500657353f089a4ab50212ff4ddfc7b982729e92e2b127440c8ad881d80b968",
    ),
    (
        "XJTU-SY_Bearing_Datasets.part02.rar",
        744_488_960,
        "4dfa6286a8e9c7cec1e925b347642349f36e27ab3f703c90d1d08977b7b4f61f",
    ),
    (
        "XJTU-SY_Bearing_Datasets.part03.rar",
        744_488_960,
        "6929f531284f79e0209246b4ee23b23dd8d4faac1c0c3ff8fb131cda4a18bd3a",
    ),
    (
        "XJTU-SY_Bearing_Datasets.part04.rar",
        744_488_960,
        "2245825acd29bed3b95e7a77879a3fbadf20f4ad4f99486384c714174621597d",
    ),
    (
        "XJTU-SY_Bearing_Datasets.part05.rar",
        744_488_960,
        "e1b0a41a32b865e48ea7981c56f952a960d94335f3496b72eb4a65932f1671bd",
    ),
    (
        "XJTU-SY_Bearing_Datasets.part06.rar",
        722_155_640,
        "df1854821a9d481104476379f7bc045ea1e101427c6e36145cd7677dc7c4a684",
    ),
)


def _config(tmp_path: Path, **changes) -> XjtuSyPreparationConfig:
    tmp_path.mkdir(parents=True, exist_ok=True)
    archives = []
    for name, _, digest in _OFFICIAL_PARTS:
        path = tmp_path / name
        path.write_bytes(name.encode("ascii"))
        archives.append(ArchivePart(path.resolve(), digest))
    executable = tmp_path / "7z.exe"
    executable.write_bytes(b"trusted test executable")
    values = {
        "archive_parts": tuple(archives),
        "seven_zip_executable": executable.resolve(),
        "destination_root": (tmp_path / "prepared").resolve(),
    }
    values.update(changes)
    return XjtuSyPreparationConfig(**values)


def test_config_binds_six_ordered_official_parts_and_task_limits(tmp_path) -> None:
    config = _config(tmp_path)

    assert tuple(part.path.name for part in config.archive_parts) == tuple(
        item[0] for item in _OFFICIAL_PARTS
    )
    assert tuple(part.sha256 for part in config.archive_parts) == tuple(
        item[2] for item in _OFFICIAL_PARTS
    )
    assert config.extraction_limits == RarExtractionLimits(
        max_total_uncompressed_bytes=64 * 1024**3
    )
    assert config.destination_root.is_absolute()
    assert config.seven_zip_executable.is_absolute()


@pytest.mark.parametrize("mutation", ["order", "name", "hash", "duplicate"])
def test_config_rejects_any_nonofficial_part_binding(tmp_path, mutation) -> None:
    base = _config(tmp_path)
    parts = list(base.archive_parts)
    if mutation == "order":
        parts[0], parts[1] = parts[1], parts[0]
    elif mutation == "name":
        parts[0] = ArchivePart((tmp_path / "renamed.part01.rar").resolve(), parts[0].sha256)
    elif mutation == "hash":
        parts[0] = ArchivePart(parts[0].path, "0" * 64)
    else:
        parts[1] = ArchivePart(parts[0].path, parts[1].sha256)

    with pytest.raises(ValueError, match="official|distinct"):
        _config(tmp_path, archive_parts=tuple(parts))


@pytest.mark.parametrize("field", ["destination_root", "seven_zip_executable"])
def test_config_rejects_relative_output_or_executable_paths(tmp_path, field) -> None:
    with pytest.raises(ValueError, match="absolute"):
        _config(tmp_path, **{field: Path("relative")})


def test_config_rejects_relative_archive_path(tmp_path) -> None:
    base = _config(tmp_path)
    parts = list(base.archive_parts)
    parts[0] = ArchivePart(Path(parts[0].path.name), parts[0].sha256)

    with pytest.raises(ValueError, match="absolute"):
        _config(tmp_path, archive_parts=tuple(parts))


def test_config_attests_the_exact_trusted_executable_bytes(tmp_path) -> None:
    config = _config(tmp_path)

    assert config._seven_zip_attestation.sha256 == hashlib.sha256(
        b"trusted test executable"
    ).hexdigest()


@pytest.mark.parametrize("unsafe_part", ["executable", "ancestor"])
def test_config_rejects_reparse_executable_or_ancestor(
    tmp_path, monkeypatch, unsafe_part
) -> None:
    trusted_bin = tmp_path / "trusted-bin"
    trusted_bin.mkdir()
    executable = trusted_bin / "7z.exe"
    executable.write_bytes(b"trusted test executable")
    unsafe_path = executable if unsafe_part == "executable" else trusted_bin
    metadata = unsafe_path.lstat()
    real_lstat = Path.lstat

    def reparse_lstat(path):
        if path != unsafe_path:
            return real_lstat(path)
        return SimpleNamespace(
            st_mode=metadata.st_mode,
            st_dev=metadata.st_dev,
            st_ino=metadata.st_ino,
            st_size=metadata.st_size,
            st_ctime_ns=metadata.st_ctime_ns,
            st_mtime_ns=metadata.st_mtime_ns,
            st_file_attributes=(
                getattr(metadata, "st_file_attributes", 0)
                | getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
            ),
            st_reparse_tag=getattr(metadata, "st_reparse_tag", 0),
        )

    monkeypatch.setattr(Path, "lstat", reparse_lstat)

    with pytest.raises(ValueError, match="regular"):
        _config(tmp_path, seven_zip_executable=executable.resolve())


def test_prepare_rejects_executable_content_changed_since_config(
    tmp_path, monkeypatch
) -> None:
    config = _config(tmp_path)
    _install_small_source(monkeypatch, config)
    config.seven_zip_executable.write_bytes(b"substitute executable")

    with pytest.raises(ValueError, match="executable changed"):
        prepare_xjtu_sy(config)

    assert not config.destination_root.exists()


@pytest.mark.parametrize("changed_part", ["file", "parent"])
def test_prepare_rejects_same_bytes_replacement_of_executable_or_parent(
    tmp_path, monkeypatch, changed_part
) -> None:
    trusted_bin = tmp_path / "trusted-bin"
    trusted_bin.mkdir()
    executable = trusted_bin / "7z.exe"
    executable.write_bytes(b"trusted test executable")
    config = _config(tmp_path, seven_zip_executable=executable.resolve())
    _install_small_source(monkeypatch, config)
    if changed_part == "file":
        executable.rename(trusted_bin / "retired-7z.exe")
        executable.write_bytes(b"trusted test executable")
    else:
        trusted_bin.rename(tmp_path / "retired-bin")
        trusted_bin.mkdir()
        executable.write_bytes(b"trusted test executable")

    with pytest.raises(ValueError, match="executable changed"):
        prepare_xjtu_sy(config)

    assert not config.destination_root.exists()


def _small_bearing_specs():
    return (
        SimpleNamespace(
            condition_index=1,
            bearing_index=1,
            condition_directory="35Hz12kN",
            bearing_directory="Bearing1_1",
            file_count=2,
            rpm=2_100,
            load_kn=12,
            terminal_components=("outer_race",),
        ),
        SimpleNamespace(
            condition_index=2,
            bearing_index=1,
            condition_directory="37.5Hz11kN",
            bearing_directory="Bearing2_1",
            file_count=1,
            rpm=2_250,
            load_kn=11,
            terminal_components=("inner_race",),
        ),
        SimpleNamespace(
            condition_index=3,
            bearing_index=2,
            condition_directory="40Hz10kN",
            bearing_directory="Bearing3_2",
            file_count=2,
            rpm=2_400,
            load_kn=10,
            terminal_components=("inner_race", "rolling_element", "cage", "outer_race"),
        ),
    )


def _csv_path(spec, sequence: int) -> str:
    return (
        "XJTU-SY_Bearing_Datasets/"
        f"{spec.condition_directory}/{spec.bearing_directory}/{sequence}.csv"
    )


def _numeric_csv(*, rows: int = 2, columns: int = 2) -> bytes:
    row = ",".join(str(index + 1) for index in range(columns))
    return ((row + "\n") * rows).encode("ascii")


def _inventory(root: Path, contents: dict[str, bytes]) -> RawInventory:
    files = []
    for relative_path, content in sorted(contents.items()):
        target = root.joinpath(*relative_path.split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        files.append(
            RawFile(
                relative_path=relative_path,
                size_bytes=len(content),
                sha256=hashlib.sha256(content).hexdigest(),
            )
        )
    binding = [
        {
            "relativePath": item.relative_path,
            "sizeBytes": item.size_bytes,
            "sha256": item.sha256,
        }
        for item in files
    ]
    inventory_hash = hashlib.sha256(
        json.dumps(binding, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()
    return RawInventory(
        files=tuple(files),
        inventory_sha256=inventory_hash,
        total_bytes=sum(item.size_bytes for item in files),
    )


def _small_contents(specs, *, bad_csv: bytes | None = None) -> dict[str, bytes]:
    contents = {
        "XJTU-SY_Bearing_Datasets/Introduction_to_XJTU-SY_Bearing_Dataset.pdf": (
            b"%PDF-1.4 synthetic author document"
        )
    }
    for spec in specs:
        for sequence in range(1, spec.file_count + 1):
            contents[_csv_path(spec, sequence)] = _numeric_csv()
    if bad_csv is not None:
        contents[_csv_path(specs[0], 1)] = bad_csv
    return contents


def _inspection(config, specs, contents, *, mutation: str | None = None):
    root = "XJTU-SY_Bearing_Datasets"
    directories = {root}
    for spec in specs:
        condition = f"{root}/{spec.condition_directory}"
        directories.add(condition)
        directories.add(f"{condition}/{spec.bearing_directory}")
    members = [
        SimpleNamespace(
            relative_path=path,
            size_bytes=0,
            compressed_bytes=0,
            is_directory=True,
        )
        for path in sorted(directories)
    ]
    members.extend(
        SimpleNamespace(
            relative_path=path,
            size_bytes=len(content),
            compressed_bytes=max(1, len(content) // 2),
            is_directory=False,
        )
        for path, content in sorted(contents.items())
    )
    if mutation == "extra_root":
        members[-1] = SimpleNamespace(
            relative_path="other-root/1.csv",
            size_bytes=members[-1].size_bytes,
            compressed_bytes=members[-1].compressed_bytes,
            is_directory=False,
        )
    elif mutation == "missing_sequence":
        target = _csv_path(specs[0], 2)
        for index, member in enumerate(members):
            if member.relative_path == target:
                members[index] = SimpleNamespace(
                    relative_path=_csv_path(specs[0], 3),
                    size_bytes=member.size_bytes,
                    compressed_bytes=member.compressed_bytes,
                    is_directory=False,
                )
                break
    elif mutation == "padded_sequence":
        target = _csv_path(specs[0], 1)
        for index, member in enumerate(members):
            if member.relative_path == target:
                members[index] = SimpleNamespace(
                    relative_path=target.replace("/1.csv", "/01.csv"),
                    size_bytes=member.size_bytes,
                    compressed_bytes=member.compressed_bytes,
                    is_directory=False,
                )
                break
    elif mutation == "wrong_pdf":
        for index, member in enumerate(members):
            if member.relative_path.endswith(".pdf"):
                members[index] = SimpleNamespace(
                    relative_path=f"{root}/unexpected.pdf",
                    size_bytes=member.size_bytes,
                    compressed_bytes=member.compressed_bytes,
                    is_directory=False,
                )
                break
    elif mutation == "unexpected_extension":
        target = _csv_path(specs[0], 1)
        for index, member in enumerate(members):
            if member.relative_path == target:
                members[index] = SimpleNamespace(
                    relative_path=target.removesuffix(".csv") + ".txt",
                    size_bytes=member.size_bytes,
                    compressed_bytes=member.compressed_bytes,
                    is_directory=False,
                )
                break
    total_bytes = sum(member.size_bytes for member in members if not member.is_directory)
    if mutation == "total_bytes":
        total_bytes += 1
    return SimpleNamespace(
        parts=config.archive_parts,
        members=tuple(members),
        total_bytes=total_bytes,
        total_compressed_bytes=sum(
            member.compressed_bytes for member in members if not member.is_directory
        ),
    )


def _install_small_source(
    monkeypatch,
    config,
    *,
    bad_csv: bytes | None = None,
    inspection_mutation: str | None = None,
    extraction_error: BaseException | None = None,
):
    specs = _small_bearing_specs()
    contents = _small_contents(specs, bad_csv=bad_csv)
    expected_total_bytes = sum(map(len, contents.values()))
    monkeypatch.setattr(xjtu_preparation, "_BEARING_SPECS", specs, raising=False)
    monkeypatch.setattr(xjtu_preparation, "_SAMPLES_PER_WINDOW", 2, raising=False)
    monkeypatch.setattr(
        xjtu_preparation, "_EXPECTED_TOTAL_BYTES", expected_total_bytes, raising=False
    )
    events: list[str] = []
    extract_calls = 0
    inspection_calls = 0

    def fake_inspect(parts, *, limits):
        nonlocal inspection_calls
        inspection_calls += 1
        events.append("inspect")
        assert tuple(parts) == config.archive_parts
        if inspection_calls == 1:
            assert not config.destination_root.exists()
        return _inspection(
            config, specs, contents, mutation=inspection_mutation
        )

    def fake_extract(parts, destination, *, limits, seven_zip_executable):
        nonlocal extract_calls
        extract_calls += 1
        events.append("extract")
        assert tuple(parts) == config.archive_parts
        if extraction_error is not None:
            raise extraction_error
        return _inventory(Path(destination), contents)

    monkeypatch.setattr(xjtu_preparation, "inspect_rar_archive", fake_inspect, raising=False)
    monkeypatch.setattr(
        xjtu_preparation, "safe_extract_rar_archive", fake_extract, raising=False
    )
    return specs, contents, events, lambda: extract_calls


def test_prepare_inspects_before_any_write_and_extracts_all_six_parts_once(
    tmp_path, monkeypatch
) -> None:
    config = _config(tmp_path)
    _, _, events, extraction_count = _install_small_source(monkeypatch, config)

    result = prepare_xjtu_sy(config)

    assert isinstance(result, XjtuSyPreparationResult)
    assert events == ["inspect", "extract"]
    assert extraction_count() == 1
    assert result.generation_root.is_dir()
    assert result.raw_root == result.generation_root / "raw"
    assert not list(config.destination_root.glob(".xjtu-sy-generation-*"))


@pytest.mark.parametrize(
    "mutation",
    [
        "extra_root",
        "missing_sequence",
        "padded_sequence",
        "wrong_pdf",
        "unexpected_extension",
        "total_bytes",
    ],
)
def test_archive_contract_divergence_is_rejected_before_staging(
    tmp_path, monkeypatch, mutation
) -> None:
    config = _config(tmp_path)
    _, _, events, extraction_count = _install_small_source(
        monkeypatch, config, inspection_mutation=mutation
    )

    with pytest.raises(ValueError, match="archive|member|sequence|PDF|byte|boundary"):
        prepare_xjtu_sy(config)

    assert events == ["inspect"]
    assert extraction_count() == 0
    assert not config.destination_root.exists()


def test_prepared_metadata_maps_inventory_and_keeps_scientific_unknowns(
    tmp_path, monkeypatch
) -> None:
    config = _config(tmp_path)
    specs, _, _, _ = _install_small_source(monkeypatch, config)

    result = prepare_xjtu_sy(config)
    metadata = json.loads(result.metadata_path.read_text(encoding="utf-8"))
    loaded = load_metadata(
        result.metadata_path,
        expected_sha256=result.metadata_sha256,
        dataset_id="xjtu-sy",
        raw_inventory=result.raw_inventory,
    )

    assert loaded.metadata_sha256 == result.metadata_sha256
    assert set(metadata["files"]) == {
        item.relative_path for item in result.raw_inventory.files
    }
    pdf_path = "XJTU-SY_Bearing_Datasets/Introduction_to_XJTU-SY_Bearing_Dataset.pdf"
    assert metadata["files"][pdf_path]["kind"] == "source_document"
    signal_entries = [
        entry for entry in metadata["files"].values() if entry["kind"] == "signal_window"
    ]
    assert len(signal_entries) == sum(spec.file_count for spec in specs)
    assert metadata["samplingHz"] == 25_600
    assert metadata["samplesPerWindow"] == 2
    assert metadata["accelerationUnit"] == "unknown"
    assert all(entry["columns"] == {"0": "horizontal", "1": "vertical"} for entry in signal_entries)
    assert all(entry["hasHeader"] is False for entry in signal_entries)
    assert all(entry["startedAt"] is None for entry in signal_entries)
    assert all(entry["timestampQuality"] == "unavailable" for entry in signal_entries)
    assert all(entry["windowStateLabel"] == "unknown" for entry in signal_entries)
    assert all(entry["terminalFailureMode"] is None for entry in signal_entries)
    assert all(entry["lifeFraction"] is None for entry in signal_entries)
    assert all(entry["load"] is None for entry in signal_entries)
    assert all("faultOnset" not in entry and "severity" not in entry for entry in signal_entries)
    assert metadata["conditions"][0]["radialLoad"] == {"value": 12, "unit": "kN"}
    compound = next(
        item for item in metadata["bearingEvidence"] if item["bearingId"].endswith("-3-2")
    )
    assert compound["terminalOutcome"]["components"] == [
        "inner_race",
        "rolling_element",
        "cage",
        "outer_race",
    ]
    windows = list(iter_xjtu(result.raw_root, loaded))
    triples = {
        (window.run_id, window.bearing_id, window.sequence_index) for window in windows
    }
    assert len(windows) == len(triples) == len(signal_entries)
    assert all(set(window.acceleration) == {"horizontal", "vertical"} for window in windows)
    assert all(window.acceleration_unit == "unknown" for window in windows)
    assert all(window.started_at is None for window in windows)
    assert all(window.timestamp_quality == "unavailable" for window in windows)
    assert all(window.window_state_label == "unknown" for window in windows)
    assert all(window.terminal_failure_mode is None for window in windows)
    assert all(window.life_fraction is None for window in windows)
    assert all(window.load is None for window in windows)


def test_attestation_is_path_free_and_all_metric_gates_remain_closed(
    tmp_path, monkeypatch
) -> None:
    config = _config(tmp_path)
    _install_small_source(monkeypatch, config)

    result = prepare_xjtu_sy(config)
    attestation = result.to_dict()
    serialized = json.dumps(attestation, sort_keys=True)

    assert attestation["status"] == "prepared_semantically_gated"
    assert attestation["source"]["volumeCount"] == 6
    assert attestation["rawInventory"]["fileCount"] == 6
    assert attestation["sourceDocument"]["sha256"] == hashlib.sha256(
        b"%PDF-1.4 synthetic author document"
    ).hexdigest()
    assert attestation["semanticGates"]["confirmatoryMetricsEnabled"] is False
    assert attestation["semanticGates"]["supervisedMetricsEnabled"] is False
    assert attestation["semanticGates"]["transferMetricsEnabled"] is False
    assert attestation["semanticGates"]["rulMetricsEnabled"] is False
    assert os.fspath(tmp_path) not in serialized
    assert os.fspath(config.seven_zip_executable) not in serialized


@pytest.mark.parametrize(
    ("bad_content", "reason"),
    [
        (b"horizontal,vertical\n1,2\n", "nonnumeric"),
        (_numeric_csv(rows=1), "32767-equivalent off-by-one low"),
        (_numeric_csv(rows=3), "32769-equivalent off-by-one high"),
        (_numeric_csv(columns=1), "one column"),
        (_numeric_csv(columns=3), "three columns"),
        (b"1,2\n\n", "blank row"),
        (b"1,2\n3\n", "ragged row"),
        (b"1,2\nnot-a-number,3\n", "nonnumeric token"),
        (b"1,2\nNaN,3\n", "NaN"),
        (b"1,2\nInf,3\n", "infinity"),
    ],
)
def test_csv_shape_or_content_divergence_never_publishes(
    tmp_path, monkeypatch, bad_content, reason
) -> None:
    config = _config(tmp_path)
    _install_small_source(monkeypatch, config, bad_csv=bad_content)

    with pytest.raises(ValueError, match="CSV"):
        prepare_xjtu_sy(config)

    assert not list(config.destination_root.iterdir()), reason


def test_author_registry_drives_exact_condition_totals_and_terminal_evidence() -> None:
    registry = xjtu_preparation._registry_binding()
    bearings = registry["bearings"]
    condition_totals = {
        condition: sum(
            item["sourceFileCount"]
            for item in bearings
            if item["conditionId"] == condition
        )
        for condition in ("condition-1", "condition-2", "condition-3")
    }

    assert len(bearings) == 15
    assert condition_totals == {
        "condition-1": 616,
        "condition-2": 1_566,
        "condition-3": 7_034,
    }
    compound = next(
        item for item in bearings if item["bearingId"] == "xjtu-sy-bearing-3-2"
    )
    assert compound["sourceFileCount"] == 2_496
    assert compound["terminalOutcome"]["components"] == [
        "inner_race",
        "rolling_element",
        "cage",
        "outer_race",
    ]
    assert compound["terminalOutcome"]["scope"] == "bearing_terminal_evidence"


def test_executable_is_revalidated_immediately_before_the_single_extract(
    tmp_path, monkeypatch
) -> None:
    config = _config(tmp_path)
    _install_small_source(monkeypatch, config)
    fake_inspect = xjtu_preparation.inspect_rar_archive

    def mutate_after_inspection(*args, **kwargs):
        inspection = fake_inspect(*args, **kwargs)
        config.seven_zip_executable.write_bytes(b"substitute executable")
        return inspection

    monkeypatch.setattr(xjtu_preparation, "inspect_rar_archive", mutate_after_inspection)

    with pytest.raises(ValueError, match="executable changed"):
        prepare_xjtu_sy(config)

    assert not list(config.destination_root.iterdir())


def test_preparation_is_deterministic_across_destination_roots(
    tmp_path, monkeypatch
) -> None:
    config_a = _config(tmp_path / "a")
    _install_small_source(monkeypatch, config_a)
    first = prepare_xjtu_sy(config_a)
    config_b = _config(tmp_path / "b")
    _install_small_source(monkeypatch, config_b)
    second = prepare_xjtu_sy(config_b)

    assert first.generation_id == second.generation_id
    assert first.metadata_sha256 == second.metadata_sha256
    assert first.attestation_sha256 == second.attestation_sha256
    assert first.to_dict() == second.to_dict()


def test_existing_exact_generation_is_fully_verified_idempotently(
    tmp_path, monkeypatch
) -> None:
    config = _config(tmp_path)
    _install_small_source(monkeypatch, config)
    first = prepare_xjtu_sy(config)

    second = prepare_xjtu_sy(config)

    assert second.generation_root == first.generation_root
    assert second.to_dict() == first.to_dict()
    assert not list(config.destination_root.glob(".xjtu-sy-generation-*"))


def test_existing_divergent_generation_is_preserved_and_rejected(
    tmp_path, monkeypatch
) -> None:
    config = _config(tmp_path)
    _install_small_source(monkeypatch, config)
    first = prepare_xjtu_sy(config)
    sentinel = first.generation_root / "attestation.json"
    sentinel.write_text("controller divergence", encoding="utf-8")

    with pytest.raises(ValueError, match="differs"):
        prepare_xjtu_sy(config)

    assert sentinel.read_text(encoding="utf-8") == "controller divergence"
    assert not list(config.destination_root.glob(".xjtu-sy-generation-*"))


def test_existing_generation_reparse_root_is_rejected_before_manifest(
    tmp_path, monkeypatch
) -> None:
    config = _config(tmp_path)
    _install_small_source(monkeypatch, config)
    first = prepare_xjtu_sy(config)
    final = first.generation_root
    metadata = final.lstat()
    real_lstat = Path.lstat

    def reparse_final(path):
        if path != final:
            return real_lstat(path)
        return SimpleNamespace(
            st_mode=metadata.st_mode,
            st_dev=metadata.st_dev,
            st_ino=metadata.st_ino,
            st_file_attributes=(
                getattr(metadata, "st_file_attributes", 0)
                | getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
            ),
            st_reparse_tag=getattr(metadata, "st_reparse_tag", 0),
            st_ctime_ns=metadata.st_ctime_ns,
        )

    monkeypatch.setattr(Path, "lstat", reparse_final)

    with pytest.raises(ValueError, match="regular directory"):
        prepare_xjtu_sy(config)

    assert (final / "attestation.json").is_file()


@pytest.mark.parametrize("error", [RuntimeError("extract"), KeyboardInterrupt(), SystemExit(7)])
def test_extraction_base_exception_preserves_object_and_cleans_owned_staging(
    tmp_path, monkeypatch, error
) -> None:
    config = _config(tmp_path)
    _install_small_source(monkeypatch, config, extraction_error=error)

    with pytest.raises(type(error)) as caught:
        prepare_xjtu_sy(config)

    assert caught.value is error
    assert not list(config.destination_root.iterdir())


@pytest.mark.parametrize("error", [RuntimeError("rename"), KeyboardInterrupt(), SystemExit(8)])
def test_rename_that_promotes_then_raises_rolls_back_owned_final(
    tmp_path, monkeypatch, error
) -> None:
    config = _config(tmp_path)
    _install_small_source(monkeypatch, config)
    real_rename = Path.rename

    def rename_then_raise(source, target):
        real_rename(source, target)
        raise error

    monkeypatch.setattr(Path, "rename", rename_then_raise)

    with pytest.raises(type(error)) as caught:
        prepare_xjtu_sy(config)

    assert caught.value is error
    assert not getattr(caught.value, "__notes__", [])
    assert not list(config.destination_root.iterdir())


@pytest.mark.parametrize("error", [RuntimeError("rename"), KeyboardInterrupt(), SystemExit(9)])
def test_rename_that_raises_before_mutation_cleans_only_staging(
    tmp_path, monkeypatch, error
) -> None:
    config = _config(tmp_path)
    _install_small_source(monkeypatch, config)

    def raise_before_rename(_source, _target):
        raise error

    monkeypatch.setattr(Path, "rename", raise_before_rename)

    with pytest.raises(type(error)) as caught:
        prepare_xjtu_sy(config)

    assert caught.value is error
    assert not getattr(caught.value, "__notes__", [])
    assert not list(config.destination_root.iterdir())


@pytest.mark.parametrize("error", [RuntimeError("identity"), KeyboardInterrupt(), SystemExit(10)])
def test_first_staging_identity_failure_cleans_only_new_empty_directory(
    tmp_path, monkeypatch, error
) -> None:
    config = _config(tmp_path)
    _install_small_source(monkeypatch, config)
    real_identity = xjtu_preparation._directory_identity
    failed = False

    def fail_first_staging_identity(path):
        nonlocal failed
        if path.name.startswith(".xjtu-sy-generation-") and not failed:
            failed = True
            raise error
        return real_identity(path)

    monkeypatch.setattr(xjtu_preparation, "_directory_identity", fail_first_staging_identity)

    with pytest.raises(type(error)) as caught:
        prepare_xjtu_sy(config)

    assert caught.value is error
    assert not list(config.destination_root.iterdir())


@pytest.mark.parametrize(
    "identities",
    [((17, 0), (17, 0)), ((17, 101), (17, 102))],
    ids=["zero-inode", "unstable"],
)
def test_directory_identity_rejects_zero_or_unstable_values(
    tmp_path, monkeypatch, identities
) -> None:
    path = tmp_path / "owned"
    path.mkdir()
    metadata = path.lstat()
    values = iter(identities)
    real_lstat = Path.lstat

    def controlled_lstat(candidate):
        if candidate != path:
            return real_lstat(candidate)
        device, inode = next(values)
        return SimpleNamespace(
            st_mode=metadata.st_mode,
            st_dev=device,
            st_ino=inode,
            st_file_attributes=getattr(metadata, "st_file_attributes", 0),
        )

    monkeypatch.setattr(Path, "lstat", controlled_lstat)

    with pytest.raises(ValueError, match="identity"):
        xjtu_preparation._directory_identity(path)


@pytest.mark.parametrize("error", [RuntimeError("identity"), KeyboardInterrupt(), SystemExit(11)])
def test_swap_before_identity_preserves_replacement_and_displaced_tree(
    tmp_path, monkeypatch, error
) -> None:
    config = _config(tmp_path)
    _install_small_source(monkeypatch, config)
    real_identity = xjtu_preparation._directory_identity
    swapped: dict[str, Path] = {}

    def swap_before_identity(path):
        if path.name.startswith(".xjtu-sy-generation-") and not swapped:
            displaced = path.with_name(f"{path.name}-displaced")
            path.rename(displaced)
            path.mkdir()
            sentinel = path / "replacement-sentinel.txt"
            sentinel.write_text("controller replacement", encoding="utf-8")
            swapped.update(replacement=path, displaced=displaced, sentinel=sentinel)
            raise error
        return real_identity(path)

    monkeypatch.setattr(xjtu_preparation, "_directory_identity", swap_before_identity)

    with pytest.raises(type(error)) as caught:
        prepare_xjtu_sy(config)

    assert caught.value is error
    assert getattr(caught.value, "__notes__", [])
    assert swapped["replacement"].is_dir()
    assert swapped["displaced"].is_dir()
    assert swapped["sentinel"].read_text(encoding="utf-8") == "controller replacement"


def _install_stable_staging_swap(monkeypatch) -> dict[str, Path]:
    real_identity = xjtu_preparation._directory_identity
    swapped: dict[str, Path] = {}

    def swap_then_return_replacement_identity(path):
        if path.name.startswith(".xjtu-sy-generation-") and not swapped:
            displaced = path.with_name(f"{path.name}-actually-created")
            path.rename(displaced)
            path.mkdir()
            sentinel = path / "replacement-sentinel.txt"
            sentinel.write_text("controller replacement", encoding="utf-8")
            swapped.update(replacement=path, displaced=displaced, sentinel=sentinel)
        return real_identity(path)

    monkeypatch.setattr(
        xjtu_preparation, "_directory_identity", swap_then_return_replacement_identity
    )
    return swapped


@pytest.mark.parametrize(
    "later_error", [RuntimeError("extract"), KeyboardInterrupt(), SystemExit(12)]
)
def test_stable_swap_before_ownership_is_rejected_before_any_extract(
    tmp_path, monkeypatch, later_error
) -> None:
    config = _config(tmp_path)
    _, _, events, _ = _install_small_source(monkeypatch, config)
    swapped = _install_stable_staging_swap(monkeypatch)
    extraction_calls = 0

    def fail_if_called(*_args, **_kwargs):
        nonlocal extraction_calls
        extraction_calls += 1
        raise later_error

    monkeypatch.setattr(xjtu_preparation, "safe_extract_rar_archive", fail_if_called)

    observed: BaseException | None = None
    try:
        prepare_xjtu_sy(config)
    except BaseException as error:
        observed = error

    assert isinstance(observed, ValueError)
    assert "changed" in str(observed)
    assert events == ["inspect"]
    assert extraction_calls == 0
    assert getattr(observed, "__notes__", [])
    assert swapped["replacement"].is_dir()
    assert swapped["displaced"].is_dir()
    assert swapped["sentinel"].read_text(encoding="utf-8") == "controller replacement"


def test_zero_identity_returned_during_binding_fails_before_extract(
    tmp_path, monkeypatch
) -> None:
    config = _config(tmp_path)
    _, _, events, extraction_count = _install_small_source(monkeypatch, config)
    real_identity = xjtu_preparation._directory_identity

    def zero_staging_inode(path):
        device, inode = real_identity(path)
        if path.name.startswith(".xjtu-sy-generation-"):
            inode = 0
        return device, inode

    monkeypatch.setattr(xjtu_preparation, "_directory_identity", zero_staging_inode)

    with pytest.raises(ValueError, match="identity"):
        prepare_xjtu_sy(config)

    assert events == ["inspect"]
    assert extraction_count() == 0
    assert not list(config.destination_root.iterdir())


class _HostileAddNoteError(RuntimeError):
    def __init__(self, note_error: BaseException) -> None:
        super().__init__("primary extraction failure")
        self.note_error = note_error

    def add_note(self, _note: str) -> None:
        raise self.note_error


@pytest.mark.parametrize(
    "note_error", [RuntimeError("note"), KeyboardInterrupt(), SystemExit(13)]
)
def test_cleanup_note_failure_never_masks_original_base_exception(
    tmp_path, monkeypatch, note_error
) -> None:
    config = _config(tmp_path)
    _install_small_source(monkeypatch, config)
    primary = _HostileAddNoteError(note_error)
    swapped: dict[str, Path] = {}

    def swap_owned_staging_then_fail(_parts, destination, **_kwargs):
        staging = Path(destination).parent
        displaced = staging.with_name(f"{staging.name}-actually-created")
        staging.rename(displaced)
        staging.mkdir()
        sentinel = staging / "replacement-sentinel.txt"
        sentinel.write_text("controller replacement", encoding="utf-8")
        swapped.update(replacement=staging, displaced=displaced, sentinel=sentinel)
        raise primary

    monkeypatch.setattr(
        xjtu_preparation, "safe_extract_rar_archive", swap_owned_staging_then_fail
    )

    observed: BaseException | None = None
    try:
        prepare_xjtu_sy(config)
    except BaseException as error:
        observed = error

    assert observed is primary
    assert not getattr(primary, "__notes__", [])
    assert swapped["replacement"].is_dir()
    assert swapped["displaced"].is_dir()
    assert swapped["sentinel"].read_text(encoding="utf-8") == "controller replacement"


def test_real_xjtu_inspection_is_explicitly_opt_in_and_read_only(tmp_path) -> None:
    source_value = os.environ.get("TWINOPS_XJTU_RAR_DIRECTORY")
    seven_zip_value = os.environ.get("TWINOPS_TRUSTED_7Z_PATH")
    if not source_value or not seven_zip_value:
        pytest.skip(
            "set TWINOPS_XJTU_RAR_DIRECTORY and TWINOPS_TRUSTED_7Z_PATH "
            "to inspect the six pinned XJTU-SY RAR volumes read-only"
        )
    source = Path(source_value)
    config = XjtuSyPreparationConfig(
        archive_parts=tuple(
            ArchivePart((source / name).resolve(), digest)
            for name, _, digest in _OFFICIAL_PARTS
        ),
        seven_zip_executable=Path(seven_zip_value).resolve(),
        destination_root=(tmp_path / "unused-prepared").resolve(),
    )

    inspection = xjtu_preparation.inspect_rar_archive(
        config.archive_parts, limits=config.extraction_limits
    )
    observed = xjtu_preparation._validate_inspection(config, inspection)

    assert len(observed) == 9_217
    assert not config.destination_root.exists()


def test_extracted_inventory_byte_total_must_match_the_inspected_archive(
    tmp_path, monkeypatch
) -> None:
    config = _config(tmp_path)
    specs, _, _, _ = _install_small_source(monkeypatch, config)
    fake_extract = xjtu_preparation.safe_extract_rar_archive

    def return_different_valid_numeric_bytes(*args, **kwargs):
        inventory = fake_extract(*args, **kwargs)
        root = Path(args[1])
        root.joinpath(*_csv_path(specs[0], 1).split("/")).write_bytes(
            b"10,20\n30,40\n"
        )
        contents = {
            item.relative_path: root.joinpath(*item.relative_path.split("/")).read_bytes()
            for item in inventory.files
        }
        return _inventory(root, contents)

    monkeypatch.setattr(
        xjtu_preparation,
        "safe_extract_rar_archive",
        return_different_valid_numeric_bytes,
    )

    with pytest.raises(ValueError, match="byte count|inspection"):
        prepare_xjtu_sy(config)

    assert not list(config.destination_root.iterdir())


def test_extracted_raw_root_must_be_plain_non_reparse_before_content_reads(
    tmp_path, monkeypatch
) -> None:
    config = _config(tmp_path)
    _install_small_source(monkeypatch, config)
    real_lstat = Path.lstat
    real_validate_csv = xjtu_preparation._validate_numeric_csv
    content_reads = 0

    def record_content_read(*args, **kwargs):
        nonlocal content_reads
        content_reads += 1
        return real_validate_csv(*args, **kwargs)

    def reparse_raw_root(path):
        metadata = real_lstat(path)
        if path.name != "raw" or not path.parent.name.startswith(
            ".xjtu-sy-generation-"
        ):
            return metadata
        return SimpleNamespace(
            st_mode=metadata.st_mode,
            st_dev=metadata.st_dev,
            st_ino=metadata.st_ino,
            st_file_attributes=(
                getattr(metadata, "st_file_attributes", 0)
                | getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
            ),
            st_reparse_tag=getattr(metadata, "st_reparse_tag", 0),
            st_ctime_ns=metadata.st_ctime_ns,
        )

    monkeypatch.setattr(Path, "lstat", reparse_raw_root)
    monkeypatch.setattr(xjtu_preparation, "_validate_numeric_csv", record_content_read)

    with pytest.raises(ValueError, match="regular directory|unsafe"):
        prepare_xjtu_sy(config)

    assert content_reads == 0
    assert not list(config.destination_root.iterdir())


def test_inspection_accepts_public_api_normalization_of_absolute_part_paths(
    tmp_path, monkeypatch
) -> None:
    base = _config(tmp_path)
    intermediary = tmp_path / "intermediary"
    intermediary.mkdir()
    parts = list(base.archive_parts)
    parts[0] = ArchivePart(
        intermediary / ".." / parts[0].path.name,
        parts[0].sha256,
    )
    config = _config(tmp_path, archive_parts=tuple(parts))
    _install_small_source(monkeypatch, config)
    fake_inspect = xjtu_preparation.inspect_rar_archive

    def normalized_inspection(*args, **kwargs):
        inspection = fake_inspect(*args, **kwargs)
        inspection.parts = tuple(
            ArchivePart(part.path.resolve(strict=True), part.sha256)
            for part in config.archive_parts
        )
        return inspection

    monkeypatch.setattr(xjtu_preparation, "inspect_rar_archive", normalized_inspection)

    result = prepare_xjtu_sy(config)

    assert result.generation_root.is_dir()
