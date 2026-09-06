"""Exercise isolated real replay sessions, pinned ML, retries and rate invariance."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from scripts.verify_demo_import import dedicated_demo_url, load_environment
from twinops.demo.repository import DemoError, DemoRepository
from twinops.demo.service import DemoService
from twinops.ml.runtime import load_assessment_scorer


def command(context, action=None):
    return {"commandId": str(uuid4()), "expectedRevision": context["revision"],
            **({"action": action} if action else {})}


def score_signature(context):
    return {
        sensor: {"assessment": value["assessment"]["assessment"] if value["assessment"] else None,
                 "quality": value["assessment"]["quality"] if value["assessment"] else None,
                 "evidence": value["assessment"]["evidence"] if value["assessment"] else None}
        for sensor, value in context["sensors"].items()
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--demo-project-ref", help="Use only the explicitly named dedicated demo database")
    args = parser.parse_args()
    settings = load_environment(args.env_file)
    url = (dedicated_demo_url(settings, args.demo_project_ref)
           if args.demo_project_ref is not None else settings["DATABASE_URL"])
    repository = DemoRepository(url, initialize=False)
    scorer = load_assessment_scorer(
        settings["TWINOPS_ML_ARTIFACT_PATH"],
        expected_manifest_hash=settings["TWINOPS_ML_MANIFEST_HASH"],
        expected_model_hash=settings["TWINOPS_ML_MODEL_HASH"],
    )
    service = DemoService(repository, scorer)
    dataset = next(item for item in repository.datasets()
                   if item["datasetId"] == "forzy-history-debbd57af9b90b8a")
    runs = [service.create_run(dataset["datasetId"], "guided", speed) for speed in (1, 2, 5)]
    assert len({run["runId"] for run in runs}) == 3
    try:
        service.context(runs[0]["runId"], runs[1]["token"])
        raise AssertionError("cross_session_authorization_failed")
    except DemoError as error:
        assert error.status_code == 404

    def replay(run):
        started = perf_counter()
        run_id, token = run["runId"], run["token"]
        context = service.control(run_id, token, command(run["context"], "play"))
        signatures, arrivals_distinct = {}, True
        while context["replay"]["state"] != "completed":
            context = service.advance(run_id, token, command(context))
            assert context["replay"]["sourceRow"] == 140 + context["replay"]["cursor"]
            for sensor in context["sensors"].values():
                latest = sensor["latest"]
                arrivals_distinct &= latest["receivedAt"] != latest["observedAt"]
                if sensor["assessment"]:
                    end = datetime.fromisoformat(sensor["assessment"]["window"]["end"].replace("Z", "+00:00"))
                    observed = datetime.fromisoformat(latest["observedAt"].replace("Z", "+00:00"))
                    assert end <= observed, "assessment_uses_future_source_time"
            if context["replay"]["cursor"] % 10 == 0:
                signatures[context["replay"]["cursor"]] = score_signature(context)
        return {
            "speed": context["replay"]["speed"], "pairs": context["replay"]["cursor"],
            "originalAndArrivalClocksDistinct": arrivals_distinct,
            "pipeline": context["pipeline"], "signatures": signatures,
            "events": [(e["kind"], e["sourceRow"], e["sensorIds"]) for e in context["events"]],
            "elapsedSeconds": round(perf_counter() - started, 3),
        }

    with ThreadPoolExecutor(max_workers=3) as workers:
        results = list(workers.map(replay, runs))
    assert all(result["pairs"] == 300 and result["originalAndArrivalClocksDistinct"] for result in results)
    assert results[0]["signatures"] == results[1]["signatures"] == results[2]["signatures"], "rate_score_divergence"
    assert results[0]["events"] == results[1]["events"] == results[2]["events"], "rate_event_divergence"

    # One exact command submitted concurrently must commit precisely one pair.
    run = service.create_run(dataset["datasetId"], "guided", 1)
    running = service.control(run["runId"], run["token"], command(run["context"], "play"))
    body = command(running)
    with ThreadPoolExecutor(max_workers=2) as workers:
        futures = [workers.submit(service.advance, run["runId"], run["token"], body) for _ in range(2)]
        first, second = [future.result() for future in futures]
    assert first == second and first["replay"]["cursor"] == 1
    paused = service.control(run["runId"], run["token"], command(first, "pause"))
    stalled = service.advance(run["runId"], run["token"], command(paused))
    assert stalled["replay"]["cursor"] == 1
    restarted = service.control(run["runId"], run["token"], command(stalled, "restart"))
    assert restarted["replay"]["cursor"] == 0 and restarted["replay"]["generation"] == 1
    assert all(service.context(r["runId"], r["token"])["replay"]["cursor"] == 300 for r in runs)
    for result in results:
        result.pop("signatures")
    report = {
        "verifiedAt": datetime.now(timezone.utc).isoformat(),
        "database": "dedicated-demo" if args.demo_project_ref else "existing-postgresql",
        "demoProjectRef": args.demo_project_ref,
        "modelManifestHash": settings["TWINOPS_ML_MANIFEST_HASH"],
        "modelHash": settings["TWINOPS_ML_MODEL_HASH"], "concurrentSessions": 3,
        "matchedSourceCursorsAcrossAllRates": list(range(10, 301, 10)),
        "scoresQualityEvidenceEqual": True, "eventSequencesEqual": True,
        "duplicateConcurrentCommandExactlyOnce": True, "sessionIsolation": True,
        "pauseAndRestart": True, "runs": results,
        "note": "Service and PostgreSQL exercised directly; wall time is accelerated for verification. Browser pacing and actual RAG provider require deployed acceptance.",
    }
    Path(args.output).write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "sessions": 3, "matchedCursors": 30,
                      "events": len(results[0]["events"]), "idempotent": True}))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(json.dumps({"ok": False, "errorType": type(error).__name__,
                          "assertion": str(error) if isinstance(error, AssertionError) else None}))
        raise SystemExit(1) from None
