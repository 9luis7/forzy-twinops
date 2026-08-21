from __future__ import annotations

import hashlib
import json
import os
import stat
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from twinops.research.downloads import ArchivePart, RawFile, RawInventory
from twinops.research.datasets import ims_preparation
from twinops.research.datasets.ims import iter_ims
from twinops.research.datasets.ims_preparation import (
    NASA_IMS_RUN_1_SHA256,
    NASA_IMS_RUN_2_SHA256,
    NASA_IMS_RUN_3_SHA256,
    NasaImsPreparationConfig,
    NasaImsPreparationResult,
    prepare_nasa_ims,
)
from twinops.research.metadata import load_metadata


def _config(tmp_path: Path, **changes) -> NasaImsPreparationConfig:
    tmp_path.mkdir(parents=True, exist_ok=True)
    archives = []
    for name, digest in (
        ("1st_test.rar", NASA_IMS_RUN_1_SHA256),
        ("2nd_test.rar", NASA_IMS_RUN_2_SHA256),
        ("3rd_test.rar", NASA_IMS_RUN_3_SHA256),
    ):
        path = tmp_path / name
        path.write_bytes(name.encode("ascii"))
        archives.append(ArchivePart(path.resolve(), digest))
    seven_zip = tmp_path / "7z.exe"
    seven_zip.write_bytes(b"trusted test executable")
    values = {
        "run_1_archive": archives[0],
        "run_2_archive": archives[1],
        "run_3_archive": archives[2],
        "seven_zip_executable": seven_zip.resolve(),
        "destination_root": (tmp_path / "prepared").resolve(),
    }
    values.update(changes)
    return NasaImsPreparationConfig(**values)


def test_preparation_config_binds_all_three_official_archives_and_absolute_paths(
    tmp_path,
) -> None:
    config = _config(tmp_path)

    assert config.run_1_archive.sha256 == NASA_IMS_RUN_1_SHA256
    assert config.run_2_archive.sha256 == NASA_IMS_RUN_2_SHA256
    assert config.run_3_archive.sha256 == NASA_IMS_RUN_3_SHA256
    assert config.destination_root.is_absolute()
    assert config.seven_zip_executable.is_absolute()


def test_preparation_config_rejects_a_wrong_run_binding(tmp_path) -> None:
    with pytest.raises(ValueError, match="run 1 archive SHA-256"):
        _config(
            tmp_path,
            run_1_archive=ArchivePart((tmp_path / "wrong.rar").resolve(), "0" * 64),
        )


@pytest.mark.parametrize("field", ["destination_root", "seven_zip_executable"])
def test_preparation_config_rejects_relative_output_or_executable_paths(
    tmp_path, field
) -> None:
    with pytest.raises(ValueError, match="absolute"):
        _config(tmp_path, **{field: Path("relative")})


