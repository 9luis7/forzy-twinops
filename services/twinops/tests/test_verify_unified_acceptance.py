import importlib
import importlib.util
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest


HUMAN_ONLY = {"AC-18", "AC-28"}
OWNER_CRITERIA = {
    "A": ("AC-06",),
    "B": ("AC-13", "AC-14"),
    "C": (
        "AC-01", "AC-02", "AC-03", "AC-04", "AC-05", "AC-07", "AC-11",
        "AC-16", "AC-17", "AC-19", "AC-21", "AC-22", "AC-25", "AC-26",
        "AC-27",
    ),
    "D": ("AC-08", "AC-09", "AC-10", "AC-20", "AC-23"),
    "E": ("AC-12", "AC-15", "AC-18", "AC-24", "AC-28"),
}
WORKTREE = Path(__file__).resolve().parents[3]
LEDGER = WORKTREE / "docs" / "verification" / "unified-twin-acceptance-v1.json"


def _verifier_module():
    if importlib.util.find_spec("scripts.verify_unified_acceptance") is None:
        pytest.fail("E1_ACCEPTANCE_VERIFIER_MISSING")
    return importlib.import_module("scripts.verify_unified_acceptance")


def test_acceptance_verifier_contract_is_required():
    verifier = _verifier_module()

    assert callable(verifier.verify_acceptance)
    assert callable(verifier.main)


def test_acceptance_ledger_has_every_spec_criterion_and_never_auto_closes_human_gates():
    verifier = _verifier_module()

    report = verifier.verify_acceptance(
        Path("docs/verification/unified-twin-acceptance-v1.json")
    )
    assert report.criteria == tuple(f"AC-{index:02d}" for index in range(1, 29))
    owned = tuple(criterion for criteria in OWNER_CRITERIA.values() for criterion in criteria)
    assert len(owned) == 28
    assert len(set(owned)) == 28
    assert tuple(sorted(owned, key=lambda value: int(value.removeprefix("AC-")))) == report.criteria
    assert all(
        report.entries[criterion].owner_plan == owner
        for owner, criteria in OWNER_CRITERIA.items()
        for criterion in criteria
    )
    assert {entry.owner_plan for entry in report.entries.values()} <= set("ABCDE")
    assert all(
        entry.gate in {"local", "database", "preview", "human"}
        for entry in report.entries.values()
    )
    for criterion_id in HUMAN_ONLY:
        entry = report.entries[criterion_id]
        assert entry.allowed_evidence_kinds == ("human",)
        assert entry.status != "passed" or entry.evidence_kind == "human"


def _git_ref(ref="HEAD"):
    return subprocess.check_output(
        ["git", "rev-parse", ref], cwd=WORKTREE, text=True
    ).strip()


def _copy_ledger(tmp_path):
    destination = tmp_path / "unified-twin-acceptance-v1.json"
    destination.write_bytes(LEDGER.read_bytes())
    return destination


def _run_verifier(*arguments, cwd=WORKTREE):
    return subprocess.run(
        [sys.executable, "scripts/verify_unified_acceptance.py", *arguments],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )


def _review(path, *, plan, reviewed_sha, verdict, findings):
    path.write_text(
        json.dumps(
            {
                "schemaVersion": "finding-review-v1",
                "plan": plan,
                "reviewedSha": reviewed_sha,
                "verdict": verdict,
                "findings": findings,
            }
        ),
        encoding="utf-8",
    )
    return path


def _run_ok(*arguments):
    result = _run_verifier(*arguments)
    assert result.returncode == 0, result.stderr
    return result


def test_verify_accepts_initial_pending_ledger_but_require_complete_rejects_it():
    initial = _run_verifier("verify", "--ledger", str(LEDGER))
    complete = _run_verifier("verify", "--require-complete", "--ledger", str(LEDGER))

    assert initial.returncode == 0
    assert initial.stdout.strip() == "acceptance_ledger_ok criteria=28 passed=0 pending=28"
    assert complete.returncode != 0
    assert "require_complete" in complete.stderr


