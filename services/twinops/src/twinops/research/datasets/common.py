"""Strict adapter helpers shared by public datasets."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any


def raw_path(root: Path, relative_path: str) -> Path:
    path = root.joinpath(*PurePosixPath(relative_path).parts)
    if not path.is_file():
        raise FileNotFoundError(f"metadata-mapped raw file does not exist: {relative_path}")
    return path


def nonempty(entry: dict[str, Any], field: str, *, context: str) -> str:
    value = entry.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{context}: {field} must be a non-empty string")
    return value.strip()


def sequence_index(entry: dict[str, Any], *, context: str) -> int:
    value = entry.get("sequenceIndex")
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{context}: sequenceIndex must be a non-negative integer")
    return value


def started_at(entry: dict[str, Any], *, context: str) -> datetime | None:
    value = entry.get("startedAt")
    quality = entry.get("timestampQuality")
    if value is None:
        if quality != "unavailable":
            raise ValueError(f"{context}: unavailable startedAt requires timestampQuality unavailable")
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{context}: startedAt must be RFC3339 text or null")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{context}: startedAt is not valid RFC3339") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{context}: startedAt must include an explicit timezone")
    if quality not in {"source_timezone_confirmed", "source_timezone_assumed"}:
        raise ValueError(f"{context}: timestampQuality does not describe the source timezone")
    return parsed
