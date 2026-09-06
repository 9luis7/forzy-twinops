"""Historical copiloting stays bounded, retrospective and free of live/replay IO."""

import asyncio
from copy import deepcopy
from datetime import timedelta
import json

import httpx
import pytest

from twinops.history.assistant import HistoricalAssistantService
from twinops.history.assistant_models import HistoricalQueryRequest, HistoricalQueryResponse
from twinops.history.service import HistoryError
from twinops.rag.demo_service import DemoRagAssistantService
from twinops.rag.generation import ChatGatewayError
from twinops.rag.request_limits import MAX_ASSISTANT_REQUEST_BYTES
from twinops.rag.retrieval import CorpusUnavailableError
from services.twinops.tests.demo.test_demo_replay import normalized_pairs
from services.twinops.tests.demo.test_runtime_isolation import runtime, DEMO_URL, LIVE_URL
from services.twinops.tests.history.test_history import setup
from services.twinops.tests.rag.test_public_service import _Chat, _Retriever, _retrieval


QUERY = '/api/history/v1/datasets/history-test/assistant/query'
CONTEXT = '/api/history/v1/datasets/history-test/context'


class HistoricalScorer:
    def __init__(self):
        self.calls = []

    def assess(self, samples, *, now):
        self.calls.append((deepcopy(samples), now))
        sensor = samples[-1].sensor_id
        return {
            'assessmentId': 'historical-' + sensor,
            'sensorId': sensor,
            'window': {'start': (now - timedelta(seconds=20)).isoformat(),
                       'end': now.isoformat(), 'receivedAt': now.isoformat(), 'freshnessMs': 0},
            'assessment': {'status': 'watch' if sensor == 's1' else 'normal',
                           'scoreSemantics': 'relative_to_historical_baseline_not_failure_probability'},
            'quality': {'status': 'ok', 'flags': []},
            'evidence': [{'id': sensor + ':velocity', 'feature': 'velocity_ewma',
                          'value': samples[-1].measurements.vibration_velocity_rms.value,
                          'unit': 'mm/s', 'windowSeconds': 20}],
            'model': {'trainedUntil': '2026-08-01T00:00:00Z'},
        }


def configured(*, chat=None, retriever=None):
    history, repository, scorer, clock, client = setup(scorer=HistoricalScorer())
    chat, retriever = chat or _Chat(), retriever or _Retriever()
    assistant = HistoricalAssistantService(history, DemoRagAssistantService(retriever, chat))
    client.app.state.historical_assistant_service = assistant
    return history, repository, scorer, clock, client, assistant, retriever, chat


def request_for(context, **updates):
    body = {'question': 'Quais verificações o manual do motor WEG W22 recomenda?',
            'contextRevision': context['revision'],
            'selection': {key: context['selection'][key] for key in ('from', 'to', 'endRow', 'limit')}}
    body.update(updates)
    return body


