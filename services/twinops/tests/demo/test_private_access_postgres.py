"""Private Data API boundary, in an isolated database on CI's disposable PG only."""
import os
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict
import pytest


TABLES = (
    'demo_datasets', 'demo_runs', 'demo_commands', 'demo_events',
    'rag_corpora', 'rag_documents', 'rag_chunks', 'rag_active_corpus',
)
MIGRATIONS = Path(__file__).resolve().parents[2] / 'migrations'


def _disposable_parameters(env):
    """Fail closed before any socket or destructive fixture action."""
    if env.get('CI') != 'true' or not env.get('TEST_DATABASE_URL'):
        return None
    if any(env.get(key) for key in ('PGSERVICE', 'PGSERVICEFILE', 'PGHOSTADDR', 'PGOPTIONS')):
        return None
    try:
        parameters = conninfo_to_dict(env['TEST_DATABASE_URL'])
    except psycopg.ProgrammingError:
        return None
    if not set(parameters) <= {'user', 'password', 'host', 'port', 'dbname', 'sslmode', 'connect_timeout'}:
        return None
    if (parameters.get('host') not in {'localhost', '127.0.0.1'}
            or parameters.get('port', '5432') != '5432'
            or parameters.get('dbname') != 'twinops_test'
            or parameters.get('user') != 'twinops_test'):
        return None
    return {**parameters, 'connect_timeout': 5}


@pytest.fixture
def disposable_private_database():
    parameters = _disposable_parameters(os.environ)
    if parameters is None:
        pytest.skip('Requires CI disposable localhost twinops_test PostgreSQL; external targets are forbidden')
    database_name = 'demo_private_test_' + uuid4().hex
    with psycopg.connect(**parameters, autocommit=True) as admin:
        # Validate the actual peer before CREATE DATABASE, even for localhost DNS.
        assert admin.info.hostaddr in {'127.0.0.1', '::1'}
        admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(database_name)))
        try:
            with psycopg.connect(**{**parameters, 'dbname': database_name}) as connection:
                try:
                    yield connection
                finally:
                    # Table and cluster-level test role creation are transactional.
                    connection.rollback()
        finally:
            admin.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(database_name)))


