"""Import a pinned source into demo tables and record sanitized exact-readback proof."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import psycopg

from twinops.demo.importer import read_history
from twinops.demo.repository import DemoRepository


SOURCE_HASH = "debbd57af9b90b8aa70f5794c48fa759afd0ec291d8b56c0c80ed63bfc670c5e"


def load_environment(path):
    result = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        result[key] = json.loads(value) if value.startswith('"') else value
    return result


def live_fingerprint(connection):
    samples = connection.execute(
        "SELECT reading_id,payload_hash,canonical_json FROM telemetry_samples_v2 ORDER BY reading_id"
    ).fetchall()
    latest = connection.execute(
        "SELECT asset_id,sensor_id,reading_id,canonical_json FROM latest_readings_v2 ORDER BY asset_id,sensor_id"
    ).fetchall()
    return {
        "sampleCount": len(samples), "latestCount": len(latest),
        "sha256": hashlib.sha256(json.dumps([samples, latest], separators=(",", ":")).encode()).hexdigest(),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--env-file", required=True)
    parser.add_argument("--environment", choices=("preview", "production"), required=True)
    parser.add_argument("--initialize", action="store_true")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    settings = load_environment(args.env_file)
    url = settings["DATABASE_URL"]
    metadata, pairs = read_history(args.source, expected_hash=SOURCE_HASH)
    assert (len(pairs), metadata["readingCount"]) == (7183, 14366)
    assert metadata["sourceFormat"] == "zip-ooxml"
    with psycopg.connect(url, connect_timeout=8) as connection:
        connection.execute("SET TRANSACTION READ ONLY")
        connection.execute("SET LOCAL statement_timeout=10000")
        identity = connection.execute("SELECT current_database(),current_user").fetchone()
        expected = tuple(settings["RAG_" + args.environment.upper() + suffix]
                         for suffix in ("_DATABASE_NAME", "_DATABASE_USER"))
        if identity != expected:
            raise ValueError("database_identity_mismatch")
        before = live_fingerprint(connection)

    repository = DemoRepository(url, initialize=False)
    if args.initialize:
        repository.initialize()
    repository.import_dataset(metadata, pairs)
    repository.import_dataset(metadata, pairs)
    with repository.transaction() as connection:
        stored_metadata, stored_pairs = repository.dataset(connection, metadata["datasetId"])
        assert stored_metadata == metadata and stored_pairs == pairs, "exact_readback_failed"
        dataset_count = repository.sql(connection,
            "SELECT COUNT(*) AS count FROM demo_datasets WHERE dataset_id=?",
            (metadata["datasetId"],)).fetchone()["count"]
        assert dataset_count == 1, "import_idempotence_failed"
    with psycopg.connect(url, connect_timeout=8) as connection:
        connection.execute("SET TRANSACTION READ ONLY")
        after = live_fingerprint(connection)
    assert after == before, "live_changed_during_import"
    moments = [datetime.fromisoformat(pair["observedAt"].replace("Z", "+00:00")) for pair in pairs]
    gaps = [(right - left).total_seconds() for left, right in zip(moments, moments[1:])]
    duplicates = {
        sensor: sum(left["sensors"][sensor] == right["sensors"][sensor]
                    for left, right in zip(pairs, pairs[1:]))
        for sensor in ("s1", "s2")
    }
    report = {
        "verifiedAt": datetime.now(timezone.utc).isoformat(), "environment": args.environment,
        "dataset": metadata, "databaseIdentityMatched": True,
        "exactReadback": True, "idempotentImport": True,
        "liveBefore": before, "liveAfter": after,
        "equalTimestampPairs": sum(gap == 0 for gap in gaps),
        "gapsOver15Seconds": sum(gap > 15 for gap in gaps), "largestGapSeconds": max(gaps),
        "consecutiveRepeatedReadings": duplicates,
    }
    Path(args.output).write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "pairs": len(pairs), "exactReadback": True,
                      "livePreserved": True, "idempotent": True}))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # Database drivers may include credentials or private hosts in errors.
        print(json.dumps({"ok": False, "errorType": type(error).__name__}))
        raise SystemExit(1) from None
