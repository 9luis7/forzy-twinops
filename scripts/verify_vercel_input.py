"""Validate the file inventory emitted by ``vercel deploy --dry --json``."""

import argparse
from collections.abc import Mapping, Sequence
import json
from pathlib import Path
import sys


_ML_ARTIFACT_PREFIX = "artifacts/ml/real-forzy/"
_REQUIRED_ML_ARTIFACTS = frozenset(
    {
        f"{_ML_ARTIFACT_PREFIX}backtest-report.json",
        f"{_ML_ARTIFACT_PREFIX}feature-manifest.json",
        f"{_ML_ARTIFACT_PREFIX}model-card.md",
        f"{_ML_ARTIFACT_PREFIX}pipeline-config.json",
        f"{_ML_ARTIFACT_PREFIX}pipeline.joblib",
    }
)
_FORBIDDEN_PREFIXES = (
    "data/",
    "test-results/",
    "tmp/",
)


def _deployment_paths(payload: object) -> set[str]:
    if not isinstance(payload, Mapping):
        raise ValueError("invalid deployment input")
    files = payload.get("files")
    if not isinstance(files, list):
        raise ValueError("invalid deployment input")

    paths: set[str] = set()
    for item in files:
        if not isinstance(item, Mapping) or not isinstance(item.get("path"), str):
            raise ValueError("invalid deployment input")
        paths.add(str(item["path"]).replace("\\", "/"))
    return paths


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    args = parser.parse_args(argv)

    try:
        input_text = (
            sys.stdin.read()
            if args.input == "-"
            else Path(args.input).read_text(encoding="utf-8")
        )
        payload = json.loads(input_text)
        paths = _deployment_paths(payload)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
        print("vercel_input_check_failed code=invalid_input", file=sys.stderr)
        return 1

    forbidden_paths = {
        path
        for path in paths
        if any(path.startswith(prefix) for prefix in _FORBIDDEN_PREFIXES)
    }
    if forbidden_paths:
        print(
            "vercel_input_check_failed "
            f"code=forbidden_paths count={len(forbidden_paths)}",
            file=sys.stderr,
        )
        return 1

    missing_ml_artifacts = _REQUIRED_ML_ARTIFACTS - paths
    if missing_ml_artifacts:
        print(
            "vercel_input_check_failed "
            f"code=missing_ml_artifacts count={len(missing_ml_artifacts)}",
            file=sys.stderr,
        )
        return 1

    deployment_artifacts = {
        path for path in paths if path.startswith("artifacts/")
    }
    unexpected_ml_artifacts = deployment_artifacts - _REQUIRED_ML_ARTIFACTS
    if unexpected_ml_artifacts:
        print(
            "vercel_input_check_failed "
            f"code=unexpected_ml_artifacts count={len(unexpected_ml_artifacts)}",
            file=sys.stderr,
        )
        return 1

    print(f"vercel_input_check_ok ml_artifacts={len(_REQUIRED_ML_ARTIFACTS)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
