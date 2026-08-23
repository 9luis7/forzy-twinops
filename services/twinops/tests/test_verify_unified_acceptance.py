import importlib
import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
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
SHARED_CAUSAL_ARTIFACT = WORKTREE / "tmp" / "twinops-admin-results" / "build-assessments-local-causal-pytest-test_export_local_causal_manif0.json"


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


def _isolated_git(directory, *arguments):
    return subprocess.run(["git", *arguments], cwd=directory, check=True, capture_output=True, text=True)


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


def _causal_payload():
    return {
        "schemaVersion": "1.0", "kind": "build-assessments", "environment": "local",
        "mode": "dry-run", "writesPerformed": 0, "batchId": "batch-1",
        "artifactSha256": "a" * 64, "reportSha256": "b" * 64, "configSha256": "c" * 64,
        "assessmentManifestSha256": "d" * 64, "assessmentCount": 2, "candidateCount": 2,
        "validatedAnchorCount": 2, "validatedEpisodeCount": 2,
        "anchorInvariantViolationCount": 0, "episodeInvariantViolationCount": 0,
    }


def _isolated_causal_context(tmp_path):
    root = tmp_path / "isolated"
    root.mkdir()
    _isolated_git(root, "init", "-q")
    _isolated_git(root, "config", "user.email", "e1@example.invalid")
    _isolated_git(root, "config", "user.name", "E1 Test")
    (root / "anchor.txt").write_text("anchor\n", encoding="utf-8")
    _isolated_git(root, "add", "anchor.txt")
    _isolated_git(root, "commit", "-qm", "anchor")
    guarded = root / "tmp" / "twinops-admin-results"
    guarded.mkdir(parents=True)
    source = guarded / "build-assessments-local-causal-fixture.json"
    source.write_text(json.dumps(_causal_payload()), encoding="utf-8")
    return root, _isolated_git(root, "rev-parse", "HEAD").stdout.strip(), source


def _run_causal(root, reviewed_sha, source, output, *, not_before="2000-01-01T00:00:00Z", expected_batch="batch-1"):
    return subprocess.run(
        [
            sys.executable, str(WORKTREE / "scripts" / "verify_unified_acceptance.py"),
            "export-local-causal-manifest", "--source-result", str(source),
            "--source-not-before", not_before, "--reviewed-code-commit", reviewed_sha,
            "--expected-batch-id", expected_batch, "--expected-artifact-sha256", "a" * 64,
            "--expected-report-sha256", "b" * 64, "--expected-config-sha256", "c" * 64,
            "--output", str(output),
        ],
        cwd=root, check=False, capture_output=True, text=True,
    )


def _assert_markdown_matches(ledger):
    verifier = _verifier_module()
    assert ledger.with_suffix(".md").read_bytes() == verifier.render_markdown(
        verifier.verify_acceptance(ledger)
    ).encode("utf-8")


def _complete_ledger(tmp_path):
    ledger = _copy_ledger(tmp_path)
    data = json.loads(ledger.read_text(encoding="utf-8"))
    sha = _git_ref()
    for entry in data["criteria"]:
        entry.update({
            "status": "passed", "evidenceKind": entry["allowedEvidenceKinds"][0],
            "evidenceRefs": [f"evidence/{entry['criterionId']}"], "verifiedCodeCommit": sha,
        })
    for plan in data["plans"].values():
        plan.update({"status": "passed", "verifiedCodeCommit": sha, "reviewVerdict": {"critical": 0, "important": 0, "minor": 0}})
    ledger.write_text(json.dumps(data), encoding="utf-8")
    return ledger, data, sha


def test_verify_accepts_initial_pending_ledger_but_require_complete_rejects_it():
    initial = _run_verifier("verify", "--ledger", str(LEDGER))
    complete = _run_verifier("verify", "--require-complete", "--ledger", str(LEDGER))

    assert initial.returncode == 0
    assert initial.stdout.strip() == "acceptance_ledger_ok criteria=28 passed=0 pending=28"
    assert complete.returncode != 0
    assert "require_complete" in complete.stderr


