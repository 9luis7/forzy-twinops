"""Validate the server-side deployment environment without revealing values."""

import argparse
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import sys

from twinops.config_v2 import is_secure_pooled_database_url, normalize_https_origin


_REQUIRED = (
    "DATABASE_URL",
    "TWINOPS_UPSTREAM_BASE_URL",
    "TWINOPS_ML_ARTIFACT_PATH",
    "TWINOPS_ML_MANIFEST_HASH",
    "TWINOPS_ML_MODEL_HASH",
)
_MANIFEST_HASH = "sha256:fe2cbd7e1b576f04b2c6380e41ecb7c97df7faa5084c39c4b0d16db786afe7f0"
_MODEL_HASH = "sha256:68d00121edbf8c4c01cf7cd231cd57c4c8eff25661135494e3c791ca78e562ba"
_RAG_REQUIRED = (
    "TWINOPS_RAG_EMBEDDING_DIMENSIONS",
    "TWINOPS_RAG_EMBEDDING_MODEL",
    "TWINOPS_RAG_EQUIPMENT_MODEL",
    "TWINOPS_RAG_GATEWAY_TIMEOUT_SECONDS",
    "TWINOPS_RAG_GENERATION_MODEL",
    "TWINOPS_RAG_MANUFACTURER",
    "TWINOPS_RAG_QUERY_TIMEOUT_SECONDS",
)
_RAG_PREVIEW_IDENTITY_REQUIRED = (
    "RAG_PREVIEW_DATABASE_NAME",
    "RAG_PREVIEW_DATABASE_USER",
)
_RAG_EMBEDDING_MODEL = "google/text-multilingual-embedding-002"
_RAG_GENERATION_MODEL = "openai/gpt-5.6-luna"


@dataclass(frozen=True)
class DeployEnvReport:
    missing: tuple[str, ...]
    invalid: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.missing and not self.invalid


