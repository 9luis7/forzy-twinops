from __future__ import annotations

import hashlib
import os
import stat
import subprocess
from types import SimpleNamespace

import pytest

from twinops.research import downloads
from twinops.research.downloads import (
    ArchivePart,
    RarExtractionLimits,
    inspect_rar_archive,
    safe_extract_rar_archive,
)


class _FakeInfo:
    def __init__(
        self,
        filename: str,
        *,
        file_size: int = 4,
        compress_size: int = 2,
        kind: str = "file",
        password: bool = False,
        file_redir=None,
    ) -> None:
        self.filename = filename
        self.file_size = file_size
        self.compress_size = compress_size
        self._kind = kind
        self._password = password
        self.file_redir = file_redir

    def is_file(self) -> bool:
        return self._kind == "file"

    def is_dir(self) -> bool:
        return self._kind == "dir"

    def is_symlink(self) -> bool:
        return self._kind == "symlink"

    def needs_password(self) -> bool:
        return self._password


class _FakeRarFile:
    def __init__(
        self,
        path,
        *,
        mode,
        errors,
        crc_check,
        volumes,
        infos,
        archive_password: bool = False,
        on_exit=None,
    ) -> None:
        assert mode == "r"
        assert errors == "strict"
        assert crc_check is True
        self.path = path
        self._volumes = volumes
        self._infos = infos
        self._archive_password = archive_password
        self._on_exit = on_exit

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        if self._on_exit is not None:
            self._on_exit()
        return None

    def volumelist(self):
        return [str(path) for path in self._volumes]

    def infolist(self):
        return self._infos

    def needs_password(self) -> bool:
        return self._archive_password


