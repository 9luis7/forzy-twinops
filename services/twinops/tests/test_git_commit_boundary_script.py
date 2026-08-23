import subprocess
import os
from pathlib import Path

import pytest


WORKTREE = Path(__file__).resolve().parents[3]
SCRIPT = WORKTREE / "scripts" / "verify_git_commit_boundary.ps1"


def _git(repository, *arguments):
    return subprocess.run(
        ["git", *arguments], cwd=repository, check=True, capture_output=True, text=True
    )


def _repository(tmp_path):
    repository = tmp_path / "repository"
    repository.mkdir()
    _git(repository, "init", "-q")
    _git(repository, "config", "user.email", "e1@example.invalid")
    _git(repository, "config", "user.name", "E1 Test")
    (repository / "tracked.txt").write_text("base\n", encoding="utf-8")
    _git(repository, "add", "tracked.txt")
    _git(repository, "commit", "-qm", "base")
    return repository


def _invoke(repository, expected_parent, paths, message="test commit"):
    escaped_paths = ", ".join(f"'{path}'" for path in paths)
    command = (
        ". $env:E1_HELPER_SCRIPT; "
        f"Invoke-ExactGitCommit -ExpectedParent '{expected_parent}' -Paths @({escaped_paths}) "
        f"-Message '{message}'"
    )
    return subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command], cwd=repository,
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "E1_HELPER_SCRIPT": str(SCRIPT)},
    )


def test_commit_boundary_helper_is_required(tmp_path):
    if not SCRIPT.is_file():
        pytest.fail("E1_COMMIT_BOUNDARY_HELPER_MISSING")

    command = (
        ". $env:E1_HELPER_SCRIPT; "
        "if (-not (Get-Command Get-ExactGitHead -ErrorAction SilentlyContinue)) { exit 41 }; "
        "if (-not (Get-Command Invoke-ExactGitCommit -ErrorAction SilentlyContinue)) { exit 42 }"
    )
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command], cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "E1_HELPER_SCRIPT": str(SCRIPT)},
    )

    assert result.returncode == 0, result.stderr


def test_commit_boundary_helper_commits_only_an_exact_changed_allowlist(tmp_path):
    repository = _repository(tmp_path)
    parent = _git(repository, "rev-parse", "HEAD").stdout.strip()
    (repository / "tracked.txt").write_text("changed\n", encoding="utf-8")

    result = _invoke(repository, parent, ["tracked.txt"])

    assert result.returncode == 0, result.stderr
    committed = result.stdout.strip()
    assert len(committed) == 40
    assert _git(repository, "rev-parse", "HEAD").stdout.strip() == committed
    assert _git(repository, "rev-parse", "HEAD^").stdout.strip() == parent
    assert _git(repository, "diff", "--cached", "--name-only").stdout == ""


@pytest.mark.parametrize("paths", [["tracked.txt", "tracked.txt"], ["..\\outside.txt"], ["missing.txt"]])
def test_commit_boundary_helper_rejects_invalid_allowlist_paths(tmp_path, paths):
    repository = _repository(tmp_path)
    parent = _git(repository, "rev-parse", "HEAD").stdout.strip()
    (repository / "tracked.txt").write_text("changed\n", encoding="utf-8")

    result = _invoke(repository, parent, paths)

    assert result.returncode != 0
    assert _git(repository, "rev-parse", "HEAD").stdout.strip() == parent


def test_commit_boundary_helper_rejects_a_pre_staged_file_without_unstaging_it(tmp_path):
    repository = _repository(tmp_path)
    parent = _git(repository, "rev-parse", "HEAD").stdout.strip()
    (repository / "tracked.txt").write_text("changed\n", encoding="utf-8")
    (repository / "extra.txt").write_text("extra\n", encoding="utf-8")
    _git(repository, "add", "extra.txt")

    result = _invoke(repository, parent, ["tracked.txt"])

    assert result.returncode != 0
    assert _git(repository, "diff", "--cached", "--name-only").stdout.strip() == "extra.txt"


def test_commit_boundary_helper_rejects_moved_parent_and_unchanged_files(tmp_path):
    repository = _repository(tmp_path)
    parent = _git(repository, "rev-parse", "HEAD").stdout.strip()
    (repository / "second.txt").write_text("move\n", encoding="utf-8")
    _git(repository, "add", "second.txt")
    _git(repository, "commit", "-qm", "move parent")

    moved = _invoke(repository, parent, ["tracked.txt"])
    unchanged = _invoke(repository, _git(repository, "rev-parse", "HEAD").stdout.strip(), ["tracked.txt"])

    assert moved.returncode != 0
    assert unchanged.returncode != 0
