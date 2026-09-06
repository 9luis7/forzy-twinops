"""Durable attempt limits survive interruption outside normal error finalization."""

import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256

import pytest

from twinops.demo.repository import DemoError, DemoRepository, encode, stamp
import twinops.rag.demo_service as demo_module
from services.twinops.tests.rag.test_demo_service import Repo, service
from services.twinops.tests.rag.test_public_service import _Chat


@pytest.fixture
def storage():
    now = [datetime(2026, 9, 4, 15, tzinfo=timezone.utc)]
    repo = DemoRepository('sqlite:///:memory:', clock=lambda: now[0])
    sample = Repo()
    sample.current['replay'].update(runId='run', expiresAt=stamp(now[0] + timedelta(hours=24)))
    with repo.transaction() as connection:
        repo.sql(connection, 'INSERT INTO demo_runs(run_id,token_hash,expires_at,state) VALUES(?,?,?,?)',
                 ('run', sha256(b'secret').hexdigest(), sample.current['replay']['expiresAt'],
                  encode({'public': sample.current})))
        for event_id in ('event-1', 'event-2'):
            event = {**sample.event, 'eventId': event_id}
            repo.sql(connection, 'INSERT INTO demo_events(event_id,run_id,generation,payload,context) VALUES(?,?,?,?,?)',
                     (event_id, 'run', 0, encode(event), encode(deepcopy(sample.current))))
    return repo, now


class InterruptedChat(_Chat):
    def __init__(self):
        super().__init__()
        self.entered = asyncio.Event()
        self.started_calls = 0

    async def generate(self, messages):
        self.started_calls += 1
        self.entered.set()
        await asyncio.Event().wait()


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['outer_timeout', 'worker_cancel'])
async def test_three_interrupted_attempts_finalize_without_fourth_generation(storage, monkeypatch, mode):
    repo, now = storage
    chat = InterruptedChat()
    assistant = service(repo, chat)
    # Scale only the outer deadline; worker cancellation retains the production 40/30 budgets.
    if mode == 'outer_timeout':
        monkeypatch.setattr(demo_module, 'DEMO_TOTAL_SECONDS', 0.2)
    for attempt in (1, 2, 3):
        chat.entered.clear()
        pending = asyncio.create_task(assistant.recommendation('run', 'secret', 'event-1'))
        await asyncio.wait_for(chat.entered.wait(), 2)
        if mode == 'worker_cancel':
            pending.cancel()
        with pytest.raises(TimeoutError if mode == 'outer_timeout' else asyncio.CancelledError):
            await pending
        event = repo.get_event('run', 'secret', 'event-1')
        assert event['attempts'] == attempt
        assert event['status'] == 'processing'
        # Even the third attempt remains owned until its original lease expires.
        assert repo.claim_event('run', 'secret', 'event-1', owner='impatient-retry') is None
        assert repo.get_event('run', 'secret', 'event-1') == event
        assert repo.claim_event('run', 'secret', 'event-2', owner='next-worker') is None
        now[0] += timedelta(seconds=61)

    terminal = await assistant.recommendation('run', 'secret', 'event-1')
    assert chat.started_calls == 3
    assert terminal['attempts'] == 3
    assert terminal['status'] == 'degraded'
    assert terminal['recommendation'] is None
    assert terminal['retryable'] is False
    assert terminal['errorCode'] == 'event_attempts_exhausted'
    assert await assistant.recommendation('run', 'secret', 'event-1') == terminal
    assert repo.finish_event('run', 'secret', 'event-1', owner='expired-worker', status='ready',
                             recommendation={'unsafe': 'late result'}) == terminal
    with repo.transaction() as connection:
        ownership = repo.sql(connection, 'SELECT owner,lease_until FROM demo_events WHERE event_id=?', ('event-1',)).fetchone()
        assert ownership['owner'] is None and ownership['lease_until'] is None
    # The following queued event can enter the real assistant/citation path immediately.
    next_event = await service(repo, _Chat()).recommendation('run', 'secret', 'event-2')
    assert next_event['status'] == 'ready'
    assert next_event['attempts'] == 1
    assert any(citation['type'] == 'manual' for citation in next_event['recommendation']['citations'])
    assert chat.started_calls == 3


def test_exhaustion_keeps_authorization_generation_and_other_lease_fences(storage):
    repo, now = storage
    for attempt in (1, 2, 3):
        claim = repo.claim_event('run', 'secret', 'event-1', owner=f'dead-worker-{attempt}')
        assert claim['event']['attempts'] == attempt
        now[0] += timedelta(seconds=61)
    before = repo.get_event('run', 'secret', 'event-1')
    for run_id, token in (('run', 'wrong'), ('wrong-run', 'secret')):
        with pytest.raises(DemoError) as denied:
            repo.claim_event(run_id, token, 'event-1', owner='unauthorized')
        assert denied.value.status_code == 404
    assert repo.get_event('run', 'secret', 'event-1') == before

    # A different event's active lease is checked before any exhaustion finalization.
    assert repo.claim_event('run', 'secret', 'event-2', owner='active-other')
    assert repo.claim_event('run', 'secret', 'event-1', owner='recovery') is None
    assert repo.get_event('run', 'secret', 'event-1') == before
    now[0] += timedelta(seconds=61)
    with repo.transaction() as connection:
        state = repo.authorized(connection, 'run', 'secret')
        state['public']['replay']['generation'] = 1
        repo.save(connection, state)
    with pytest.raises(DemoError) as obsolete:
        repo.claim_event('run', 'secret', 'event-1', owner='obsolete-generation')
    assert obsolete.value.status_code == 404
    with repo.transaction() as connection:
        unchanged = repo.sql(connection, 'SELECT payload FROM demo_events WHERE event_id=?', ('event-1',)).fetchone()
        assert unchanged['payload'] == encode(before)
