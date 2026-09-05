"""Offline composition checks: local state only, no provider or database sockets."""
import asyncio
from types import SimpleNamespace

from fastapi.testclient import TestClient
import psycopg
import pytest

from twinops import main_v2
from twinops.config_v2 import SettingsV2
from twinops.storage.sqlite_v2_repository import SQLiteTelemetryRepositoryV2
from services.twinops.tests.demo.test_demo_replay import setup


LIVE_URL = 'postgresql://user:secret@ep-live-pooler.us-east-1.aws.neon.tech/live?sslmode=require'
DEMO_URL = 'postgresql://postgres.project:secret@aws-0-sa-east-1.pooler.supabase.com:5432/postgres?sslmode=require'
PRIVATE = 'PRIVATE_DATABASE_ERROR_SENTINEL'


class LocalLive(SQLiteTelemetryRepositoryV2):
    def __init__(self, path):
        super().__init__(path)
        self.calls = 0
        self.fail = False
        self.fail_history = False

    def initialize(self):
        self.calls += 1
        if self.fail:
            raise psycopg.OperationalError(PRIVATE)
        super().initialize()

    def history(self, query):
        if self.fail_history:
            raise psycopg.OperationalError(PRIVATE)
        return super().history(query)


def runtime(monkeypatch, tmp_path, *, dedicated=True, enabled=True):
    live = LocalLive(tmp_path / 'live.sqlite3')
    demo, _, scorer, clock = setup()
    corpus = {}
    demo_urls = []
    monkeypatch.setattr(main_v2, 'PostgresTelemetryRepository', lambda *a, **k: live)

    def rag_repository(url, **kwargs):
        corpus[url] = SimpleNamespace(url=url)
        return corpus[url]

    def demo_repository(url, **kwargs):
        demo_urls.append(url)
        return demo

    monkeypatch.setattr(main_v2, 'PostgresRagRepository', rag_repository)
    monkeypatch.setattr(main_v2, 'DemoRepository', demo_repository)
    monkeypatch.setattr(main_v2, '_load_configured_scorer', lambda settings: scorer)
    monkeypatch.setattr(main_v2, '_build_embedding_clients', lambda *a: (object(), object()))
    monkeypatch.setattr(main_v2, '_build_chat_client', lambda *a, **k: SimpleNamespace(model='offline'))
    env = {'TWINOPS_UPSTREAM_BASE_URL': 'https://upstream.invalid', 'DATABASE_URL': LIVE_URL, 'DEMO_ENABLED': str(enabled).lower(),
           'TWINOPS_RAG_ENABLED': 'true', 'TWINOPS_RAG_MANUFACTURER': 'WEG',
           'TWINOPS_RAG_EQUIPMENT_MODEL': 'W22'}
    if dedicated:
        env['DEMO_DATABASE_URL'] = DEMO_URL
    app = main_v2.create_app_v2_from_env(env, clock=clock)
    return app, live, demo, corpus, demo_urls


def test_dedicated_demo_replays_without_initializing_live(monkeypatch, tmp_path):
    app, live, demo, corpus, urls = runtime(monkeypatch, tmp_path)
    live.fail = True
    with TestClient(app) as client:
        assert live.calls == 0
        assert client.get('/api/demo/v1/datasets').status_code == 200
        result = client.post('/api/demo/v1/runs', json={
            'datasetId': 'dataset-test', 'scenario': 'full', 'speed': 1})
        assert result.status_code == 200
        run = result.json()
        headers = {'Authorization': 'Bearer ' + run['token']}
        response = client.post(f"/api/demo/v1/runs/{run['runId']}/control", headers=headers,
                               json={'commandId': 'one', 'expectedRevision': 0, 'action': 'step'})
        assert response.status_code == 200
        assert response.json()['replay']['cursor'] == 1
        replay = client.post(f"/api/demo/v1/runs/{run['runId']}/control", headers=headers,
                             json={'commandId': 'one', 'expectedRevision': 0, 'action': 'step'})
        assert replay.json() == response.json()
        assert live.calls == 0
        assert urls == [DEMO_URL]
        assistant = app.state.demo_assistant_service
        assert assistant.repository is demo
        assert assistant.assistant.retriever.repository is corpus[DEMO_URL]
        assert app.state.rag_assistant_service.retriever.repository is corpus[LIVE_URL]
        assert assistant.assistant.query_timeout_seconds == 40
        assert app.state.rag_assistant_service.query_timeout_seconds == 10


def test_live_failure_is_sanitized_and_recovers_without_restarting_demo(monkeypatch, tmp_path, caplog):
    app, live, _, _, _ = runtime(monkeypatch, tmp_path)
    ticks = [100.0]
    monkeypatch.setattr(main_v2, 'monotonic', lambda: ticks[0])
    live.fail = True
    with TestClient(app) as client:
        for path in ['/api/v2/integration/health', '/api/v2/assets/forzy-motor-01/history',
                     '/api/v2/assets/forzy-motor-01/twin-context']:
            response = client.get(path)
            assert response.status_code == 503
            assert response.json() == {'detail': 'live_unavailable'}
            assert response.headers['cache-control'] == 'no-store'
            assert response.headers['retry-after'] == '30'
        assert live.calls == 1
        assert client.get('/api/demo/v1/datasets').status_code == 200
        assert client.get('/api/v2/assets/unknown/history').status_code == 404
        live.fail = False
        ticks[0] += 31
        assert client.get('/api/v2/assets/forzy-motor-01/history').status_code == 200
        assert live.calls == 2
        live.fail_history = True
        assert client.get('/api/v2/assets/forzy-motor-01/history').status_code == 503
        assert client.get('/api/demo/v1/datasets').status_code == 200
        live.fail_history = False
        ticks[0] += 31
        assert client.get('/api/v2/assets/forzy-motor-01/history').status_code == 200
        assert live.calls == 3
    assert PRIVATE not in caplog.text


