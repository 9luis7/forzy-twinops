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


@dataclass(frozen=True)
class DeployEnvReport:
    missing: tuple[str, ...]
    invalid: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.missing and not self.invalid


def verify_deploy_env(env: Mapping[str, str]) -> DeployEnvReport:
    missing = tuple(sorted(name for name in _REQUIRED if not env.get(name, "").strip()))
    invalid: set[str] = set()

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
