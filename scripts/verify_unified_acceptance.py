"""Fail-closed verifier and renderer for the unified TwinOps acceptance ledger."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal


SCHEMA_VERSION = "unified-twin-acceptance-v1"
SPEC_SHA256 = "20629d860f19a212bc2b941d6270e2316c747a0b85c473f0b51bbee6106e3a44"
PLANS = ("A", "B", "C", "D", "E")
CRITERIA = tuple(f"AC-{number:02d}" for number in range(1, 29))
SHA256 = re.compile(r"^[0-9a-f]{64}$")
PREFIXED_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
GIT_SHA = re.compile(r"^[0-9a-f]{40}$")
RESULT_NAME = re.compile(r"^build-assessments-local-causal-[A-Za-z0-9_-]+\.json$")
ATTESTATION_NAME = re.compile(
    r"^phase-b-local-causal-attestation-[A-Za-z0-9_-]+\.json$"
)
ATTESTATION_RESULT_KEYS = {
    "command", "mode", "environment", "targetFingerprint", "schemaVersion",
    "assetId", "batchId", "sourceSha256", "historyManifestSha256",
    "artifactSha256", "featureManifestSha256", "reportSha256", "configSha256",
    "modelFamily", "modelVersion", "assessmentManifestSha256", "assessmentCount",
    "candidateCount", "validatedAnchorCount", "validatedEpisodeCount",
    "anchorInvariantViolationCount", "episodeInvariantViolationCount",
    "insertedCount", "existingCount", "writesPerformed",
}
ATTESTATION_SHA_FIELDS = (
    "targetFingerprint", "batchId", "sourceSha256", "historyManifestSha256",
    "artifactSha256", "featureManifestSha256", "reportSha256", "configSha256",
    "assessmentManifestSha256",
)
ATTESTATION_COUNT_FIELDS = (
    "assessmentCount", "candidateCount", "validatedAnchorCount",
    "validatedEpisodeCount", "anchorInvariantViolationCount",
    "episodeInvariantViolationCount", "insertedCount", "existingCount",
    "writesPerformed",
)

OWNER_CRITERIA = {
    "A": ("AC-06",),
    "B": ("AC-13", "AC-14"),
    "C": (
        "AC-01", "AC-02", "AC-03", "AC-04", "AC-05", "AC-07", "AC-11",
        "AC-16", "AC-17", "AC-19", "AC-21", "AC-22", "AC-25", "AC-26", "AC-27",
    ),
    "D": ("AC-08", "AC-09", "AC-10", "AC-20", "AC-23"),
    "E": ("AC-12", "AC-15", "AC-18", "AC-24", "AC-28"),
}
HUMAN_ONLY = {"AC-18", "AC-28"}
EVIDENCE_KINDS = {"automated", "database", "preview", "human"}
GATES = {"local", "database", "preview", "human"}
ENTRY_STATUSES = {"pending", "passed", "failed", "blocked"}
PLAN_STATUSES = {"pending", "in_progress", "passed", "failed", "blocked"}
FINDING_STATUSES = {"open", "fixed", "accepted"}
SEVERITIES = {"critical", "important", "minor"}


class LedgerError(ValueError):
    """A ledger or mutation input violates a closed acceptance contract."""


@dataclass(frozen=True)
class AcceptanceEntry:
    criterion_id: str
    owner_plan: Literal["A", "B", "C", "D", "E"]
    gate: Literal["local", "database", "preview", "human"]
    allowed_evidence_kinds: tuple[Literal["automated", "database", "preview", "human"], ...]
    status: Literal["pending", "passed", "failed", "blocked"]
    evidence_kind: Literal["automated", "database", "preview", "human"] | None
    evidence_refs: tuple[str, ...]
    verified_code_commit: str | None


@dataclass(frozen=True)
class FindingEntry:
    finding_id: str
    plan: Literal["A", "B", "C", "D", "E"]
    severity: Literal["critical", "important", "minor"]
    status: Literal["open", "fixed", "accepted"]
    title: str
    introduced_sha: str
    resolved_sha: str | None
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class PlanLedger:
    plan: Literal["A", "B", "C", "D", "E"]
    status: Literal["pending", "in_progress", "passed", "failed", "blocked"]
    verified_code_commit: str | None
    review_verdict: tuple[int, int, int] | None
    finding_ids: tuple[str, ...]
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class AcceptanceReport:
    criteria: tuple[str, ...]
    entries: dict[str, AcceptanceEntry]
    plans: dict[str, PlanLedger]
    findings: dict[str, FindingEntry]


def _expected_contract(criterion_id: str) -> tuple[str, str, tuple[str, ...]]:
    owner = next(plan for plan, values in OWNER_CRITERIA.items() if criterion_id in values)
    if criterion_id == "AC-06":
        return owner, "database", ("database",)
    if criterion_id in {"AC-12", "AC-24"}:
        return owner, "preview", ("preview",)
    if criterion_id in HUMAN_ONLY:
        return owner, "human", ("human",)
    return owner, "local", ("automated",)


def _ensure_keys(value: dict, expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise LedgerError(f"{label} has unexpected or missing keys")


def _ensure_sha(value: object, label: str, *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or not GIT_SHA.fullmatch(value):
        raise LedgerError(f"{label} must be a 40-hex Git SHA")
    return value


def _load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise LedgerError(f"cannot read JSON: {path.name}") from error
    if not isinstance(value, dict):
        raise LedgerError("JSON root must be an object")
    return value


def _parse_entry(raw: object, criterion_id: str) -> AcceptanceEntry:
    if not isinstance(raw, dict):
        raise LedgerError(f"criterion {criterion_id} must be an object")
    _ensure_keys(raw, {
        "criterionId", "ownerPlan", "gate", "allowedEvidenceKinds", "status",
        "evidenceKind", "evidenceRefs", "verifiedCodeCommit",
    }, f"criterion {criterion_id}")
    if raw["criterionId"] != criterion_id:
        raise LedgerError("criterionId must match its criterion key")
    owner, gate, allowed = _expected_contract(criterion_id)
    if raw["ownerPlan"] != owner or raw["gate"] != gate or tuple(raw["allowedEvidenceKinds"]) != allowed:
        raise LedgerError(f"criterion {criterion_id} violates the frozen ownership matrix")
    if raw["gate"] not in GATES or raw["status"] not in ENTRY_STATUSES:
        raise LedgerError(f"criterion {criterion_id} has an invalid gate or status")
    if not isinstance(raw["evidenceRefs"], list) or not all(isinstance(item, str) and item for item in raw["evidenceRefs"]):
        raise LedgerError(f"criterion {criterion_id} has invalid evidence refs")
    evidence_kind = raw["evidenceKind"]
    code_sha = _ensure_sha(raw["verifiedCodeCommit"], f"criterion {criterion_id} code SHA", nullable=True)
    if evidence_kind is not None and evidence_kind not in EVIDENCE_KINDS:
        raise LedgerError(f"criterion {criterion_id} has an invalid evidence kind")
    if raw["status"] == "passed":
        if evidence_kind not in allowed or not raw["evidenceRefs"] or code_sha is None:
            raise LedgerError(f"criterion {criterion_id} passed without valid evidence")
    elif evidence_kind is not None or code_sha is not None:
        raise LedgerError(f"criterion {criterion_id} non-passed state carries closure evidence")
    return AcceptanceEntry(
        criterion_id=criterion_id, owner_plan=owner, gate=gate,
        allowed_evidence_kinds=allowed, status=raw["status"], evidence_kind=evidence_kind,
        evidence_refs=tuple(raw["evidenceRefs"]), verified_code_commit=code_sha,
    )


def _parse_finding(finding_id: str, raw: object) -> FindingEntry:
    if not isinstance(raw, dict):
        raise LedgerError(f"finding {finding_id} must be an object")
    _ensure_keys(raw, {
        "findingId", "plan", "severity", "status", "title", "introducedSha",
        "resolvedSha", "evidenceRefs",
    }, f"finding {finding_id}")
    if raw["findingId"] != finding_id or raw["plan"] not in PLANS or raw["severity"] not in SEVERITIES:
        raise LedgerError(f"finding {finding_id} has invalid identity")
    if raw["status"] not in FINDING_STATUSES or not isinstance(raw["title"], str) or not raw["title"]:
        raise LedgerError(f"finding {finding_id} has invalid state")
    introduced = _ensure_sha(raw["introducedSha"], f"finding {finding_id} introduced SHA")
    resolved = _ensure_sha(raw["resolvedSha"], f"finding {finding_id} resolved SHA", nullable=True)
    refs = raw["evidenceRefs"]
    if not isinstance(refs, list) or not all(isinstance(item, str) and item for item in refs):
        raise LedgerError(f"finding {finding_id} has invalid evidence refs")
    if raw["status"] == "open" and resolved is not None:
        raise LedgerError(f"finding {finding_id} open finding has a resolved SHA")
    if raw["status"] in {"fixed", "accepted"} and (resolved is None or not refs):
        raise LedgerError(f"finding {finding_id} resolved finding lacks evidence")
    if raw["status"] == "accepted" and raw["severity"] != "minor":
        raise LedgerError("only Minor findings may be accepted")
    return FindingEntry(finding_id, raw["plan"], raw["severity"], raw["status"], raw["title"], introduced, resolved, tuple(refs))


def _derive_plan_status(plan: str, entries: dict[str, AcceptanceEntry], findings: dict[str, FindingEntry], code_sha: str | None) -> str:
    owned = [entries[criterion] for criterion in OWNER_CRITERIA[plan]]
    plan_findings = [finding for finding in findings.values() if finding.plan == plan]
    if any(entry.status in {"failed", "blocked"} for entry in owned):
        return "blocked"
    if any(finding.status == "open" and finding.severity in {"critical", "important"} for finding in plan_findings):
        return "blocked"
    if code_sha is None:
        return "pending"
    if all(entry.status == "passed" for entry in owned) and all(
        finding.status == "fixed" for finding in plan_findings if finding.severity in {"critical", "important"}
    ):
        return "passed"
    return "in_progress"


def verify_acceptance(path: Path) -> AcceptanceReport:
    raw = _load_json(path)
    _ensure_keys(raw, {"schemaVersion", "specSha256", "criteria", "plans", "findings"}, "ledger")
    if raw["schemaVersion"] != SCHEMA_VERSION or raw["specSha256"] != SPEC_SHA256:
        raise LedgerError("ledger schema or frozen spec hash is invalid")
    if not isinstance(raw["criteria"], list) or tuple(item.get("criterionId") if isinstance(item, dict) else None for item in raw["criteria"]) != CRITERIA:
        raise LedgerError("criteria must contain AC-01 through AC-28 exactly once and in order")
    entries = {criterion: _parse_entry(value, criterion) for criterion, value in zip(CRITERIA, raw["criteria"], strict=True)}
    if not isinstance(raw["findings"], dict):
        raise LedgerError("findings must be a map")
    findings = {key: _parse_finding(key, value) for key, value in raw["findings"].items()}
    if not isinstance(raw["plans"], dict) or set(raw["plans"]) != set(PLANS):
        raise LedgerError("plans must contain A through E exactly")
    plans: dict[str, PlanLedger] = {}
    for plan in PLANS:
        value = raw["plans"][plan]
        if not isinstance(value, dict):
            raise LedgerError(f"plan {plan} must be an object")
        _ensure_keys(value, {"status", "verifiedCodeCommit", "reviewVerdict", "findingIds", "evidenceRefs"}, f"plan {plan}")
        code_sha = _ensure_sha(value["verifiedCodeCommit"], f"plan {plan} code SHA", nullable=True)
        verdict = value["reviewVerdict"]
        if verdict is None:
            parsed_verdict = None
        else:
            if not isinstance(verdict, dict):
                raise LedgerError(f"plan {plan} verdict must be an object")
            _ensure_keys(verdict, {"critical", "important", "minor"}, f"plan {plan} verdict")
            if not all(type(verdict[key]) is int and verdict[key] >= 0 for key in verdict):
                raise LedgerError(f"plan {plan} verdict is invalid")
            parsed_verdict = (verdict["critical"], verdict["important"], verdict["minor"])
        ids = value["findingIds"]
        refs = value["evidenceRefs"]
        if not isinstance(ids, list) or len(ids) != len(set(ids)) or not all(item in findings for item in ids):
            raise LedgerError(f"plan {plan} finding IDs are invalid")
        if {finding.finding_id for finding in findings.values() if finding.plan == plan} != set(ids):
            raise LedgerError(f"plan {plan} discards a prior finding")
        if not isinstance(refs, list) or not all(isinstance(item, str) and item for item in refs):
            raise LedgerError(f"plan {plan} evidence refs are invalid")
        derived = _derive_plan_status(plan, entries, findings, code_sha)
        if value["status"] not in PLAN_STATUSES or value["status"] != derived:
            raise LedgerError(f"plan {plan} status does not match cumulative ledger state")
        if (code_sha is None) != (parsed_verdict is None):
            raise LedgerError(f"plan {plan} review SHA and verdict must both be null or both be set")
        if code_sha is not None and not _git_commit_exists(code_sha):
            raise LedgerError(f"plan {plan} review SHA is not a commit")
        if parsed_verdict is not None and plan != "E":
            counts = tuple(sum(finding.plan == plan and finding.status == "open" and finding.severity == severity for finding in findings.values()) for severity in ("critical", "important", "minor"))
            if counts != parsed_verdict:
                raise LedgerError(f"plan {plan} verdict does not match cumulative open findings")
        plans[plan] = PlanLedger(plan, derived, code_sha, parsed_verdict, tuple(ids), tuple(refs))
    for entry in entries.values():
        if entry.status == "passed" and entry.verified_code_commit != plans[entry.owner_plan].verified_code_commit:
            raise LedgerError(f"criterion {entry.criterion_id} is bound to the wrong owner SHA")
    return AcceptanceReport(CRITERIA, entries, plans, findings)


def render_markdown(report: AcceptanceReport) -> str:
    lines = [
        "# Unified Twin Acceptance Ledger", "", f"- Schema: `{SCHEMA_VERSION}`", f"- Frozen spec SHA-256: `{SPEC_SHA256}`", "",
        "## Plans", "", "| Plan | Status | Verified code commit | Review verdict |", "| --- | --- | --- | --- |",
    ]
    for plan in PLANS:
        item = report.plans[plan]
        verdict = "pending" if item.review_verdict is None else "/".join(map(str, item.review_verdict))
        lines.append(f"| {plan} | {item.status} | {item.verified_code_commit or 'pending'} | {verdict} |")
    lines.extend(["", "## Acceptance criteria", "", "| Criterion | Owner | Gate | Allowed evidence | Status | Evidence |", "| --- | --- | --- | --- | --- | --- |"])
    for criterion in report.criteria:
        item = report.entries[criterion]
        lines.append(f"| {criterion} | {item.owner_plan} | {item.gate} | {', '.join(item.allowed_evidence_kinds)} | {item.status} | {', '.join(item.evidence_refs) or 'pending'} |")
    lines.extend(["", "## Findings", ""])
    if not report.findings:
        lines.append("No findings recorded.")
    else:
        lines.extend(["| ID | Plan | Severity | Status | Introduced SHA | Resolved SHA |", "| --- | --- | --- | --- | --- | --- |"])
        for finding_id in sorted(report.findings):
            item = report.findings[finding_id]
            lines.append(f"| {item.finding_id} | {item.plan} | {item.severity} | {item.status} | {item.introduced_sha} | {item.resolved_sha or 'pending'} |")
    return "\n".join(lines) + "\n"


def _canonical_json(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", delete=False) as temporary:
        temporary.write(data)
        temporary.flush()
        os.fsync(temporary.fileno())
        temporary_path = Path(temporary.name)
    try:
        os.replace(temporary_path, path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()
    if path.read_bytes() != data:
        raise LedgerError(f"atomic write could not be byte-verified: {path.name}")


def _write_mutated_ledger(path: Path, ledger: dict) -> None:
    encoded = _canonical_json(ledger)
    with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".json", delete=False) as candidate:
        candidate.write(encoded)
        candidate.flush()
        os.fsync(candidate.fileno())
        candidate_path = Path(candidate.name)
    try:
        report = verify_acceptance(candidate_path)
    finally:
        if candidate_path.exists():
            candidate_path.unlink()
    rendered = render_markdown(report).encode("utf-8")
    markdown_path = path.with_suffix(".md")
    before_json = path.read_bytes()
    before_markdown = markdown_path.read_bytes() if markdown_path.exists() else None
    try:
        _atomic_write(path, encoded)
        _atomic_write(markdown_path, rendered)
    except Exception:
        _atomic_write(path, before_json)
        if before_markdown is not None:
            _atomic_write(markdown_path, before_markdown)
        raise
    if markdown_path.read_bytes() != rendered:
        raise LedgerError("rendered Markdown could not be byte-verified")


def _git_commit_exists(sha: str) -> bool:
    result = subprocess.run(["git", "cat-file", "-e", f"{sha}^{{commit}}"], capture_output=True, text=True, check=False)
    return result.returncode == 0


def _review_input(path: Path) -> dict:
    review = _load_json(path)
    _ensure_keys(review, {"schemaVersion", "plan", "reviewedSha", "verdict", "findings"}, "review")
    if review["schemaVersion"] != "finding-review-v1" or review["plan"] not in PLANS:
        raise LedgerError("review has invalid schema or plan")
    _ensure_sha(review["reviewedSha"], "reviewed SHA")
    if not _git_commit_exists(review["reviewedSha"]):
        raise LedgerError("reviewed SHA is not a commit")
    if not isinstance(review["verdict"], dict):
        raise LedgerError("review verdict must be an object")
    _ensure_keys(review["verdict"], {"critical", "important", "minor"}, "review verdict")
    if not all(type(review["verdict"][key]) is int and review["verdict"][key] >= 0 for key in review["verdict"]):
        raise LedgerError("review verdict is invalid")
    if not isinstance(review["findings"], list):
        raise LedgerError("review findings must be a list")
    return review


def _open_counts(findings: dict[str, dict], plan: str) -> dict[str, int]:
    counts = {"critical": 0, "important": 0, "minor": 0}
    for finding in findings.values():
        if finding["plan"] == plan and finding["status"] == "open":
            counts[finding["severity"]] += 1
    return counts


def _merge_review(ledger: dict, review: dict, *, evidence_only: bool) -> None:
    plan = review["plan"]
    current = ledger["plans"][plan]
    current_sha = current["verifiedCodeCommit"]
    reviewed_sha = review["reviewedSha"]
    if not evidence_only:
        if current_sha is not None:
            ancestry = subprocess.run(["git", "merge-base", "--is-ancestor", current_sha, reviewed_sha], capture_output=True, check=False)
            if reviewed_sha == current_sha or ancestry.returncode == 1:
                raise LedgerError("stale reviewed SHA")
            if ancestry.returncode != 0:
                raise LedgerError("could not verify review SHA lineage")
        current["verifiedCodeCommit"] = reviewed_sha
        current["reviewVerdict"] = dict(review["verdict"])
    seen: set[str] = set()
    for incoming in review["findings"]:
        if not isinstance(incoming, dict):
            raise LedgerError("review finding must be an object")
        _ensure_keys(incoming, {"findingId", "severity", "status", "title", "evidenceRefs", "resolvedSha"}, "review finding")
        finding_id = incoming["findingId"]
        if not isinstance(finding_id, str) or not finding_id or finding_id in seen:
            raise LedgerError("review has duplicate or missing finding IDs")
        seen.add(finding_id)
        severity, status, title = incoming["severity"], incoming["status"], incoming["title"]
        refs, resolved = incoming["evidenceRefs"], incoming["resolvedSha"]
        if severity not in SEVERITIES or status not in FINDING_STATUSES or not isinstance(title, str) or not title:
            raise LedgerError("review finding has invalid fields")
        if not isinstance(refs, list) or not all(isinstance(item, str) and item for item in refs):
            raise LedgerError("review finding has invalid evidence refs")
        _ensure_sha(resolved, "finding resolved SHA", nullable=True)
        if status == "open" and resolved is not None:
            raise LedgerError("open finding has a resolved SHA")
        if status in {"fixed", "accepted"} and (resolved != reviewed_sha or not refs):
            raise LedgerError("resolved finding must carry this review SHA and evidence")
        if status == "accepted" and severity != "minor":
            raise LedgerError("only Minor findings may be accepted")
        existing = ledger["findings"].get(finding_id)
        if existing is None:
            if status != "open":
                raise LedgerError("a finding must first be opened")
            ledger["findings"][finding_id] = {
                "findingId": finding_id, "plan": plan, "severity": severity, "status": status,
                "title": title, "introducedSha": reviewed_sha, "resolvedSha": None, "evidenceRefs": refs,
            }
        else:
            if existing["plan"] != plan or existing["severity"] != severity or existing["title"] != title:
                raise LedgerError("conflicting finding lineage")
            if existing["status"] != "open" or status == "open":
                raise LedgerError("finding lineage cannot be reopened or closed twice")
            existing["status"] = status
            existing["resolvedSha"] = resolved
            existing["evidenceRefs"] = list(dict.fromkeys([*existing["evidenceRefs"], *refs]))
        if finding_id not in current["findingIds"]:
            current["findingIds"].append(finding_id)
        current["evidenceRefs"] = list(dict.fromkeys([*current["evidenceRefs"], *refs]))
    if _open_counts(ledger["findings"], plan) != review["verdict"]:
        raise LedgerError("review verdict does not equal currently open findings")
    _rederive_plan(ledger, plan)


def _rederive_plan(ledger: dict, plan: str) -> None:
    entries = {item["criterionId"]: item for item in ledger["criteria"]}
    owned = [entries[criterion] for criterion in OWNER_CRITERIA[plan]]
    findings = [finding for finding in ledger["findings"].values() if finding["plan"] == plan]
    if any(item["status"] in {"failed", "blocked"} for item in owned) or any(item["status"] == "open" and item["severity"] in {"critical", "important"} for item in findings):
        status = "blocked"
    elif ledger["plans"][plan]["verifiedCodeCommit"] is None:
        status = "pending"
    elif all(item["status"] == "passed" for item in owned) and all(item["status"] == "fixed" for item in findings if item["severity"] in {"critical", "important"}):
        status = "passed"
    else:
        status = "in_progress"
    ledger["plans"][plan]["status"] = status


def ingest_review(ledger_path: Path, review_path: Path) -> None:
    ledger = _load_json(ledger_path)
    verify_acceptance(ledger_path)
    review = _review_input(review_path)
    _merge_review(ledger, review, evidence_only=False)
    _write_mutated_ledger(ledger_path, ledger)


def ingest_evidence_review(ledger_path: Path, review_path: Path, verified_code_commit: str, evidence_commit: str) -> None:
    if not GIT_SHA.fullmatch(verified_code_commit) or not GIT_SHA.fullmatch(evidence_commit) or verified_code_commit == evidence_commit:
        raise LedgerError("verified code and evidence commits must differ and be 40-hex SHAs")
    if not _git_commit_exists(verified_code_commit) or not _git_commit_exists(evidence_commit):
        raise LedgerError("evidence review commits must exist")
    ledger = _load_json(ledger_path)
    report = verify_acceptance(ledger_path)
    review = _review_input(review_path)
    if review["plan"] != "E" or review["reviewedSha"] != evidence_commit:
        raise LedgerError("evidence review reviewedSha must equal evidence commit and plan E")
    if report.plans["E"].verified_code_commit != verified_code_commit:
        raise LedgerError("evidence review cannot change the stored E code SHA")
    code_identity = (ledger["plans"]["E"]["verifiedCodeCommit"], ledger["plans"]["E"]["reviewVerdict"])
    _merge_review(ledger, review, evidence_only=True)
    if code_identity != (ledger["plans"]["E"]["verifiedCodeCommit"], ledger["plans"]["E"]["reviewVerdict"]):
        raise LedgerError("evidence review attempted to alter the E code identity")
    _write_mutated_ledger(ledger_path, ledger)


def update_criterion(ledger_path: Path, criterion: str, status: str, evidence_kind: str | None, evidence_ref: str | None, verified_code_commit: str | None) -> None:
    ledger = _load_json(ledger_path)
    report = verify_acceptance(ledger_path)
    if criterion not in report.entries or status not in ENTRY_STATUSES:
        raise LedgerError("unknown criterion or status")
    entry = report.entries[criterion]
    expected_sha = report.plans[entry.owner_plan].verified_code_commit
    if status == "passed":
        if evidence_kind not in entry.allowed_evidence_kinds:
            raise LedgerError("evidence kind is not allowed for this criterion")
        if expected_sha is None or not evidence_ref or verified_code_commit != expected_sha:
            raise LedgerError("criterion evidence must bind to its owner code SHA")
    elif evidence_kind is not None or evidence_ref is not None or verified_code_commit is not None:
        raise LedgerError("non-passed criteria cannot carry closure evidence")
    raw_entry = next(item for item in ledger["criteria"] if item["criterionId"] == criterion)
    raw_entry.update({
        "status": status, "evidenceKind": evidence_kind if status == "passed" else None,
        "evidenceRefs": list(dict.fromkeys([*raw_entry["evidenceRefs"], *([evidence_ref] if status == "passed" else [])])),
        "verifiedCodeCommit": verified_code_commit if status == "passed" else None,
    })
    _rederive_plan(ledger, entry.owner_plan)
    _write_mutated_ledger(ledger_path, ledger)


def _parse_rfc3339(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise LedgerError("source-not-before must be RFC3339") from error
    if parsed.tzinfo is None:
        raise LedgerError("source-not-before must include an offset")
    return parsed.astimezone(UTC)


def export_local_causal_manifest(args: argparse.Namespace) -> None:
    root = Path.cwd().resolve()
    source = Path(args.source_result)
    guarded = root / "tmp" / "twinops-admin-results"
    if ".." in source.parts or not source.is_absolute() or source.parent != guarded or not RESULT_NAME.fullmatch(source.name):
        raise LedgerError("source result must be a direct guarded local-causal result")
    try:
        before_open = os.lstat(source)
    except OSError as error:
        raise LedgerError("source result is not a guarded regular file") from error
    if stat.S_ISLNK(before_open.st_mode) or (getattr(before_open, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
        raise LedgerError("source result must be a direct guarded local-causal result")
    if not stat.S_ISREG(before_open.st_mode):
        raise LedgerError("source result is not a guarded regular file")
    descriptor = None
    try:
        descriptor = os.open(source, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        source_stat = os.fstat(descriptor)
        if not stat.S_ISREG(source_stat.st_mode) or (before_open.st_dev, before_open.st_ino) != (source_stat.st_dev, source_stat.st_ino):
            raise LedgerError("source result is not a guarded regular file")
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = None
            source_bytes = handle.read()
    except OSError as error:
        raise LedgerError("source result is not a guarded regular file") from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
    if source_stat.st_size != len(source_bytes):
        raise LedgerError("source result is not a guarded regular file")
    not_before = _parse_rfc3339(args.source_not_before)
    if source_stat.st_mtime < not_before.timestamp():
        raise LedgerError("source result is stale")
    if not GIT_SHA.fullmatch(args.reviewed_code_commit) or not _git_commit_exists(args.reviewed_code_commit):
        raise LedgerError("reviewed code commit must exist")
    try:
        result = json.loads(source_bytes)
    except json.JSONDecodeError as error:
        raise LedgerError("local causal result is invalid JSON") from error
    if not isinstance(result, dict):
        raise LedgerError("local causal result is invalid JSON")
    expected_keys = {
        "schemaVersion", "kind", "environment", "mode", "writesPerformed", "batchId", "artifactSha256", "reportSha256", "configSha256", "assessmentManifestSha256", "assessmentCount", "candidateCount", "validatedAnchorCount", "validatedEpisodeCount", "anchorInvariantViolationCount", "episodeInvariantViolationCount",
    }
    _ensure_keys(result, expected_keys, "local causal result")
    if result["schemaVersion"] != "1.0" or result["kind"] != "build-assessments" or result["environment"] != "local" or result["mode"] != "dry-run" or result["writesPerformed"] != 0:
        raise LedgerError("local causal result is not a closed local dry-run")
    for key, expected in {"batchId": args.expected_batch_id, "artifactSha256": args.expected_artifact_sha256, "reportSha256": args.expected_report_sha256, "configSha256": args.expected_config_sha256}.items():
        if result[key] != expected:
            raise LedgerError("local causal result has an unexpected identity")
    if not all(isinstance(result[key], str) and SHA256.fullmatch(result[key]) for key in ("artifactSha256", "reportSha256", "configSha256", "assessmentManifestSha256")):
        raise LedgerError("local causal result has malformed hashes")
    if not all(isinstance(result[key], int) and result[key] >= 0 for key in ("assessmentCount", "candidateCount", "validatedAnchorCount", "validatedEpisodeCount", "anchorInvariantViolationCount", "episodeInvariantViolationCount")):
        raise LedgerError("local causal result has malformed counts")
    if result["validatedAnchorCount"] != result["assessmentCount"] or result["validatedEpisodeCount"] != result["candidateCount"] or result["anchorInvariantViolationCount"] != 0 or result["episodeInvariantViolationCount"] != 0:
        raise LedgerError("local causal result violates causal count invariants")
    output = {
        "schemaVersion": "1.0", "kind": "phase-b-local-causal-manifest", "reviewedCodeCommit": args.reviewed_code_commit,
        "batchId": result["batchId"], "artifactSha256": result["artifactSha256"], "reportSha256": result["reportSha256"], "configSha256": result["configSha256"], "assessmentManifestSha256": result["assessmentManifestSha256"], "assessmentCount": result["assessmentCount"], "candidateCount": result["candidateCount"], "validatedAnchorCount": result["validatedAnchorCount"], "validatedEpisodeCount": result["validatedEpisodeCount"], "anchorInvariantViolationCount": 0, "episodeInvariantViolationCount": 0, "sourceResultSha256": hashlib.sha256(source_bytes).hexdigest(),
    }
    _atomic_write(Path(args.output), _canonical_json(output))
    if _load_json(Path(args.output)) != output:
        raise LedgerError("local causal manifest could not be byte-verified")


def _compact_canonical_json(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _is_reparse(path_stat: os.stat_result) -> bool:
    return bool(
        getattr(path_stat, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    ) or stat.S_ISLNK(path_stat.st_mode)


def _attestation_identity(value: os.stat_result) -> tuple[int, int]:
    return (int(value.st_dev), int(value.st_ino))


def _attestation_file_identity(
    value: os.stat_result,
) -> tuple[int, int, int, int, int]:
    return (
        int(value.st_dev),
        int(value.st_ino),
        int(value.st_size),
        int(value.st_mtime_ns),
        int(value.st_nlink),
    )


def _require_attestation_directory(path: Path, value: os.stat_result) -> os.stat_result:
    if not stat.S_ISDIR(value.st_mode) or _is_reparse(value):
        raise LedgerError("attestation boundary must be direct and non-reparse")
    return value


def _require_attestation_file(
    path: Path,
    value: os.stat_result,
    *,
    link_count: int | None = 1,
) -> os.stat_result:
    if not stat.S_ISREG(value.st_mode) or _is_reparse(value):
        raise LedgerError("attestation file must be direct, regular, and non-reparse")
    if link_count is not None and int(value.st_nlink) != link_count:
        raise LedgerError("attestation file has an invalid link count")
    return value


def _open_windows_attestation_directory(path: Path) -> int:
    import ctypes
    from ctypes import wintypes

    create_file = ctypes.windll.kernel32.CreateFileW
    create_file.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    )
    create_file.restype = wintypes.HANDLE
    handle = create_file(
        str(path),
        0x1 | 0x80,
        0x1 | 0x2,
        None,
        3,
        0x02000000 | 0x00200000,
        None,
    )
    invalid = ctypes.c_void_p(-1).value
    if handle in (None, invalid):
        raise OSError("attestation directory handle unavailable")
    return int(handle)


def _windows_attestation_handle_info(
    handle: int,
) -> tuple[tuple[int, int], int, int]:
    import ctypes
    from ctypes import wintypes

    class ByHandleFileInformation(ctypes.Structure):
        _fields_ = (
            ("dwFileAttributes", wintypes.DWORD),
            ("ftCreationTime", wintypes.FILETIME),
            ("ftLastAccessTime", wintypes.FILETIME),
            ("ftLastWriteTime", wintypes.FILETIME),
            ("dwVolumeSerialNumber", wintypes.DWORD),
            ("nFileSizeHigh", wintypes.DWORD),
            ("nFileSizeLow", wintypes.DWORD),
            ("nNumberOfLinks", wintypes.DWORD),
            ("nFileIndexHigh", wintypes.DWORD),
            ("nFileIndexLow", wintypes.DWORD),
        )

    class FileId128(ctypes.Structure):
        _fields_ = (("Identifier", ctypes.c_ubyte * 16),)

    class FileIdInformation(ctypes.Structure):
        _fields_ = (
            ("VolumeSerialNumber", ctypes.c_ulonglong),
            ("FileId", FileId128),
        )

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    get_information = kernel32.GetFileInformationByHandle
    get_information.argtypes = (
        wintypes.HANDLE,
        ctypes.POINTER(ByHandleFileInformation),
    )
    get_information.restype = wintypes.BOOL
    get_information_ex = kernel32.GetFileInformationByHandleEx
    get_information_ex.argtypes = (
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.LPVOID,
        wintypes.DWORD,
    )
    get_information_ex.restype = wintypes.BOOL
    information = ByHandleFileInformation()
    if not get_information(wintypes.HANDLE(handle), ctypes.byref(information)):
        error = ctypes.get_last_error()
        raise OSError(error, "attestation handle identity unavailable")
    file_id_information = FileIdInformation()
    if not get_information_ex(
        wintypes.HANDLE(handle),
        18,
        ctypes.byref(file_id_information),
        ctypes.sizeof(file_id_information),
    ):
        error = ctypes.get_last_error()
        raise OSError(error, "attestation handle file ID unavailable")
    identity = (
        int(file_id_information.VolumeSerialNumber),
        int.from_bytes(bytes(file_id_information.FileId.Identifier), "little"),
    )
    return (
        identity,
        int(information.dwFileAttributes),
        int(information.nNumberOfLinks),
    )


def _require_windows_attestation_directory_handle(
    handle: int,
    expected_identity: tuple[int, int],
) -> None:
    identity, attributes, _links = _windows_attestation_handle_info(handle)
    if (
        identity != expected_identity
        or not attributes & 0x10
        or attributes & 0x400
    ):
        raise LedgerError("pinned attestation directory handle identity changed")


def _unlink_windows_attestation_file_if_identity(
    path: Path,
    expected_identity: tuple[int, int],
) -> bool:
    import ctypes
    from ctypes import wintypes

    class FileDispositionInformation(ctypes.Structure):
        _fields_ = (("DeleteFile", ctypes.c_ubyte),)

    class FileDispositionInformationEx(ctypes.Structure):
        _fields_ = (("Flags", wintypes.DWORD),)

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    )
    create_file.restype = wintypes.HANDLE
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = (wintypes.HANDLE,)
    close_handle.restype = wintypes.BOOL
    set_information = kernel32.SetFileInformationByHandle
    set_information.argtypes = (
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.LPVOID,
        wintypes.DWORD,
    )
    set_information.restype = wintypes.BOOL
    handle = create_file(
        str(path),
        0x00010000 | 0x80,
        0x1 | 0x2,
        None,
        3,
        0x00200000,
        None,
    )
    invalid = ctypes.c_void_p(-1).value
    if handle in (None, invalid):
        return False
    marked_for_deletion = False
    try:
        identity, attributes, _links = _windows_attestation_handle_info(int(handle))
        if (
            identity != expected_identity
            or attributes & 0x10
            or attributes & 0x400
        ):
            return False
        disposition_ex = FileDispositionInformationEx(0x1 | 0x2)
        marked_for_deletion = bool(
            set_information(
                wintypes.HANDLE(handle),
                21,
                ctypes.byref(disposition_ex),
                ctypes.sizeof(disposition_ex),
            )
        )
        if not marked_for_deletion and ctypes.get_last_error() in {1, 50, 87}:
            disposition = FileDispositionInformation(True)
            marked_for_deletion = bool(
                set_information(
                    wintypes.HANDLE(handle),
                    4,
                    ctypes.byref(disposition),
                    ctypes.sizeof(disposition),
                )
            )
    finally:
        close_handle(wintypes.HANDLE(handle))
    if not marked_for_deletion:
        return False
    try:
        current = os.lstat(path)
    except FileNotFoundError:
        return True
    except OSError:
        return False
    return _attestation_identity(current) != expected_identity


def _close_windows_attestation_handle(handle: int | None) -> None:
    if handle is None:
        return
    import ctypes
    from ctypes import wintypes

    close_handle = ctypes.windll.kernel32.CloseHandle
    close_handle.argtypes = (wintypes.HANDLE,)
    close_handle.restype = wintypes.BOOL
    close_handle(wintypes.HANDLE(handle))


class _PinnedAttestationBoundary:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.tmp = root / "tmp"
        self.guard = self.tmp / "twinops-admin-results"
        self.root_identity: tuple[int, int] | None = None
        self.tmp_identity: tuple[int, int] | None = None
        self.guard_identity: tuple[int, int] | None = None
        self.root_descriptor: int | None = None
        self.tmp_descriptor: int | None = None
        self.guard_descriptor: int | None = None
        self.tmp_handle: int | None = None
        self.guard_handle: int | None = None
        self._pin()

    @staticmethod
    def _directory_flags() -> int:
        return (
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0)
        )

    def _pin(self) -> None:
        try:
            root_stat = _require_attestation_directory(self.root, os.lstat(self.root))
            tmp_stat = _require_attestation_directory(self.tmp, os.lstat(self.tmp))
            guard_stat = _require_attestation_directory(self.guard, os.lstat(self.guard))
            if os.path.ismount(self.tmp) or os.path.ismount(self.guard):
                raise LedgerError("attestation boundary must not contain a mount point")
            self.root_identity = _attestation_identity(root_stat)
            self.tmp_identity = _attestation_identity(tmp_stat)
            self.guard_identity = _attestation_identity(guard_stat)
            if os.name == "nt":
                self.tmp_handle = _open_windows_attestation_directory(self.tmp)
                _require_windows_attestation_directory_handle(
                    self.tmp_handle,
                    self.tmp_identity,
                )
                self.guard_handle = _open_windows_attestation_directory(self.guard)
                _require_windows_attestation_directory_handle(
                    self.guard_handle,
                    self.guard_identity,
                )
            else:
                flags = self._directory_flags()
                self.root_descriptor = os.open(self.root, flags)
                self.tmp_descriptor = os.open(
                    "tmp", flags, dir_fd=self.root_descriptor,
                )
                self.guard_descriptor = os.open(
                    self.guard.name, flags, dir_fd=self.tmp_descriptor,
                )
            self.reattest()
        except BaseException as error:
            self.close()
            if isinstance(error, LedgerError):
                raise
            raise LedgerError("attestation boundary could not be pinned") from error

    def close(self) -> None:
        for attribute in ("guard_descriptor", "tmp_descriptor", "root_descriptor"):
            descriptor = getattr(self, attribute)
            if descriptor is not None:
                try:
                    os.close(descriptor)
                finally:
                    setattr(self, attribute, None)
        for attribute in ("guard_handle", "tmp_handle"):
            handle = getattr(self, attribute)
            if handle is not None:
                try:
                    _close_windows_attestation_handle(handle)
                finally:
                    setattr(self, attribute, None)

    def __enter__(self) -> _PinnedAttestationBoundary:
        return self

    def __exit__(self, *_exception: object) -> None:
        self.close()

    def reattest(self) -> None:
        if (
            self.root_identity is None
            or self.tmp_identity is None
            or self.guard_identity is None
        ):
            raise LedgerError("attestation boundary identity is unavailable")
        try:
            root_stat = _require_attestation_directory(self.root, os.lstat(self.root))
            tmp_stat = _require_attestation_directory(self.tmp, os.lstat(self.tmp))
            guard_stat = _require_attestation_directory(self.guard, os.lstat(self.guard))
            if (
                _attestation_identity(root_stat) != self.root_identity
                or _attestation_identity(tmp_stat) != self.tmp_identity
                or _attestation_identity(guard_stat) != self.guard_identity
            ):
                raise LedgerError("attestation boundary identity changed")
            for descriptor, identity, path in (
                (self.root_descriptor, self.root_identity, self.root),
                (self.tmp_descriptor, self.tmp_identity, self.tmp),
                (self.guard_descriptor, self.guard_identity, self.guard),
            ):
                if descriptor is not None and _attestation_identity(
                    _require_attestation_directory(path, os.fstat(descriptor))
                ) != identity:
                    raise LedgerError("pinned attestation boundary identity changed")
            for handle, identity in (
                (self.tmp_handle, self.tmp_identity),
                (self.guard_handle, self.guard_identity),
            ):
                if handle is not None:
                    _require_windows_attestation_directory_handle(handle, identity)
        except LedgerError:
            raise
        except OSError as error:
            raise LedgerError("attestation boundary could not be reattested") from error

    def raw_child_stat(self, name: str) -> os.stat_result:
        if Path(name).name != name or ":" in name:
            raise LedgerError("attestation child filename is not allowed")
        if self.guard_descriptor is not None:
            return os.stat(name, dir_fd=self.guard_descriptor, follow_symlinks=False)
        return os.lstat(self.guard / name)

    def child_stat(self, name: str, *, link_count: int | None = 1) -> os.stat_result:
        try:
            value = self.raw_child_stat(name)
        except FileNotFoundError:
            raise
        except OSError as error:
            raise LedgerError("attestation child could not be inspected") from error
        return _require_attestation_file(
            self.guard / name,
            value,
            link_count=link_count,
        )

    def open_child(self, name: str, flags: int, mode: int = 0o600) -> int:
        if self.guard_descriptor is not None:
            return os.open(name, flags, mode, dir_fd=self.guard_descriptor)
        return os.open(self.guard / name, flags, mode)

    def link_child(self, source_name: str, destination_name: str) -> None:
        if self.guard_descriptor is not None:
            os.link(
                source_name,
                destination_name,
                src_dir_fd=self.guard_descriptor,
                dst_dir_fd=self.guard_descriptor,
                follow_symlinks=False,
            )
            return
        os.link(
            self.guard / source_name,
            self.guard / destination_name,
            follow_symlinks=False,
        )

    def unlink_child(self, name: str) -> None:
        if self.guard_descriptor is not None:
            os.unlink(name, dir_fd=self.guard_descriptor)
            return
        os.unlink(self.guard / name)

    def _pinned_guard_is_intact_for_rollback(self) -> bool:
        try:
            if self.guard_descriptor is not None:
                return (
                    self.guard_identity is not None
                    and _attestation_identity(os.fstat(self.guard_descriptor))
                    == self.guard_identity
                )
            self.reattest()
            return True
        except (OSError, LedgerError):
            return False

    def unlink_if_identity(
        self, name: str, expected_identity: tuple[int, int] | None,
    ) -> bool:
        if expected_identity is None or not self._pinned_guard_is_intact_for_rollback():
            return False
        if os.name == "nt":
            return _unlink_windows_attestation_file_if_identity(
                self.guard / name,
                expected_identity,
            )
        try:
            current = self.raw_child_stat(name)
            if (
                _attestation_identity(current) != expected_identity
                or not stat.S_ISREG(current.st_mode)
                or _is_reparse(current)
            ):
                return False
            self.unlink_child(name)
            try:
                self.raw_child_stat(name)
            except FileNotFoundError:
                return True
            return False
        except (OSError, LedgerError):
            return False

    def fsync_guard(self) -> None:
        if self.guard_descriptor is not None:
            os.fsync(self.guard_descriptor)


def _attestation_paths(args: argparse.Namespace) -> tuple[Path, Path, Path]:
    root = Path.cwd().resolve()
    guarded = root / "tmp" / "twinops-admin-results"
    source = Path(args.source_result)
    output = Path(args.output)
    if not RESULT_NAME.fullmatch(source.name):
        raise LedgerError("attestation source filename is not allowed")
    if not ATTESTATION_NAME.fullmatch(output.name):
        raise LedgerError("attestation output filename is not allowed")
    if (
        not source.is_absolute()
        or ".." in source.parts
        or source.parent != guarded
    ):
        raise LedgerError("attestation source must be a direct guarded file")
    if (
        not output.is_absolute()
        or ".." in output.parts
        or output.parent != guarded
        or output == source
    ):
        raise LedgerError("attestation output must be a new direct guarded file")
    return root, source, output


def _read_attestation_source(
    args: argparse.Namespace,
    boundary: _PinnedAttestationBoundary,
    source: Path,
    output: Path,
) -> bytes:
    boundary.reattest()
    try:
        boundary.raw_child_stat(output.name)
    except FileNotFoundError:
        pass
    except OSError as error:
        raise LedgerError("attestation output cannot be inspected") from error
    else:
        raise LedgerError("attestation output must not already exist")

    try:
        before_open = boundary.child_stat(source.name)
    except OSError as error:
        raise LedgerError("attestation source is not a guarded regular file") from error
    pinned_identity = _attestation_file_identity(before_open)
    descriptor: int | None = None
    try:
        descriptor = boundary.open_child(
            source.name,
            os.O_RDONLY
            | getattr(os, "O_BINARY", 0)
            | getattr(os, "O_NOFOLLOW", 0),
        )
        opened = _require_attestation_file(source, os.fstat(descriptor))
        if _attestation_file_identity(opened) != pinned_identity:
            raise LedgerError("attestation source changed before it could be read")
        chunks: list[bytes] = []
        remaining = int(opened.st_size) + 1
        while remaining > 0:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        source_bytes = b"".join(chunks)
        after_read = _require_attestation_file(source, os.fstat(descriptor))
        if (
            _attestation_file_identity(after_read) != pinned_identity
            or len(source_bytes) != int(opened.st_size)
        ):
            raise LedgerError("attestation source changed while it was read")
    except OSError as error:
        raise LedgerError("attestation source is not a guarded regular file") from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
    try:
        after_close = boundary.child_stat(source.name)
    except OSError as error:
        raise LedgerError("attestation source changed after it was read") from error
    if _attestation_file_identity(after_close) != pinned_identity:
        raise LedgerError("attestation source changed after it was read")
    boundary.reattest()
    if opened.st_mtime < _parse_rfc3339(args.source_not_before).timestamp():
        raise LedgerError("attestation source is stale")
    return source_bytes


def _verify_attestation_git_state(reviewed_code_commit: str) -> None:
    root = Path.cwd().resolve()

    def git(*arguments: str) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                ["git", *arguments],
                cwd=root,
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError as error:
            raise LedgerError("attestation Git state could not be inspected") from error

    top_level = git("rev-parse", "--show-toplevel")
    if top_level.returncode != 0 or top_level.stderr:
        raise LedgerError("attestation must run at a Git worktree root")
    try:
        discovered_root = Path(top_level.stdout.strip()).resolve()
    except OSError as error:
        raise LedgerError("attestation Git root could not be resolved") from error
    if discovered_root != root:
        raise LedgerError("attestation must run at the Git worktree root")
    head = git("rev-parse", "--verify", "HEAD")
    current_head = head.stdout.strip()
    if (
        head.returncode != 0
        or head.stderr
        or not GIT_SHA.fullmatch(reviewed_code_commit)
        or reviewed_code_commit != current_head
    ):
        raise LedgerError("reviewed code commit must equal current HEAD")
    index_flags = git("ls-files", "-v", "-z")
    if index_flags.returncode != 0 or index_flags.stderr or any(
        not entry.startswith("H ")
        for entry in index_flags.stdout.split("\0")
        if entry
    ):
        raise LedgerError("attestation rejects hidden tracked index flags")
    tracked_status = git(
        "status", "--porcelain=v1", "--untracked-files=no", "--ignore-submodules=none",
    )
    if tracked_status.returncode != 0 or tracked_status.stdout or tracked_status.stderr:
        raise LedgerError("attestation requires a clean tracked worktree and index")
    status_result = git(
        "status", "--porcelain=v1", "--untracked-files=all", "--ignore-submodules=none",
        "--", ".", ":(exclude)services/twinops/.pytest_cache",
        ":(exclude)services/twinops/.pytest_cache/**",
    )
    if status_result.returncode != 0 or status_result.stdout or status_result.stderr:
        raise LedgerError("attestation requires a clean tracked worktree and index")


def _read_verified_attestation_child(
    boundary: _PinnedAttestationBoundary,
    name: str,
    expected_identity: tuple[int, int, int, int, int],
) -> bytes:
    descriptor: int | None = None
    try:
        descriptor = boundary.open_child(
            name,
            os.O_RDONLY
            | getattr(os, "O_BINARY", 0)
            | getattr(os, "O_NOFOLLOW", 0),
        )
        before = _require_attestation_file(
            boundary.guard / name,
            os.fstat(descriptor),
        )
        if _attestation_file_identity(before) != expected_identity:
            raise LedgerError("attestation output identity changed before verification")
        chunks: list[bytes] = []
        remaining = int(before.st_size) + 1
        while remaining > 0:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
        after = _require_attestation_file(
            boundary.guard / name,
            os.fstat(descriptor),
        )
        if (
            _attestation_file_identity(after) != expected_identity
            or len(payload) != int(before.st_size)
        ):
            raise LedgerError("attestation output identity changed during verification")
    except OSError as error:
        raise LedgerError("attestation output could not be byte-verified") from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
    try:
        after_close = boundary.child_stat(name)
    except OSError as error:
        raise LedgerError("attestation output changed after verification") from error
    if _attestation_file_identity(after_close) != expected_identity:
        raise LedgerError("attestation output changed after verification")
    return payload


def _atomic_create(
    boundary: _PinnedAttestationBoundary,
    output_name: str,
    data: bytes,
    reviewed_code_commit: str,
) -> None:
    private_name: str | None = None
    private_identity: tuple[int, int] | None = None
    published_identity: tuple[int, int] | None = None
    succeeded = False
    descriptor: int | None = None
    try:
        for _attempt in range(16):
            candidate = f".{output_name}.{secrets.token_hex(16)}.tmp"
            try:
                descriptor = boundary.open_child(
                    candidate,
                    os.O_WRONLY
                    | os.O_CREAT
                    | os.O_EXCL
                    | getattr(os, "O_BINARY", 0),
                    0o600,
                )
                private_name = candidate
                opened_raw = os.fstat(descriptor)
                private_identity = _attestation_identity(opened_raw)
                _require_attestation_file(
                    boundary.guard / candidate,
                    opened_raw,
                )
                break
            except FileExistsError:
                descriptor = None
        else:
            raise LedgerError("attestation private file allocation failed")

        if descriptor is None or private_name is None or private_identity is None:
            raise LedgerError("attestation private file identity is unavailable")
        offset = 0
        while offset < len(data):
            written = os.write(descriptor, data[offset:])
            if written <= 0:
                raise LedgerError("attestation private file could not be written")
            offset += written
        os.fsync(descriptor)
        written_stat = _require_attestation_file(
            boundary.guard / private_name,
            os.fstat(descriptor),
        )
        if (
            _attestation_identity(written_stat) != private_identity
            or int(written_stat.st_size) != len(data)
        ):
            raise LedgerError("attestation private file identity changed")
        os.close(descriptor)
        descriptor = None
        private_stat = boundary.child_stat(private_name)
        private_full_identity = _attestation_file_identity(private_stat)
        if (
            _attestation_identity(private_stat) != private_identity
            or int(private_stat.st_size) != len(data)
        ):
            raise LedgerError("attestation private file changed after close")

        try:
            boundary.raw_child_stat(output_name)
        except FileNotFoundError:
            pass
        else:
            raise LedgerError("attestation output must not already exist")
        _verify_attestation_git_state(reviewed_code_commit)
        boundary.reattest()
        try:
            boundary.link_child(private_name, output_name)
        except FileExistsError as error:
            raise LedgerError("attestation output must not already exist") from error
        except OSError as error:
            try:
                failed_link_stat = boundary.raw_child_stat(output_name)
                if (
                    stat.S_ISREG(failed_link_stat.st_mode)
                    and not _is_reparse(failed_link_stat)
                    and _attestation_identity(failed_link_stat) == private_identity
                ):
                    published_identity = private_identity
            except (FileNotFoundError, OSError, LedgerError):
                pass
            raise LedgerError("attestation output could not be atomically created") from error
        published_identity = private_identity

        linked_stat = boundary.child_stat(output_name, link_count=None)
        if (
            _attestation_identity(linked_stat) != published_identity
            or int(linked_stat.st_nlink) != 2
        ):
            raise LedgerError("attestation published link identity is invalid")
        if not boundary.unlink_if_identity(private_name, private_identity):
            raise LedgerError("attestation private file could not be removed safely")
        private_name = None

        published_stat = boundary.child_stat(output_name)
        published_full_identity = _attestation_file_identity(published_stat)
        if published_full_identity != private_full_identity:
            raise LedgerError("attestation published file identity changed")
        if _read_verified_attestation_child(
            boundary,
            output_name,
            published_full_identity,
        ) != data:
            raise LedgerError("attestation output bytes do not match")
        boundary.reattest()
        _verify_attestation_git_state(reviewed_code_commit)
        boundary.fsync_guard()
        boundary.reattest()
        if _attestation_file_identity(
            boundary.child_stat(output_name)
        ) != published_full_identity:
            raise LedgerError("attestation output changed after final verification")
        if _read_verified_attestation_child(
            boundary,
            output_name,
            published_full_identity,
        ) != data:
            raise LedgerError("attestation output bytes changed after final verification")
        succeeded = True
    except LedgerError:
        raise
    except Exception as error:
        raise LedgerError("attestation output publication failed") from error
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
        if not succeeded and published_identity is not None:
            boundary.unlink_if_identity(output_name, published_identity)
        if private_name is not None:
            boundary.unlink_if_identity(private_name, private_identity)


def _build_local_causal_attestation(
    args: argparse.Namespace,
    source_bytes: bytes,
) -> dict[str, object]:
    try:
        result = json.loads(source_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise LedgerError("local causal attestation source is invalid JSON") from error
    if not isinstance(result, dict):
        raise LedgerError("local causal attestation source must be a JSON object")
    if source_bytes != _compact_canonical_json(result):
        raise LedgerError("local causal attestation source is not canonical JSON")
    _ensure_keys(result, ATTESTATION_RESULT_KEYS, "local causal attestation source")
    expected_literals = {
        "command": "build-assessments",
        "mode": "dry-run",
        "environment": "local",
        "schemaVersion": "003",
        "assetId": "forzy-motor-01",
        "modelFamily": "robust-baseline",
        "modelVersion": "1.0.1",
        "writesPerformed": 0,
    }
    if any(result[field] != expected for field, expected in expected_literals.items()):
        raise LedgerError("local causal attestation source has invalid literals")
    if not all(
        isinstance(result[field], str) and PREFIXED_SHA256.fullmatch(result[field])
        for field in ATTESTATION_SHA_FIELDS
    ):
        raise LedgerError("local causal attestation source has malformed hashes")
    if not all(
        type(result[field]) is int and result[field] >= 0
        for field in ATTESTATION_COUNT_FIELDS
    ):
        raise LedgerError("local causal attestation source has malformed counts")
    if result["assessmentCount"] <= 0:
        raise LedgerError("local causal attestation source has no assessments")
    if not (
        result["candidateCount"] <= result["assessmentCount"]
        and result["validatedAnchorCount"] == result["assessmentCount"]
        and result["validatedEpisodeCount"] == result["candidateCount"]
        and result["anchorInvariantViolationCount"] == 0
        and result["episodeInvariantViolationCount"] == 0
        and result["insertedCount"] + result["existingCount"]
        == result["assessmentCount"]
    ):
        raise LedgerError("local causal attestation source violates count invariants")
    expected_identities = {
        "targetFingerprint": args.expected_target_fingerprint,
        "assetId": args.expected_asset_id,
        "batchId": args.expected_batch_id,
        "sourceSha256": args.expected_source_sha256,
        "historyManifestSha256": args.expected_history_manifest_sha256,
        "artifactSha256": args.expected_artifact_sha256,
        "featureManifestSha256": args.expected_feature_manifest_sha256,
        "reportSha256": args.expected_report_sha256,
        "configSha256": args.expected_config_sha256,
        "modelFamily": args.expected_model_family,
        "modelVersion": args.expected_model_version,
        "assessmentManifestSha256": args.expected_assessment_manifest_sha256,
    }
    if any(
        result[field] != expected for field, expected in expected_identities.items()
    ):
        raise LedgerError("local causal attestation source has an unexpected identity")
    output = {
        "reviewedCodeCommit": args.reviewed_code_commit,
        "batchId": result["batchId"],
        "sourceSha256": result["sourceSha256"],
        "historyManifestSha256": result["historyManifestSha256"],
        "artifactSha256": result["artifactSha256"],
        "featureManifestSha256": result["featureManifestSha256"],
        "reportSha256": result["reportSha256"],
        "configSha256": result["configSha256"],
        "modelFamily": result["modelFamily"],
        "modelVersion": result["modelVersion"],
        "assessmentManifestSha256": result["assessmentManifestSha256"],
        "assessmentCount": result["assessmentCount"],
        "candidateCount": result["candidateCount"],
        "validatedAnchorCount": result["validatedAnchorCount"],
        "validatedEpisodeCount": result["validatedEpisodeCount"],
        "anchorInvariantViolationCount": result["anchorInvariantViolationCount"],
        "episodeInvariantViolationCount": result["episodeInvariantViolationCount"],
        "sourceResultSha256": "sha256:" + hashlib.sha256(source_bytes).hexdigest(),
    }
    return output


def export_local_causal_attestation(args: argparse.Namespace) -> None:
    _verify_attestation_git_state(args.reviewed_code_commit)
    root, source_path, output_path = _attestation_paths(args)
    with _PinnedAttestationBoundary(root) as boundary:
        source_bytes = _read_attestation_source(
            args,
            boundary,
            source_path,
            output_path,
        )
        output = _build_local_causal_attestation(args, source_bytes)
        _verify_attestation_git_state(args.reviewed_code_commit)
        _atomic_create(
            boundary,
            output_path.name,
            _compact_canonical_json(output),
            args.reviewed_code_commit,
        )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("render", "verify", "ingest-review", "ingest-evidence-review", "update-criterion"):
        command = commands.add_parser(name)
        command.add_argument("--ledger", required=True)
        if name == "render": command.add_argument("--output", required=True)
        if name == "verify": command.add_argument("--require-complete", action="store_true")
        if name in {"ingest-review", "ingest-evidence-review"}: command.add_argument("--review-report", required=True)
        if name == "ingest-evidence-review":
            command.add_argument("--verified-code-commit", required=True); command.add_argument("--evidence-commit", required=True)
        if name == "update-criterion":
            command.add_argument("--criterion", required=True); command.add_argument("--status", required=True)
            command.add_argument("--evidence-kind"); command.add_argument("--evidence-ref"); command.add_argument("--verified-code-commit")
    export = commands.add_parser("export-local-causal-manifest")
    for argument in ("source-result", "source-not-before", "reviewed-code-commit", "expected-batch-id", "expected-artifact-sha256", "expected-report-sha256", "expected-config-sha256", "output"):
        export.add_argument(f"--{argument}", required=True)
    attestation = commands.add_parser("export-local-causal-attestation")
    for argument in (
        "source-result", "source-not-before", "reviewed-code-commit",
        "expected-target-fingerprint", "expected-asset-id", "expected-batch-id",
        "expected-source-sha256", "expected-history-manifest-sha256",
        "expected-artifact-sha256", "expected-feature-manifest-sha256",
        "expected-report-sha256", "expected-config-sha256", "expected-model-family",
        "expected-model-version", "expected-assessment-manifest-sha256", "output",
    ):
        attestation.add_argument(f"--{argument}", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "render":
            _atomic_write(Path(args.output), render_markdown(verify_acceptance(Path(args.ledger))).encode("utf-8"))
        elif args.command == "verify":
            report = verify_acceptance(Path(args.ledger))
            if args.require_complete:
                if any(plan.status != "passed" for plan in report.plans.values()) or any(entry.status != "passed" for entry in report.entries.values()) or any(finding.status == "open" for finding in report.findings.values()):
                    raise LedgerError("require_complete rejected incomplete ledger")
            passed = sum(entry.status == "passed" for entry in report.entries.values())
            pending = sum(entry.status == "pending" for entry in report.entries.values())
            print(f"acceptance_ledger_ok criteria=28 passed={passed} pending={pending}")
        elif args.command == "ingest-review": ingest_review(Path(args.ledger), Path(args.review_report))
        elif args.command == "ingest-evidence-review": ingest_evidence_review(Path(args.ledger), Path(args.review_report), args.verified_code_commit, args.evidence_commit)
        elif args.command == "update-criterion": update_criterion(Path(args.ledger), args.criterion, args.status, args.evidence_kind, args.evidence_ref, args.verified_code_commit)
        elif args.command == "export-local-causal-manifest": export_local_causal_manifest(args)
        else: export_local_causal_attestation(args)
    except LedgerError as error:
        print(str(error), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