def test_query_binds_actual_window_two_sensors_without_live_arrival_or_writes():
    history, repository, scorer, _, client, _, retriever, chat = configured()
    context = client.get(CONTEXT, params={'endRow': 100, 'limit': 5}).json()
    assert context['capabilities']['copilot'] is True
    changes = repository._memory.total_changes
    traced = []
    repository._memory.set_trace_callback(traced.append)
    result = client.post(QUERY, json=request_for(context))
    assert result.status_code == 200, result.text
    assert result.headers['cache-control'] == 'no-store'
    body = result.json()
    HistoricalQueryResponse.model_validate(body)
    assert body['schemaVersion'] == 'historical-assistant-1.0'
    assert body['selection'] == context['selection']
    assert body['contextRevision'] == context['revision']
    assert body['datasetId'] == context['dataset']['datasetId']
    assert [(item['sensorId'], item['component']) for item in body['historicalEvidence']] == [('s1', 'motor'), ('s2', 'bomba')]
    for item in body['historicalEvidence']:
        assert item['sourceRow'] == 100
        assert item['observedAt'] == context['selection']['observedAt']
        assert item['evidence'][0]['value'] == 1.99
        assert item['trainedUntil'] == '2026-08-01T00:00:00Z'
        assert 'receivedAt' not in item and 'freshnessMs' not in item
    response = body['response']
    assert response['groundingStatus'] == 'operational_unavailable'
    assert not response['fallbackUsed']
    assert response['citations'] and all(citation['type'] == 'manual' for citation in response['citations'])
    assert 'Condição no instante consultado' in response['answer']['currentState']
    assert 'S1 (motor, associação assumida): atenção' in response['answer']['currentState']
    assert 'S2 (bomba, associação assumida): sem desvio identificado' in response['answer']['currentState']
    assert any('recebimento original é desconhecido' in limitation for limitation in response['limitations'])
    assert any('baseline' in limitation for limitation in response['limitations'])
    assert len(retriever.calls) == len(chat.calls) == 1
    assert '1.99' not in json.dumps(chat.calls)  # No telemetry is treated as document evidence.
    assert repository._memory.total_changes == changes
    assert not any(any(table in statement for table in ('demo_runs', 'demo_commands', 'demo_events')) for statement in traced)
    assert not any(statement.lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE')) for statement in traced)
    assert all(sample.observed_at <= now.isoformat().replace('+00:00', 'Z') for samples, now in scorer.calls for sample in samples)


@pytest.mark.parametrize('selection_change', [{'endRow': 101}, {'limit': 4}, {'from': '2026-05-19T00:00:01Z'}])
def test_stale_selection_is_409_before_any_provider_work(selection_change):
    history, _, _, _, client, _, retriever, chat = configured()
    body = request_for(history.context('history-test', end_row=100, limit=5))
    body['selection'].update(selection_change)
    result = client.post(QUERY, json=body)
    assert result.status_code == 409
    assert result.json() == {'detail': 'historical_context_changed'}
    assert result.headers['cache-control'] == 'no-store'
    assert retriever.calls == chat.calls == []


@pytest.mark.asyncio
async def test_context_is_detached_before_generation_await_and_never_uses_new_selection():
    entered, release = asyncio.Event(), asyncio.Event()

    class WaitingChat(_Chat):
        async def generate(self, messages):
            entered.set()
            await release.wait()
            return await super().generate(messages)

    history, _, _, _, _, _, retriever, _ = configured()
    original = history.context('history-test', end_row=100, limit=5)
    expected = deepcopy(original)

    class SharedContextHistory:
        def context(self, *args, **kwargs):
            return original

    chat = WaitingChat()
    assistant = HistoricalAssistantService(SharedContextHistory(), DemoRagAssistantService(retriever, chat))
    pending = asyncio.create_task(assistant.query('history-test', HistoricalQueryRequest.model_validate(request_for(original))))
    await entered.wait()
    original['revision'] = 'f' * 64
    original['selection']['endRow'] = 800
    original['sensors']['s1']['assessment']['evidence'][0]['value'] = 9000
    release.set()
    result = await pending
    assert result['contextRevision'] == expected['revision']
    assert result['selection'] == expected['selection']
    assert result['historicalEvidence'][0]['evidence'][0]['value'] == 1.99
    assert len(chat.calls) == 1


@pytest.mark.parametrize('question', ['Como lubrificar a bomba?', 'Quais procedimentos usar no sensor 2?',
                                     'How do I replace the pump bearing?', 'Qual é a causa raiz da vibração?',
                                     'Qual a probabilidade de falha?', 'Desligue o motor agora'])
def test_pump_and_unsafe_scope_do_not_call_provider_or_promote_answer(question):
    history, _, _, _, client, _, retriever, chat = configured()
    result = client.post(QUERY, json=request_for(history.context('history-test', end_row=100), question=question))
    assert result.status_code == 200
    assert result.json()['response']['groundingStatus'] == 'out_of_scope'
    assert result.json()['response']['citations'] == []
    assert retriever.calls == chat.calls == []
    assert result.json()['historicalEvidence'][0]['sourceRow'] == 100


@pytest.mark.parametrize('question', ['Como fazer isso?', 'O manual WEG W22 ajuda nisso?'])
def test_pump_followup_does_not_relabel_motor_manual_as_pump_procedure(question):
    history, _, _, _, client, _, retriever, chat = configured()
    request = request_for(history.context('history-test', end_row=100), question=question,
                          history=[{'question': 'Como lubrificar a bomba?', 'answer': 'Sem manual da bomba.'}])
    result = client.post(QUERY, json=request)
    assert result.json()['response']['groundingStatus'] == 'out_of_scope'
    assert retriever.calls == chat.calls == []


@pytest.mark.parametrize('question,turns', [
    ('Quais verificações o manual WEG W22 recomenda para o motor do conjunto motor-bomba?', []),
    ('Quais verificações o manual recomenda para S1 no conjunto motor-bomba?', []),
    ('Agora quero as verificações do manual WEG W22 para o motor.',
     [{'question': 'Como lubrificar a bomba?', 'answer': 'Sem manual da bomba.'}]),
    ('Quais verificações o manual WEG W22 recomenda para o motor do conjunto motor-bomba?',
     [{'question': 'Como lubrificar a bomba?', 'answer': 'Sem manual da bomba.'}]),
    ('Quais outras verificações o manual recomenda?',
     [{'question': 'Como lubrificar a bomba?', 'answer': 'Sem manual da bomba.'},
      {'question': 'Quais verificações há para o motor WEG W22?', 'answer': 'Referência do motor.'}]),
])
def test_motor_topic_and_assembly_context_use_motor_manual(question, turns):
    history, _, _, _, client, _, retriever, chat = configured()
    request = request_for(history.context('history-test', end_row=100), question=question, history=turns)
    result = client.post(QUERY, json=request)
    assert result.status_code == 200
    response = result.json()['response']
    assert response['groundingStatus'] == 'operational_unavailable'
    assert response['citations'] and all(citation['type'] == 'manual' for citation in response['citations'])
    assert len(retriever.calls) == len(chat.calls) == 1


@pytest.mark.parametrize('question', [
    'Quais procedimentos o manual WEG W22 recomenda para a bomba S2?',
    'Como lubrificar a bomba do conjunto motor-bomba?',
    'Quais procedimentos são usados em S1 e S2?',
    'Como lubrificar o conjunto motor-bomba?',
])
def test_explicit_pump_or_mixed_procedures_remain_out_of_scope(question):
    history, _, _, _, client, _, retriever, chat = configured()
    request = request_for(history.context('history-test', end_row=100), question=question,
                          history=[{'question': 'Quais verificações há para o motor?', 'answer': 'Referência do motor.'}])
    result = client.post(QUERY, json=request)
    assert result.status_code == 200
    assert result.json()['response']['groundingStatus'] == 'out_of_scope'
    assert retriever.calls == chat.calls == []


def test_repeated_ambiguous_followup_keeps_latest_pump_refusal_without_scanning_old_topics():
    history, _, _, _, client, _, retriever, chat = configured()
    request = request_for(history.context('history-test', end_row=100), question='E como faço isso?',
                          history=[{'question': 'Quais procedimentos usar em S2?', 'answer': 'Sem manual da bomba.'}])
    previous = client.post(QUERY, json=request).json()['response']['answer']['manual']
    request['question'] = 'Pode explicar melhor?'
    request['history'] = [{'question': 'E como faço isso?', 'answer': previous}]
    result = client.post(QUERY, json=request)
    assert result.json()['response']['groundingStatus'] == 'out_of_scope'
    assert retriever.calls == chat.calls == []


@pytest.mark.parametrize('sufficient,failure,expected', [
    (False, None, 'manual_insufficient'),
    (True, ChatGatewayError('http_status', status_code=429), 'degraded_fallback'),
])
def test_insufficient_or_fallback_status_is_preserved_without_retry(sufficient, failure, expected):
    history, _, _, _, client, _, retriever, chat = configured(
        retriever=_Retriever(_retrieval(sufficient=sufficient)), chat=_Chat(failure=failure))
    result = client.post(QUERY, json=request_for(history.context('history-test', end_row=100), question='bearing'))
    assert result.status_code == 200
    response = result.json()['response']
    assert response['groundingStatus'] == expected
    assert response['fallbackUsed'] is (failure is not None)
    assert len(retriever.calls) == 1
    assert len(chat.calls) == int(sufficient)


def test_missing_corpus_is_sanitized_unavailable_no_generation_or_retry():
    history, _, _, _, client, _, retriever, chat = configured(retriever=_Retriever(failure=CorpusUnavailableError('PRIVATE_CORPUS_DETAIL')))
    result = client.post(QUERY, json=request_for(history.context('history-test', end_row=100)))
    assert result.status_code == 503
    assert result.json() == {'detail': 'historical_assistant_unavailable'}
    assert result.headers['cache-control'] == 'no-store'
    assert len(retriever.calls) == 1
    assert chat.calls == []


@pytest.mark.parametrize('mutation', [
    lambda body: body.update(question='a' * 501),
    lambda body: body.update(history=[{'question': 'a', 'answer': 'b'}] * 5),
    lambda body: body.update(contextRevision=3),
    lambda body: body.update(contextRevision='not-a-revision'),
    lambda body: body.update(measurements={'temperature': 500}),
    lambda body: body['selection'].update(limit='5'),
    lambda body: body['selection'].update(limit=301),
    lambda body: body['selection'].update(endRow=True),
    lambda body: body['selection'].update(receivedAt='2026-09-06T00:00:00Z'),
])
def test_request_is_strict_and_bounded_before_provider(mutation):
    history, _, _, _, client, _, retriever, chat = configured()
    body = request_for(history.context('history-test', end_row=100, limit=5))
    mutation(body)
    response = client.post(QUERY, json=body)
    assert response.status_code == 422
    assert response.json() == {'detail': 'invalid_request'}
    assert response.headers['cache-control'] == 'no-store'
    assert retriever.calls == chat.calls == []


@pytest.mark.asyncio
async def test_chunked_body_limit_is_enforced_before_json_and_provider():
    _, _, _, _, client, _, retriever, chat = configured()

    async def oversized():
        yield b'{"question":"'
        for _ in range(MAX_ASSISTANT_REQUEST_BYTES // 1000 + 1):
            yield b'a' * 1000
        yield b'"}'

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=client.app), base_url='http://test') as http:
        response = await http.post(QUERY, content=oversized())
    assert response.status_code == 413
    assert response.json() == {'detail': 'assistant_request_too_large'}
    assert response.headers['cache-control'] == 'no-store'
    assert retriever.calls == chat.calls == []


