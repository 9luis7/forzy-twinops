"""Import a pinned source into demo tables and record sanitized exact-readback proof."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import parse_qsl, unquote, urlsplit

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


def dedicated_demo_url(settings, project_ref):
    """Select only the explicitly named dedicated Supabase destination."""
    if not isinstance(project_ref, str) or re.fullmatch(r"[a-z0-9]{20}", project_ref) is None:
        raise ValueError("expected_demo_project_ref_required")
    url = settings.get("DEMO_DATABASE_URL", "")
    try:
        parsed = urlsplit(url)
        if (
            parsed.scheme not in {"postgres", "postgresql"}
            or re.fullmatch(r"aws-[0-9]+-[a-z0-9-]+\.pooler\.supabase\.com", parsed.hostname or "") is None
            or parsed.port != 5432 or parsed.path != "/postgres"
            or unquote(parsed.username or "") != f"postgres.{project_ref}"
            or not parsed.password or parsed.fragment
            or parse_qsl(parsed.query, keep_blank_values=True) not in (
                [("sslmode", "require")], [("sslmode", "verify-full")],
            )
            or url == settings.get("DATABASE_URL")
        ):
            raise ValueError
    except (ValueError, TypeError):
        raise ValueError("dedicated_demo_destination_mismatch") from None
    return url


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--env-file", required=True)
    parser.add_argument("--environment", choices=("preview", "production"), required=True)
    parser.add_argument("--initialize", action="store_true")
    parser.add_argument("--demo-project-ref", help="Use only DEMO_DATABASE_URL for this dedicated Supabase project; never connect live")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    settings = load_environment(args.env_file)
    dedicated = args.demo_project_ref is not None
    url = dedicated_demo_url(settings, args.demo_project_ref) if dedicated else settings["DATABASE_URL"]
    metadata, pairs = read_history(args.source, expected_hash=SOURCE_HASH)
    assert (len(pairs), metadata["readingCount"]) == (7183, 14366)
    assert metadata["sourceFormat"] == "zip-ooxml"
    with psycopg.connect(url, connect_timeout=8) as connection:
        connection.execute("SET TRANSACTION READ ONLY")
        connection.execute("SET LOCAL statement_timeout=10000")
        identity = connection.execute("SELECT current_database(),current_user").fetchone()
        expected = ("postgres", "postgres") if dedicated else tuple(
            settings["RAG_" + args.environment.upper() + suffix]
            for suffix in ("_DATABASE_NAME", "_DATABASE_USER"))
        if identity != expected:
            raise ValueError("database_identity_mismatch")
        if dedicated and not connection.pgconn.ssl_in_use:
            raise ValueError("database_tls_not_active")
        before = None if dedicated else live_fingerprint(connection)

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
    after = None
    if not dedicated:
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
        "databaseMode": "dedicated-demo" if dedicated else "shared-live",
        "demoProjectRef": args.demo_project_ref,
        "liveConnected": not dedicated,
        "liveFingerprintVerified": not dedicated,
        "equalTimestampPairs": sum(gap == 0 for gap in gaps),
        "gapsOver15Seconds": sum(gap > 15 for gap in gaps), "largestGapSeconds": max(gaps),
        "consecutiveRepeatedReadings": duplicates,
    }
    Path(args.output).write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "pairs": len(pairs), "exactReadback": True,
                      "liveConnected": not dedicated,
                      "liveFingerprintVerified": not dedicated, "idempotent": True}))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # Database drivers may include credentials or private hosts in errors.
        print(json.dumps({"ok": False, "errorType": type(error).__name__}))
        raise SystemExit(1) from None