@pytest.mark.parametrize("case", ["pending", "wrong-owner-sha", "missing-evidence", "duplicate-ac", "missing-ac", "open-critical", "open-important", "unresolved-minor"])
def test_require_complete_rejects_each_incomplete_or_invalid_closure_state(tmp_path, case):
    ledger, data, sha = _complete_ledger(tmp_path)
    assert _run_verifier("verify", "--require-complete", "--ledger", str(ledger)).returncode == 0
    if case == "pending":
        data["criteria"][0].update({"status": "pending", "evidenceKind": None, "verifiedCodeCommit": None})
        data["plans"]["C"]["status"] = "in_progress"
    elif case == "wrong-owner-sha":
        data["criteria"][0]["verifiedCodeCommit"] = _git_ref("HEAD^")
    elif case == "missing-evidence":
        data["criteria"][0]["evidenceRefs"] = []
    elif case == "duplicate-ac":
        data["criteria"][1]["criterionId"] = "AC-01"
    elif case == "missing-ac":
        data["criteria"].pop()
    else:
        severity = {"open-critical": "critical", "open-important": "important", "unresolved-minor": "minor"}[case]
        data["findings"] = {
            "A-closure": {
                "findingId": "A-closure", "plan": "A", "severity": severity, "status": "open",
                "title": "closure remains incomplete", "introducedSha": sha, "resolvedSha": None, "evidenceRefs": [],
            }
        }
        data["plans"]["A"]["findingIds"] = ["A-closure"]
        data["plans"]["A"]["reviewVerdict"] = {"critical": int(severity == "critical"), "important": int(severity == "important"), "minor": int(severity == "minor")}
        data["plans"]["A"]["status"] = "blocked" if severity != "minor" else "passed"
    ledger.write_text(json.dumps(data), encoding="utf-8")

    result = _run_verifier("verify", "--require-complete", "--ledger", str(ledger))

    assert result.returncode != 0, f"{case} closure state was accepted"


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
    _run_ok("render", "--ledger", str(ledger), "--output", str(ledger.with_suffix(".md")))
    code_sha, evidence_sha = _git_ref("HEAD^"), _git_ref()
    review = _review(
        tmp_path / "a-review.json", plan="A", reviewed_sha=evidence_sha,
        verdict={"critical": 0, "important": 0, "minor": 0}, findings=[],
    )
    _run_ok("ingest-review", "--ledger", str(ledger), "--review-report", str(review))
    _assert_markdown_matches(ledger)
    _run_ok("update-criterion", "--ledger", str(ledger), "--criterion", "AC-06", "--status", "passed", "--evidence-kind", "database", "--evidence-ref", "first", "--verified-code-commit", evidence_sha)
    _assert_markdown_matches(ledger)
    _run_ok("update-criterion", "--ledger", str(ledger), "--criterion", "AC-06", "--status", "pending")
    _assert_markdown_matches(ledger)
    _run_ok("update-criterion", "--ledger", str(ledger), "--criterion", "AC-06", "--status", "passed", "--evidence-kind", "database", "--evidence-ref", "second", "--verified-code-commit", evidence_sha)
    _assert_markdown_matches(ledger)
    code_review = _review(tmp_path / "e-code.json", plan="E", reviewed_sha=code_sha, verdict={"critical": 0, "important": 0, "minor": 0}, findings=[])
    _run_ok("ingest-review", "--ledger", str(ledger), "--review-report", str(code_review))
    _assert_markdown_matches(ledger)
    evidence_review = _review(tmp_path / "e-evidence.json", plan="E", reviewed_sha=evidence_sha, verdict={"critical": 0, "important": 0, "minor": 1}, findings=[{"findingId": "E-mutation", "severity": "minor", "status": "open", "title": "mutation evidence note", "evidenceRefs": [], "resolvedSha": None}])
    _run_ok("ingest-evidence-review", "--ledger", str(ledger), "--review-report", str(evidence_review), "--verified-code-commit", code_sha, "--evidence-commit", evidence_sha)
    _assert_markdown_matches(ledger)