def verify_deploy_env(env: Mapping[str, str]) -> DeployEnvReport:
    required = set(_REQUIRED)
    invalid: set[str] = set()

    rag_enabled = _boolean_flag(env, "TWINOPS_RAG_ENABLED", invalid)
    admin_enabled = _boolean_flag(env, "RAG_ADMIN_ENABLED", invalid)
    vite_admin_enabled = _boolean_flag(env, "VITE_RAG_ADMIN_ENABLED", invalid)
    if rag_enabled or admin_enabled:
        required.update(_RAG_REQUIRED)
        if not (
            env.get("AI_GATEWAY_API_KEY", "").strip()
            or env.get("VERCEL_OIDC_TOKEN", "").strip()
        ):
            required.add("AI_GATEWAY_API_KEY")
    if admin_enabled:
        required.update(_RAG_PREVIEW_IDENTITY_REQUIRED)
    missing = tuple(sorted(name for name in required if not env.get(name, "").strip()))

    if "DATABASE_URL" not in missing and not _valid_database_url(env["DATABASE_URL"]):
        invalid.add("DATABASE_URL")
    if "TWINOPS_UPSTREAM_BASE_URL" not in missing and not _valid_https_url(
        env["TWINOPS_UPSTREAM_BASE_URL"]
    ):
        invalid.add("TWINOPS_UPSTREAM_BASE_URL")
    if (
        "TWINOPS_ML_ARTIFACT_PATH" not in missing
        and env["TWINOPS_ML_ARTIFACT_PATH"] != "artifacts/ml/real-forzy"
    ):
        invalid.add("TWINOPS_ML_ARTIFACT_PATH")
    if (
        "TWINOPS_ML_MANIFEST_HASH" not in missing
        and env["TWINOPS_ML_MANIFEST_HASH"] != _MANIFEST_HASH
    ):
        invalid.add("TWINOPS_ML_MANIFEST_HASH")
    if (
        "TWINOPS_ML_MODEL_HASH" not in missing
        and env["TWINOPS_ML_MODEL_HASH"] != _MODEL_HASH
    ):
        invalid.add("TWINOPS_ML_MODEL_HASH")

    exact_optional = {
        "TWINOPS_ASSET_ID": "forzy-motor-01",
        "TWINOPS_TIMEZONE": "America/Sao_Paulo",
    }
    for name, expected in exact_optional.items():
        if name in env and env[name] != expected:
            invalid.add(name)

    for name in (
        "TWINOPS_POLL_INTERVAL_SECONDS",
        "TWINOPS_REQUEST_TIMEOUT_SECONDS",
    ):
        if name in env and not _positive_finite(env[name]):
            invalid.add(name)

    if rag_enabled or admin_enabled:
        if (
            "TWINOPS_RAG_MANUFACTURER" not in missing
            and env["TWINOPS_RAG_MANUFACTURER"] != env["TWINOPS_RAG_MANUFACTURER"].strip()
        ):
            invalid.add("TWINOPS_RAG_MANUFACTURER")
        if (
            "TWINOPS_RAG_EQUIPMENT_MODEL" not in missing
            and env["TWINOPS_RAG_EQUIPMENT_MODEL"] != env["TWINOPS_RAG_EQUIPMENT_MODEL"].strip()
        ):
            invalid.add("TWINOPS_RAG_EQUIPMENT_MODEL")
        if (
            "TWINOPS_RAG_EMBEDDING_MODEL" not in missing
            and env["TWINOPS_RAG_EMBEDDING_MODEL"] != _RAG_EMBEDDING_MODEL
        ):
            invalid.add("TWINOPS_RAG_EMBEDDING_MODEL")
        if (
            "TWINOPS_RAG_GENERATION_MODEL" not in missing
            and env["TWINOPS_RAG_GENERATION_MODEL"] != _RAG_GENERATION_MODEL
        ):
            invalid.add("TWINOPS_RAG_GENERATION_MODEL")
        if (
            "TWINOPS_RAG_EMBEDDING_DIMENSIONS" not in missing
            and not _positive_integer(env["TWINOPS_RAG_EMBEDDING_DIMENSIONS"])
        ):
            invalid.add("TWINOPS_RAG_EMBEDDING_DIMENSIONS")
        for name, minimum, maximum in (
            ("TWINOPS_RAG_GATEWAY_TIMEOUT_SECONDS", 1, 10),
            ("TWINOPS_RAG_QUERY_TIMEOUT_SECONDS", 1, 11),
        ):
            if name not in missing and not _finite_in_range(env[name], minimum, maximum):
                invalid.add(name)

    if admin_enabled and env.get("VERCEL_ENV") != "preview":
        invalid.update(("RAG_ADMIN_ENABLED", "VERCEL_ENV"))
        if vite_admin_enabled:
            invalid.add("VITE_RAG_ADMIN_ENABLED")
    if vite_admin_enabled and (not admin_enabled or env.get("VERCEL_ENV") != "preview"):
        invalid.add("VITE_RAG_ADMIN_ENABLED")
    if admin_enabled:
        for name in _RAG_PREVIEW_IDENTITY_REQUIRED:
            if name not in missing and env[name] != env[name].strip():
                invalid.add(name)

    return DeployEnvReport(missing=missing, invalid=tuple(sorted(invalid)))


def _valid_database_url(value: str) -> bool:
    return is_secure_pooled_database_url(value)


def _valid_https_url(value: str) -> bool:
    try:
        normalize_https_origin(value)
        return True
    except ValueError:
        return False


def _positive_finite(value: str) -> bool:
    try:
        number = float(value)
    except ValueError:
        return False
    return math.isfinite(number) and number > 0


def _positive_integer(value: str) -> bool:
    try:
        return int(value) > 0 and str(int(value)) == value
    except ValueError:
        return False


def _finite_in_range(value: str, minimum: float, maximum: float) -> bool:
    try:
        number = float(value)
    except ValueError:
        return False
    return math.isfinite(number) and minimum <= number <= maximum


def _boolean_flag(env: Mapping[str, str], name: str, invalid: set[str]) -> bool:
    raw = env.get(name, "false")
    if raw not in {"true", "false"}:
        invalid.add(name)
        return False
    return raw == "true"


def _load_env_file(path: Path) -> dict[str, str]:
    loaded: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, raw_value = line.split("=", 1)
        name = name.strip()
        value = raw_value.strip()
        if value.startswith('"') and value.endswith('"'):
            value = json.loads(value)
        elif value.startswith("'") and value.endswith("'"):
            value = value[1:-1]
        loaded[name] = value
    return loaded


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", type=Path)
    args = parser.parse_args(argv)
    try:
        source_env = _load_env_file(args.file) if args.file else os.environ
        report = verify_deploy_env(source_env)
        if report.ok:
            print("deploy_env_ok required=5")
            return 0
        missing = ",".join(report.missing) or "-"
        invalid = ",".join(report.invalid) or "-"
        print(f"deploy_env_failed missing={missing} invalid={invalid}")
        return 1
    except Exception as exc:
        print(
            f"deploy_env_failed error_type={type(exc).__name__}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
