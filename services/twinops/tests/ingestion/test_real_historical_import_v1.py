from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
import stat as stat_module
import sys
from types import SimpleNamespace

import pytest

from twinops.ingestion.historical_import_v1 import prepare_historical_batch
from twinops.ingestion.history_profiles_v1 import registered_profile


_SOURCE_ENV = "TWINOPS_FORZY_HISTORY_CSV"
_SOURCE_REJECTION = "controller history source is unavailable or unsafe"
_SOURCE_SKIP = "real history controller source is not configured"
_PREPARATION_REJECTION = "controller history preparation failed"
_REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
_DEPLOY_OUTPUT_ROOTS = tuple(
    _REPOSITORY_ROOT / name for name in ("dist", "dist-ssr", ".vercel")
)


def _is_windows_reparse_point(path: Path, metadata: os.stat_result) -> bool:
    del path
    return bool(
        getattr(metadata, "st_file_attributes", 0)
        & getattr(stat_module, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    )


def _attest_regular_non_reparse_file(path: Path) -> None:
    anchor = Path(path.anchor)
    if path == anchor:
        metadata = path.lstat()
        if (
            stat_module.S_ISLNK(metadata.st_mode)
            or _is_windows_reparse_point(path, metadata)
            or not stat_module.S_ISREG(metadata.st_mode)
        ):
            raise ValueError
        return
    current = anchor
    components = path.parts[1:] if path.is_absolute() else path.parts
    for component in components:
        current = current / component
        metadata = current.lstat()
        if stat_module.S_ISLNK(metadata.st_mode) or _is_windows_reparse_point(
            current, metadata
        ):
            raise ValueError
        is_final = current == path
        if is_final and not stat_module.S_ISREG(metadata.st_mode):
            raise ValueError
        if not is_final and not stat_module.S_ISDIR(metadata.st_mode):
            raise ValueError


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _controller_file_from_env() -> Path:
    raw_source = os.environ.get(_SOURCE_ENV)
    if raw_source is None:
        pytest.skip(_SOURCE_SKIP)
    try:
        candidate = Path(raw_source)
        if not candidate.is_absolute():
            raise ValueError
        _attest_regular_non_reparse_file(candidate)
        resolved = candidate.resolve(strict=True)
        _attest_regular_non_reparse_file(resolved)
        if any(
            _is_within(resolved, root.resolve(strict=False))
            for root in _DEPLOY_OUTPUT_ROOTS
        ):
            raise ValueError
    except (OSError, RuntimeError, ValueError):
        raise ValueError(_SOURCE_REJECTION) from None
    return resolved


def _read_controller_source_bytes(source: Path) -> bytes:
    try:
        return source.read_bytes()
    except OSError:
        raise ValueError(_SOURCE_REJECTION) from None


def _prepare_controller_source(source_bytes: bytes):
    try:
        return prepare_historical_batch(
            source_bytes,
            profile=registered_profile("forzy-history-2026-05-19-v1"),
            asset_id="forzy-motor-01",
            ingested_at=datetime(2026, 8, 22, 12, tzinfo=timezone.utc),
        )
    except Exception:
        pass
    raise ValueError(_PREPARATION_REJECTION) from None


def test_controller_source_skips_only_when_environment_variable_is_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(_SOURCE_ENV, raising=False)

    with pytest.raises(pytest.skip.Exception, match=_SOURCE_SKIP):
        _controller_file_from_env()


@pytest.mark.parametrize(
    "unsafe_kind",
    ["empty", "relative", "missing", "directory", "root-directory"],
)
def test_present_controller_values_fail_closed_without_path_disclosure(
    unsafe_kind: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controlled_source = Path(__file__).resolve()
    if unsafe_kind == "empty":
        raw_source = ""
    elif unsafe_kind == "relative":
        raw_source = "relative-source"
    elif unsafe_kind == "missing":
        raw_source = str(
            controlled_source.with_name("__task7_missing_source_boundary__")
        )
    elif unsafe_kind == "directory":
        raw_source = str(controlled_source.parent)
    else:
        raw_source = controlled_source.anchor
    monkeypatch.setenv(_SOURCE_ENV, raw_source)

    with pytest.raises(ValueError) as error:
        _controller_file_from_env()

    assert str(error.value) == _SOURCE_REJECTION
    if raw_source:
        assert raw_source not in str(error.value)


def test_existing_relative_regular_file_is_rejected_by_the_absolute_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = Path(__file__).resolve()
    relative_source = Path(os.path.relpath(source, start=Path.cwd()))
    assert not relative_source.is_absolute()
    assert relative_source.is_file()
    raw_source = os.fspath(relative_source)
    monkeypatch.setenv(_SOURCE_ENV, raw_source)

    try:
        _controller_file_from_env()
    except ValueError as error:
        assert str(error) == _SOURCE_REJECTION
        assert raw_source not in str(error)
    else:
        pytest.fail("RED:T7:existing-relative-file-accepted")


def test_deploy_output_source_is_rejected_without_path_disclosure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = Path(__file__).resolve()
    raw_source = str(source)
    monkeypatch.setattr(
        sys.modules[__name__],
        "_DEPLOY_OUTPUT_ROOTS",
        (source.parent,),
    )
    monkeypatch.setenv(_SOURCE_ENV, raw_source)

    with pytest.raises(ValueError) as error:
        _controller_file_from_env()

    assert str(error.value) == _SOURCE_REJECTION
    assert raw_source not in str(error.value)


@pytest.mark.parametrize("reparse_location", ["file", "parent"])
def test_file_or_parent_reparse_source_is_rejected_without_path_disclosure(
    reparse_location: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = Path(__file__).resolve()
    flagged_path = source if reparse_location == "file" else source.parent
    raw_source = str(source)
    monkeypatch.setattr(
        sys.modules[__name__],
        "_is_windows_reparse_point",
        lambda path, metadata: Path(path) == flagged_path,
    )
    monkeypatch.setenv(_SOURCE_ENV, raw_source)

    with pytest.raises(ValueError) as error:
        _controller_file_from_env()

    assert str(error.value) == _SOURCE_REJECTION
    assert raw_source not in str(error.value)


@pytest.mark.parametrize(
    ("symlink_location", "ancestor_index"),
    [("file", None), ("parent", 0), ("deep-ancestor", 2)],
    ids=["file", "parent", "deep-ancestor"],
)
def test_stat_symlink_file_or_ancestor_is_rejected_without_path_disclosure(
    symlink_location: str,
    ancestor_index: int | None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = Path(__file__).resolve()
    flagged_path = source if ancestor_index is None else source.parents[ancestor_index]
    raw_source = str(source)
    real_lstat = Path.lstat
    real_isdir = stat_module.S_ISDIR
    real_isreg = stat_module.S_ISREG
    symlink_mode = stat_module.S_IFLNK | 0o777

    def symlink_lstat(path: Path):
        metadata = real_lstat(path)
        if path == flagged_path:
            return SimpleNamespace(
                st_mode=symlink_mode,
                st_file_attributes=0,
            )
        return metadata

    def target_isdir(mode: int) -> bool:
        if mode == symlink_mode:
            return symlink_location != "file"
        return real_isdir(mode)

    def target_isreg(mode: int) -> bool:
        if mode == symlink_mode:
            return symlink_location == "file"
        return real_isreg(mode)

    monkeypatch.setattr(Path, "lstat", symlink_lstat)
    monkeypatch.setattr(stat_module, "S_ISDIR", target_isdir)
    monkeypatch.setattr(stat_module, "S_ISREG", target_isreg)
    monkeypatch.setenv(_SOURCE_ENV, raw_source)

    try:
        _controller_file_from_env()
    except ValueError as error:
        assert str(error) == _SOURCE_REJECTION
        assert raw_source not in str(error)
    else:
        pytest.fail(f"RED:T7:stat-symlink-{symlink_location}-accepted")


def test_filesystem_attestation_errors_are_sanitized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = Path(__file__).resolve()
    raw_source = str(source)
    real_lstat = Path.lstat

    def failing_lstat(path: Path) -> os.stat_result:
        if path == source:
            raise OSError(f"filesystem detail containing {raw_source}")
        return real_lstat(path)

    monkeypatch.setattr(Path, "lstat", failing_lstat)
    monkeypatch.setenv(_SOURCE_ENV, raw_source)

    with pytest.raises(ValueError) as error:
        _controller_file_from_env()

    assert str(error.value) == _SOURCE_REJECTION
    assert raw_source not in str(error.value)


def test_controller_rejection_writes_nothing_to_stdout_or_stderr(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = Path(__file__).resolve()
    raw_source = str(source)
    real_lstat = Path.lstat

    def failing_lstat(path: Path) -> os.stat_result:
        if path == source:
            raise OSError(f"filesystem detail containing {raw_source}")
        return real_lstat(path)

    monkeypatch.setattr(Path, "lstat", failing_lstat)
    monkeypatch.setenv(_SOURCE_ENV, raw_source)

    with pytest.raises(ValueError) as error:
        _controller_file_from_env()

    captured = capsys.readouterr()
    assert str(error.value) == _SOURCE_REJECTION
    assert raw_source not in str(error.value)
    assert captured.out == "", "RED:T7:rejection-wrote-stdout"
    assert captured.err == "", "RED:T7:rejection-wrote-stderr"
    assert raw_source not in captured.out
    assert raw_source not in captured.err


def test_controller_success_writes_nothing_to_stdout_or_stderr(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = Path(__file__).resolve()
    raw_source = str(source)
    monkeypatch.setenv(_SOURCE_ENV, raw_source)

    resolved = _controller_file_from_env()

    captured = capsys.readouterr()
    assert resolved == source
    assert captured.out == "", "RED:T7:success-wrote-stdout"
    assert captured.err == "", "RED:T7:success-wrote-stderr"
    assert raw_source not in captured.out
    assert raw_source not in captured.err


def test_read_controller_source_bytes_sanitizes_path_bearing_oserror_and_is_silent(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = Path(__file__).resolve()
    raw_source = str(source)
    real_read_bytes = Path.read_bytes

    def failing_read_bytes(path: Path) -> bytes:
        if path == source:
            raise OSError(f"read detail containing {raw_source}")
        return real_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", failing_read_bytes)

    try:
        _read_controller_source_bytes(source)
    except ValueError as error:
        assert str(error) == _SOURCE_REJECTION, "RED:T7:read-error-not-sanitized"
        assert raw_source not in str(error)
    except OSError:
        pytest.fail("RED:T7:read-error-not-sanitized")
    else:
        pytest.fail("RED:T7:read-error-not-raised")

    captured = capsys.readouterr()
    assert captured.out == "", "RED:T7:read-wrote-stdout"
    assert captured.err == "", "RED:T7:read-wrote-stderr"
    assert raw_source not in captured.out
    assert raw_source not in captured.err


def test_prepare_controller_source_sanitizes_importer_failures_and_is_silent(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    injected_marker = "synthetic-path-and-content-marker"

    def failing_prepare(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise ValueError(f"importer detail containing {injected_marker}")

    monkeypatch.setattr(
        sys.modules[__name__],
        "prepare_historical_batch",
        failing_prepare,
    )

    try:
        _prepare_controller_source(b"synthetic-controller-source")
    except ValueError as error:
        assert str(error) == "controller history preparation failed"
        assert injected_marker not in str(error)
        assert error.__cause__ is None
        assert error.__context__ is None
        assert error.__suppress_context__ is True
    else:
        pytest.fail("RED:T7:importer-failure-not-raised")

    captured = capsys.readouterr()
    assert captured.out == "", "RED:T7:preparation-wrote-stdout"
    assert captured.err == "", "RED:T7:preparation-wrote-stderr"
    assert injected_marker not in captured.out
    assert injected_marker not in captured.err


def test_safe_source_resolves_to_an_absolute_regular_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = Path(__file__).resolve()
    lexical_source = source.parent / ".." / source.parent.name / source.name
    monkeypatch.setenv(_SOURCE_ENV, str(lexical_source))

    resolved = _controller_file_from_env()

    assert resolved == source.resolve(strict=True)
    assert resolved.is_absolute()


@pytest.mark.real_history
def test_registered_forzy_file_matches_audited_counts() -> None:
    source = _controller_file_from_env()
    source_bytes = _read_controller_source_bytes(source)

    prepared = _prepare_controller_source(source_bytes)

    assert len(prepared.raw_rows) == 7_183
    assert len(prepared.samples) == 14_366
    assert len(
        {sample.reading.operating_cycle_id for sample in prepared.samples}
    ) == 204
    assert prepared.source_sha256 == (
        "sha256:f09a6613bf6ba3416555a15de6b381bd842474f5f3f33c20660416c7164f0be4"
    )