def test_export_local_causal_manifest_accepts_only_a_fresh_closed_local_result(tmp_path):
    isolated, isolated_sha, source = _isolated_causal_context(tmp_path)
    output = isolated / "manifest.json"
    result = _run_causal(isolated, isolated_sha, source, output)
    assert result.returncode == 0, result.stderr
    manifest = json.loads(output.read_text(encoding="utf-8"))
    assert manifest["kind"] == "phase-b-local-causal-manifest"
    assert manifest["assessmentCount"] == 2
    outside = isolated / "outside.json"
    outside.write_bytes(source.read_bytes())
    outside_result = _run_causal(isolated, isolated_sha, outside, output)
    assert outside_result.returncode != 0
    assert "guarded" in outside_result.stderr


def test_causal_manifest_rejects_a_non_direct_lexical_traversal_before_normalization(tmp_path):
    isolated, isolated_sha, source = _isolated_causal_context(tmp_path)
    lexical_traversal = source.parent / ".." / source.parent.name / source.name

    result = _run_causal(isolated, isolated_sha, lexical_traversal, isolated / "manifest.json")

    assert result.returncode != 0
    assert "direct guarded" in result.stderr


def test_causal_manifest_rejects_a_real_reparse_source_before_opening_it(tmp_path):
    isolated, isolated_sha, source = _isolated_causal_context(tmp_path)
    target = isolated / "junction-target"
    target.mkdir()
    source.unlink()
    junction = subprocess.run(
        ["cmd.exe", "/d", "/c", "mklink", "/J", str(source), str(target)],
        check=False, capture_output=True, text=True,
    )
    if junction.returncode != 0:
        pytest.fail(f"E1_REPARSE_FIXTURE_UNAVAILABLE: {junction.stderr or junction.stdout}")
    attributes = getattr(os.lstat(source), "st_file_attributes", 0)
    assert attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)

    result = _run_causal(isolated, isolated_sha, source, isolated / "manifest.json")

    assert result.returncode != 0
    assert "direct guarded" in result.stderr


@pytest.mark.parametrize(
    ("case", "mutate", "not_before", "expected_batch"),
    [
        ("stale", {}, "2100-01-01T00:00:00Z", "batch-1"),
        ("nonlocal", {"environment": "preview"}, "2000-01-01T00:00:00Z", "batch-1"),
        ("write-capable", {"writesPerformed": 1}, "2000-01-01T00:00:00Z", "batch-1"),
        ("extra-key", {"unexpected": "value"}, "2000-01-01T00:00:00Z", "batch-1"),
        ("missing-key", {"batchId": None}, "2000-01-01T00:00:00Z", "batch-1"),
        ("identity", {}, "2000-01-01T00:00:00Z", "different-batch"),
        ("count", {"validatedAnchorCount": 1}, "2000-01-01T00:00:00Z", "batch-1"),
        ("episode-count", {"validatedEpisodeCount": 1}, "2000-01-01T00:00:00Z", "batch-1"),
        ("causal-violation", {"anchorInvariantViolationCount": 1}, "2000-01-01T00:00:00Z", "batch-1"),
        ("episode-violation", {"episodeInvariantViolationCount": 1}, "2000-01-01T00:00:00Z", "batch-1"),
    ],
)
def test_causal_manifest_rejects_each_closed_source_violation(tmp_path, case, mutate, not_before, expected_batch):
    isolated, isolated_sha, source = _isolated_causal_context(tmp_path)
    payload = _causal_payload()
    payload.update(mutate)
    if case == "missing-key":
        payload.pop("batchId")
    source.write_text(json.dumps(payload), encoding="utf-8")

    result = _run_causal(
        isolated, isolated_sha, source, isolated / "manifest.json",
        not_before=not_before, expected_batch=expected_batch,
    )

    assert result.returncode != 0, f"{case} source was accepted"


def test_causal_manifest_tests_leave_no_artifact_in_the_shared_worktree():
    assert not SHARED_CAUSAL_ARTIFACT.exists()