@pytest.mark.postgres
def test_private_migration_blocks_api_roles_preserves_owner_and_other_tables(disposable_private_database):
    connection = disposable_private_database
    for name in ('003_rag_asset_aware_v1.sql', '004_demo_replay_v1.sql'):
        connection.execute((MIGRATIONS / name).read_text(encoding='utf-8'))
    migration = (MIGRATIONS / '005_demo_private_access.sql').read_text(encoding='utf-8')
    # The CI cluster should have neither Supabase API role. Never drop existing roles.
    assert not connection.execute(
        "SELECT 1 FROM pg_roles WHERE rolname IN ('anon', 'authenticated')"
    ).fetchall(), 'Disposable cluster must start without Supabase roles'
    connection.execute(migration)  # Works on ordinary PostgreSQL without API roles.
    for role in ('anon', 'authenticated'):
        connection.execute(sql.SQL('CREATE ROLE {} NOLOGIN').format(sql.Identifier(role)))

    owner = 'demo_owner_' + uuid4().hex
    connection.execute(sql.SQL('CREATE ROLE {} NOLOGIN').format(sql.Identifier(owner)))
    connection.execute(sql.SQL('GRANT USAGE, CREATE ON SCHEMA public TO {}').format(sql.Identifier(owner)))
    connection.execute('GRANT USAGE ON SCHEMA public TO anon, authenticated')
    # A non-superuser owner proves ENABLE RLS did not disable the backend path.
    for table in TABLES:
        connection.execute(sql.SQL('ALTER TABLE public.{} OWNER TO {}').format(
            sql.Identifier(table), sql.Identifier(owner)))
        connection.execute(sql.SQL('GRANT ALL ON TABLE public.{} TO PUBLIC, anon, authenticated').format(
            sql.Identifier(table)))
    connection.execute('CREATE TABLE public.telemetry_samples_v2 (id INTEGER)')
    connection.execute('GRANT SELECT ON public.telemetry_samples_v2 TO anon')
    sentinel_before = connection.execute(
        "SELECT relrowsecurity, relacl::text FROM pg_class WHERE oid='public.telemetry_samples_v2'::regclass"
    ).fetchone()
    connection.execute(sql.SQL('SET LOCAL ROLE {}').format(sql.Identifier(owner)))
    connection.execute(migration)
    connection.execute(migration)  # Repeat is safe after all privileges were revoked.
    connection.execute('RESET ROLE')
    assert connection.execute(
        "SELECT relrowsecurity, relacl::text FROM pg_class WHERE oid='public.telemetry_samples_v2'::regclass"
    ).fetchone() == sentinel_before

    for table in TABLES:
        row = connection.execute(
            'SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE oid=%s::regclass',
            ('public.' + table,),
        ).fetchone()
        assert row == (True, False)
        assert connection.execute(
            'SELECT COUNT(*) FROM pg_policies WHERE schemaname=%s AND tablename=%s',
            ('public', table),
        ).fetchone()[0] == 0
        for role in ('anon', 'authenticated'):
            for privilege in ('SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'REFERENCES', 'TRIGGER'):
                assert not connection.execute(
                    'SELECT has_table_privilege(%s,%s,%s)', (role, 'public.' + table, privilege)
                ).fetchone()[0]
            column = ('dataset_id' if table == 'demo_datasets' else
                      'run_id' if table in {'demo_runs', 'demo_commands', 'demo_events'} else
                      'corpus_id')
            statements = (
                'SELECT * FROM public.{}', 'INSERT INTO public.{} DEFAULT VALUES',
                'DELETE FROM public.{}', f'UPDATE public.{{}} SET {column}={column}',
            )
            for statement in statements:
                with pytest.raises(psycopg.errors.InsufficientPrivilege):
                    with connection.transaction():
                        connection.execute(sql.SQL('SET LOCAL ROLE {}').format(sql.Identifier(role)))
                        connection.execute(sql.SQL(statement).format(sql.Identifier(table)))

    connection.execute(sql.SQL('SET LOCAL ROLE {}').format(sql.Identifier(owner)))
    for table in TABLES:
        assert connection.execute(sql.SQL('SELECT COUNT(*) FROM public.{}').format(sql.Identifier(table))).fetchone()[0] == 0
    connection.execute("INSERT INTO public.demo_datasets VALUES ('private-test', '{}', '[]')")
    assert connection.execute('SELECT COUNT(*) FROM public.demo_datasets').fetchone()[0] == 1
    connection.execute("UPDATE public.demo_datasets SET metadata='{}' WHERE dataset_id='private-test'")
    connection.execute("DELETE FROM public.demo_datasets WHERE dataset_id='private-test'")
    connection.execute('RESET ROLE')


@pytest.mark.parametrize('env', [
    {},
    {'TEST_DATABASE_URL': 'postgresql://twinops_test:test@localhost:5432/twinops_test'},
    {'CI': 'true', 'TEST_DATABASE_URL': 'postgresql://twinops_test:test@remote.invalid:5432/twinops_test'},
    {'CI': 'true', 'TEST_DATABASE_URL': 'postgresql://twinops_test:test@localhost:5432/production'},
    {'CI': 'true', 'TEST_DATABASE_URL': 'postgresql://owner:test@localhost:5432/twinops_test'},
    {'CI': 'true', 'TEST_DATABASE_URL': 'postgresql://twinops_test:test@localhost:5432/twinops_test?hostaddr=192.0.2.1'},
    {'CI': 'true', 'TEST_DATABASE_URL': 'postgresql://twinops_test:test@localhost:5432/twinops_test', 'PGSERVICE': 'production'},
])
def test_destructive_fixture_refuses_non_ci_or_non_disposable_target_before_connect(env):
    assert _disposable_parameters(env) is None


def test_disposable_gate_accepts_only_the_existing_ci_service_configuration():
    parameters = _disposable_parameters({
        'CI': 'true',
        'TEST_DATABASE_URL': 'postgresql://twinops_test:test@localhost:5432/twinops_test',
    })
    assert parameters is not None
    assert parameters['host'] == 'localhost'
    assert parameters['dbname'] == 'twinops_test'
    assert parameters['connect_timeout'] == 5