@pytest.mark.parametrize("unsafe_part", ["executable", "ancestor"])
def test_preparation_config_rejects_reparse_executable_or_ancestor(
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


def test_preparation_config_attests_the_exact_executable_bytes(tmp_path) -> None:
    config = _config(tmp_path)

    assert config._seven_zip_attestation.sha256 == hashlib.sha256(
        b"trusted test executable"
    ).hexdigest()


def test_prepare_rejects_executable_content_changed_since_config(
    tmp_path, monkeypatch
) -> None:
    _install_small_source(monkeypatch)
    config = _config(tmp_path)
    config.seven_zip_executable.write_bytes(b"substitute executable")

    with pytest.raises(ValueError, match="executable changed"):
        prepare_nasa_ims(config)

    assert not config.destination_root.exists()


@pytest.mark.parametrize("changed_part", ["file", "parent"])
def test_prepare_rejects_same_bytes_replacement_of_executable_or_parent(
    tmp_path, monkeypatch, changed_part
) -> None:
    _install_small_source(monkeypatch)
    trusted_bin = tmp_path / "trusted-bin"
    trusted_bin.mkdir()
    executable = trusted_bin / "7z.exe"
    executable.write_bytes(b"trusted test executable")
    config = _config(tmp_path, seven_zip_executable=executable.resolve())
    if changed_part == "file":
        executable.rename(trusted_bin / "retired-7z.exe")
        executable.write_bytes(b"trusted test executable")
    else:
        trusted_bin.rename(tmp_path / "retired-bin")
        trusted_bin.mkdir()
        executable.write_bytes(b"trusted test executable")

    with pytest.raises(ValueError, match="executable changed"):
        prepare_nasa_ims(config)

    assert not config.destination_root.exists()


def test_executable_is_revalidated_immediately_before_each_extract(
    tmp_path, monkeypatch
) -> None:
    _install_small_source(monkeypatch)
    config = _config(tmp_path)
    fake_extract = ims_preparation.safe_extract_rar_archive
    calls = 0

    def mutate_after_first_extract(*args, **kwargs):
        nonlocal calls
        calls += 1
        inventory = fake_extract(*args, **kwargs)
        if calls == 1:
            config.seven_zip_executable.write_bytes(b"substitute executable")
        return inventory

    monkeypatch.setattr(
        ims_preparation, "safe_extract_rar_archive", mutate_after_first_extract
    )

    with pytest.raises(ValueError, match="executable changed"):
        prepare_nasa_ims(config)

    assert calls == 1
    assert not list(config.destination_root.iterdir())


def _specs(*, samples_per_window: int = 2):
    return (
        SimpleNamespace(
            number=1,
            run_id="ims-run-1",
            archive_field="run_1_archive",
            prefix="1st_test",
            first_timestamp="2003.10.22.12.06.24",
            last_timestamp="2003.11.25.23.39.56",
            regular_file_count=2,
            total_member_count=3,
            samples_per_window=samples_per_window,
            column_count=8,
            documented_file_count=None,
            documented_prefix_last_timestamp=None,
            first_extension_timestamp=None,
        ),
        SimpleNamespace(
            number=2,
            run_id="ims-run-2",
            archive_field="run_2_archive",
            prefix="2nd_test",
            first_timestamp="2004.02.12.10.32.39",
            last_timestamp="2004.02.19.06.22.39",
            regular_file_count=2,
            total_member_count=3,
            samples_per_window=samples_per_window,
            column_count=4,
            documented_file_count=None,
            documented_prefix_last_timestamp=None,
            first_extension_timestamp=None,
        ),
        SimpleNamespace(
            number=3,
            run_id="ims-run-3",
            archive_field="run_3_archive",
            prefix="4th_test/txt",
            first_timestamp="2004.03.04.09.27.46",
            last_timestamp="2004.04.18.02.42.55",
            regular_file_count=4,
            total_member_count=6,
            samples_per_window=samples_per_window,
            column_count=4,
            documented_file_count=2,
            documented_prefix_last_timestamp="2004.04.04.19.01.57",
            first_extension_timestamp="2004.04.04.19.11.57",
        ),
    )


def _names(spec) -> list[str]:
    if spec.number != 3:
        return [spec.first_timestamp, spec.last_timestamp]
    return [
        spec.first_timestamp,
        spec.documented_prefix_last_timestamp,
        spec.first_extension_timestamp,
        spec.last_timestamp,
    ]


def _inspection(spec):
    directory_members = []
    current = []
    for part in spec.prefix.split("/"):
        current.append(part)
        directory_members.append(
            SimpleNamespace(
                relative_path="/".join(current),
                size_bytes=0,
                compressed_bytes=0,
                is_directory=True,
            )
        )
    files = [
        SimpleNamespace(
            relative_path=f"{spec.prefix}/{name}",
            size_bytes=1,
            compressed_bytes=1,
            is_directory=False,
        )
        for name in _names(spec)
    ]
    return SimpleNamespace(members=tuple(directory_members + files))


def _raw_inventory(root: Path, paths: list[str], content_by_path: dict[str, bytes]) -> RawInventory:
    files = []
    for relative_path in sorted(paths):
        target = root.joinpath(*relative_path.split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        content = content_by_path[relative_path]
        target.write_bytes(content)
        files.append(
            RawFile(
                relative_path=relative_path,
                size_bytes=len(content),
                sha256=hashlib.sha256(content).hexdigest(),
            )
        )
    canonical = json.dumps(
        [
            {
                "relativePath": item.relative_path,
                "sizeBytes": item.size_bytes,
                "sha256": item.sha256,
            }
            for item in files
        ],
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return RawInventory(
        files=tuple(files),
        inventory_sha256=hashlib.sha256(canonical).hexdigest(),
        total_bytes=sum(item.size_bytes for item in files),
    )


def _numeric_content(rows: int, columns: int) -> bytes:
    row = " ".join(str(index + 1) for index in range(columns))
    return ((row + "\n") * rows).encode("ascii")


def _install_small_source(
    monkeypatch,
    *,
    samples_per_window: int = 2,
    bad_run_1_content: bytes | None = None,
    extraction_error: BaseException | None = None,
):
    specs = _specs(samples_per_window=samples_per_window)
    monkeypatch.setattr(ims_preparation, "_RUN_SPECS", specs)
    events: list[str] = []

    def fake_inspect(parts, *, limits):
        name = parts[0].path.name
        number = int(name[0])
        events.append(f"inspect-{number}")
        return _inspection(specs[number - 1])

    extraction_count = 0

    def fake_extract(parts, destination, *, limits, seven_zip_executable):
        nonlocal extraction_count
        extraction_count += 1
        number = int(parts[0].path.name[0])
        events.append(f"extract-{number}")
        if extraction_count == 2 and extraction_error is not None:
            raise extraction_error
        spec = specs[number - 1]
        paths = [f"{spec.prefix}/{name}" for name in _names(spec)]
        default = _numeric_content(spec.samples_per_window, spec.column_count)
        contents = {path: default for path in paths}
        if number == 1 and bad_run_1_content is not None:
            contents[paths[0]] = bad_run_1_content
        return _raw_inventory(Path(destination), paths, contents)

    monkeypatch.setattr(ims_preparation, "inspect_rar_archive", fake_inspect)
    monkeypatch.setattr(ims_preparation, "safe_extract_rar_archive", fake_extract)
    return specs, events


def test_prepare_inspects_every_archive_before_writing_and_never_extracts_run_3(
    tmp_path, monkeypatch
) -> None:
    _, events = _install_small_source(monkeypatch)

    result = prepare_nasa_ims(_config(tmp_path))

    assert isinstance(result, NasaImsPreparationResult)
    assert events == ["inspect-1", "inspect-2", "inspect-3", "extract-1", "extract-2"]
    assert result.generation_root.is_dir()
    assert not list(result.generation_root.parent.glob(".nasa-ims-generation-*"))


def test_prepared_metadata_is_deterministic_complete_and_semantically_fail_closed(
    tmp_path, monkeypatch
) -> None:
    specs, _ = _install_small_source(monkeypatch)

    result = prepare_nasa_ims(_config(tmp_path))
    metadata_payloads = []
    for number, spec, path, inventory, digest in (
        (1, specs[0], result.run_1_metadata_path, result.run_1_inventory, result.run_1_metadata_sha256),
        (2, specs[1], result.run_2_metadata_path, result.run_2_inventory, result.run_2_metadata_sha256),
    ):
        loaded = load_metadata(
            path,
            expected_sha256=digest,
            dataset_id="nasa-ims",
            raw_inventory=inventory,
        )
        payload = dict(loaded.payload)
        metadata_payloads.append(payload)
        assert set(payload["files"]) == {item.relative_path for item in inventory.files}
        assert payload["accelerationUnit"] == "unknown"
        assert payload["samplesPerWindow"] == spec.samples_per_window
        assert payload["sourceArchiveSha256"] == getattr(
            _config(tmp_path), f"run_{number}_archive"
        ).sha256
        assert payload["rawInventorySha256"] == inventory.inventory_sha256
        for sequence, entry in enumerate(payload["files"].values()):
            assert entry["runId"] == f"ims-run-{number}"
            assert entry["sequenceIndex"] == sequence
            assert entry["startedAt"] is None
            assert entry["timestampQuality"] == "unavailable"
            assert entry["sourceLocalTimestampEvidence"]["timezone"] == "unknown"
            assert all(channel["windowStateLabel"] == "unknown" for channel in entry["channels"])
            assert all(channel["terminalFailureMode"] is None for channel in entry["channels"])
            assert all(channel["lifeFraction"] is None for channel in entry["channels"])
            assert {channel["columnIndex"] for channel in entry["channels"]} == set(
                range(spec.column_count)
            )
        windows = list(
            iter_ims(
                result.run_1_raw_root if number == 1 else result.run_2_raw_root,
                loaded,
            )
        )
        assert all(window.acceleration_unit == "unknown" for window in windows)
        assert all(window.window_state_label == "unknown" for window in windows)
        assert all(window.terminal_failure_mode is None for window in windows)
        assert all(window.life_fraction is None for window in windows)
        assert all(window.started_at is None for window in windows)
        assert all(window.timestamp_quality == "unavailable" for window in windows)
        expected_axes = {"source-channel-1", "source-channel-2"} if number == 1 else {
            "source-channel-1"
        }
        assert all(set(window.acceleration) == expected_axes for window in windows)
    bearing_ids = {
        channel["bearingId"]
        for payload in metadata_payloads
        for entry in payload["files"].values()
        for channel in entry["channels"]
    }
    assert "ims-run-1-bearing-1" in bearing_ids
    assert "ims-run-2-bearing-1" in bearing_ids
    assert len(bearing_ids) == 8

    conflict = metadata_payloads[0]["terminalOutcomeEvidence"]["bearings"][
        "ims-run-1-bearing-4"
    ]["observations"]
    assert {item["outcome"] for item in conflict} == {
        "rolling_element",
        "rolling_element_plus_outer_race",
    }
    assert {item["sourceRef"] for item in conflict} == {
        "nasa-ims-internal-readme-cf46d37c",
        "qiu-et-al-jsv-2006",
    }
    sources = metadata_payloads[0]["terminalOutcomeEvidence"]["sources"]
    assert sources["nasa-ims-internal-readme-cf46d37c"] == {
        "localRelativePath": "IMS/Readme Document for IMS Bearing Data.pdf",
        "sha256": "cf46d37c21f7f292c11bbbdd4695d876c417ed1d6425e3d87c962ae2182ae6ed",
    }
    assert sources["qiu-et-al-jsv-2006"] == {
        "citation": "Qiu et al., Journal of Sound and Vibration",
        "doi": "10.1016/j.jsv.2005.03.007",
        "url": "https://doi.org/10.1016/j.jsv.2005.03.007",
    }


def test_attestation_has_no_local_paths_and_quarantines_the_undocumented_extension(
    tmp_path, monkeypatch
) -> None:
    _install_small_source(monkeypatch)

    result = prepare_nasa_ims(_config(tmp_path))
    attestation = result.to_dict()

    serialized = json.dumps(attestation, sort_keys=True)
    assert str(tmp_path) not in serialized
    assert "7z.exe" not in serialized
    quarantine = attestation["quarantine"]
    assert quarantine == {
        "runId": "ims-run-3",
        "status": "quarantined_source_contradiction",
        "sourceArchiveSha256": NASA_IMS_RUN_3_SHA256,
        "documentedFileCount": 2,
        "observedFileCount": 4,
        "documentedPrefixLastPath": "4th_test/txt/2004.04.04.19.01.57",
        "undocumentedExtensionCount": 2,
        "firstExtensionPath": "4th_test/txt/2004.04.04.19.11.57",
        "lastObservedPath": "4th_test/txt/2004.04.18.02.42.55",
        "includedInConfirmatoryMetrics": False,
        "includedInSupervisedMetrics": False,
        "includedInRulMetrics": False,
    }
    assert attestation["semanticGates"]["accelerationUnit"] == "unknown"
    assert attestation["semanticGates"]["sourceTimezone"] == "unknown"
    assert attestation["semanticGates"]["lifeFraction"] is None


def test_preparation_is_deterministic_across_destination_roots(tmp_path, monkeypatch) -> None:
    _install_small_source(monkeypatch)
    first = prepare_nasa_ims(_config(tmp_path / "first"))
    second = prepare_nasa_ims(_config(tmp_path / "second"))

    assert first.generation_id == second.generation_id
    assert first.run_1_metadata_sha256 == second.run_1_metadata_sha256
    assert first.run_2_metadata_sha256 == second.run_2_metadata_sha256
    assert first.attestation_sha256 == second.attestation_sha256
    assert first.to_dict() == second.to_dict()


def test_existing_exact_generation_is_verified_idempotently(tmp_path, monkeypatch) -> None:
    _install_small_source(monkeypatch)
    config = _config(tmp_path)
    first = prepare_nasa_ims(config)

    second = prepare_nasa_ims(config)

    assert second.generation_root == first.generation_root
    assert second.to_dict() == first.to_dict()
    assert not list(config.destination_root.glob(".nasa-ims-generation-*"))


def test_existing_mismatched_generation_is_preserved_and_rejected(tmp_path, monkeypatch) -> None:
    _install_small_source(monkeypatch)
    config = _config(tmp_path)
    first = prepare_nasa_ims(config)
    first.run_1_metadata_path.write_text("controller-owned mismatch", encoding="utf-8")

    with pytest.raises(ValueError, match="existing generation"):
        prepare_nasa_ims(config)

    assert first.run_1_metadata_path.read_text(encoding="utf-8") == "controller-owned mismatch"
    assert not list(config.destination_root.glob(".nasa-ims-generation-*"))


@pytest.mark.parametrize("unsafe_kind", ["symlink-mode", "reparse-attribute"])
def test_existing_generation_root_is_validated_before_manifest_or_idempotency(
    tmp_path, monkeypatch, unsafe_kind
) -> None:
    _install_small_source(monkeypatch)
    config = _config(tmp_path)
    first = prepare_nasa_ims(config)
    metadata = first.generation_root.lstat()
    real_lstat = Path.lstat

    def unsafe_root_lstat(path):
        if path != first.generation_root:
            return real_lstat(path)
        mode = metadata.st_mode
        attributes = getattr(metadata, "st_file_attributes", 0)
        if unsafe_kind == "symlink-mode":
            mode = stat.S_IFLNK | 0o777
        else:
            attributes |= getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        return SimpleNamespace(
            st_mode=mode,
            st_dev=metadata.st_dev,
            st_ino=metadata.st_ino,
            st_file_attributes=attributes,
        )

    monkeypatch.setattr(Path, "lstat", unsafe_root_lstat)

    with pytest.raises(ValueError, match="regular directory"):
        prepare_nasa_ims(config)

    assert first.run_1_metadata_path.is_file()
    assert not list(config.destination_root.glob(".nasa-ims-generation-*"))


def test_existing_generation_symlink_preserves_its_external_target(tmp_path, monkeypatch) -> None:
    _install_small_source(monkeypatch)
    config = _config(tmp_path)
    first = prepare_nasa_ims(config)
    external = tmp_path / "external-generation"
    first.generation_root.rename(external)
    try:
        first.generation_root.symlink_to(external, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"directory symlinks are unavailable: {error.__class__.__name__}")

    with pytest.raises(ValueError, match="regular directory"):
        prepare_nasa_ims(config)

    assert first.generation_root.is_symlink()
    assert (external / "run-1" / "metadata.json").is_file()
    assert not list(config.destination_root.glob(".nasa-ims-generation-*"))


@pytest.mark.parametrize("error", [RuntimeError("stop"), KeyboardInterrupt(), SystemExit(7)])
def test_pair_publication_rolls_back_the_owned_staging_on_base_exception(
    tmp_path, monkeypatch, error
) -> None:
    _install_small_source(monkeypatch, extraction_error=error)
    config = _config(tmp_path)

    with pytest.raises(type(error)) as caught:
        prepare_nasa_ims(config)

    assert caught.value is error
    assert not list(config.destination_root.iterdir())


@pytest.mark.parametrize("error", [RuntimeError("identity"), KeyboardInterrupt(), SystemExit(9)])
def test_staging_identity_failure_cleans_the_new_empty_generation(
    tmp_path, monkeypatch, error
) -> None:
    _install_small_source(monkeypatch)
    config = _config(tmp_path)
    real_identity = ims_preparation._directory_identity
    failed = False

    def fail_first_staging_identity(path):
        nonlocal failed
        if path.name.startswith(".nasa-ims-generation-") and not failed:
            failed = True
            raise error
        return real_identity(path)

    monkeypatch.setattr(ims_preparation, "_directory_identity", fail_first_staging_identity)

    with pytest.raises(type(error)) as caught:
        prepare_nasa_ims(config)

    assert caught.value is error
    assert not list(config.destination_root.iterdir())


@pytest.mark.parametrize(
    "identities",
    [
        ((17, 0), (17, 0)),
        ((17, 101), (17, 102)),
    ],
    ids=["zero-inode", "unstable"],
)
def test_directory_identity_rejects_invalid_or_unstable_values(
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
        ims_preparation._directory_identity(path)


@pytest.mark.parametrize("error", [RuntimeError("identity"), KeyboardInterrupt(), SystemExit(10)])
def test_staging_swap_before_identity_never_erases_the_replacement(
    tmp_path, monkeypatch, error
) -> None:
    _install_small_source(monkeypatch)
    config = _config(tmp_path)
    real_identity = ims_preparation._directory_identity
    swapped: dict[str, Path] = {}

    def swap_before_identity(path):
        if path.name.startswith(".nasa-ims-generation-") and not swapped:
            displaced = path.with_name(f"{path.name}-displaced")
            path.rename(displaced)
            path.mkdir()
            swapped.update(replacement=path, displaced=displaced)
            raise error
        return real_identity(path)

    monkeypatch.setattr(ims_preparation, "_directory_identity", swap_before_identity)

    with pytest.raises(type(error)) as caught:
        prepare_nasa_ims(config)

    assert caught.value is error
    assert getattr(caught.value, "__notes__", [])
    assert swapped["replacement"].is_dir()
    assert swapped["displaced"].is_dir()


@pytest.mark.parametrize("error", [RuntimeError("rename"), KeyboardInterrupt(), SystemExit(11)])
def test_rename_that_promotes_then_raises_rolls_back_the_final_generation(
    tmp_path, monkeypatch, error
) -> None:
    _install_small_source(monkeypatch)
    config = _config(tmp_path)
    real_rename = Path.rename

    def rename_then_raise(source, target):
        real_rename(source, target)
        raise error

    monkeypatch.setattr(Path, "rename", rename_then_raise)

    with pytest.raises(type(error)) as caught:
        prepare_nasa_ims(config)

    assert caught.value is error
    assert not getattr(caught.value, "__notes__", [])
    assert not list(config.destination_root.iterdir())


@pytest.mark.parametrize("error", [RuntimeError("rename"), KeyboardInterrupt(), SystemExit(12)])
def test_rename_that_raises_before_mutation_cleans_only_staging(
    tmp_path, monkeypatch, error
) -> None:
    _install_small_source(monkeypatch)
    config = _config(tmp_path)

    def raise_before_rename(_source, _target):
        raise error

    monkeypatch.setattr(Path, "rename", raise_before_rename)

    with pytest.raises(type(error)) as caught:
        prepare_nasa_ims(config)

    assert caught.value is error
    assert not getattr(caught.value, "__notes__", [])
    assert not list(config.destination_root.iterdir())


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (b"", "blank"),
        (_numeric_content(1, 8), "row count"),
        (_numeric_content(2, 7), "column count"),
        (_numeric_content(2, 9), "column count"),
        (b"1 2 3 4 5 6 7 8\n1 2 3 4 5 6 7\n", "ragged"),
        (b"1 2 3 4 5 6 7 8\n1 2 3 4 5 6 7 nan\n", "finite"),
    ],
)
def test_numeric_shape_and_content_failures_never_publish(
    tmp_path, monkeypatch, content, message
) -> None:
    _install_small_source(monkeypatch, bad_run_1_content=content)
    config = _config(tmp_path)

    with pytest.raises(ValueError, match=message):
        prepare_nasa_ims(config)

    assert not list(config.destination_root.iterdir())


def _timestamp_names(first: str, last: str, count: int) -> list[str]:
    start = datetime.strptime(first, "%Y.%m.%d.%H.%M.%S")
    end = datetime.strptime(last, "%Y.%m.%d.%H.%M.%S")
    span_seconds = int((end - start).total_seconds())
    return [
        (start + timedelta(seconds=(span_seconds * index) // (count - 1))).strftime(
            "%Y.%m.%d.%H.%M.%S"
        )
        for index in range(count)
    ]


def test_official_inspection_boundaries_and_run_3_quarantine_facts_are_exact() -> None:
    run_1, run_2, run_3 = ims_preparation._RUN_SPECS
    run_1_names = _timestamp_names(
        "2003.10.22.12.06.24", "2003.11.25.23.39.56", 2_156
    )
    run_2_names = _timestamp_names(
        "2004.02.12.10.32.39", "2004.02.19.06.22.39", 984
    )
    documented = _timestamp_names(
        "2004.03.04.09.27.46", "2004.04.04.19.01.57", 4_448
    )
    extension = _timestamp_names(
        "2004.04.04.19.11.57", "2004.04.18.02.42.55", 1_876
    )

    observed = []
    for spec, names in (
        (run_1, run_1_names),
        (run_2, run_2_names),
        (run_3, documented + extension),
    ):
        inspection = _inspection(SimpleNamespace(**{**spec.__dict__}) if hasattr(spec, "__dict__") else spec)
        directory_count = len(spec.prefix.split("/"))
        inspection = SimpleNamespace(
            members=inspection.members[:directory_count]
            + tuple(
                SimpleNamespace(
                    relative_path=f"{spec.prefix}/{name}",
                    size_bytes=1,
                    compressed_bytes=1,
                    is_directory=False,
                )
                for name in names
            )
        )
        observed.append(ims_preparation._validate_inspection(spec, inspection))

    assert len(observed[0]) == 2_156
    assert len(observed[1]) == 984
    assert len(observed[2]) == 6_324
    quarantine = ims_preparation._quarantine(
        run_3,
        ArchivePart(Path("3rd_test.rar"), NASA_IMS_RUN_3_SHA256),
    )
    assert quarantine["documentedFileCount"] == 4_448
    assert quarantine["undocumentedExtensionCount"] == 1_876
    assert quarantine["observedFileCount"] == 6_324
    assert quarantine["firstExtensionPath"] == "4th_test/txt/2004.04.04.19.11.57"
    assert quarantine["lastObservedPath"] == "4th_test/txt/2004.04.18.02.42.55"


def test_real_nasa_inspection_is_explicitly_opt_in_and_read_only(tmp_path) -> None:
    source_value = os.environ.get("TWINOPS_NASA_RAR_DIRECTORY")
    seven_zip_value = os.environ.get("TWINOPS_TRUSTED_7Z_PATH")
    if not source_value or not seven_zip_value:
        pytest.skip(
            "set TWINOPS_NASA_RAR_DIRECTORY and TWINOPS_TRUSTED_7Z_PATH "
            "to inspect the three pinned NASA RARs read-only"
        )
    source = Path(source_value)
    config = NasaImsPreparationConfig(
        run_1_archive=ArchivePart(
            (source / "1st_test.rar").resolve(), NASA_IMS_RUN_1_SHA256
        ),
        run_2_archive=ArchivePart(
            (source / "2nd_test.rar").resolve(), NASA_IMS_RUN_2_SHA256
        ),
        run_3_archive=ArchivePart(
            (source / "3rd_test.rar").resolve(), NASA_IMS_RUN_3_SHA256
        ),
        seven_zip_executable=Path(seven_zip_value).resolve(),
        destination_root=(tmp_path / "unused-prepared").resolve(),
    )

    for spec in ims_preparation._RUN_SPECS:
        inspection = ims_preparation.inspect_rar_archive(
            [getattr(config, spec.archive_field)], limits=config.extraction_limits
        )
        ims_preparation._validate_inspection(spec, inspection)

    assert not config.destination_root.exists()