def test_review_findings_are_cumulative_and_plan_state_derives_from_review_and_criteria(tmp_path):
    ledger = _copy_ledger(tmp_path)
    old_sha, current_sha = _git_ref("HEAD^"), _git_ref()
    opened = _review(
        tmp_path / "opened.json",
        plan="B",
        reviewed_sha=old_sha,
        verdict={"critical": 0, "important": 1, "minor": 0},
        findings=[{
            "findingId": "B-01", "severity": "important", "status": "open",
            "title": "causal result omits its anchor", "evidenceRefs": [], "resolvedSha": None,
        }],
    )
    _run_ok("ingest-review", "--ledger", str(ledger), "--review-report", str(opened))
    blocked = _verifier_module().verify_acceptance(ledger)
    assert blocked.plans["B"].status == "blocked"
    assert blocked.findings["B-01"].introduced_sha == old_sha

    fixed = _review(
        tmp_path / "fixed.json",
        plan="B",
        reviewed_sha=current_sha,
        verdict={"critical": 0, "important": 0, "minor": 0},
        findings=[{
            "findingId": "B-01", "severity": "important", "status": "fixed",
            "title": "causal result omits its anchor", "evidenceRefs": ["services/twinops/tests/example.py"],
            "resolvedSha": current_sha,
        }],
    )
    _run_ok("ingest-review", "--ledger", str(ledger), "--review-report", str(fixed))
    for criterion in OWNER_CRITERIA["B"]:
        _run_ok(
            "update-criterion", "--ledger", str(ledger), "--criterion", criterion,
            "--status", "passed", "--evidence-kind", "automated",
            "--evidence-ref", f"services/twinops/tests/{criterion}.py",
            "--verified-code-commit", current_sha,
        )
    report = _verifier_module().verify_acceptance(ledger)
    assert report.plans["B"].status == "passed"
    assert report.findings["B-01"].status == "fixed"


def test_review_ingestion_rejects_stale_and_conflicting_finding_lineage(tmp_path):
    ledger = _copy_ledger(tmp_path)
    old_sha, current_sha = _git_ref("HEAD^"), _git_ref()
    first = _review(
        tmp_path / "first.json", plan="A", reviewed_sha=old_sha,
        verdict={"critical": 0, "important": 0, "minor": 1},
        findings=[{
            "findingId": "A-01", "severity": "minor", "status": "open",
            "title": "evidence heading is ambiguous", "evidenceRefs": [], "resolvedSha": None,
        }],
    )
    _run_ok("ingest-review", "--ledger", str(ledger), "--review-report", str(first))
    stale = _review(
        tmp_path / "stale.json", plan="A", reviewed_sha=old_sha,
        verdict={"critical": 0, "important": 0, "minor": 1},
        findings=[{
            "findingId": "A-01", "severity": "minor", "status": "open",
            "title": "evidence heading is ambiguous", "evidenceRefs": [], "resolvedSha": None,
        }],
    )
    stale_result = _run_verifier("ingest-review", "--ledger", str(ledger), "--review-report", str(stale))
    assert stale_result.returncode != 0
    assert "stale reviewed SHA" in stale_result.stderr

    conflict = _review(
        tmp_path / "conflict.json", plan="A", reviewed_sha=current_sha,
        verdict={"critical": 0, "important": 0, "minor": 1},
        findings=[{
            "findingId": "A-01", "severity": "important", "status": "open",
            "title": "different title", "evidenceRefs": [], "resolvedSha": None,
        }],
    )
    conflict_result = _run_verifier("ingest-review", "--ledger", str(ledger), "--review-report", str(conflict))
    assert conflict_result.returncode != 0
    assert "conflicting finding lineage" in conflict_result.stderr


def test_critical_and_important_findings_cannot_be_accepted(tmp_path):
    ledger = _copy_ledger(tmp_path)
    report = _review(
        tmp_path / "accepted.json", plan="C", reviewed_sha=_git_ref(),
        verdict={"critical": 0, "important": 0, "minor": 0},
        findings=[{
            "findingId": "C-01", "severity": "critical", "status": "accepted",
            "title": "unsafe state is ignored", "evidenceRefs": ["user acceptance"], "resolvedSha": _git_ref(),
        }],
    )
    result = _run_verifier("ingest-review", "--ledger", str(ledger), "--review-report", str(report))

    assert result.returncode != 0
    assert "only Minor findings may be accepted" in result.stderr


