import os

import pytest

from test_sqlite_v2_repository import repository_contract as assert_repository_contract


@pytest.fixture
def repository_contract():
    return assert_repository_contract


@pytest.fixture
def postgres_repo():
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("TEST_DATABASE_URL not configured")

    from twinops.storage.postgres_repository import PostgresTelemetryRepository
    import psycopg

    repository = PostgresTelemetryRepository(database_url)
    repository.initialize()
    with psycopg.connect(database_url) as connection:
        connection.execute(
            "TRUNCATE TABLE collection_attempts_v2, raw_readings_v2, "
            "telemetry_samples_v2"
        )
    try:
        yield repository
    finally:
        with psycopg.connect(database_url) as connection:
            connection.execute(
                "TRUNCATE TABLE collection_attempts_v2, raw_readings_v2, "
                "telemetry_samples_v2"
            )


@pytest.mark.postgres
def test_postgres_repository_satisfies_shared_contract(
    postgres_repo, repository_contract
):
    repository_contract(postgres_repo)
