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
from twinops.ingestion.schedule import CollectionWindow
from twinops.ingestion.upstream import UpstreamClient
from twinops.main import create_app
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
    args = parser.parse_args()

    settings = Settings.from_env(os.environ)
    repository = SQLiteTelemetryRepository(settings.database_path)
    repository.initialize()

    if args.command == "serve":
        uvicorn.run(
            create_app(repository, settings), host="127.0.0.1", port=8000
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