def test_rejected_closure_and_render_failure_leave_ledger_and_markdown_byte_identical(tmp_path, monkeypatch):
    ledger = _copy_ledger(tmp_path)
    markdown = ledger.with_suffix(".md")
    _run_ok("render", "--ledger", str(ledger), "--output", str(markdown))
    before_json, before_markdown = ledger.read_bytes(), markdown.read_bytes()
    rejected = _run_verifier(
        "update-criterion", "--ledger", str(ledger), "--criterion", "AC-06", "--status", "passed",
        "--evidence-kind", "database", "--evidence-ref", "db-proof",
    )
    assert rejected.returncode != 0
    assert ledger.read_bytes() == before_json
    assert markdown.read_bytes() == before_markdown
    verifier = _verifier_module()
    monkeypatch.setattr(verifier, "render_markdown", lambda _report: (_ for _ in ()).throw(OSError("render failed")))
    with pytest.raises(OSError, match="render failed"):
        verifier.update_criterion(ledger, "AC-06", "pending", None, None, None)
    assert ledger.read_bytes() == before_json
    assert markdown.read_bytes() == before_markdown


def test_rejected_review_ingestion_leaves_ledger_and_markdown_byte_identical(tmp_path):
    ledger = _copy_ledger(tmp_path)
    markdown = ledger.with_suffix(".md")
    _run_ok("render", "--ledger", str(ledger), "--output", str(markdown))
    before_json, before_markdown = ledger.read_bytes(), markdown.read_bytes()
    rejected_review = _review(
        tmp_path / "rejected-review.json", plan="A", reviewed_sha=_git_ref(),
        verdict={"critical": 1, "important": 0, "minor": 0}, findings=[],
    )

    result = _run_verifier("ingest-review", "--ledger", str(ledger), "--review-report", str(rejected_review))

    assert result.returncode != 0
    assert ledger.read_bytes() == before_json
    assert markdown.read_bytes() == before_markdown


@pytest.mark.parametrize("mutation", ["bool_verdict", "mismatched_verdict", "uncoupled_identity", "unknown_commit"])
def test_verification_rejects_invalid_review_verdict_and_identity_contract(tmp_path, mutation):
    ledger = _copy_ledger(tmp_path)
    data = json.loads(ledger.read_text(encoding="utf-8"))
    plan = data["plans"]["A"]
    if mutation == "bool_verdict":
        plan["verifiedCodeCommit"] = _git_ref()
        plan["reviewVerdict"] = {"critical": True, "important": 0, "minor": 0}
        plan["status"] = "in_progress"
    elif mutation == "mismatched_verdict":
        plan["verifiedCodeCommit"] = _git_ref()
        plan["reviewVerdict"] = {"critical": 1, "important": 0, "minor": 0}
        plan["status"] = "in_progress"
    elif mutation == "uncoupled_identity":
        plan["verifiedCodeCommit"] = _git_ref()
        plan["reviewVerdict"] = None
        plan["status"] = "in_progress"
    else:
        plan["verifiedCodeCommit"] = "f" * 40
        plan["reviewVerdict"] = {"critical": 0, "important": 0, "minor": 0}
        plan["status"] = "in_progress"
    ledger.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(_verifier_module().LedgerError):
        _verifier_module().verify_acceptance(ledger)


def test_criterion_transitions_preserve_prior_evidence_and_mutation_markdown(tmp_path):
    ledger = _copy_ledger(tmp_path)
    sha = _git_ref()
    review = _review(tmp_path / "review.json", plan="A", reviewed_sha=sha, verdict={"critical": 0, "important": 0, "minor": 0}, findings=[])
    _run_ok("ingest-review", "--ledger", str(ledger), "--review-report", str(review))
    _run_ok("update-criterion", "--ledger", str(ledger), "--criterion", "AC-06", "--status", "passed", "--evidence-kind", "database", "--evidence-ref", "first", "--verified-code-commit", sha)
    _run_ok("update-criterion", "--ledger", str(ledger), "--criterion", "AC-06", "--status", "pending")
    _run_ok("update-criterion", "--ledger", str(ledger), "--criterion", "AC-06", "--status", "passed", "--evidence-kind", "database", "--evidence-ref", "second", "--verified-code-commit", sha)
    raw = next(entry for entry in json.loads(ledger.read_text())["criteria"] if entry["criterionId"] == "AC-06")
    assert raw["evidenceRefs"] == ["first", "second"]
    assert ledger.with_suffix(".md").read_bytes() == _verifier_module().render_markdown(_verifier_module().verify_acceptance(ledger)).encode()
