"""Recommend a threshold from strict raw retrieval captures without persistence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from capture_schema import CalibrationCapture, read_capture_jsonl
from validate import validate


def _read_manifest(path: Path) -> list[dict]:
    errors = validate(path, require_complete=True)
    if errors:
        raise ValueError("; ".join(errors))
    return [
        json.loads(raw)
        for raw in path.read_text(encoding="utf-8").splitlines()
        if raw.strip()
    ]


def _expected_chunk_ids(case: dict) -> list[str]:
    return [anchor["chunkId"] for anchor in case["expectedManualEvidence"]]


def _index_exact(captures: list[CalibrationCapture]) -> dict[str, CalibrationCapture]:
    by_id = {capture.case_id: capture for capture in captures}
    if len(by_id) != len(captures):
        raise ValueError("capture case ids must be unique")
    return by_id


def calibrate(manifest_path: Path, captures_path: Path) -> dict[str, float]:
    cases = _read_manifest(manifest_path)
    real_cases = [case for case in cases if case["caseKind"] == "real_manual"]
    captures = read_capture_jsonl(captures_path, CalibrationCapture)
    by_id = _index_exact(captures)
    expected_ids = {case["id"] for case in real_cases}
    if set(by_id) != expected_ids:
        raise ValueError(
            "calibration captures must match completed real-manual cases exactly; "
            "synthetic fixtures are excluded"
        )
    for case in real_cases:
        if by_id[case["id"]].question != case["question"]:
            raise ValueError("capture question does not match manifest")

    supported = [case for case in real_cases if case["manualExpectation"] == "supported"]
    refusals = [case for case in real_cases if case["manualExpectation"] != "supported"]
    expected_count = sum(len(_expected_chunk_ids(case)) for case in supported)
    if expected_count == 0 or not refusals:
        raise ValueError("calibration requires real support and refusal cases")

    expected_scores: list[float | None] = []
    for case in supported:
        score_by_chunk = {
            hit.chunk_id: hit.absolute_score for hit in by_id[case["id"]].hits
        }
        expected_scores.extend(
            score_by_chunk.get(chunk_id) for chunk_id in _expected_chunk_ids(case)
        )
    negative_scores = [
        hit.absolute_score
        for case in refusals
        for hit in by_id[case["id"]].hits
    ]
    max_negative = max(negative_scores, default=0.0)
    above_negative = sorted(
        score
        for score in expected_scores
        if score is not None and score > max_negative
    )
    threshold = 0.0
    if above_negative:
        all_retrieved = [score for score in expected_scores if score is not None]
        threshold = (
            min(all_retrieved)
            if all_retrieved and max_negative < min(all_retrieved)
            else (max_negative + above_negative[0]) / 2
        )

    recalled = sum(
        score is not None and score >= threshold for score in expected_scores
    )
    recall = recalled / expected_count
    correct_refusals = sum(
        not any(hit.absolute_score >= threshold for hit in by_id[case["id"]].hits)
        for case in refusals
    )
    refusal_accuracy = correct_refusals / len(refusals)
    metrics = {
        "recall_at_6": recall,
        "refusal_accuracy": refusal_accuracy,
        "recommended_threshold": threshold,
    }
    if threshold <= 0 or recall < 0.9 or refusal_accuracy != 1.0:
        raise RuntimeError(json.dumps(metrics, sort_keys=True))
    return metrics


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("captures", type=Path)
    args = parser.parse_args(argv)
    try:
        metrics = calibrate(args.manifest, args.captures)
    except Exception as exc:
        detail = str(exc)
        print(f"calibration_failed detail={detail}", file=sys.stderr)
        return 1
    print(
        "calibration_ok "
        f"recall_at_6={metrics['recall_at_6']:.3f} "
        f"refusal_accuracy={metrics['refusal_accuracy']:.3f} "
        f"recommended_threshold={metrics['recommended_threshold']!r}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