def _sha256(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _install_fake_rarfile(monkeypatch, *, volumes, infos, **container_options) -> None:
    fake = SimpleNamespace(
        __version__="4.5",
        RarFile=lambda path, **kwargs: _FakeRarFile(
            path,
            volumes=volumes,
            infos=infos,
            **container_options,
            **kwargs,
        ),
    )
    monkeypatch.setattr(downloads, "_require_rarfile", lambda: fake)


def test_inspect_rar_archive_uses_strict_crc_checked_first_volume(tmp_path, monkeypatch) -> None:
    first = tmp_path / "dataset.rar"
    first.write_bytes(b"rar")
    fake = SimpleNamespace(
        __version__="4.5",
        RarFile=lambda path, **kwargs: _FakeRarFile(
            path,
            volumes=[first],
            infos=[_FakeInfo("bearing/a.csv")],
            **kwargs,
        ),
    )
    monkeypatch.setattr(downloads, "_require_rarfile", lambda: fake)

    inspected = inspect_rar_archive(
        [ArchivePart(first, _sha256(first))],
        limits=RarExtractionLimits(max_file_count=1),
    )

    assert inspected.total_bytes == 4
    assert [member.relative_path for member in inspected.members] == ["bearing/a.csv"]


@pytest.mark.parametrize(
    "member_name",
    [
        "../escape.csv",
        "/absolute.csv",
        "C:/drive.csv",
        "safe.csv:stream",
        "bad\x00name.csv",
        "bad\x1fname.csv",
        "bad<name.csv",
        "bad|name.csv",
        "wild*.csv",
        "wild?.csv",
        "wild[name].csv",
        "@members.txt",
        "safe/@members.txt",
        "CON",
        "safe/NUL.txt",
        "trailing.csv.",
        "trailing.csv ",
        "node/../escape.csv",
    ],
)
def test_inspect_rar_archive_rejects_external_tool_and_filesystem_unsafe_names(
    tmp_path, monkeypatch, member_name
) -> None:
    first = tmp_path / "dataset.rar"
    first.write_bytes(b"rar")
    fake = SimpleNamespace(
        __version__="4.5",
        RarFile=lambda path, **kwargs: _FakeRarFile(
            path,
            volumes=[first],
            infos=[_FakeInfo(member_name)],
            **kwargs,
        ),
    )
    monkeypatch.setattr(downloads, "_require_rarfile", lambda: fake)

    with pytest.raises(ValueError, match="unsafe archive member"):
        inspect_rar_archive([ArchivePart(first, _sha256(first))])


@pytest.mark.parametrize("digest", ["0" * 63, "0" * 65, "g" * 64, ""])
def test_archive_part_requires_an_exact_sha256(tmp_path, digest) -> None:
    with pytest.raises(ValueError, match="exactly 64"):
        ArchivePart(tmp_path / "dataset.rar", digest)


def test_default_rar_limits_admit_verified_largest_nasa_archive() -> None:
    limits = RarExtractionLimits()

    assert limits.max_file_count >= 6_324
    assert limits.max_total_uncompressed_bytes >= 3_502_648_779


def test_inspect_rar_archive_requires_exact_multipart_order_and_membership(
    tmp_path, monkeypatch
) -> None:
    first = tmp_path / "dataset.part1.rar"
    second = tmp_path / "dataset.part2.rar"
    third = tmp_path / "dataset.part3.rar"
    for index, path in enumerate((first, second, third), start=1):
        path.write_bytes(f"part-{index}".encode())
    infos = [_FakeInfo("bearing/a.csv")]
    expected = [ArchivePart(first, _sha256(first)), ArchivePart(second, _sha256(second))]

    _install_fake_rarfile(monkeypatch, volumes=[first, second], infos=infos)
    assert inspect_rar_archive(expected).parts == tuple(expected)

    with pytest.raises(ValueError, match="ordered caller-supplied"):
        inspect_rar_archive(list(reversed(expected)))
    with pytest.raises(ValueError, match="duplicate"):
        inspect_rar_archive([expected[0], expected[0]])

    _install_fake_rarfile(monkeypatch, volumes=[first], infos=infos)
    with pytest.raises(ValueError, match="ordered caller-supplied"):
        inspect_rar_archive(expected)

    _install_fake_rarfile(monkeypatch, volumes=[first, second], infos=infos)
    with pytest.raises(ValueError, match="ordered caller-supplied"):
        inspect_rar_archive([expected[0]])
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        inspect_rar_archive([ArchivePart(first, "0" * 64)])
    with pytest.raises(FileNotFoundError, match="does not exist"):
        inspect_rar_archive([ArchivePart(tmp_path / "missing.rar", "0" * 64)])


def test_inspect_rar_archive_rehashes_every_part_after_inspection(tmp_path, monkeypatch) -> None:
    first = tmp_path / "dataset.part1.rar"
    second = tmp_path / "dataset.part2.rar"
    first.write_bytes(b"part-1")
    second.write_bytes(b"part-2")
    parts = [ArchivePart(first, _sha256(first)), ArchivePart(second, _sha256(second))]
    _install_fake_rarfile(
        monkeypatch,
        volumes=[first, second],
        infos=[_FakeInfo("bearing/a.csv")],
        on_exit=lambda: second.write_bytes(b"changed"),
    )

    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        inspect_rar_archive(parts)


@pytest.mark.parametrize(
    ("info", "message"),
    [
        (_FakeInfo("link", kind="symlink"), "symlink"),
        (_FakeInfo("hard", file_redir=(4, 0, "target")), "redirected"),
        (_FakeInfo("copy", file_redir=(5, 0, "target")), "redirected"),
        (_FakeInfo("junction", file_redir=(3, 1, "target")), "redirected"),
        (_FakeInfo("secret", password=True), "password-protected"),
        (_FakeInfo("unknown", kind="unknown"), "unsupported"),
        (_FakeInfo("negative", file_size=-1), "invalid size"),
        (_FakeInfo("negative", compress_size=-1), "invalid size"),
    ],
)
def test_inspect_rar_archive_rejects_unsafe_member_semantics(
    tmp_path, monkeypatch, info, message
) -> None:
    first = tmp_path / "dataset.rar"
    first.write_bytes(b"rar")
    _install_fake_rarfile(monkeypatch, volumes=[first], infos=[info])

    with pytest.raises(ValueError, match=message):
        inspect_rar_archive([ArchivePart(first, _sha256(first))])


def test_inspect_rar_archive_rejects_encrypted_archive_headers(tmp_path, monkeypatch) -> None:
    first = tmp_path / "dataset.rar"
    first.write_bytes(b"rar")
    _install_fake_rarfile(
        monkeypatch,
        volumes=[first],
        infos=[_FakeInfo("bearing/a.csv")],
        archive_password=True,
    )

    with pytest.raises(ValueError, match="password-protected"):
        inspect_rar_archive([ArchivePart(first, _sha256(first))])


@pytest.mark.parametrize(
    ("infos", "limits", "message"),
    [
        (
            [_FakeInfo("a", file_size=1, compress_size=1), _FakeInfo("b", file_size=1, compress_size=1)],
            RarExtractionLimits(max_file_count=1),
            "file count",
        ),
        (
            [_FakeInfo("a", file_size=5, compress_size=2)],
            RarExtractionLimits(max_file_uncompressed_bytes=4),
            "per-file size",
        ),
        (
            [_FakeInfo("a", file_size=4, compress_size=2), _FakeInfo("b", file_size=4, compress_size=2)],
            RarExtractionLimits(max_total_uncompressed_bytes=7),
            "total uncompressed",
        ),
        (
            [_FakeInfo("a", file_size=5, compress_size=1)],
            RarExtractionLimits(max_compression_ratio=4),
            "compression-ratio",
        ),
    ],
)
def test_inspect_rar_archive_enforces_limits_before_writing(
    tmp_path, monkeypatch, infos, limits, message
) -> None:
    first = tmp_path / "dataset.rar"
    first.write_bytes(b"rar")
    _install_fake_rarfile(monkeypatch, volumes=[first], infos=infos)

    with pytest.raises(ValueError, match=message):
        inspect_rar_archive([ArchivePart(first, _sha256(first))], limits=limits)


@pytest.mark.parametrize(
    "infos",
    [
        [_FakeInfo("A.csv"), _FakeInfo("a.csv")],
        [_FakeInfo("node/child.csv"), _FakeInfo("node")],
        [_FakeInfo("node", kind="dir", file_size=0, compress_size=0), _FakeInfo("NODE", kind="dir", file_size=0, compress_size=0)],
        [
            _FakeInfo("A", kind="dir", file_size=0, compress_size=0),
            _FakeInfo("a/child.csv"),
        ],
    ],
)
def test_inspect_rar_archive_rejects_case_and_file_directory_collisions(
    tmp_path, monkeypatch, infos
) -> None:
    first = tmp_path / "dataset.rar"
    first.write_bytes(b"rar")
    _install_fake_rarfile(monkeypatch, volumes=[first], infos=infos)

    with pytest.raises(ValueError, match="collision"):
        inspect_rar_archive([ArchivePart(first, _sha256(first))])


class _FakeProcess:
    def __init__(
        self,
        command,
        *,
        stdin,
        stdout,
        stderr,
        shell,
        calls,
        content,
        returncode=0,
        timeout_once=False,
        stderr_content=b"",
        on_communicate=None,
    ) -> None:
        self.command = command
        self.stdout = stdout
        self.content = content
        self.returncode = returncode
        self.killed = False
        self.timeout_once = timeout_once
        self.stderr_content = stderr_content
        self.on_communicate = on_communicate
        self._wrote = False
        calls.append(
            {
                "command": command,
                "stdin": stdin,
                "stdout_name": stdout.name,
                "stderr": stderr,
                "shell": shell,
            }
        )

    def communicate(self, timeout=None):
        if self.timeout_once and not self.killed:
            raise subprocess.TimeoutExpired(self.command, timeout)
        if not self._wrote:
            self.stdout.write(self.content.get(self.command[-1], b""))
            self.stdout.flush()
            self._wrote = True
            if self.on_communicate is not None:
                self.on_communicate()
        return None, self.stderr_content

    def kill(self) -> None:
        self.killed = True


def test_safe_extract_rar_streams_each_member_to_python_owned_targets(tmp_path, monkeypatch) -> None:
    first = tmp_path / "dataset.rar"
    first.write_bytes(b"rar")
    infos = [
        _FakeInfo("bearing", kind="dir", file_size=0, compress_size=0),
        _FakeInfo("bearing/a.csv", file_size=4, compress_size=2),
    ]
    _install_fake_rarfile(monkeypatch, volumes=[first], infos=infos)
    calls = []
    monkeypatch.setattr(
        downloads.subprocess,
        "Popen",
        lambda command, **kwargs: _FakeProcess(
            command,
            calls=calls,
            content={"bearing/a.csv": b"data"},
            **kwargs,
        ),
    )

    destination = tmp_path / "raw"
    result = safe_extract_rar_archive(
        [ArchivePart(first, _sha256(first))],
        destination,
        seven_zip_executable="trusted-7z",
    )

    assert (destination / "bearing" / "a.csv").read_bytes() == b"data"
    assert [(item.relative_path, item.size_bytes) for item in result.files] == [
        ("bearing/a.csv", 4)
    ]
    assert len(calls) == 1
    call = calls[0]
    assert isinstance(call["command"], list)
    assert call["shell"] is False
    assert "--" in call["command"]
    assert call["command"].index("--") < len(call["command"]) - 2
    assert not any(argument.startswith("-o") for argument in call["command"])
    assert isinstance(call["stdout_name"], int)


def _install_fake_process(monkeypatch, *, calls, content, **process_options) -> None:
    monkeypatch.setattr(
        downloads.subprocess,
        "Popen",
        lambda command, **kwargs: _FakeProcess(
            command,
            calls=calls,
            content=content,
            **process_options,
            **kwargs,
        ),
    )


def _single_file_rar(tmp_path, monkeypatch, *, advertised_size=4):
    first = tmp_path / "dataset.rar"
    first.write_bytes(b"rar")
    _install_fake_rarfile(
        monkeypatch,
        volumes=[first],
        infos=[_FakeInfo("bearing/a.csv", file_size=advertised_size, compress_size=2)],
    )
    return first


def test_safe_extract_rar_accepts_an_existing_empty_destination(tmp_path, monkeypatch) -> None:
    first = _single_file_rar(tmp_path, monkeypatch)
    _install_fake_process(monkeypatch, calls=[], content={"bearing/a.csv": b"data"})
    destination = tmp_path / "raw"
    destination.mkdir()

    safe_extract_rar_archive([ArchivePart(first, _sha256(first))], destination)

    assert (destination / "bearing" / "a.csv").read_bytes() == b"data"


def test_safe_extract_rar_times_out_and_removes_only_temporary_output(tmp_path, monkeypatch) -> None:
    first = _single_file_rar(tmp_path, monkeypatch)
    calls = []
    _install_fake_process(
        monkeypatch,
        calls=calls,
        content={"bearing/a.csv": b"partial"},
        timeout_once=True,
    )
    destination = tmp_path / "raw"

    with pytest.raises(TimeoutError, match="per-member timeout"):
        safe_extract_rar_archive(
            [ArchivePart(first, _sha256(first))],
            destination,
            limits=RarExtractionLimits(member_timeout_seconds=0.01),
        )

    assert not destination.exists()
    assert not list(tmp_path.glob(".raw-rar-extract-*"))


def test_safe_extract_rar_preserves_base_exception_and_stops_7z(tmp_path, monkeypatch) -> None:
    first = _single_file_rar(tmp_path, monkeypatch)
    process = _FakeProcess(
        ["7z", "x", "--", str(first), "bearing/a.csv"],
        stdin=subprocess.DEVNULL,
        stdout=SimpleNamespace(name=1, write=lambda _value: None, flush=lambda: None),
        stderr=subprocess.PIPE,
        shell=False,
        calls=[],
        content={},
    )
    process.communicate = lambda timeout=None: (_ for _ in ()).throw(KeyboardInterrupt())
    monkeypatch.setattr(downloads.subprocess, "Popen", lambda *_args, **_kwargs: process)
    destination = tmp_path / "raw"

    with pytest.raises(KeyboardInterrupt):
        safe_extract_rar_archive([ArchivePart(first, _sha256(first))], destination)

    assert process.killed is True
    assert not destination.exists()
    assert not list(tmp_path.glob(".raw-rar-extract-*"))


def test_safe_extract_rar_does_not_leak_external_stderr(tmp_path, monkeypatch) -> None:
    first = _single_file_rar(tmp_path, monkeypatch)
    _install_fake_process(
        monkeypatch,
        calls=[],
        content={"bearing/a.csv": b"partial"},
        returncode=2,
        stderr_content=b"secret archive content and path",
    )
    destination = tmp_path / "raw"

    with pytest.raises(ValueError, match="exit code 2") as captured:
        safe_extract_rar_archive([ArchivePart(first, _sha256(first))], destination)

    assert "secret" not in str(captured.value)
    assert not destination.exists()


def test_safe_extract_rar_rejects_stderr_even_when_7z_returns_success(
    tmp_path, monkeypatch
) -> None:
    first = _single_file_rar(tmp_path, monkeypatch)
    _install_fake_process(
        monkeypatch,
        calls=[],
        content={"bearing/a.csv": b"data"},
        stderr_content=b"unexpected warning with sensitive member data",
    )
    destination = tmp_path / "raw"

    with pytest.raises(ValueError, match="diagnostic output") as captured:
        safe_extract_rar_archive([ArchivePart(first, _sha256(first))], destination)

    assert "sensitive" not in str(captured.value)
    assert not destination.exists()


def test_safe_extract_rar_rejects_streamed_size_mismatch(tmp_path, monkeypatch) -> None:
    first = _single_file_rar(tmp_path, monkeypatch, advertised_size=5)
    _install_fake_process(monkeypatch, calls=[], content={"bearing/a.csv": b"data"})
    destination = tmp_path / "raw"

    with pytest.raises(ValueError, match="byte count"):
        safe_extract_rar_archive([ArchivePart(first, _sha256(first))], destination)

    assert not destination.exists()


def test_safe_extract_rar_rehashes_parts_before_promotion(tmp_path, monkeypatch) -> None:
    first = _single_file_rar(tmp_path, monkeypatch)
    expected = _sha256(first)
    _install_fake_process(
        monkeypatch,
        calls=[],
        content={"bearing/a.csv": b"data"},
        on_communicate=lambda: first.write_bytes(b"changed"),
    )
    destination = tmp_path / "raw"

    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        safe_extract_rar_archive([ArchivePart(first, expected)], destination)

    assert not destination.exists()


def test_safe_extract_rar_revalidates_staging_after_source_rehash(
    tmp_path, monkeypatch
) -> None:
    first = _single_file_rar(tmp_path, monkeypatch)
    _install_fake_process(monkeypatch, calls=[], content={"bearing/a.csv": b"data"})
    real_verify = downloads.verify_archive
    verify_count = 0

    def tampering_verify(path, expected_sha256):
        nonlocal verify_count
        result = real_verify(path, expected_sha256)
        verify_count += 1
        if verify_count == 3:
            staging = next(tmp_path.glob(".raw-rar-extract-*"))
            (staging / "bearing" / "a.csv").write_bytes(b"evil")
        return result

    monkeypatch.setattr(downloads, "verify_archive", tampering_verify)
    destination = tmp_path / "raw"

    with pytest.raises(ValueError, match="streamed RAR inventory"):
        safe_extract_rar_archive([ArchivePart(first, _sha256(first))], destination)

    assert not destination.exists()
    assert not list(tmp_path.glob(".raw-rar-extract-*"))


@pytest.mark.parametrize("error_type", [RuntimeError, KeyboardInterrupt, SystemExit])
@pytest.mark.parametrize("rename_happened", [False, True])
def test_safe_extract_rar_rolls_back_when_replace_raises(
    tmp_path, monkeypatch, error_type, rename_happened
) -> None:
    first = _single_file_rar(tmp_path, monkeypatch)
    _install_fake_process(monkeypatch, calls=[], content={"bearing/a.csv": b"data"})
    destination = tmp_path / "raw"
    real_replace = downloads.Path.replace
    original = error_type("replace failed")

    def failing_replace(path, target):
        if rename_happened:
            real_replace(path, target)
        raise original

    monkeypatch.setattr(downloads.Path, "replace", failing_replace)

    with pytest.raises(error_type) as captured:
        safe_extract_rar_archive([ArchivePart(first, _sha256(first))], destination)

    assert captured.value is original
    assert not getattr(original, "__notes__", [])
    assert not destination.exists()
    assert not list(tmp_path.glob(".raw-rar-extract-*"))


@pytest.mark.parametrize("rename_happened", [False, True])
def test_safe_extract_rar_restores_preexisting_empty_destination_after_replace_error(
    tmp_path, monkeypatch, rename_happened
) -> None:
    first = _single_file_rar(tmp_path, monkeypatch)
    _install_fake_process(monkeypatch, calls=[], content={"bearing/a.csv": b"data"})
    destination = tmp_path / "raw"
    destination.mkdir()
    real_replace = downloads.Path.replace
    original = SystemExit("interrupted after rename")

    def failing_replace(path, target):
        if rename_happened:
            real_replace(path, target)
        raise original

    monkeypatch.setattr(downloads.Path, "replace", failing_replace)

    with pytest.raises(SystemExit) as captured:
        safe_extract_rar_archive([ArchivePart(first, _sha256(first))], destination)

    assert captured.value is original
    assert destination.is_dir()
    assert not any(destination.iterdir())
    assert not getattr(original, "__notes__", [])
    assert not list(tmp_path.glob(".raw-rar-extract-*"))


def test_safe_extract_rar_does_not_remove_replaced_empty_destination(
    tmp_path, monkeypatch
) -> None:
    first = _single_file_rar(tmp_path, monkeypatch)
    _install_fake_process(monkeypatch, calls=[], content={"bearing/a.csv": b"data"})
    destination = tmp_path / "raw"
    destination.mkdir()
    replacement_identity = None
    real_validate = downloads._validate_rar_filesystem

    def replace_empty_destination(*args, **kwargs):
        nonlocal replacement_identity
        result = real_validate(*args, **kwargs)
        destination.rmdir()
        destination.mkdir()
        metadata = destination.lstat()
        replacement_identity = (metadata.st_dev, metadata.st_ino)
        return result

    monkeypatch.setattr(downloads, "_validate_rar_filesystem", replace_empty_destination)

    with pytest.raises(ValueError, match="destination changed"):
        safe_extract_rar_archive([ArchivePart(first, _sha256(first))], destination)

    metadata = destination.lstat()
    assert (metadata.st_dev, metadata.st_ino) == replacement_identity
    assert not any(destination.iterdir())
    assert not list(tmp_path.glob(".raw-rar-extract-*"))


@pytest.mark.parametrize("cleanup_behavior", ["raises", "no_op"])
def test_safe_extract_rar_notes_failed_or_no_op_cleanup_without_masking_original(
    tmp_path, monkeypatch, cleanup_behavior
) -> None:
    first = _single_file_rar(tmp_path, monkeypatch)
    _install_fake_process(monkeypatch, calls=[], content={"bearing/a.csv": b"data"})
    destination = tmp_path / "raw"
    original = RuntimeError("primary replace failure")
    monkeypatch.setattr(
        downloads.Path,
        "replace",
        lambda _path, _target: (_ for _ in ()).throw(original),
    )

    if cleanup_behavior == "raises":
        monkeypatch.setattr(
            downloads.shutil,
            "rmtree",
            lambda _path: (_ for _ in ()).throw(OSError("cleanup failed")),
        )
    else:
        monkeypatch.setattr(downloads.shutil, "rmtree", lambda _path: None)

    with pytest.raises(RuntimeError) as captured:
        safe_extract_rar_archive([ArchivePart(first, _sha256(first))], destination)

    assert captured.value is original
    assert any("staging cleanup failed safely" in note for note in original.__notes__)
    assert len(list(tmp_path.glob(".raw-rar-extract-*"))) == 1
    assert not destination.exists()


def test_safe_extract_rar_does_not_remove_staging_path_after_identity_changes(
    tmp_path, monkeypatch
) -> None:
    first = _single_file_rar(tmp_path, monkeypatch)
    _install_fake_process(monkeypatch, calls=[], content={"bearing/a.csv": b"data"})
    destination = tmp_path / "raw"
    original_replace = downloads.Path.replace
    original = SystemExit("identity changed during replace")
    displaced = tmp_path / "displaced-owned-tree"

    def displace_and_replace_with_unowned(path, _target):
        original_replace(path, displaced)
        path.mkdir()
        (path / "do-not-delete.txt").write_text("unowned", encoding="utf-8")
        raise original

    monkeypatch.setattr(downloads.Path, "replace", displace_and_replace_with_unowned)

    with pytest.raises(SystemExit) as captured:
        safe_extract_rar_archive([ArchivePart(first, _sha256(first))], destination)

    assert captured.value is original
    staging = next(tmp_path.glob(".raw-rar-extract-*"))
    assert (staging / "do-not-delete.txt").read_text(encoding="utf-8") == "unowned"
    assert displaced.is_dir()
    assert any("staging cleanup failed safely" in note for note in original.__notes__)


@pytest.mark.parametrize("error_type", [RuntimeError, KeyboardInterrupt, SystemExit])
def test_safe_extract_rar_cleans_empty_staging_when_initial_identity_raises(
    tmp_path, monkeypatch, error_type
) -> None:
    first = _single_file_rar(tmp_path, monkeypatch)
    destination = tmp_path / "raw"
    original = error_type("initial identity failed")
    monkeypatch.setattr(
        downloads,
        "_directory_identity",
        lambda _path: (_ for _ in ()).throw(original),
    )

    with pytest.raises(error_type) as captured:
        safe_extract_rar_archive([ArchivePart(first, _sha256(first))], destination)

    assert captured.value is original
    assert not getattr(original, "__notes__", [])
    assert not destination.exists()
    assert not list(tmp_path.glob(".raw-rar-extract-*"))


@pytest.mark.parametrize("cleanup_behavior", ["raises", "no_op"])
def test_safe_extract_rar_notes_uninitialized_rmdir_failure_without_masking_original(
    tmp_path, monkeypatch, cleanup_behavior
) -> None:
    first = _single_file_rar(tmp_path, monkeypatch)
    destination = tmp_path / "raw"
    original = KeyboardInterrupt("initial identity failed")
    monkeypatch.setattr(
        downloads,
        "_directory_identity",
        lambda _path: (_ for _ in ()).throw(original),
    )
    if cleanup_behavior == "raises":
        monkeypatch.setattr(
            downloads.Path,
            "rmdir",
            lambda _path: (_ for _ in ()).throw(OSError("SECRET cleanup path")),
        )
    else:
        monkeypatch.setattr(downloads.Path, "rmdir", lambda _path: None)

    with pytest.raises(KeyboardInterrupt) as captured:
        safe_extract_rar_archive([ArchivePart(first, _sha256(first))], destination)

    assert captured.value is original
    assert any(
        "uninitialized staging cleanup failed safely" in note
        for note in original.__notes__
    )
    assert all("SECRET" not in note for note in original.__notes__)
    assert len(list(tmp_path.glob(".raw-rar-extract-*"))) == 1
    assert not destination.exists()


@pytest.mark.parametrize("changed_state", ["symlink", "reparse", "unowned", "non_empty"])
def test_safe_extract_rar_never_deletes_unsafe_uninitialized_staging(
    tmp_path, monkeypatch, changed_state
) -> None:
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    if changed_state == "reparse" and not reparse_flag:
        pytest.skip("platform does not expose the reparse-point flag")
    first = _single_file_rar(tmp_path, monkeypatch)
    destination = tmp_path / "raw"
    original = SystemExit("SECRET initial identity failure")
    state_changed = False
    real_lstat = downloads.Path.lstat

    def guarded_lstat(path):
        metadata = real_lstat(path)
        if state_changed and "rar-extract" in path.name:
            if changed_state == "symlink":
                return SimpleNamespace(
                    st_mode=stat.S_IFLNK,
                    st_file_attributes=0,
                    st_dev=metadata.st_dev,
                    st_ino=metadata.st_ino,
                )
            if changed_state == "reparse":
                return SimpleNamespace(
                    st_mode=metadata.st_mode,
                    st_file_attributes=reparse_flag,
                    st_dev=metadata.st_dev,
                    st_ino=metadata.st_ino,
                )
        return metadata

    def mutate_then_fail(path):
        nonlocal state_changed
        if changed_state == "unowned":
            path.rmdir()
            path.mkdir()
        elif changed_state == "non_empty":
            (path / "do-not-delete.txt").write_text("unowned", encoding="utf-8")
        state_changed = True
        raise original

    monkeypatch.setattr(downloads.Path, "lstat", guarded_lstat)
    monkeypatch.setattr(downloads, "_directory_identity", mutate_then_fail)

    with pytest.raises(SystemExit) as captured:
        safe_extract_rar_archive([ArchivePart(first, _sha256(first))], destination)

    assert captured.value is original
    staging = next(tmp_path.glob(".raw-rar-extract-*"))
    assert staging.is_dir()
    if changed_state == "non_empty":
        assert (staging / "do-not-delete.txt").read_text(encoding="utf-8") == "unowned"
    assert any(
        "uninitialized staging cleanup failed safely" in note
        for note in original.__notes__
    )
    assert all("SECRET" not in note for note in original.__notes__)
    assert not destination.exists()


def test_safe_extract_rar_rejects_extra_empty_directory_after_streaming(
    tmp_path, monkeypatch
) -> None:
    first = _single_file_rar(tmp_path, monkeypatch)
    _install_fake_process(monkeypatch, calls=[], content={"bearing/a.csv": b"data"})
    real_stream = downloads._stream_rar_member

    def tampering_stream(*args, **kwargs):
        result = real_stream(*args, **kwargs)
        target = args[2]
        (target.parent.parent / "unexpected-empty").mkdir()
        return result

    monkeypatch.setattr(downloads, "_stream_rar_member", tampering_stream)
    destination = tmp_path / "raw"

    with pytest.raises(ValueError, match="directories"):
        safe_extract_rar_archive([ArchivePart(first, _sha256(first))], destination)

    assert not destination.exists()


def test_safe_extract_rar_rejects_tampered_file_after_streaming(tmp_path, monkeypatch) -> None:
    first = _single_file_rar(tmp_path, monkeypatch)
    _install_fake_process(monkeypatch, calls=[], content={"bearing/a.csv": b"data"})
    real_stream = downloads._stream_rar_member

    def tampering_stream(*args, **kwargs):
        result = real_stream(*args, **kwargs)
        args[2].write_bytes(b"evil")
        return result

    monkeypatch.setattr(downloads, "_stream_rar_member", tampering_stream)
    destination = tmp_path / "raw"

    with pytest.raises(ValueError, match="streamed RAR inventory"):
        safe_extract_rar_archive([ArchivePart(first, _sha256(first))], destination)

    assert not destination.exists()


def test_safe_extract_rar_rejects_reparse_file_after_streaming(tmp_path, monkeypatch) -> None:
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    if not reparse_flag:
        pytest.skip("platform does not expose the reparse-point flag")
    first = _single_file_rar(tmp_path, monkeypatch)
    _install_fake_process(monkeypatch, calls=[], content={"bearing/a.csv": b"data"})
    real_lstat = downloads.Path.lstat

    def reparse_lstat(path):
        metadata = real_lstat(path)
        if path.name == "a.csv" and "rar-extract" in str(path):
            return SimpleNamespace(
                st_mode=metadata.st_mode,
                st_file_attributes=reparse_flag,
            )
        return metadata

    monkeypatch.setattr(downloads.Path, "lstat", reparse_lstat)
    destination = tmp_path / "raw"

    with pytest.raises(ValueError, match="link"):
        safe_extract_rar_archive([ArchivePart(first, _sha256(first))], destination)

    assert not destination.exists()


def test_safe_extract_rar_reports_missing_7z_action(tmp_path, monkeypatch) -> None:
    first = _single_file_rar(tmp_path, monkeypatch)
    monkeypatch.setattr(
        downloads.subprocess,
        "Popen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(FileNotFoundError()),
    )
    destination = tmp_path / "raw"

    with pytest.raises(RuntimeError, match="install 7-Zip"):
        safe_extract_rar_archive([ArchivePart(first, _sha256(first))], destination)

    assert not destination.exists()


def test_safe_extract_rar_rejects_nonempty_destination_before_inspection(tmp_path) -> None:
    destination = tmp_path / "raw"
    destination.mkdir()
    (destination / "keep.txt").write_text("keep", encoding="utf-8")

    with pytest.raises(ValueError, match="destination must be empty"):
        safe_extract_rar_archive([], destination)

    assert (destination / "keep.txt").read_text(encoding="utf-8") == "keep"


def test_safe_extract_rar_rejects_destination_reparse_before_inspection(
    tmp_path, monkeypatch
) -> None:
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    if not reparse_flag:
        pytest.skip("platform does not expose the reparse-point flag")
    destination = tmp_path / "raw"
    destination.mkdir()
    real_lstat = downloads.Path.lstat

    def reparse_lstat(path):
        metadata = real_lstat(path)
        if path == destination:
            return SimpleNamespace(
                st_mode=metadata.st_mode,
                st_file_attributes=reparse_flag,
            )
        return metadata

    monkeypatch.setattr(downloads.Path, "lstat", reparse_lstat)

    with pytest.raises(ValueError, match="destination"):
        safe_extract_rar_archive([], destination)


@pytest.mark.parametrize("version", ["4.4", "5.0", "unknown"])
def test_inspect_rar_archive_reports_incompatible_research_dependency(
    tmp_path, monkeypatch, version
) -> None:
    first = tmp_path / "dataset.rar"
    first.write_bytes(b"rar")
    monkeypatch.setattr(
        downloads.importlib,
        "import_module",
        lambda _name: SimpleNamespace(__version__=version),
    )

    with pytest.raises(RuntimeError, match=r"research extra.*rarfile>=4.5,<5"):
        inspect_rar_archive([ArchivePart(first, _sha256(first))])


def test_inspect_rar_archive_reports_missing_research_dependency(tmp_path, monkeypatch) -> None:
    first = tmp_path / "dataset.rar"
    first.write_bytes(b"rar")
    monkeypatch.setattr(
        downloads.importlib,
        "import_module",
        lambda _name: (_ for _ in ()).throw(ModuleNotFoundError()),
    )

    with pytest.raises(RuntimeError, match=r"research extra.*rarfile>=4.5,<5"):
        inspect_rar_archive([ArchivePart(first, _sha256(first))])


def test_inspect_rar_archive_rejects_encrypted_header_parse_error(tmp_path, monkeypatch) -> None:
    class PasswordRequired(Exception):
        pass

    first = tmp_path / "dataset.rar"
    first.write_bytes(b"rar")
    fake = SimpleNamespace(
        __version__="4.5",
        RarFile=lambda *_args, **_kwargs: (_ for _ in ()).throw(PasswordRequired()),
    )
    monkeypatch.setattr(downloads, "_require_rarfile", lambda: fake)

    with pytest.raises(ValueError, match="encrypted RAR headers"):
        inspect_rar_archive([ArchivePart(first, _sha256(first))])


def test_real_nasa_rar_inspection_smoke() -> None:
    path_value = os.environ.get("TWINOPS_NASA_RAR_PATH")
    if not path_value:
        pytest.skip("set TWINOPS_NASA_RAR_PATH to opt into the NASA RAR smoke")
    path = downloads.Path(path_value)
    inspected = inspect_rar_archive([ArchivePart(path, downloads.hash_file(path))])

    assert inspected.members
    assert inspected.total_bytes > 0
    assert all(member.relative_path for member in inspected.members[:5])
