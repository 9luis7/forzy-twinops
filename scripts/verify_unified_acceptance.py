"""Fail-closed verifier and renderer for the unified TwinOps acceptance ledger."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
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
GIT_SHA = re.compile(r"^[0-9a-f]{40}$")
RESULT_NAME = re.compile(r"^build-assessments-local-causal-[A-Za-z0-9_-]+\.json$")

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
        else: export_local_causal_manifest(args)
    except LedgerError as error:
        print(str(error), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
