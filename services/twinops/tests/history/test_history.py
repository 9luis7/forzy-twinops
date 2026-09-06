"""Local-only acceptance of real-history reads and isolated composition."""
from contextlib import contextmanager
from datetime import timedelta
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from twinops.demo.repository import DemoRepository, parse
from twinops.demo.service import DemoService
from twinops.history.routes import create_history_router
from twinops.history.service import HistoryError, HistoryService
from twinops.ml.baseline import BaselineConfig, RobustBaseline
from twinops.ml.curation import curate_samples
from twinops.ml.features import FeatureConfig, compute_trailing_features
from twinops.ml.scorer import AssessmentScorer
from services.twinops.tests.demo.test_demo_replay import Clock, Scorer, normalized_pairs
from services.twinops.tests.demo.test_runtime_isolation import runtime, DEMO_URL


PRIVATE = 'PRIVATE_HISTORY_SENTINEL'
CONTEXT = '/api/history/v1/datasets/history-test/context'


def setup(pairs=None, scorer=None):
    pairs = normalized_pairs(800) if pairs is None else pairs
    clock, scorer = Clock(), scorer or Scorer()
    repository = DemoRepository('sqlite:///:memory:', clock=clock)
    metadata = {
        'datasetId': 'history-test', 'label': 'Histórico real Forzy',
        'pairCount': len(pairs), 'readingCount': len(pairs) * 2,
        'startAt': pairs[0]['observedAt'] if pairs else None,
        'endAt': pairs[-1]['observedAt'] if pairs else None,
        'sourceFormat': 'csv', 'sourceHash': PRIVATE, 'path': PRIVATE,
        'guided': {'startRow': 141, 'endRow': 440}, 'raw': PRIVATE,
    }
    repository.import_dataset(metadata, pairs)
    service = HistoryService(repository, scorer, clock)
    app = FastAPI()
    app.state.history_service = service
    app.include_router(create_history_router())
    return service, repository, scorer, clock, TestClient(app)


