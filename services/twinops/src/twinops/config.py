"""Validated server-side configuration for acquisition and storage."""

from dataclasses import dataclass
import math
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True)
class Settings:
    upstream_base_url: str
    database_path: Path = Path("var/twinops.sqlite3")
    asset_tag: str = "MTR-BMB-042"
    poll_interval_seconds: float = 5.0
    request_timeout_seconds: float = 2.0
    timezone_name: str = "America/Sao_Paulo"

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
        )
