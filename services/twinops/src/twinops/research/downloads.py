"""Integrity helpers for externally approved public-dataset downloads."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path


_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")


def verify_archive(path: str | Path, expected_sha256: str) -> str:
    """Return an archive SHA-256, raising when it differs from the manifest."""

    archive = Path(path)
    if not archive.is_file():
        raise FileNotFoundError(f"dataset archive does not exist: {archive}")
    if not isinstance(expected_sha256, str) or not _SHA256.fullmatch(expected_sha256):
        raise ValueError("expected_sha256 must be exactly 64 hexadecimal characters")

    digest = hashlib.sha256()
    with archive.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    actual = digest.hexdigest()
    if actual != expected_sha256.lower():
        raise ValueError(
            f"SHA-256 mismatch for {archive.name}: expected {expected_sha256.lower()}, got {actual}"
        )
    return actual