def test_missing_dedicated_corpus_never_falls_back_to_live(monkeypatch, tmp_path):
    app, live, _, corpus, _ = runtime(monkeypatch, tmp_path)
    looked_up = []

    def dedicated_lookup(asset_id):
        looked_up.append(asset_id)
        return None

    def forbidden_live_lookup(asset_id):
        pytest.fail('Demo attempted live corpus access')

    corpus[DEMO_URL].get_active_corpus = dedicated_lookup
    corpus[LIVE_URL].get_active_corpus = forbidden_live_lookup
    with TestClient(app) as client:
        result = client.post('/api/demo/v1/runs', json={
            'datasetId': 'dataset-test', 'scenario': 'full', 'speed': 1})
        run = result.json()
        response = client.post(f"/api/demo/v1/runs/{run['runId']}/assistant/query",
                               headers={'Authorization': 'Bearer ' + run['token']},
                               json={'question': 'Como lubrificar o motor WEG?', 'contextRevision': 0})
        assert response.status_code == 503
        assert response.json() == {'detail': 'demo_assistant_unavailable'}
        assert looked_up == ['forzy-motor-01']
        assert live.calls == 0
        assert client.get('/api/demo/v1/datasets').status_code == 200


@pytest.mark.parametrize('dedicated,enabled', [(False, True), (True, False)])
def test_default_live_startup_and_shared_corpus_unchanged(monkeypatch, tmp_path, dedicated, enabled):
    app, live, demo, corpus, urls = runtime(monkeypatch, tmp_path, dedicated=dedicated, enabled=enabled)
    with TestClient(app):
        assert live.calls == 1
        assert app.state.live_availability is None
        if enabled:
            assert urls == [LIVE_URL]
            assert app.state.demo_assistant_service.assistant.retriever.repository is corpus[LIVE_URL]
        else:
            assert app.state.demo_service is None
            assert urls == []


def test_shared_database_keeps_eager_startup_failure(monkeypatch, tmp_path):
    app, live, _, _, _ = runtime(monkeypatch, tmp_path, dedicated=False)
    live.fail = True
    with pytest.raises(psycopg.OperationalError):
        with TestClient(app):
            pass


def test_lazy_live_initialization_is_single_flight():
    repository = SimpleNamespace(calls=0)

    def initialize():
        repository.calls += 1

    repository.initialize = initialize

    async def run():
        availability = main_v2._LiveAvailability(repository)
        assert all(await asyncio.gather(*(availability.ensure_ready() for _ in range(20))))

    asyncio.run(run())
    assert repository.calls == 1


@pytest.mark.parametrize('url', [DEMO_URL, DEMO_URL.replace(':5432', ''), LIVE_URL])
def test_dedicated_configuration_accepts_only_explicit_secure_providers(url):
    settings = SettingsV2.from_env({'TWINOPS_UPSTREAM_BASE_URL': 'https://upstream.invalid', 'DATABASE_URL': LIVE_URL, 'DEMO_DATABASE_URL': url, 'DEMO_ENABLED': 'true'})
    assert settings.effective_demo_database_url == url
    assert settings.has_dedicated_demo_database == (url != LIVE_URL)
    assert 'secret' not in repr(settings)


@pytest.mark.parametrize('url', [
    DEMO_URL.replace('sslmode=require', 'sslmode=disable'),
    DEMO_URL.replace('?sslmode=require', ''),
    DEMO_URL + '&sslmode=require',
    DEMO_URL + '&host=attacker.invalid',
    DEMO_URL + '&hostaddr=127.0.0.1',
    DEMO_URL.replace(':5432', ':6543'),
    DEMO_URL.replace(':5432', ':9999'),
    DEMO_URL.replace('pooler.supabase.com', 'pooler.supabase.com.attacker.invalid'),
    'postgresql://secret@example-pooler.invalid/db?sslmode=require',
    'sqlite:///local.sqlite3',
])
def test_dedicated_configuration_rejects_unsafe_or_unapproved_urls(url):
    with pytest.raises(ValueError, match='DEMO_DATABASE_URL') as error:
        SettingsV2.from_env({'TWINOPS_UPSTREAM_BASE_URL': 'https://upstream.invalid', 'DEMO_DATABASE_URL': url})
    assert url not in str(error.value)


def test_unset_demo_url_preserves_database_fallback():
    settings = SettingsV2.from_env({'TWINOPS_UPSTREAM_BASE_URL': 'https://upstream.invalid', 'DATABASE_URL': LIVE_URL, 'DEMO_ENABLED': 'true'})
    assert settings.effective_demo_database_url == LIVE_URL
    assert not settings.has_dedicated_demo_database