def test_evidence_review_preserves_the_e_code_review_identity_and_rejects_misbinding(tmp_path):
    ledger = _copy_ledger(tmp_path)
    code_sha, evidence_sha = _git_ref("HEAD^"), _git_ref()
    code_review = _review(
        tmp_path / "code-review.json", plan="E", reviewed_sha=code_sha,
        verdict={"critical": 0, "important": 0, "minor": 0}, findings=[],
    )
    _run_ok("ingest-review", "--ledger", str(ledger), "--review-report", str(code_review))
    evidence_review = _review(
        tmp_path / "evidence-review.json", plan="E", reviewed_sha=evidence_sha,
        verdict={"critical": 0, "important": 0, "minor": 1},
        findings=[{
            "findingId": "E-01", "severity": "minor", "status": "open",
            "title": "evidence note needs a timestamp", "evidenceRefs": [], "resolvedSha": None,
        }],
    )
    _run_ok(
        "ingest-evidence-review", "--ledger", str(ledger), "--review-report", str(evidence_review),
        "--verified-code-commit", code_sha, "--evidence-commit", evidence_sha,
    )
    report = _verifier_module().verify_acceptance(ledger)
    assert report.plans["E"].verified_code_commit == code_sha
    assert report.plans["E"].review_verdict == (0, 0, 0)
    assert report.findings["E-01"].introduced_sha == evidence_sha

    equal = _run_verifier(
        "ingest-evidence-review", "--ledger", str(ledger), "--review-report", str(evidence_review),
        "--verified-code-commit", code_sha, "--evidence-commit", code_sha,
    )
    assert equal.returncode != 0
    assert "must differ" in equal.stderr

    wrong_report = _review(
        tmp_path / "wrong-evidence-review.json", plan="E", reviewed_sha=code_sha,
        verdict={"critical": 0, "important": 0, "minor": 0}, findings=[],
    )
    mismatched = _run_verifier(
        "ingest-evidence-review", "--ledger", str(ledger), "--review-report", str(wrong_report),
        "--verified-code-commit", code_sha, "--evidence-commit", evidence_sha,
    )
    assert mismatched.returncode != 0
    assert "reviewedSha must equal evidence commit" in mismatched.stderr


def test_criterion_updates_bind_evidence_to_the_owner_review_and_keep_human_gates_human(tmp_path):
    ledger = _copy_ledger(tmp_path)
    sha = _git_ref()
    review = _review(
        tmp_path / "review.json", plan="E", reviewed_sha=sha,
        verdict={"critical": 0, "important": 0, "minor": 0}, findings=[],
    )
    _run_ok("ingest-review", "--ledger", str(ledger), "--review-report", str(review))
    automatic = _run_verifier(
        "update-criterion", "--ledger", str(ledger), "--criterion", "AC-18", "--status", "passed",
        "--evidence-kind", "automated", "--evidence-ref", "test", "--verified-code-commit", sha,
    )
    assert automatic.returncode != 0
    assert "not allowed" in automatic.stderr
    _run_ok(
        "update-criterion", "--ledger", str(ledger), "--criterion", "AC-18", "--status", "passed",
        "--evidence-kind", "human", "--evidence-ref", "docs/verification/human.md",
        "--verified-code-commit", sha,
    )
    assert _verifier_module().verify_acceptance(ledger).entries["AC-18"].evidence_kind == "human"


def test_every_ledger_mutation_reproduces_the_markdown_from_json(tmp_path):
    ledger = _copy_ledger(tmp_path)
    output = tmp_path / "ledger.md"
    sha = _git_ref()
    _run_ok("render", "--ledger", str(ledger), "--output", str(output))
    before = output.read_bytes()
    review = _review(
        tmp_path / "review.json", plan="A", reviewed_sha=sha,
        verdict={"critical": 0, "important": 0, "minor": 0}, findings=[],
    )
    _run_ok("ingest-review", "--ledger", str(ledger), "--review-report", str(review))
    generated = ledger.with_suffix(".md")
    assert generated.read_bytes() == _verifier_module().render_markdown(
        _verifier_module().verify_acceptance(ledger)
    ).encode("utf-8")
    assert generated.read_bytes() != before


def test_export_local_causal_manifest_accepts_only_a_fresh_closed_local_result(tmp_path):
    source_dir = WORKTREE / "tmp" / "twinops-admin-results"
    source_dir.mkdir(parents=True, exist_ok=True)
    nonce = f"pytest-{tmp_path.name}"
    source = source_dir / f"build-assessments-local-causal-{nonce}.json"
    not_before = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    source.write_text(json.dumps({
        "schemaVersion": "1.0", "kind": "build-assessments", "environment": "local",
        "mode": "dry-run", "writesPerformed": 0, "batchId": "batch-1",
        "artifactSha256": "a" * 64, "reportSha256": "b" * 64, "configSha256": "c" * 64,
        "assessmentManifestSha256": "d" * 64, "assessmentCount": 2, "candidateCount": 2,
        "validatedAnchorCount": 2, "validatedEpisodeCount": 2,
        "anchorInvariantViolationCount": 0, "episodeInvariantViolationCount": 0,
    }), encoding="utf-8")
    output = tmp_path / "manifest.json"
    _run_ok(
        "export-local-causal-manifest", "--source-result", str(source), "--source-not-before", not_before,
        "--reviewed-code-commit", _git_ref(), "--expected-batch-id", "batch-1",
        "--expected-artifact-sha256", "a" * 64, "--expected-report-sha256", "b" * 64,
        "--expected-config-sha256", "c" * 64, "--output", str(output),
    )
    manifest = json.loads(output.read_text(encoding="utf-8"))
    assert manifest["kind"] == "phase-b-local-causal-manifest"
    assert manifest["assessmentCount"] == 2
