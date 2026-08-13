"""Validated server-side configuration for acquisition and storage."""

from dataclasses import dataclass
import math
from pathlib import Path
import re
from typing import Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


@dataclass(frozen=True)
class Settings:
    upstream_base_url: str
    database_path: Path = Path("var/twinops.sqlite3")
    asset_tag: str = "MTR-BMB-042"
    poll_interval_seconds: float = 5.0
    request_timeout_seconds: float = 2.0
    timezone_name: str = "America/Sao_Paulo"
    ml_artifact_path: Path | None = None
    ml_manifest_hash: str | None = None
    ml_model_hash: str | None = None

    def __post_init__(self) -> None:
        try:
            ZoneInfo(self.timezone_name)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError(
                f"unknown TWINOPS_TIMEZONE: {self.timezone_name}"
            ) from None
        ml_values = (
            self.ml_artifact_path,
            self.ml_manifest_hash,
            self.ml_model_hash,
        )
        if any(value is not None for value in ml_values) and not all(
            value is not None for value in ml_values
        ):
            raise ValueError("ML artifact settings must be provided together")
        for value in (self.ml_manifest_hash, self.ml_model_hash):
            if (
                value is not None
                and re.fullmatch(r"sha256:[0-9a-f]{64}", value) is None
            ):
                raise ValueError("ML artifact hashes must be lowercase SHA-256 values")

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "Settings":
        url = env.get("TWINOPS_UPSTREAM_BASE_URL", "").rstrip("/")
        if not url.startswith("https://"):
            raise ValueError("TWINOPS_UPSTREAM_BASE_URL must use https")
        interval = float(env.get("TWINOPS_POLL_INTERVAL_SECONDS", "5"))
        timeout = float(env.get("TWINOPS_REQUEST_TIMEOUT_SECONDS", "2"))
        if (
            not math.isfinite(interval)
            or not math.isfinite(timeout)
            or interval <= 0
            or timeout <= 0
        ):
            raise ValueError("poll interval and timeout must be positive finite numbers")
        return cls(
            upstream_base_url=url,
            database_path=Path(
                env.get("TWINOPS_DATABASE_PATH", "var/twinops.sqlite3")
            ),
            asset_tag=env.get("TWINOPS_ASSET_TAG", "MTR-BMB-042"),
            poll_interval_seconds=interval,
            request_timeout_seconds=timeout,
            timezone_name=env.get("TWINOPS_TIMEZONE", "America/Sao_Paulo"),
            ml_artifact_path=(
                Path(env["TWINOPS_ML_ARTIFACT_PATH"])
                if env.get("TWINOPS_ML_ARTIFACT_PATH")
                else None
            ),
            ml_manifest_hash=env.get("TWINOPS_ML_MANIFEST_HASH") or None,
            ml_model_hash=env.get("TWINOPS_ML_MODEL_HASH") or None,
        )
