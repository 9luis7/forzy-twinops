"""Command-line runtime for API service, collector, and CSV import."""

import argparse
import asyncio
from datetime import datetime, timezone
import os
from pathlib import Path

import httpx
import uvicorn

from twinops.config import Settings
from twinops.ingestion.collector import Collector
from twinops.ingestion.csv_importer import import_csv
from twinops.ingestion.forzy_history import import_forzy_history
from twinops.ingestion.schedule import CollectionWindow
from twinops.ingestion.upstream import UpstreamClient
from twinops.main import create_app
from twinops.ml.runtime import load_assessment_scorer
from twinops.storage.repository import TelemetryRepository
from twinops.storage.sqlite_repository import SQLiteTelemetryRepository


def create_collector(
    http: httpx.AsyncClient,
    repository: TelemetryRepository,
    settings: Settings,
) -> Collector:
    return Collector(
        UpstreamClient(
            http,
            settings.upstream_base_url,
            settings.request_timeout_seconds,
        ),
        repository,
        settings.asset_tag,
        window=CollectionWindow(settings.timezone_name),
        poll_interval_seconds=settings.poll_interval_seconds,
    )


def main() -> None:
    parser = argparse.ArgumentParser(prog="twinops")
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("serve")
    subcommands.add_parser("collect")
    csv_parser = subcommands.add_parser("import-csv")
    csv_parser.add_argument("path", type=Path)
    forzy_parser = subcommands.add_parser("import-forzy-history")
    forzy_parser.add_argument("path", type=Path)
    args = parser.parse_args()

    settings = Settings.from_env(os.environ)
    repository = SQLiteTelemetryRepository(settings.database_path)
    repository.initialize()

    if args.command == "serve":
        scorer = None
        if settings.ml_artifact_path is not None:
            assert settings.ml_manifest_hash is not None
            assert settings.ml_model_hash is not None
            scorer = load_assessment_scorer(
                settings.ml_artifact_path,
                expected_manifest_hash=settings.ml_manifest_hash,
                expected_model_hash=settings.ml_model_hash,
            )
        uvicorn.run(
            create_app(repository, settings, assessment_scorer=scorer),
            host="127.0.0.1",
            port=8000,
        )
        return
    if args.command == "import-csv":
        print(
            import_csv(
                args.path,
                repository,
                settings.asset_tag,
                datetime.now(timezone.utc),
            )
        )
        return
    if args.command == "import-forzy-history":
        print(
            import_forzy_history(
                args.path,
                repository,
                asset_tag=settings.asset_tag,
                timezone_name=settings.timezone_name,
                received_at=datetime.now(timezone.utc),
            )
        )
        return

    async def collect() -> None:
        stop = asyncio.Event()
        async with httpx.AsyncClient() as http:
            collector = create_collector(http, repository, settings)
            await collector.run(
                stop=stop,
                interval_seconds=settings.poll_interval_seconds,
                clock=lambda: datetime.now(timezone.utc),
                sleep=asyncio.sleep,
            )

    try:
        asyncio.run(collect())
    except KeyboardInterrupt:
        return


if __name__ == "__main__":
    main()