def test_latest_page_has_real_times_no_arrival_or_replay_and_only_two_scores():
    service, repository, scorer, _, client = setup()
    changes = repository._memory.total_changes
    traced = []
    repository._memory.set_trace_callback(traced.append)
    response = client.get(CONTEXT)
    assert response.status_code == 200
    assert response.headers['cache-control'] == 'no-store'
    body = response.json()
    assert body['schemaVersion'] == 'historical-1.0'
    assert body['mode'] == 'historical'
    assert body['selection'] == {
        'from': None, 'to': None, 'endRow': 800, 'limit': 300,
        'observedAt': body['sensors']['s1']['latest']['observedAt'],
        'totalPairs': 800, 'returnedPairs': 300,
        'hasPrevious': True, 'previousEndRow': 500, 'hasNext': False, 'nextEndRow': None,
    }
    assert len(body['history']) == 600
    assert body['history'][0]['sourceRow'] == 501
    assert body['history'][-1]['sourceRow'] == 800
    assert all(frame['receivedAt'] is None and frame['preloaded'] is False for frame in body['history'])
    assert body['capabilities'] == {'twin3d': True, 'copilot': False, 'replayControls': False}
    assert {'replay', 'events', 'pipeline', 'runId', 'token'}.isdisjoint(body)
    assert all(not sensor['newInformation'] for sensor in body['sensors'].values())
    assert len(scorer.calls) == 2
    assert repository._memory.total_changes == changes
    assert not any(sql.lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE')) for sql in traced)
    assert not any('demo_runs' in sql or 'demo_events' in sql or 'demo_commands' in sql for sql in traced)
    assert len(service.repository._dataset_cache) == 1


def test_public_allowlists_strip_private_nested_and_dataset_values():
    pairs = normalized_pairs(5)
    for pair in pairs:
        pair.update(raw=PRIVATE, pdi=PRIVATE, path=PRIVATE)
        pair['sensors']['private'] = PRIVATE
        for sensor in ('s1', 's2'):
            pair['sensors'][sensor]['private'] = PRIVATE
            pair['sensors'][sensor]['temperature']['secret'] = PRIVATE
    _, _, _, _, client = setup(pairs)
    catalog = client.get('/api/history/v1/datasets')
    context = client.get(CONTEXT)
    assert catalog.status_code == context.status_code == 200
    assert PRIVATE not in catalog.text + context.text
    assert set(catalog.json()['datasets'][0]) == {
        'datasetId', 'label', 'pairCount', 'readingCount', 'startAt', 'endAt', 'sourceFormat',
    }
    assert set(context.json()['history'][0]) == {
        'frameId', 'sensorId', 'sourceRow', 'observedAt', 'receivedAt', 'measurements', 'qualityFlags', 'gapBefore', 'preloaded',
    }


def test_row_pagination_preserves_equal_timestamps_and_date_bounds():
    pairs = normalized_pairs(9)
    for index in range(3, 6):
        pairs[index]['observedAt'] = pairs[3]['observedAt']
    service, _, scorer, _, _ = setup(pairs)
    kwargs = {'from_time': pairs[1]['observedAt'], 'to_time': pairs[7]['observedAt'], 'limit': 2}
    last = service.context('history-test', **kwargs)
    middle = service.context('history-test', end_row=last['selection']['previousEndRow'], **kwargs)
    first = service.context('history-test', end_row=middle['selection']['previousEndRow'], **kwargs)
    earliest = service.context('history-test', end_row=first['selection']['previousEndRow'], **kwargs)
    windows = [earliest, first, middle, last]
    assert [[frame['sourceRow'] for frame in body['history'][::2]] for body in windows] == [[2], [3, 4], [5, 6], [7, 8]]
    assert all(body['selection']['totalPairs'] == 7 for body in windows)
    assert not earliest['selection']['hasPrevious']
    # Cursor identity is source order, not timestamp; no tied row is skipped.
    assert first['selection']['nextEndRow'] == 6
    next_page = service.context('history-test', end_row=first['selection']['nextEndRow'], **kwargs)
    assert next_page['history'] == middle['history']
    for samples, now in scorer.calls:
        assert all(parse(sample.observed_at) <= now for sample in samples)
    first_end_samples = scorer.calls[4][0]
    assert max(int(str(sample.reading_id).split('-')[0], 16) for sample in first_end_samples) == 4


def test_scoring_uses_causal_configured_tail_before_display_filter():
    pairs = normalized_pairs(500, seconds=1)
    scorer = Scorer()
    scorer.feature_config = SimpleNamespace(long_window_seconds=90)
    scorer.baseline = SimpleNamespace(config=SimpleNamespace(persistence_seconds=120))
    service, _, _, _, _ = setup(pairs, scorer)
    body = service.context('history-test', from_time=pairs[198]['observedAt'], end_row=200, limit=1)
    assert [frame['sourceRow'] for frame in body['history']] == [200, 200]
    assert len(scorer.calls) == 2
    for samples, now in scorer.calls:
        assert now == parse(pairs[199]['observedAt'])
        assert [int(str(sample.reading_id).split('-')[0], 16) for sample in samples] == list(range(79, 201))
        assert all(sample.received_at == sample.observed_at for sample in samples)
    assert body['sensors']['s1']['latest']['receivedAt'] is None


def test_stable_revision_changes_with_selection_but_not_request_time():
    service, _, _, clock, _ = setup()
    first = service.context('history-test', end_row=50, limit=5)
    clock.now += timedelta(hours=1)
    second = service.context('history-test', end_row=50, limit=5)
    assert first['revision'] == second['revision']
    assert first['generatedAt'] != second['generatedAt']
    assert first['revision'] != service.context('history-test', end_row=51, limit=5)['revision']
    assert first['revision'] != service.context('history-test', end_row=50, limit=4)['revision']


def test_gap_and_duplicate_quality_are_preserved_without_new_arrivals():
    pairs = normalized_pairs(5, repeated=True)
    pairs[3]['observedAt'] = pairs[4]['observedAt'] = '2026-05-19T00:01:00Z'
    pairs[3]['qualityFlags'] = ['observed_timezone_assumed:America/Sao_Paulo']
    service, _, _, _, _ = setup(pairs)
    body = service.context('history-test')
    frames = body['history'][::2]
    assert frames[0]['qualityFlags'] == []
    assert 'duplicate_payload' in frames[1]['qualityFlags']
    assert frames[3]['gapBefore']
    assert frames[3]['qualityFlags'] == ['observed_timezone_assumed:America/Sao_Paulo', 'gap_before']
    assert 'duplicate_payload' in frames[4]['qualityFlags']


@pytest.mark.parametrize('params,detail', [
    ({'from': '2026-05-19'}, 'historical_timezone_required'),
    ({'to': '2026-05-19T00:00:00'}, 'historical_timezone_required'),
    ({'from': 'bad'}, 'invalid_historical_interval'),
    ({'from': '2026-05-20T00:00:00Z', 'to': '2026-05-19T00:00:00Z'}, 'invalid_historical_interval'),
    ({'from': '2027-01-01T00:00:00Z'}, 'historical_selection_empty'),
    ({'to': '2020-01-01T00:00:00Z'}, 'historical_selection_empty'),
    ({'from': '2026-05-19T00:01:00Z', 'endRow': 2}, 'historical_selection_empty'),
    ({'limit': 0}, 'invalid_historical_selection'),
    ({'limit': 301}, 'invalid_historical_selection'),
    ({'endRow': 0}, 'invalid_historical_selection'),
    ({'endRow': 'abc'}, 'invalid_historical_selection'),
])
def test_invalid_or_empty_windows_are_explicit_noncacheable(params, detail):
    _, _, scorer, _, client = setup()
    response = client.get(CONTEXT, params=params)
    assert response.status_code == 400
    assert response.json() == {'detail': detail}
    assert response.headers['cache-control'] == 'no-store'
    assert not scorer.calls


def test_timezone_equivalence_is_inclusive_and_empty_dataset_is_explicit():
    service, _, _, _, _ = setup(normalized_pairs(3))
    context = service.context('history-test', from_time='2026-05-18T21:00:00-03:00', to_time='2026-05-19T00:00:02Z')
    assert context['selection']['returnedPairs'] == 2
    assert context['selection']['from'] == '2026-05-19T00:00:00.000000Z'
    service, _, scorer, _, _ = setup([])
    with pytest.raises(HistoryError, match='historical_selection_empty'):
        service.context('history-test')
    assert not scorer.calls


def test_unknown_dataset_is_404_and_unavailable_errors_never_expose_details(caplog):
    _, _, _, _, client = setup()
    unknown = client.get('/api/history/v1/datasets/unknown/context')
    assert unknown.status_code == 404
    assert unknown.json() == {'detail': 'historical_dataset_not_found'}
    assert unknown.headers['cache-control'] == 'no-store'
    client.app.state.history_service = None
    missing = client.get(CONTEXT)
    assert missing.status_code == 503
    assert missing.headers['cache-control'] == 'no-store'

    class BrokenRepository:
        def datasets(self):
            raise RuntimeError(PRIVATE)

        @contextmanager
        def transaction(self):
            raise RuntimeError(PRIVATE)
            yield

    client.app.state.history_service = HistoryService(BrokenRepository(), Scorer())
    for path in [CONTEXT, '/api/history/v1/datasets']:
        response = client.get(path)
        assert response.status_code == 503
        assert response.json() == {'detail': 'historical_unavailable'}
        assert response.headers['cache-control'] == 'no-store'
        assert PRIVATE not in response.text
    assert PRIVATE not in caplog.text


def test_real_scorer_matches_prefix_and_preserves_retrospective_model_metadata():
    pairs = normalized_pairs(180, seconds=1)
    feature_config = FeatureConfig(10, 60, 3)
    metadata = {'datasetId': 'history-test'}
    times = [parse(pair['observedAt']) for pair in pairs]
    calibration = [DemoService._canonical(HistoryService._frame(metadata, pairs, times, index, sensor))
                   for sensor in ('s1', 's2') for index in range(90)]
    baseline = RobustBaseline(BaselineConfig(persistence_seconds=30)).fit(
        compute_trailing_features(curate_samples(calibration, gap_seconds=15), feature_config))
    scorer = AssessmentScorer(baseline, feature_config=feature_config)
    service, _, _, _, _ = setup(pairs, scorer)
    # The baseline is deliberately trained beyond this selected instant. This is
    # retrospective analysis, and its trainedUntil must not be hidden or rewritten.
    body = service.context('history-test', end_row=80, limit=3)
    for sensor in ('s1', 's2'):
        expected = scorer.assess(
            [DemoService._canonical(HistoryService._frame(metadata, pairs, times, index, sensor)) for index in range(80)],
            now=times[79],
        ).model_dump(by_alias=True, mode='json')
        actual = body['sensors'][sensor]['assessment']
        assert actual['model'] == expected['model']
        assert parse(actual['model']['trainedUntil']) > times[79]
        assert actual['quality'] == expected['quality']
        assert actual['assessment'] == expected['assessment']
        assert actual['humanValidationRequired']
        assert actual['retrospective']
        assert actual['window']['receivedAt'] is None
        assert actual['window']['freshnessMs'] is None
        assert actual['assessment']['scoreSemantics'] == 'relative_to_historical_baseline_not_failure_probability'


def test_history_remains_read_only_with_replay_disabled_and_live_unavailable(monkeypatch, tmp_path):
    app, live, demo, _, urls = runtime(monkeypatch, tmp_path, enabled=False)
    live.fail = True
    original_live_url = app.state.settings.database_url
    changes = demo._memory.total_changes
    with TestClient(app) as client:
        assert app.state.demo_service is None
        assert app.state.demo_assistant_service is None
        assert urls == [DEMO_URL]
        assert app.state.history_service.repository is demo
        assert live.calls == 0
        assert client.get('/api/demo/v1/datasets').status_code == 404
        assert client.get('/api/v2/assets/forzy-motor-01/history').status_code == 503
        assert live.calls == 1
        assert client.get('/api/history/v1/datasets').status_code == 200
        result = client.get('/api/history/v1/datasets/dataset-test/context', params={'limit': 1})
        assert result.status_code == 200
        assert result.json()['mode'] == 'historical'
        assert result.json()['capabilities']['copilot'] is True
        assert live.calls == 1
        assert demo._memory.total_changes == changes
        assert app.state.settings.database_url == original_live_url
    assert app.state.history_service is None
