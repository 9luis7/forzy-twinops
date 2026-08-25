import importlib
import importlib.util
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest


HUMAN_ONLY = {"AC-18", "AC-28"}
FROZEN_SPEC_SHA256 = "20629d860f19a212bc2b941d6270e2316c747a0b85c473f0b51bbee6106e3a44"
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
ATTESTATION_SHA_FIELDS = {
    "targetFingerprint": "sha256:" + "1" * 64,
    "batchId": "sha256:" + "2" * 64,
    "sourceSha256": "sha256:" + "3" * 64,
    "historyManifestSha256": "sha256:" + "4" * 64,
    "artifactSha256": "sha256:" + "5" * 64,
    "featureManifestSha256": "sha256:" + "6" * 64,
    "reportSha256": "sha256:" + "7" * 64,
    "configSha256": "sha256:" + "8" * 64,
    "assessmentManifestSha256": "sha256:" + "9" * 64,
}
ATTESTATION_KEYS = {
    "reviewedCodeCommit", "batchId", "sourceSha256", "historyManifestSha256",
    "artifactSha256", "featureManifestSha256", "reportSha256", "configSha256",
    "modelFamily", "modelVersion", "assessmentManifestSha256", "assessmentCount",
    "candidateCount", "validatedAnchorCount", "validatedEpisodeCount",
    "anchorInvariantViolationCount", "episodeInvariantViolationCount",
    "sourceResultSha256",
}


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
    criteria = []
    for number in range(1, 29):
        criterion_id = f"AC-{number:02d}"
        owner = next(plan for plan, values in OWNER_CRITERIA.items() if criterion_id in values)
        if criterion_id == "AC-06":
            gate, allowed = "database", ["database"]
        elif criterion_id in {"AC-12", "AC-24"}:
            gate, allowed = "preview", ["preview"]
        elif criterion_id in HUMAN_ONLY:
            gate, allowed = "human", ["human"]
        else:
            gate, allowed = "local", ["automated"]
        criteria.append({
            "criterionId": criterion_id, "ownerPlan": owner, "gate": gate,
            "allowedEvidenceKinds": allowed, "status": "pending", "evidenceKind": None,
            "evidenceRefs": [], "verifiedCodeCommit": None,
        })
    ledger = {
        "schemaVersion": "unified-twin-acceptance-v1", "specSha256": FROZEN_SPEC_SHA256,
        "criteria": criteria,
        "plans": {
            plan: {
                "status": "pending", "verifiedCodeCommit": None, "reviewVerdict": None,
                "findingIds": [], "evidenceRefs": [],
            }
            for plan in "ABCDE"
        },
        "findings": {},
    }
    destination.write_text(json.dumps(ledger, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return destination


def test_test_ledger_fixture_is_initial_and_does_not_inherit_tracked_e_review_state(tmp_path):
    ledger = _copy_ledger(tmp_path)

    report = _verifier_module().verify_acceptance(ledger)

    assert not report.findings
    assert all(
        plan.status == "pending" and plan.verified_code_commit is None and plan.review_verdict is None
        and not plan.finding_ids and not plan.evidence_refs
        for plan in report.plans.values()
    )
    assert all(
        entry.status == "pending" and entry.evidence_kind is None
        and entry.verified_code_commit is None and not entry.evidence_refs
        for entry in report.entries.values()
    )


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


def _compact_json(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _attestation_payload():
    return {
        "command": "build-assessments",
        "mode": "dry-run",
        "environment": "local",
        "targetFingerprint": ATTESTATION_SHA_FIELDS["targetFingerprint"],
        "schemaVersion": "003",
        "assetId": "forzy-motor-01",
        "batchId": ATTESTATION_SHA_FIELDS["batchId"],
        "sourceSha256": ATTESTATION_SHA_FIELDS["sourceSha256"],
        "historyManifestSha256": ATTESTATION_SHA_FIELDS["historyManifestSha256"],
        "artifactSha256": ATTESTATION_SHA_FIELDS["artifactSha256"],
        "featureManifestSha256": ATTESTATION_SHA_FIELDS["featureManifestSha256"],
        "reportSha256": ATTESTATION_SHA_FIELDS["reportSha256"],
        "configSha256": ATTESTATION_SHA_FIELDS["configSha256"],
        "modelFamily": "robust-baseline",
        "modelVersion": "1.0.1",
        "assessmentManifestSha256": ATTESTATION_SHA_FIELDS["assessmentManifestSha256"],
        "assessmentCount": 2,
        "candidateCount": 1,
        "validatedAnchorCount": 2,
        "validatedEpisodeCount": 1,
        "anchorInvariantViolationCount": 0,
        "episodeInvariantViolationCount": 0,
        "insertedCount": 1,
        "existingCount": 1,
        "writesPerformed": 0,
    }


def _isolated_attestation_context(tmp_path):
    root = tmp_path / "attestation-repository"
    root.mkdir()
    _isolated_git(root, "init", "-q")
    _isolated_git(root, "config", "user.email", "attestation@example.invalid")
    _isolated_git(root, "config", "user.name", "Attestation Test")
    (root / "tracked.txt").write_text("tracked\n", encoding="utf-8")
    (root / ".gitignore").write_text(
        "tmp/\nhistory.sqlite3\noperator-sentinel.bin\n",
        encoding="utf-8",
    )
    _isolated_git(root, "add", "tracked.txt", ".gitignore")
    _isolated_git(root, "commit", "-qm", "attestation anchor")
    guarded = root / "tmp" / "twinops-admin-results"
    guarded.mkdir(parents=True)
    source = guarded / "build-assessments-local-causal-attestation-fixture.json"
    source.write_bytes(_compact_json(_attestation_payload()))
    return root, _isolated_git(root, "rev-parse", "HEAD").stdout.strip(), source


def _attestation_arguments(
    reviewed_sha,
    source,
    output,
    *,
    not_before="2000-01-01T00:00:00Z",
    expected_overrides=None,
):
    expected = {
        "target-fingerprint": ATTESTATION_SHA_FIELDS["targetFingerprint"],
        "asset-id": "forzy-motor-01",
        "batch-id": ATTESTATION_SHA_FIELDS["batchId"],
        "source-sha256": ATTESTATION_SHA_FIELDS["sourceSha256"],
        "history-manifest-sha256": ATTESTATION_SHA_FIELDS["historyManifestSha256"],
        "artifact-sha256": ATTESTATION_SHA_FIELDS["artifactSha256"],
        "feature-manifest-sha256": ATTESTATION_SHA_FIELDS["featureManifestSha256"],
        "report-sha256": ATTESTATION_SHA_FIELDS["reportSha256"],
        "config-sha256": ATTESTATION_SHA_FIELDS["configSha256"],
        "model-family": "robust-baseline",
        "model-version": "1.0.1",
        "assessment-manifest-sha256": ATTESTATION_SHA_FIELDS["assessmentManifestSha256"],
    }
    expected.update(expected_overrides or {})
    arguments = [
        "export-local-causal-attestation",
        "--source-result",
        str(source),
        "--source-not-before",
        not_before,
        "--reviewed-code-commit",
        reviewed_sha,
    ]
    for name, value in expected.items():
        arguments.extend((f"--expected-{name}", value))
    arguments.extend(("--output", str(output)))
    return arguments


def _run_attestation(
    root,
    reviewed_sha,
    source,
    output,
    *,
    not_before="2000-01-01T00:00:00Z",
    expected_overrides=None,
):
    arguments = _attestation_arguments(
        reviewed_sha,
        source,
        output,
        not_before=not_before,
        expected_overrides=expected_overrides,
    )
    return subprocess.run(
        [
            sys.executable,
            str(WORKTREE / "scripts" / "verify_unified_acceptance.py"),
            *arguments,
        ],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
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
    report = _verifier_module().verify_acceptance(LEDGER)
    passed = sum(entry.status == "passed" for entry in report.entries.values())
    pending = sum(entry.status == "pending" for entry in report.entries.values())

    assert initial.returncode == 0
    assert initial.stdout.strip() == (
        f"acceptance_ledger_ok criteria=28 passed={passed} pending={pending}"
    )
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


def test_export_local_causal_attestation_writes_the_exact_canonical_preimage(tmp_path):
    isolated, isolated_sha, source = _isolated_attestation_context(tmp_path)
    output = source.parent / "phase-b-local-causal-attestation-vs6-happy.json"

    result = _run_attestation(isolated, isolated_sha, source, output)

    assert result.returncode == 0, result.stderr
    source_bytes = source.read_bytes()
    expected = {
        "reviewedCodeCommit": isolated_sha,
        "batchId": ATTESTATION_SHA_FIELDS["batchId"],
        "sourceSha256": ATTESTATION_SHA_FIELDS["sourceSha256"],
        "historyManifestSha256": ATTESTATION_SHA_FIELDS["historyManifestSha256"],
        "artifactSha256": ATTESTATION_SHA_FIELDS["artifactSha256"],
        "featureManifestSha256": ATTESTATION_SHA_FIELDS["featureManifestSha256"],
        "reportSha256": ATTESTATION_SHA_FIELDS["reportSha256"],
        "configSha256": ATTESTATION_SHA_FIELDS["configSha256"],
        "modelFamily": "robust-baseline",
        "modelVersion": "1.0.1",
        "assessmentManifestSha256": ATTESTATION_SHA_FIELDS["assessmentManifestSha256"],
        "assessmentCount": 2,
        "candidateCount": 1,
        "validatedAnchorCount": 2,
        "validatedEpisodeCount": 1,
        "anchorInvariantViolationCount": 0,
        "episodeInvariantViolationCount": 0,
        "sourceResultSha256": "sha256:" + hashlib.sha256(source_bytes).hexdigest(),
    }
    expected_bytes = _compact_json(expected)
    assert set(expected) == ATTESTATION_KEYS
    assert output.read_bytes() == expected_bytes
    assert hashlib.sha256(output.read_bytes()).hexdigest() == hashlib.sha256(expected_bytes).hexdigest()


@pytest.mark.parametrize(
    "mutation",
    [f"missing:{key}" for key in sorted(_attestation_payload())] + ["extra"],
)
def test_local_causal_attestation_rejects_the_closed_source_field_matrix(tmp_path, mutation):
    isolated, isolated_sha, source = _isolated_attestation_context(tmp_path)
    payload = _attestation_payload()
    if mutation == "extra":
        payload["unexpected"] = "closed-contract-violation"
    else:
        payload.pop(mutation.removeprefix("missing:"))
    source.write_bytes(_compact_json(payload))
    output = source.parent / "phase-b-local-causal-attestation-vs6-closed.json"

    result = _run_attestation(isolated, isolated_sha, source, output)

    assert result.returncode != 0, f"{mutation} was accepted"
    assert not output.exists()


@pytest.mark.parametrize(
    ("field", "invalid"),
    [
        ("command", "not-build-assessments"),
        ("mode", "apply"),
        ("environment", "preview"),
        ("schemaVersion", "3"),
        ("assetId", "another-asset"),
        ("modelFamily", "another-model"),
        ("modelVersion", "9.9.9"),
        ("writesPerformed", 1),
        *[
            (field, "sha256:" + "A" * 64)
            for field in ATTESTATION_SHA_FIELDS
        ],
    ],
)
def test_local_causal_attestation_rejects_invalid_source_literals_and_hashes(
    tmp_path, field, invalid,
):
    isolated, isolated_sha, source = _isolated_attestation_context(tmp_path)
    payload = _attestation_payload()
    payload[field] = invalid
    source.write_bytes(_compact_json(payload))
    output = source.parent / "phase-b-local-causal-attestation-vs6-literal.json"

    result = _run_attestation(isolated, isolated_sha, source, output)

    assert result.returncode != 0, f"invalid {field} was accepted"
    assert not output.exists()


ATTESTATION_COUNT_FIELDS = (
    "assessmentCount", "candidateCount", "validatedAnchorCount",
    "validatedEpisodeCount", "anchorInvariantViolationCount",
    "episodeInvariantViolationCount", "insertedCount", "existingCount",
    "writesPerformed",
)


@pytest.mark.parametrize(
    ("case", "updates"),
    [
        *[(f"bool:{field}", {field: False}) for field in ATTESTATION_COUNT_FIELDS],
        *[(f"negative:{field}", {field: -1}) for field in ATTESTATION_COUNT_FIELDS],
        ("empty-assessments", {"assessmentCount": 0, "validatedAnchorCount": 0, "insertedCount": 0}),
        ("too-many-candidates", {"candidateCount": 3, "validatedEpisodeCount": 3}),
        ("anchor-validation", {"validatedAnchorCount": 1}),
        ("episode-validation", {"validatedEpisodeCount": 0}),
        ("anchor-violation", {"anchorInvariantViolationCount": 1}),
        ("episode-violation", {"episodeInvariantViolationCount": 1}),
        ("inserted-existing-algebra", {"insertedCount": 0, "existingCount": 0}),
    ],
)
def test_local_causal_attestation_rejects_invalid_count_types_and_invariants(
    tmp_path, case, updates,
):
    isolated, isolated_sha, source = _isolated_attestation_context(tmp_path)
    payload = _attestation_payload()
    payload.update(updates)
    source.write_bytes(_compact_json(payload))
    output = source.parent / "phase-b-local-causal-attestation-vs6-count.json"

    result = _run_attestation(isolated, isolated_sha, source, output)

    assert result.returncode != 0, f"{case} was accepted"
    assert not output.exists()


@pytest.mark.parametrize(
    ("argument", "different"),
    [
        ("target-fingerprint", "sha256:" + "a" * 64),
        ("asset-id", "another-asset"),
        ("batch-id", "sha256:" + "b" * 64),
        ("source-sha256", "sha256:" + "c" * 64),
        ("history-manifest-sha256", "sha256:" + "d" * 64),
        ("artifact-sha256", "sha256:" + "e" * 64),
        ("feature-manifest-sha256", "sha256:" + "f" * 64),
        ("report-sha256", "sha256:" + "a" * 64),
        ("config-sha256", "sha256:" + "b" * 64),
        ("model-family", "another-model"),
        ("model-version", "9.9.9"),
        ("assessment-manifest-sha256", "sha256:" + "c" * 64),
    ],
)
def test_local_causal_attestation_validates_every_expected_identity_argument(
    tmp_path, argument, different,
):
    isolated, isolated_sha, source = _isolated_attestation_context(tmp_path)
    output = source.parent / "phase-b-local-causal-attestation-vs6-identity.json"

    result = _run_attestation(
        isolated,
        isolated_sha,
        source,
        output,
        expected_overrides={argument: different},
    )

    assert result.returncode != 0, f"--expected-{argument} was ignored"
    assert not output.exists()


@pytest.mark.parametrize(
    "variant",
    ["pretty", "unsorted", "spaced", "no-lf", "crlf", "double-lf", "bom", "duplicate-key"],
)
def test_local_causal_attestation_rejects_every_noncanonical_source_variant(
    tmp_path, variant,
):
    isolated, isolated_sha, source = _isolated_attestation_context(tmp_path)
    payload = _attestation_payload()
    canonical = _compact_json(payload)
    if variant == "pretty":
        source_bytes = (json.dumps(payload, sort_keys=True, indent=2) + "\n").encode("utf-8")
    elif variant == "unsorted":
        source_bytes = (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")
    elif variant == "spaced":
        source_bytes = (json.dumps(payload, sort_keys=True) + "\n").encode("utf-8")
    elif variant == "no-lf":
        source_bytes = canonical.removesuffix(b"\n")
    elif variant == "crlf":
        source_bytes = canonical.removesuffix(b"\n") + b"\r\n"
    elif variant == "double-lf":
        source_bytes = canonical + b"\n"
    elif variant == "bom":
        source_bytes = b"\xef\xbb\xbf" + canonical
    else:
        pair = (
            b'"artifactSha256":"'
            + ATTESTATION_SHA_FIELDS["artifactSha256"].encode("ascii")
            + b'"'
        )
        source_bytes = canonical.replace(pair, pair + b"," + pair, 1)
    source.write_bytes(source_bytes)
    output = source.parent / "phase-b-local-causal-attestation-vs6-canonical.json"

    result = _run_attestation(isolated, isolated_sha, source, output)

    assert result.returncode != 0, f"{variant} source bytes were accepted"
    assert not output.exists()


@pytest.mark.parametrize(
    "case",
    [
        "stale-source", "relative-source", "traversed-source", "outside-source",
        "nested-source", "relative-output", "traversed-output", "outside-output",
        "nested-output", "source-is-output", "existing-output",
    ],
)
def test_local_causal_attestation_rejects_stale_or_unguarded_paths_without_mutation(
    tmp_path, case,
):
    isolated, isolated_sha, source = _isolated_attestation_context(tmp_path)
    guarded = source.parent
    source_argument = source
    output_argument = guarded / "phase-b-local-causal-attestation-vs6-path.json"
    actual_output = output_argument
    not_before = "2000-01-01T00:00:00Z"
    existing_bytes = None
    if case == "stale-source":
        not_before = "2100-01-01T00:00:00Z"
    elif case == "relative-source":
        source_argument = Path("tmp/twinops-admin-results") / source.name
    elif case == "traversed-source":
        source_argument = guarded / ".." / guarded.name / source.name
    elif case == "outside-source":
        source_argument = isolated / "outside-source.json"
        source_argument.write_bytes(source.read_bytes())
    elif case == "nested-source":
        nested = guarded / "nested-source"
        nested.mkdir()
        source_argument = nested / source.name
        source_argument.write_bytes(source.read_bytes())
    elif case == "relative-output":
        output_argument = Path(
            "tmp/twinops-admin-results/phase-b-local-causal-attestation-vs6-relative.json"
        )
        actual_output = guarded / output_argument.name
    elif case == "traversed-output":
        output_argument = (
            guarded
            / ".."
            / guarded.name
            / "phase-b-local-causal-attestation-vs6-traversed.json"
        )
        actual_output = guarded / output_argument.name
    elif case == "outside-output":
        output_argument = isolated / "phase-b-local-causal-attestation-vs6-outside.json"
        actual_output = output_argument
    elif case == "nested-output":
        nested = guarded / "nested-output"
        nested.mkdir()
        output_argument = nested / "phase-b-local-causal-attestation-vs6-nested.json"
        actual_output = output_argument
    elif case == "source-is-output":
        output_argument = source
        actual_output = source
    else:
        existing_bytes = b"existing-output-sentinel\n"
        actual_output.write_bytes(existing_bytes)
    source_before = source.read_bytes()

    result = _run_attestation(
        isolated,
        isolated_sha,
        source_argument,
        output_argument,
        not_before=not_before,
    )

    assert result.returncode != 0, f"{case} was accepted"
    assert source.read_bytes() == source_before
    if existing_bytes is not None:
        assert actual_output.read_bytes() == existing_bytes
    elif actual_output != source:
        assert not actual_output.exists()


@pytest.mark.parametrize(
    "case", ["unsafe-source-name", "source-ads", "unsafe-output-name", "output-ads"],
)
def test_local_causal_attestation_rejects_unsafe_filenames_and_ads_before_publication(
    tmp_path, case,
):
    isolated, isolated_sha, source = _isolated_attestation_context(tmp_path)
    guarded = source.parent
    source_argument = source
    output = guarded / "phase-b-local-causal-attestation-vs6-filename.json"
    if case == "unsafe-source-name":
        source_argument = guarded / "build-assessments.json"
        source_argument.write_bytes(source.read_bytes())
    elif case == "source-ads":
        source_argument = Path(f"{source}:payload")
        try:
            source_argument.write_bytes(source.read_bytes())
        except OSError as error:
            pytest.fail(f"ATTESTATION_ADS_FIXTURE_UNAVAILABLE: {error}")
    elif case == "unsafe-output-name":
        output = guarded / "phase-b-local-causal-attestation.json"
    else:
        output = guarded / "phase-b-local-causal-attestation-vs6-filename.json:payload"

    result = _run_attestation(isolated, isolated_sha, source_argument, output)

    assert result.returncode == 2, result.stderr
    assert "filename" in result.stderr
    assert not output.exists()


@pytest.mark.parametrize("boundary", ["source", "output", "guard", "tmp"])
def test_local_causal_attestation_rejects_windows_reparse_boundaries_without_mutation(
    tmp_path, boundary,
):
    isolated, isolated_sha, source = _isolated_attestation_context(tmp_path)
    guarded = source.parent
    source_bytes = source.read_bytes()
    output = guarded / "phase-b-local-causal-attestation-vs6-reparse.json"
    target = isolated / f"{boundary}-junction-target"
    target.mkdir()
    if boundary == "source":
        source.unlink()
        link = source
    elif boundary == "output":
        link = output
    elif boundary == "guard":
        source.unlink()
        guarded.rmdir()
        (target / source.name).write_bytes(source_bytes)
        link = guarded
    else:
        source.unlink()
        guarded.rmdir()
        guarded.parent.rmdir()
        target_guard = target / guarded.name
        target_guard.mkdir()
        (target_guard / source.name).write_bytes(source_bytes)
        link = guarded.parent
    junction = subprocess.run(
        ["cmd.exe", "/d", "/c", "mklink", "/J", str(link), str(target)],
        check=False,
        capture_output=True,
        text=True,
    )
    if junction.returncode != 0:
        pytest.fail(f"ATTESTATION_REPARSE_FIXTURE_UNAVAILABLE: {junction.stderr or junction.stdout}")
    attributes = getattr(os.lstat(link), "st_file_attributes", 0)
    assert attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)

    result = _run_attestation(isolated, isolated_sha, source, output)

    assert result.returncode != 0, f"{boundary} reparse point was accepted"
    target_guard = target / guarded.name if boundary == "tmp" else target
    assert not (target_guard / output.name).exists()
    if boundary in {"guard", "tmp"}:
        assert (target_guard / source.name).read_bytes() == source_bytes
    else:
        assert not any(target.iterdir())


def test_local_causal_attestation_pins_guard_during_publication_and_rolls_back(
    tmp_path, monkeypatch,
):
    isolated, isolated_sha, source = _isolated_attestation_context(tmp_path)
    verifier = _verifier_module()
    guarded = source.parent
    moved_guard = isolated / "moved-admin-results"
    output = guarded / "phase-b-local-causal-attestation-vs6-guard-swap.json"
    original_link = verifier.os.link
    attempted = False

    def swap_guard_then_link(source_name, destination_name, *args, **kwargs):
        nonlocal attempted
        attempted = True
        guarded.rename(moved_guard)
        guarded.mkdir()
        if kwargs.get("src_dir_fd") is None:
            replacement_temp = guarded / Path(source_name).name
            shutil.copyfile(moved_guard / Path(source_name).name, replacement_temp)
            return original_link(
                replacement_temp,
                guarded / Path(destination_name).name,
                *args,
                **kwargs,
            )
        return original_link(source_name, destination_name, *args, **kwargs)

    monkeypatch.setattr(verifier.os, "link", swap_guard_then_link)
    monkeypatch.chdir(isolated)

    result = verifier.main(_attestation_arguments(isolated_sha, source, output))

    assert attempted
    assert result == 2
    assert not output.exists()
    assert not (moved_guard / output.name).exists()


def test_local_causal_attestation_rejects_multiply_linked_source_without_output(
    tmp_path,
):
    isolated, isolated_sha, source = _isolated_attestation_context(tmp_path)
    alias = source.parent / "source-hardlink-alias.json"
    os.link(source, alias)
    output = source.parent / "phase-b-local-causal-attestation-vs6-source-link.json"

    result = _run_attestation(isolated, isolated_sha, source, output)

    assert result.returncode == 2
    assert not output.exists()
    assert source.read_bytes() == alias.read_bytes()


def test_local_causal_attestation_rejects_same_size_source_replacement_after_read(
    tmp_path, monkeypatch,
):
    isolated, isolated_sha, source = _isolated_attestation_context(tmp_path)
    verifier = _verifier_module()
    output = source.parent / "phase-b-local-causal-attestation-vs6-source-swap.json"
    original_open = verifier.os.open
    original_close = verifier.os.close
    source_descriptor = None
    replacement_injected = False

    def record_source_descriptor(path, *args, **kwargs):
        nonlocal source_descriptor
        descriptor = original_open(path, *args, **kwargs)
        if Path(path).name == source.name and not (args[0] & os.O_WRONLY):
            source_descriptor = descriptor
        return descriptor

    def replace_after_read(descriptor):
        nonlocal replacement_injected, source_descriptor
        original_close(descriptor)
        if descriptor == source_descriptor:
            source_descriptor = None
            pinned = os.lstat(source)
            replacement = source.parent / "same-size-source-replacement.tmp"
            replacement.write_bytes(source.read_bytes())
            os.utime(
                replacement,
                ns=(pinned.st_atime_ns, pinned.st_mtime_ns),
            )
            os.replace(replacement, source)
            replacement_injected = True

    monkeypatch.setattr(verifier.os, "open", record_source_descriptor)
    monkeypatch.setattr(verifier.os, "close", replace_after_read)
    monkeypatch.chdir(isolated)

    result = verifier.main(_attestation_arguments(isolated_sha, source, output))

    assert replacement_injected
    assert result == 2
    assert not output.exists()


def test_local_causal_attestation_rechecks_git_after_initial_clean_check(
    tmp_path, monkeypatch,
):
    isolated, isolated_sha, source = _isolated_attestation_context(tmp_path)
    verifier = _verifier_module()
    output = source.parent / "phase-b-local-causal-attestation-vs6-git-race.json"
    tracked = isolated / "tracked.txt"
    original_run = verifier.subprocess.run
    dirty_injected = False

    def dirty_after_first_status(command, *args, **kwargs):
        nonlocal dirty_injected
        completed = original_run(command, *args, **kwargs)
        if (
            not dirty_injected
            and command[:3] == ["git", "status", "--porcelain=v1"]
            and completed.returncode == 0
        ):
            tracked.write_text("dirty after initial check\n", encoding="utf-8")
            dirty_injected = True
        return completed

    monkeypatch.setattr(verifier.subprocess, "run", dirty_after_first_status)
    monkeypatch.chdir(isolated)

    result = verifier.main(_attestation_arguments(isolated_sha, source, output))

    assert dirty_injected
    assert result == 2
    assert not output.exists()


def test_local_causal_attestation_rejects_an_incomplete_git_status_scan(
    tmp_path, monkeypatch,
):
    isolated, isolated_sha, source = _isolated_attestation_context(tmp_path)
    verifier = _verifier_module()
    output = source.parent / "phase-b-local-causal-attestation-vs6-status-warning.json"
    original_run = verifier.subprocess.run
    warning_injected = False

    def warn_after_status(command, *args, **kwargs):
        nonlocal warning_injected
        completed = original_run(command, *args, **kwargs)
        if (
            not warning_injected
            and command[:3] == ["git", "status", "--porcelain=v1"]
            and completed.returncode == 0
        ):
            warning_injected = True
            return subprocess.CompletedProcess(
                completed.args,
                completed.returncode,
                completed.stdout,
                "warning: could not open directory\n",
            )
        return completed

    monkeypatch.setattr(verifier.subprocess, "run", warn_after_status)
    monkeypatch.chdir(isolated)

    result = verifier.main(_attestation_arguments(isolated_sha, source, output))

    assert warning_injected
    assert result == 2
    assert not output.exists()


@pytest.mark.parametrize("index_flag", ["--assume-unchanged", "--skip-worktree"])
def test_local_causal_attestation_rejects_hidden_tracked_worktree_changes(
    tmp_path, index_flag,
):
    isolated, isolated_sha, source = _isolated_attestation_context(tmp_path)
    output = source.parent / "phase-b-local-causal-attestation-vs6-index-flag.json"
    tracked = isolated / "tracked.txt"
    _isolated_git(isolated, "update-index", index_flag, "tracked.txt")
    tracked.write_text("hidden dirty worktree\n", encoding="utf-8")

    result = _run_attestation(isolated, isolated_sha, source, output)

    assert result.returncode == 2
    assert not output.exists()


def test_local_causal_attestation_rejects_untracked_worktree_files(tmp_path):
    isolated, isolated_sha, source = _isolated_attestation_context(tmp_path)
    output = source.parent / "phase-b-local-causal-attestation-vs6-untracked.json"
    (isolated / "untracked.py").write_text("raise RuntimeError('shadow')\n", encoding="utf-8")

    result = _run_attestation(isolated, isolated_sha, source, output)

    assert result.returncode == 2
    assert not output.exists()


def test_local_causal_attestation_never_hides_tracked_cache_paths(tmp_path):
    isolated, _reviewed_sha, source = _isolated_attestation_context(tmp_path)
    output = source.parent / "phase-b-local-causal-attestation-vs6-cache-tracked.json"
    cache_path = isolated / "services" / "twinops" / ".pytest_cache" / "probe.py"
    cache_path.parent.mkdir(parents=True)
    cache_path.write_text("ORIGINAL = True\n", encoding="utf-8")
    _isolated_git(isolated, "add", "-f", str(cache_path.relative_to(isolated)))
    _isolated_git(isolated, "commit", "-qm", "track forbidden cache file")
    reviewed_sha = _isolated_git(isolated, "rev-parse", "HEAD").stdout.strip()
    cache_path.write_text("DIRTY = True\n", encoding="utf-8")

    result = _run_attestation(isolated, reviewed_sha, source, output)

    assert result.returncode == 2
    assert not output.exists()


def test_local_causal_attestation_rejects_output_hardlink_race_and_rolls_back(
    tmp_path, monkeypatch,
):
    isolated, isolated_sha, source = _isolated_attestation_context(tmp_path)
    verifier = _verifier_module()
    output = source.parent / "phase-b-local-causal-attestation-vs6-output-link.json"
    alias = source.parent / "published-hardlink-alias.json"
    original_link = verifier.os.link
    injected = False

    def publish_then_add_hardlink(source_name, destination_name, *args, **kwargs):
        nonlocal injected
        result = original_link(source_name, destination_name, *args, **kwargs)
        if not injected:
            if kwargs.get("dst_dir_fd") is None:
                original_link(destination_name, alias)
            else:
                original_link(
                    destination_name,
                    alias.name,
                    src_dir_fd=kwargs["dst_dir_fd"],
                    dst_dir_fd=kwargs["dst_dir_fd"],
                )
            injected = True
        return result

    monkeypatch.setattr(verifier.os, "link", publish_then_add_hardlink)
    monkeypatch.chdir(isolated)

    result = verifier.main(_attestation_arguments(isolated_sha, source, output))

    assert injected
    assert result == 2
    assert not output.exists()
    assert alias.is_file()


def test_local_causal_attestation_removes_output_after_byte_verification_failure(
    tmp_path, monkeypatch,
):
    isolated, isolated_sha, source = _isolated_attestation_context(tmp_path)
    verifier = _verifier_module()
    output = source.parent / "phase-b-local-causal-attestation-vs6-byte-race.json"
    original_lstat = verifier.os.lstat
    corrupted = False

    def corrupt_published_output(path, *args, **kwargs):
        nonlocal corrupted
        value = original_lstat(path, *args, **kwargs)
        if not corrupted and Path(path) == output:
            output.write_bytes(b"x" * value.st_size)
            corrupted = True
        return value

    monkeypatch.setattr(verifier.os, "lstat", corrupt_published_output)
    monkeypatch.chdir(isolated)

    result = verifier.main(_attestation_arguments(isolated_sha, source, output))

    assert corrupted
    assert result == 2
    assert not output.exists()
    assert not any(source.parent.glob(f".{output.name}.*"))


def test_local_causal_attestation_rollback_never_deletes_replacement_attacker_path(
    tmp_path, monkeypatch,
):
    isolated, isolated_sha, source = _isolated_attestation_context(tmp_path)
    verifier = _verifier_module()
    output = source.parent / "phase-b-local-causal-attestation-vs6-attacker-path.json"
    displaced = source.parent / "displaced-published-attestation.json"
    attacker_bytes = b"attacker-owned-path\n"
    original_lstat = verifier.os.lstat
    replaced = False

    def replace_published_identity(path, *args, **kwargs):
        nonlocal replaced
        value = original_lstat(path, *args, **kwargs)
        if not replaced and Path(path) == output:
            os.replace(output, displaced)
            output.write_bytes(attacker_bytes)
            replaced = True
        return value

    monkeypatch.setattr(verifier.os, "lstat", replace_published_identity)
    monkeypatch.chdir(isolated)

    result = verifier.main(_attestation_arguments(isolated_sha, source, output))

    assert replaced
    assert result == 2
    assert output.read_bytes() == attacker_bytes
    assert displaced.is_file()
    assert not any(source.parent.glob(f".{output.name}.*"))


@pytest.mark.skipif(os.name != "nt", reason="Windows identity-bound rollback")
def test_local_causal_attestation_rollback_cannot_unlink_a_post_stat_replacement(
    tmp_path, monkeypatch,
):
    isolated, isolated_sha, source = _isolated_attestation_context(tmp_path)
    verifier = _verifier_module()
    output = source.parent / "phase-b-local-causal-attestation-vs6-unlink-race.json"
    original_unlink_child = verifier._PinnedAttestationBoundary.unlink_child
    path_unlink_attempted = False

    def force_verification_failure(*_args, **_kwargs):
        raise verifier.LedgerError("forced post-publication verification failure")

    def record_path_unlink(boundary, name):
        nonlocal path_unlink_attempted
        if name == output.name:
            path_unlink_attempted = True
        return original_unlink_child(boundary, name)

    monkeypatch.setattr(
        verifier,
        "_read_verified_attestation_child",
        force_verification_failure,
    )
    monkeypatch.setattr(
        verifier._PinnedAttestationBoundary,
        "unlink_child",
        record_path_unlink,
    )
    monkeypatch.chdir(isolated)

    result = verifier.main(_attestation_arguments(isolated_sha, source, output))

    assert result == 2
    assert not path_unlink_attempted
    assert not output.exists()


def test_local_causal_attestation_detects_corruption_after_git_checkpoint(
    tmp_path, monkeypatch,
):
    isolated, isolated_sha, source = _isolated_attestation_context(tmp_path)
    verifier = _verifier_module()
    output = source.parent / "phase-b-local-causal-attestation-vs6-final-bytes.json"
    original_verify = verifier._verify_attestation_git_state
    verification_count = 0
    corruption_injected = False

    def corrupt_during_final_git_check(reviewed_code_commit):
        nonlocal verification_count, corruption_injected
        verification_count += 1
        original_verify(reviewed_code_commit)
        if verification_count == 4:
            before = output.stat()
            output.write_bytes(b"x" * before.st_size)
            os.utime(
                output,
                ns=(before.st_atime_ns, before.st_mtime_ns),
            )
            corruption_injected = True

    monkeypatch.setattr(
        verifier,
        "_verify_attestation_git_state",
        corrupt_during_final_git_check,
    )
    monkeypatch.chdir(isolated)

    result = verifier.main(_attestation_arguments(isolated_sha, source, output))

    assert corruption_injected
    assert result == 2
    assert not output.exists()


@pytest.mark.skipif(os.name != "nt", reason="Windows directory handle binding")
@pytest.mark.parametrize("boundary_name", ["tmp", "twinops-admin-results"])
def test_local_causal_attestation_rejects_a_handle_for_the_wrong_guard(
    tmp_path, monkeypatch, boundary_name,
):
    isolated, isolated_sha, source = _isolated_attestation_context(tmp_path)
    verifier = _verifier_module()
    output = source.parent / "phase-b-local-causal-attestation-vs6-wrong-handle.json"
    decoy = isolated / "decoy-directory"
    decoy.mkdir()
    original_open = verifier._open_windows_attestation_directory
    wrong_handle_injected = False

    def open_wrong_guard(path):
        nonlocal wrong_handle_injected
        if Path(path).name == boundary_name:
            wrong_handle_injected = True
            return original_open(decoy)
        return original_open(path)

    monkeypatch.setattr(
        verifier,
        "_open_windows_attestation_directory",
        open_wrong_guard,
    )
    monkeypatch.chdir(isolated)

    result = verifier.main(_attestation_arguments(isolated_sha, source, output))

    assert wrong_handle_injected
    assert result == 2
    assert not output.exists()


@pytest.mark.parametrize(
    "case", ["malformed-reviewed-sha", "wrong-reviewed-sha", "advanced-head", "dirty-worktree", "dirty-index"],
)
def test_local_causal_attestation_requires_exact_head_and_a_clean_tracked_repository(
    tmp_path, case,
):
    isolated, isolated_sha, source = _isolated_attestation_context(tmp_path)
    reviewed_sha = isolated_sha
    if case == "malformed-reviewed-sha":
        reviewed_sha = isolated_sha[:-1]
    elif case == "wrong-reviewed-sha":
        reviewed_sha = "f" * 40
    elif case == "advanced-head":
        (isolated / "tracked.txt").write_text("advanced\n", encoding="utf-8")
        _isolated_git(isolated, "add", "tracked.txt")
        _isolated_git(isolated, "commit", "-qm", "advance head")
    elif case == "dirty-worktree":
        (isolated / "tracked.txt").write_text("dirty worktree\n", encoding="utf-8")
    else:
        (isolated / "tracked.txt").write_text("dirty index\n", encoding="utf-8")
        _isolated_git(isolated, "add", "tracked.txt")
    status_before = _isolated_git(
        isolated, "status", "--short", "--untracked-files=no",
    ).stdout
    output = source.parent / "phase-b-local-causal-attestation-vs6-git.json"

    result = _run_attestation(isolated, reviewed_sha, source, output)

    assert result.returncode != 0, f"{case} was accepted"
    assert not output.exists()
    assert _isolated_git(
        isolated, "status", "--short", "--untracked-files=no",
    ).stdout == status_before


def test_local_causal_attestation_is_deterministic_and_never_mutates_database_or_sentinels(
    tmp_path,
):
    isolated, isolated_sha, source = _isolated_attestation_context(tmp_path)
    database = isolated / "history.sqlite3"
    sentinel = isolated / "operator-sentinel.bin"
    database.write_bytes(b"SQLite format 3\x00database-sentinel")
    sentinel.write_bytes(b"operator-sentinel\x00bytes")
    protected = {
        path: (path.read_bytes(), path.stat().st_mtime_ns)
        for path in (database, sentinel, source, isolated / "tracked.txt")
    }
    first = source.parent / "phase-b-local-causal-attestation-vs6-deterministic-first.json"
    second = source.parent / "phase-b-local-causal-attestation-vs6-deterministic-second.json"

    first_result = _run_attestation(isolated, isolated_sha, source, first)
    second_result = _run_attestation(isolated, isolated_sha, source, second)

    assert first_result.returncode == 0, first_result.stderr
    assert second_result.returncode == 0, second_result.stderr
    assert first.read_bytes() == second.read_bytes()
    assert set(json.loads(first.read_bytes())) == ATTESTATION_KEYS
    assert "attestationSha256" not in json.loads(first.read_bytes())
    for path, (before_bytes, before_mtime) in protected.items():
        assert path.read_bytes() == before_bytes
        assert path.stat().st_mtime_ns == before_mtime
    assert _isolated_git(
        isolated, "status", "--short", "--untracked-files=no",
    ).stdout == ""
    assert not any(
        item.name.startswith(f".{first.name}.")
        or item.name.startswith(f".{second.name}.")
        for item in source.parent.iterdir()
    )


def test_export_local_causal_manifest_legacy_bytes_and_contract_are_unchanged(tmp_path):
    isolated, isolated_sha, source = _isolated_causal_context(tmp_path)
    output = isolated / "legacy-manifest.json"

    result = _run_causal(isolated, isolated_sha, source, output)

    assert result.returncode == 0, result.stderr
    expected = {
        "schemaVersion": "1.0",
        "kind": "phase-b-local-causal-manifest",
        "reviewedCodeCommit": isolated_sha,
        "batchId": "batch-1",
        "artifactSha256": "a" * 64,
        "reportSha256": "b" * 64,
        "configSha256": "c" * 64,
        "assessmentManifestSha256": "d" * 64,
        "assessmentCount": 2,
        "candidateCount": 2,
        "validatedAnchorCount": 2,
        "validatedEpisodeCount": 2,
        "anchorInvariantViolationCount": 0,
        "episodeInvariantViolationCount": 0,
        "sourceResultSha256": hashlib.sha256(source.read_bytes()).hexdigest(),
    }
    expected_bytes = (
        json.dumps(expected, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    assert output.read_bytes() == expected_bytes
    assert not json.loads(output.read_bytes())["sourceResultSha256"].startswith("sha256:")


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
