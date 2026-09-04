import json
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).parents[4]
MANIFEST = ROOT / "evals" / "rag" / "forzy-motor-01-v1.jsonl"
VALIDATOR = ROOT / "evals" / "rag" / "validate.py"


def test_evaluation_manifest_has_at_least_30_versioned_non_invented_cases():
    cases = [
        json.loads(line)
        for line in MANIFEST.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    assert len(cases) >= 30
    assert len({case["id"] for case in cases}) == len(cases)
    assert all(case["schemaVersion"] == "1.0" for case in cases)
    assert all(
        case["manualExpectation"] in {None, "supported", "absent", "out_of_scope"}
        for case in cases
    )
    assert all(
        case["expectedManualEvidence"] == []
        for case in cases
        if case["status"] == "pending_manual"
    )
    assert any(case["category"] == "cross_language" for case in cases)
    assert {"real_manual", "synthetic_fixture"}.issubset(
        {case["caseKind"] for case in cases}
    )
    assert {"normal", "watch", "alert", "unavailable"}.issubset(
        {case["expectedOperationalState"] for case in cases}
    )


def test_validator_passes_structure_but_require_complete_fails_pending_gate():
    ordinary = subprocess.run(
        [sys.executable, str(VALIDATOR), str(MANIFEST)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    gated = subprocess.run(
        [sys.executable, str(VALIDATOR), str(MANIFEST), "--require-complete"],
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert ordinary.returncode == 0, ordinary.stderr
    assert gated.returncode == 1
    assert "pending manual cases remain" in gated.stderr


def _cases():
    return [
        json.loads(line)
        for line in MANIFEST.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _write_cases(tmp_path, cases):
    path = tmp_path / "cases.jsonl"
    path.write_text(
        "\n".join(json.dumps(case) for case in cases) + "\n",
        encoding="utf-8",
    )
    return path


def _real_manual_anchors(case):
    case["status"] = "complete"
    case["manualExpectation"] = "supported"
    case["manualIdentity"] = {
        "manufacturer": "WEG",
        "equipmentModel": "W22",
        "revision": "2026-01",
        "sourceUrl": "https://manufacturer.example/w22-manual.pdf",
    }
    case["expectedManualEvidence"] = [
        {
            "documentSha256": "a" * 64,
            "chunkId": f"chunk-{case['id']}",
            "pageStart": 7,
            "pageEnd": 7,
            "contentHash": "b" * 64,
            "exactQuote": "Inspect bearing lubrication before startup.",
        }
    ]


def _run(path, *extra):
    return subprocess.run(
        [sys.executable, str(VALIDATOR), str(path), *extra],
        capture_output=True,
        text=True,
        timeout=10,
    )


def test_real_manual_case_can_transition_from_pending_to_completed_with_anchors(tmp_path):
    cases = _cases()
    real_case = next(case for case in cases if case["caseKind"] == "real_manual")
    _real_manual_anchors(real_case)

    result = _run(_write_cases(tmp_path, cases))

    assert result.returncode == 0, result.stderr


def test_completed_real_manual_case_rejects_empty_or_unverifiable_evidence(tmp_path):
    cases = _cases()
    real_case = next(case for case in cases if case["caseKind"] == "real_manual")
    real_case["status"] = "complete"
    real_case["manualIdentity"] = None
    real_case["manualExpectation"] = "supported"
    real_case["expectedManualEvidence"] = []

    result = _run(_write_cases(tmp_path, cases))

    assert result.returncode == 1
    assert "completed real manual" in result.stderr


@pytest.mark.parametrize("expectation", ["absent", "out_of_scope"])
def test_completed_real_refusal_case_requires_empty_evidence(tmp_path, expectation):
    cases = _cases()
    real_case = next(case for case in cases if case["caseKind"] == "real_manual")
    _real_manual_anchors(real_case)
    real_case["manualExpectation"] = expectation

    result = _run(_write_cases(tmp_path, cases))

    assert result.returncode == 1
    assert "requires empty evidence" in result.stderr


def test_require_complete_accepts_real_manual_cases_only_with_verifiable_anchors(
    tmp_path,
):
    cases = _cases()
    for case in cases:
        if case["caseKind"] == "real_manual":
            _real_manual_anchors(case)

    result = _run(_write_cases(tmp_path, cases), "--require-complete")

    assert result.returncode == 0, result.stderr


def test_require_complete_rejects_fixture_only_manifest_with_empty_evidence(tmp_path):
    cases = _cases()
    for case in cases:
        case["caseKind"] = "synthetic_fixture"
        case["status"] = "complete"
        case["manualIdentity"] = None
        case["expectedManualEvidence"] = []

    result = _run(_write_cases(tmp_path, cases), "--require-complete")

    assert result.returncode == 1
    assert "completed real manual cases" in result.stderr


@pytest.mark.parametrize(
    "invalid_evidence",
    [
        ["chunk-without-fixture-prefix"],
        [1],
        [{"chunkId": "fixture:chunk-safe-001"}],
    ],
)
def test_supported_synthetic_fixture_requires_canonical_string_anchors(
    tmp_path, invalid_evidence
):
    cases = _cases()
    fixture = next(
        case
        for case in cases
        if case["caseKind"] == "synthetic_fixture"
        and case["manualExpectation"] == "supported"
    )
    fixture["expectedManualEvidence"] = invalid_evidence

    result = _run(_write_cases(tmp_path, cases))

    assert result.returncode == 1
    assert "fixture anchors" in result.stderr
