"""Validated configuration for the version 2 TwinOps service boundary."""

from dataclasses import dataclass
import math
from pathlib import Path
import re
from typing import Mapping, Self
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


@dataclass(frozen=True)
class SettingsV2:
    upstream_base_url: str
    database_url: str | None = None
    database_path: Path = Path("var/twinops.sqlite3")
    asset_id: str = "forzy-motor-01"
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

        anchors = (
            self.ml_artifact_path,
            self.ml_manifest_hash,
            self.ml_model_hash,
        )
        if any(value is not None for value in anchors) and not all(
            value is not None for value in anchors
        ):
            raise ValueError("ML artifact settings must be provided together")
        for value in (self.ml_manifest_hash, self.ml_model_hash):
            if (
                value is not None
                and re.fullmatch(r"sha256:[0-9a-f]{64}", value) is None
            ):
                raise ValueError("ML artifact hashes must be lowercase SHA-256 values")

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> Self:
        upstream_base_url = env.get("TWINOPS_UPSTREAM_BASE_URL", "").rstrip("/")
        if not upstream_base_url.startswith("https://"):
            raise ValueError("TWINOPS_UPSTREAM_BASE_URL must use https")

        poll_interval_seconds = float(
            env.get("TWINOPS_POLL_INTERVAL_SECONDS", "5")
        )
        request_timeout_seconds = float(
            env.get("TWINOPS_REQUEST_TIMEOUT_SECONDS", "2")
        )
        if (
            not math.isfinite(poll_interval_seconds)
            or not math.isfinite(request_timeout_seconds)
            or poll_interval_seconds <= 0
            or request_timeout_seconds <= 0
        ):
            raise ValueError("poll interval and timeout must be positive finite numbers")

        return cls(
            upstream_base_url=upstream_base_url,
            database_url=env.get("DATABASE_URL") or None,
            database_path=Path(env.get("TWINOPS_DATABASE_PATH", "var/twinops.sqlite3")),
            asset_id=env.get("TWINOPS_ASSET_ID", "forzy-motor-01"),
            poll_interval_seconds=poll_interval_seconds,
            request_timeout_seconds=request_timeout_seconds,
            timezone_name=env.get("TWINOPS_TIMEZONE", "America/Sao_Paulo"),
            ml_artifact_path=(
                Path(env["TWINOPS_ML_ARTIFACT_PATH"])
                if env.get("TWINOPS_ML_ARTIFACT_PATH")
                else None
            ),
            ml_manifest_hash=env.get("TWINOPS_ML_MANIFEST_HASH") or None,
            ml_model_hash=env.get("TWINOPS_ML_MODEL_HASH") or None,
        )

    def for_deploy(self) -> Self:
        if self.database_url is None:
            raise ValueError("DATABASE_URL is required for deployment")
        return self
