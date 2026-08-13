from twinops.copilot.evaluate import evaluate_cases


def test_evaluation_counts_invalid_refs_and_forbidden_claims():
    cases = [
        {
            "caseId": "case-1",
            "allowedEvidenceRefs": ["ev-1"],
            "forbiddenClaims": ["causa raiz"],
        }
    ]
    responses = [
        {
            "answer": "A causa raiz foi confirmada.",
            "evidenceRefs": ["ev-2"],
            "latencyMs": 12.0,
        }
    ]

    report = evaluate_cases(cases, responses, provider="stub")

    assert report["cases"] == 1
    assert report["invalidEvidenceRefs"] == 1
    assert report["forbiddenClaimHits"] == 1
    assert report["latencyMs"]["p50"] == 12.0


def test_evaluation_accepts_traceable_response():
    report = evaluate_cases(
        [{"caseId": "ok", "allowedEvidenceRefs": ["ev-1"], "forbiddenClaims": ["causa raiz"]}],
        [{"answer": "Desvio relativo ao histórico.", "evidenceRefs": ["ev-1"], "latencyMs": 5.0}],
        provider="deterministic",
    )

    assert report["invalidEvidenceRefs"] == 0
    assert report["forbiddenClaimHits"] == 0
