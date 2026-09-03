"""Validate the versioned RAG evaluation manifest without running providers."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys


MINIMUM_CASES = 30
MINIMUM_REAL_MANUAL_CASES = 15
VALID_STATUSES = {"complete", "pending_manual"}
VALID_CASE_KINDS = {"real_manual", "synthetic_fixture"}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def validate(path: Path, *, require_complete: bool = False) -> list[str]:
    errors: list[str] = []
    cases: list[dict[str, object]] = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            case = json.loads(raw)
        except json.JSONDecodeError:
            errors.append(f"line {line_number}: invalid JSON")
            continue
        if not isinstance(case, dict):
            errors.append(f"line {line_number}: case must be an object")
            continue
        cases.append(case)

    if len(cases) < MINIMUM_CASES:
        errors.append(f"expected at least {MINIMUM_CASES} cases, found {len(cases)}")
    identifiers = [case.get("id") for case in cases]
    if len(set(identifiers)) != len(identifiers) or any(
        not isinstance(identifier, str) or not identifier for identifier in identifiers
    ):
        errors.append("case ids must be unique non-empty strings")

    for case in cases:
        identifier = case.get("id", "<unknown>")
        status = case.get("status")
        case_kind = case.get("caseKind")
        if case.get("schemaVersion") != "1.0":
            errors.append(f"{identifier}: unsupported schemaVersion")
        if status not in VALID_STATUSES:
            errors.append(f"{identifier}: invalid status")
        if case_kind not in VALID_CASE_KINDS:
            errors.append(f"{identifier}: invalid caseKind")
        if not isinstance(case.get("question"), str) or not case["question"].strip():
            errors.append(f"{identifier}: question is required")
        evidence = case.get("expectedManualEvidence")
        if not isinstance(evidence, list):
            errors.append(f"{identifier}: expectedManualEvidence must be a list")
        elif status == "pending_manual" and evidence:
            errors.append(f"{identifier}: pending cases must not invent evidence")
        if status == "pending_manual" and case_kind != "real_manual":
            errors.append(f"{identifier}: only real manual cases may be pending")
        if case_kind == "synthetic_fixture":
            if status != "complete":
                errors.append(f"{identifier}: synthetic fixtures must be complete")
            if case.get("manualIdentity") is not None:
                errors.append(f"{identifier}: synthetic fixtures have no manual identity")
        if case_kind == "real_manual" and status == "pending_manual":
            if case.get("manualIdentity") is not None:
                errors.append(f"{identifier}: pending real manual identity must be null")
        if case_kind == "real_manual" and status == "complete":
            errors.extend(_validate_completed_real_manual(case, identifier))

    pending = [case.get("id") for case in cases if case.get("status") == "pending_manual"]
    if require_complete and pending:
        errors.append(
            "pending manual cases remain: " + ", ".join(str(item) for item in pending)
        )
    if require_complete:
        completed_real = [
            case
            for case in cases
            if case.get("caseKind") == "real_manual"
            and case.get("status") == "complete"
        ]
        if len(completed_real) < MINIMUM_REAL_MANUAL_CASES:
            errors.append(
                "require-complete needs at least "
                f"{MINIMUM_REAL_MANUAL_CASES} completed real manual cases"
            )
    return errors


def _validate_completed_real_manual(
    case: dict[str, object], identifier: object
) -> list[str]:
    errors: list[str] = []
    identity = case.get("manualIdentity")
    identity_valid = isinstance(identity, dict) and all(
        isinstance(identity.get(field), str) and bool(identity[field].strip())
        for field in ("manufacturer", "equipmentModel", "revision", "sourceUrl")
    )
    source_url = identity.get("sourceUrl", "") if isinstance(identity, dict) else ""
    if not identity_valid or not str(source_url).startswith("https://"):
        errors.append(
            f"{identifier}: completed real manual requires verifiable manualIdentity"
        )

    evidence = case.get("expectedManualEvidence")
    if not isinstance(evidence, list) or not evidence:
        errors.append(
            f"{identifier}: completed real manual requires non-empty evidence"
        )
        return errors
    for index, anchor in enumerate(evidence):
        label = f"{identifier}: evidence[{index}]"
        if not isinstance(anchor, dict):
            errors.append(f"{label} must be a verifiable anchor object")
            continue
        if _SHA256.fullmatch(str(anchor.get("documentSha256", ""))) is None:
            errors.append(f"{label} has invalid documentSha256")
        if _SHA256.fullmatch(str(anchor.get("contentHash", ""))) is None:
            errors.append(f"{label} has invalid contentHash")
        if not isinstance(anchor.get("chunkId"), str) or not anchor["chunkId"].strip():
            errors.append(f"{label} requires chunkId")
        if not isinstance(anchor.get("exactQuote"), str) or not anchor[
            "exactQuote"
        ].strip():
            errors.append(f"{label} requires exactQuote")
        page_start = anchor.get("pageStart")
        page_end = anchor.get("pageEnd")
        if (
            not isinstance(page_start, int)
            or isinstance(page_start, bool)
            or page_start < 1
            or not isinstance(page_end, int)
            or isinstance(page_end, bool)
            or page_end < page_start
        ):
            errors.append(f"{label} has invalid page range")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--require-complete", action="store_true")
    args = parser.parse_args(argv)
    errors = validate(args.manifest, require_complete=args.require_complete)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print("evaluation manifest valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
