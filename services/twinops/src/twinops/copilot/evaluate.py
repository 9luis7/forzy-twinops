"""Provider-neutral evaluation helpers for evidence-bound explanations."""

from statistics import median
from typing import Any, Sequence


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = round((len(ordered) - 1) * fraction)
    return ordered[index]


def evaluate_cases(
    cases: Sequence[dict[str, Any]],
    responses: Sequence[dict[str, Any]],
    *,
    provider: str,
) -> dict[str, Any]:
    if len(cases) != len(responses):
        raise ValueError("cases and responses must have the same length")

    invalid_refs = 0
    forbidden_hits = 0
    latencies: list[float] = []
    results = []

    for case, response in zip(cases, responses, strict=True):
        allowed = set(case.get("allowedEvidenceRefs", []))
        cited = set(response.get("evidenceRefs", []))
        unknown = sorted(cited - allowed)
        answer = str(response.get("answer", ""))
        hits = [
            claim
            for claim in case.get("forbiddenClaims", [])
            if str(claim).casefold() in answer.casefold()
        ]
        latency = response.get("latencyMs")
        if isinstance(latency, (int, float)) and latency >= 0:
            latencies.append(float(latency))
        invalid_refs += len(unknown)
        forbidden_hits += len(hits)
        results.append(
            {
                "caseId": case["caseId"],
                "invalidEvidenceRefs": unknown,
                "forbiddenClaimHits": hits,
                "passed": not unknown and not hits,
            }
        )

    return {
        "provider": provider,
        "cases": len(cases),
        "invalidEvidenceRefs": invalid_refs,
        "forbiddenClaimHits": forbidden_hits,
        "passed": invalid_refs == 0 and forbidden_hits == 0,
        "latencyMs": {
            "p50": median(latencies) if latencies else None,
            "p95": _percentile(latencies, 0.95),
        },
        "results": results,
    }