def test_unknown_dataset_and_invalid_dates_do_not_invoke_provider():
    history, _, _, _, client, _, retriever, chat = configured()
    body = request_for(history.context('history-test', end_row=100))
    result = client.post(QUERY.replace('history-test', 'other'), json=body)
    assert result.status_code == 404
    body['selection']['from'] = '2026-05-19T00:00:00'
    assert client.post(QUERY, json=body).status_code == 400
    assert retriever.calls == chat.calls == []


def test_capability_tracks_configured_service_and_query_missing_service_is_503():
    history, _, _, _, client, _, _, _ = configured()
    body = request_for(history.context('history-test', end_row=100))
    client.app.state.historical_assistant_service = None
    assert client.get(CONTEXT).json()['capabilities']['copilot'] is False
    result = client.post(QUERY, json=body)
    assert result.status_code == 503
    assert result.headers['cache-control'] == 'no-store'


def test_historical_rag_uses_only_dedicated_corpus_even_with_replay_off_and_live_down(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    app, live, repository, corpus, urls = runtime(monkeypatch, tmp_path, enabled=False,
                                                env_overrides={'DEMO_RAG_EQUIPMENT_MODEL': 'W22',
                                                               'TWINOPS_RAG_EQUIPMENT_MODEL': 'W22 13887610'})
    live.fail = True
    looked_up = []

    def lookup(asset_id):
        looked_up.append(asset_id)
        return None

    corpus[DEMO_URL].get_active_corpus = lookup
    corpus[LIVE_URL].get_active_corpus = lambda *_: pytest.fail('Historical query used live corpus')
    changes = repository._memory.total_changes
    with TestClient(app) as client:
        service = app.state.historical_assistant_service
        assert service is not None
        assert app.state.demo_assistant_service is app.state.demo_service is None
        assert service.assistant.retriever.repository is corpus[DEMO_URL]
        assert service.assistant.retriever.equipment_model == 'W22'
        assert app.state.rag_assistant_service.retriever.equipment_model == 'W22 13887610'
        assert service.assistant.query_timeout_seconds == 40
        context = client.get(CONTEXT.replace('history-test', 'dataset-test'), params={'endRow': 100, 'limit': 5}).json()
        assert context['capabilities']['copilot'] is True
        result = client.post(QUERY.replace('history-test', 'dataset-test'), json=request_for(context))
        assert result.status_code == 503
        assert result.json() == {'detail': 'historical_assistant_unavailable'}
        assert looked_up == ['forzy-motor-01']
        assert live.calls == 0
        assert urls == [DEMO_URL]
        assert repository._memory.total_changes == changes
        assert app.state.settings.database_url == LIVE_URL
    assert app.state.historical_assistant_service is None


def test_missing_dedicated_database_never_enables_historical_rag_from_live_corpus(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    app, _, _, _, _ = runtime(monkeypatch, tmp_path, dedicated=False)
    with TestClient(app) as client:
        assert app.state.historical_assistant_service is None
        assert app.state.demo_assistant_service is not None
        context = client.get(CONTEXT.replace('history-test', 'dataset-test')).json()
        assert context['capabilities']['copilot'] is False


@pytest.mark.asyncio
async def test_future_reading_changes_do_not_change_selected_answer_or_revision():
    contexts, answers = [], []
    for corrupt_future in (False, True):
        pairs = normalized_pairs(800)
        if corrupt_future:
            for pair in pairs[100:]:
                for measurements in pair['sensors'].values():
                    measurements['vibrationVelocityRms']['value'] = 9999
        history, _, _, _, _ = setup(pairs, scorer=HistoricalScorer())
        context = history.context('history-test', end_row=100, limit=5)
        assistant = HistoricalAssistantService(history, DemoRagAssistantService(_Retriever(), _Chat()))
        answer = await assistant.query('history-test', HistoricalQueryRequest.model_validate(request_for(context)))
        contexts.append(context)
        answers.append(answer)
    assert contexts[0]['revision'] == contexts[1]['revision']
    assert answers[0]['historicalEvidence'] == answers[1]['historicalEvidence']
    assert answers[0]['response']['answer'] == answers[1]['response']['answer']


@pytest.mark.asyncio
@pytest.mark.parametrize('mutation', [
    lambda context: context['sensors']['s1']['assessment']['window'].update(end='2027-01-01T00:00:00Z'),
    lambda context: context['sensors']['s1']['latest'].update(sensorId='s2'),
    lambda context: context['sensors']['s2']['assessment'].update(sensorId='s1'),
])
async def test_invalid_server_assessment_is_rejected_before_embeddings(mutation):
    history, _, _, _, _, _, retriever, chat = configured()
    context = history.context('history-test', end_row=100)
    mutation(context)

    class InvalidHistory:
        def context(self, *args, **kwargs):
            return context

    assistant = HistoricalAssistantService(InvalidHistory(), DemoRagAssistantService(retriever, chat))
    with pytest.raises(ValueError):
        await assistant.query('history-test', HistoricalQueryRequest.model_validate(request_for(context)))
    assert retriever.calls == chat.calls == []
