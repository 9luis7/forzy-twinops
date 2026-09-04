"""Validated configuration for the version 2 TwinOps service boundary."""

from dataclasses import dataclass, field
import ipaddress
import math
from pathlib import Path
import re
from typing import Mapping, Self
from urllib.parse import parse_qsl, urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


_SAFE_SSL_MODES = frozenset({"require", "verify-ca", "verify-full"})
_DNS_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")


def normalize_https_origin(value: str) -> str:
    """Validate and normalize a credential-free HTTPS origin."""

    if (
        not value
        or value != value.strip()
        or "\\" in value
        or "?" in value
        or "#" in value
        or any(
            ord(character) <= 0x20 or ord(character) == 0x7F
            for character in value
        )
    ):
        raise ValueError("TWINOPS_UPSTREAM_BASE_URL must be a clean https origin")

    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        raise ValueError(
            "TWINOPS_UPSTREAM_BASE_URL must be a clean https origin"
        ) from None

    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or (port is not None and not 1 <= port <= 65535)
    ):
        raise ValueError("TWINOPS_UPSTREAM_BASE_URL must be a clean https origin")

    hostname = parsed.hostname
    if "%" in hostname:
        raise ValueError("TWINOPS_UPSTREAM_BASE_URL must be a clean https origin")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        try:
            canonical_hostname = hostname.encode("idna").decode("ascii").lower()
        except UnicodeError:
            raise ValueError(
                "TWINOPS_UPSTREAM_BASE_URL must be a clean https origin"
            ) from None
        labels = canonical_hostname.split(".")
        if (
            len(canonical_hostname) > 253
            or any(_DNS_LABEL.fullmatch(label) is None for label in labels)
        ):
            raise ValueError(
                "TWINOPS_UPSTREAM_BASE_URL must be a clean https origin"
            )
        authority = canonical_hostname
    else:
        authority = (
            f"[{address.compressed}]"
            if address.version == 6
            else address.compressed
        )

    if port is not None:
        authority = f"{authority}:{port}"
    return f"https://{authority}"


def is_secure_pooled_database_url(value: str) -> bool:
    """Return whether a libpq URI selects one secure mode on a pooled host."""

    if (
        not value
        or value != value.strip()
        or "\\" in value
        or "#" in value
        or any(
            ord(character) <= 0x20 or ord(character) == 0x7F
            for character in value
        )
    ):
        return False
    try:
        parsed = urlsplit(value)
        port = parsed.port
        query = parse_qsl(
            parsed.query,
            keep_blank_values=True,
            strict_parsing=False,
            encoding="utf-8",
            errors="strict",
        )
    except (UnicodeError, ValueError):
        return False

    ssl_modes = [query_value for name, query_value in query if name == "sslmode"]
    return (
        parsed.scheme in {"postgres", "postgresql"}
        and parsed.hostname is not None
        and "-pooler" in parsed.hostname.lower()
        and not parsed.fragment
        and (port is None or 1 <= port <= 65535)
        and len(ssl_modes) == 1
        and ssl_modes[0] in _SAFE_SSL_MODES
    )


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
    vercel_environment: str | None = None
    rag_admin_enabled: bool = False
    rag_enabled: bool = False
    ai_gateway_api_key: str | None = field(default=None, repr=False)
    rag_embedding_model: str = "google/text-multilingual-embedding-002"
    rag_embedding_dimensions: int = 768
    rag_generation_model: str = "openai/gpt-5.6-luna"
    rag_gateway_timeout_seconds: float = 10.0
    rag_query_timeout_seconds: float = 10.0
    rag_manufacturer: str | None = None
    rag_equipment_model: str | None = None

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
        if self.vercel_environment not in {None, "development", "preview", "production"}:
            raise ValueError("VERCEL_ENV must be development, preview, or production")
        if self.rag_embedding_dimensions <= 0:
            raise ValueError("RAG embedding dimensions must be positive")
        if (
            not self.rag_embedding_model.strip()
            or self.rag_embedding_model != self.rag_embedding_model.strip()
            or not self.rag_generation_model.strip()
            or self.rag_generation_model != self.rag_generation_model.strip()
        ):
            raise ValueError("RAG model identifiers must not be empty")
        if (
            not math.isfinite(self.rag_gateway_timeout_seconds)
            or self.rag_gateway_timeout_seconds <= 0
        ):
            raise ValueError("RAG Gateway timeout must be positive and finite")
        if (
            not math.isfinite(self.rag_query_timeout_seconds)
            or not 1 <= self.rag_query_timeout_seconds <= 11
        ):
            raise ValueError("RAG query timeout must be in [1, 11]")
        if (self.rag_enabled or self.rag_admin_enabled) and (
            self.rag_manufacturer is None
            or not self.rag_manufacturer.strip()
            or self.rag_manufacturer != self.rag_manufacturer.strip()
            or self.rag_equipment_model is None
            or not self.rag_equipment_model.strip()
            or self.rag_equipment_model != self.rag_equipment_model.strip()
        ):
            raise ValueError(
                "RAG requires approved manufacturer and equipment model"
            )

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> Self:
        upstream_base_url = normalize_https_origin(
            env.get("TWINOPS_UPSTREAM_BASE_URL", "")
        )

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

        rag_admin_raw = env.get("RAG_ADMIN_ENABLED", "false").lower()
        if rag_admin_raw not in {"true", "false"}:
            raise ValueError("RAG_ADMIN_ENABLED must be true or false")
        rag_enabled_raw = env.get("TWINOPS_RAG_ENABLED", "false").lower()
        if rag_enabled_raw not in {"true", "false"}:
            raise ValueError("TWINOPS_RAG_ENABLED must be true or false")

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
            vercel_environment=env.get("VERCEL_ENV") or None,
            rag_admin_enabled=rag_admin_raw == "true",
            rag_enabled=rag_enabled_raw == "true",
            ai_gateway_api_key=(
                env.get("AI_GATEWAY_API_KEY")
                or env.get("VERCEL_OIDC_TOKEN")
                or None
            ),
            rag_embedding_model=env.get(
                "TWINOPS_RAG_EMBEDDING_MODEL",
                "google/text-multilingual-embedding-002",
            ),
            rag_embedding_dimensions=int(
                env.get("TWINOPS_RAG_EMBEDDING_DIMENSIONS", "768")
            ),
            rag_generation_model=env.get(
                "TWINOPS_RAG_GENERATION_MODEL", "openai/gpt-5.6-luna"
            ),
            rag_gateway_timeout_seconds=float(
                env.get("TWINOPS_RAG_GATEWAY_TIMEOUT_SECONDS", "10")
            ),
            rag_query_timeout_seconds=float(
                env.get("TWINOPS_RAG_QUERY_TIMEOUT_SECONDS", "10")
            ),
            rag_manufacturer=env.get("TWINOPS_RAG_MANUFACTURER") or None,
            rag_equipment_model=(
                env.get("TWINOPS_RAG_EQUIPMENT_MODEL") or None
            ),
        )

    def for_deploy(self) -> Self:
        if self.database_url is None:
            raise ValueError("DATABASE_URL is required for deployment")
        if not is_secure_pooled_database_url(self.database_url):
            raise ValueError(
                "DATABASE_URL must use a pooled PostgreSQL host with one safe sslmode"
            )
        return self
