from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
import uuid
from zipfile import ZipFile

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from twinops.demo.importer import EXPECTED, import_history, read_history
from twinops.demo.repository import DemoError, DemoRepository, encode, stamp
from twinops.demo.routes import create_demo_router
from twinops.demo.service import DemoService
from twinops.ml.curation import curate_samples


class Clock:
    def __init__(self):
        self.now = datetime(2026, 9, 4, tzinfo=timezone.utc)

    def __call__(self):
        return self.now


class Scorer:
    def __init__(self):
        self.calls = []
        self.failure_at = None
        self.status = 'normal'

    def assess(self, samples, *, now):
        self.calls.append((samples, now))
        if self.failure_at == len(self.calls):
            raise RuntimeError('deliberate scoring failure')
        return {'quality': {'status': 'ok'}, 'assessment': {'status': self.status, 'persistenceSeconds': 30}}


def normalized_pairs(count=500, *, seconds=2, repeated=False):
    result = []
    start = datetime(2026, 5, 19, tzinfo=timezone.utc)
    for i in range(count):
        value = 1.0 if repeated else 1 + i / 100
        sensors = {sensor: {
            'vibrationVelocityRms': {'value': value, 'unit': 'mm/s', 'semanticConfidence': 'inferred_from_datasheet'},
            'vibrationAcceleration': {'value': 0.1, 'unit': 'g', 'statistic': 'unknown', 'semanticConfidence': 'unconfirmed'},
            'temperature': {'value': 30.0, 'unit': 'degC', 'semanticConfidence': 'inferred_from_datasheet'},
        } for sensor in ('s1', 's2')}
        result.append({'sourceRow': i + 1, 'observedAt': stamp(start + timedelta(seconds=i * seconds)), 'sensors': sensors, 'qualityFlags': []})
    return result


def setup(pairs=None, path=':memory:'):
    pairs = pairs or normalized_pairs()
    clock, scorer = Clock(), Scorer()
    repository = DemoRepository('sqlite:///' + str(path), clock=clock)
    metadata = {'datasetId': 'dataset-test', 'label': 'Test', 'pairCount': len(pairs), 'readingCount': len(pairs) * 2,
                'startAt': pairs[0]['observedAt'], 'endAt': pairs[-1]['observedAt'], 'sourceHash': 'sha256:' + 'a' * 64,
                'sourceFormat': 'csv', 'guided': {'startRow': 141, 'endRow': 440}}
    repository.import_dataset(metadata, pairs)
    return repository, DemoService(repository, scorer, clock), scorer, clock


def command(service, run, action, *, key=None, revision=None, **kwargs):
    current = service.context(run['runId'], run['token'])
    body = {'commandId': key or str(uuid.uuid4()), 'expectedRevision': current['revision'] if revision is None else revision, **kwargs}
    if action == 'advance':
        return service.advance(run['runId'], run['token'], body)
    return service.control(run['runId'], run['token'], {**body, 'action': action})


def assert_error(code, detail, operation):
    with pytest.raises(DemoError) as error:
        operation()
    assert (error.value.status_code, error.value.detail) == (code, detail)


def test_guided_warmup_and_full_no_future():
    repository, service, scorer, _ = setup()
    full = service.create_run('dataset-test', 'full', 1)
    assert full['context']['history'] == []
    guided = service.create_run('dataset-test', 'guided', 1)
    initial = guided['context']
    assert initial['replay']['warmupPairs'] == 31
    assert initial['pipeline']['receivedPairs'] == 0
    assert all(row['sourceRow'] < 141 and row['preloaded'] for row in initial['history'])
    first = command(service, guided, 'step')
    assert first['replay']['sourceRow'] == 141
    assert first['pipeline']['receivedReadings'] == 2
    for samples, now in scorer.calls:
        assert all(datetime.fromisoformat(sample.observed_at.replace('Z', '+00:00')) <= now for sample in samples)
        assert all(sample.received_at == sample.observed_at for sample in samples)
    assert first['sensors']['s1']['latest']['receivedAt'] != first['replay']['sourceTime']


@pytest.mark.parametrize('speed', [1, 2, 5])
def test_speed_control_and_restart(speed):
    _, service, _, _ = setup()
    run = service.create_run('dataset-test', 'full', speed)
    command(service, run, 'advance')
    assert service.context(run['runId'], run['token'])['replay']['cursor'] == 0
    command(service, run, 'play')
    result = command(service, run, 'advance')
    assert result['replay']['cursor'] == speed
    assert result['pipeline']['assessmentsComputed'] == speed * 2
    command(service, run, 'pause')
    changed = command(service, run, 'speed', speed=5)
    assert changed['replay']['cursor'] == speed
    reset = command(service, run, 'restart')
    assert reset['replay']['generation'] == 1
    assert reset['replay']['cursor'] == 0
    assert reset['history'] == []


def test_exact_command_idempotence_and_conflicting_reuse():
    _, service, _, _ = setup()
    run = service.create_run('dataset-test', 'full', 1)
    first = command(service, run, 'step', key='same', revision=0)
    again = command(service, run, 'step', key='same', revision=0)
    assert first == again
    assert_error(409, 'command_id_conflict', lambda: command(service, run, 'pause', key='same', revision=0))
    assert_error(409, 'revision_conflict', lambda: command(service, run, 'step', revision=0))


def test_command_retention_keeps_identity_without_reexecution():
    repository, service, _, _ = setup()
    run = service.create_run('dataset-test', 'full', 1)
    command(service, run, 'step', key='old', revision=0)
    for _ in range(9):
        last = command(service, run, 'step')
    assert_error(409, 'command_response_expired', lambda: command(service, run, 'step', key='old', revision=0))
    assert service.context(run['runId'], run['token'])['replay']['cursor'] == 10
    with repository.transaction() as connection:
        rows = repository.sql(connection, 'SELECT response FROM demo_commands WHERE run_id=?', (run['runId'],)).fetchall()
    assert len(rows) == 10
    assert sum(row['response'] is not None for row in rows) == 8


def test_cleanup_expired_cascades_demo_only_and_preserves_active():
    repository, service, scorer, clock = setup()
    scorer.status = 'watch'
    expired = service.create_run('dataset-test', 'full', 1)
    for _ in range(4):
        command(service, expired, 'step')
    with repository.transaction() as connection:
        repository.sql(connection, 'CREATE TABLE live_test_sentinel (value TEXT)')
        repository.sql(connection, "INSERT INTO live_test_sentinel VALUES ('keep')")
    clock.now += timedelta(hours=12)
    active = service.create_run('dataset-test', 'full', 1)
    clock.now += timedelta(hours=12)
    assert repository.cleanup_expired(limit=1) == 1
    assert service.context(active['runId'], active['token'])['replay']['cursor'] == 0
    with repository.transaction() as connection:
        assert repository.sql(connection, 'SELECT COUNT(*) AS n FROM demo_commands').fetchone()['n'] == 0
        assert repository.sql(connection, 'SELECT COUNT(*) AS n FROM demo_events').fetchone()['n'] == 0
        assert repository.sql(connection, 'SELECT value FROM live_test_sentinel').fetchone()['value'] == 'keep'
    with pytest.raises(ValueError):
        repository.cleanup_expired(101)


def test_new_session_performs_bounded_expiry_cleanup():
    repository, service, _, clock = setup()
    expired = service.create_run('dataset-test', 'full', 1)
    clock.now += timedelta(hours=25)
    assert_error(410, 'run_expired', lambda: service.context(expired['runId'], expired['token']))
    assert_error(404, 'run_not_found', lambda: service.context(expired['runId'], 'wrong-token'))
    service.create_run('dataset-test', 'full', 1)
    # Garbage collection intentionally discards expired identities; no unbounded tombstones.
    assert_error(404, 'run_not_found', lambda: service.context(expired['runId'], expired['token']))
    assert_error(404, 'run_not_found', lambda: service.context(expired['runId'], 'wrong-token'))
    with repository.transaction() as connection:
        assert repository.sql(connection, 'SELECT COUNT(*) AS n FROM demo_runs').fetchone()['n'] == 1


def test_concurrent_revisions_and_isolation(tmp_path):
    repository, service, _, clock = setup(path=tmp_path / 'demo.db')
    other_repository = DemoRepository('sqlite:///' + str(tmp_path / 'demo.db'), clock=clock)
    other_service = DemoService(other_repository, Scorer(), clock)
    run = service.create_run('dataset-test', 'full', 1)
    def attempt(index):
        try:
            return command((service, other_service)[index], run, 'step', key=f'concurrent-{index}', revision=0)
        except DemoError as error:
            return error.detail
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, (0, 1)))
    assert sum(isinstance(result, dict) for result in results) == 1
    assert 'revision_conflict' in results
    other = service.create_run('dataset-test', 'full', 1)
    assert service.context(other['runId'], other['token'])['replay']['cursor'] == 0
    assert_error(404, 'run_not_found', lambda: service.context(run['runId'], other['token']))
    clock.now += timedelta(hours=24)
    assert_error(410, 'run_expired', lambda: service.context(run['runId'], run['token']))


def test_batch_rollback_on_scorer_failure():
    _, service, scorer, _ = setup()
    run = service.create_run('dataset-test', 'full', 5)
    before = command(service, run, 'play')
    scorer.failure_at = 4
    with pytest.raises(RuntimeError):
        command(service, run, 'advance')
    assert service.context(run['runId'], run['token']) == before


def test_repeated_raw_cadence_reuse_expiry_and_gap():
    pairs = normalized_pairs(30, seconds=2, repeated=True)
    pairs[20]['observedAt'] = stamp(datetime(2026, 5, 19, tzinfo=timezone.utc) + timedelta(seconds=100))
    _, service, scorer, _ = setup(pairs)
    run = service.create_run('dataset-test', 'full', 1)
    first = command(service, run, 'step')
    second = command(service, run, 'step')
    assert second['sensors']['s1']['assessmentState'] == 'reused'
    assert second['pipeline']['repeatedReadings'] == 2
    for _ in range(15):
        last = command(service, run, 'step')
    assert last['sensors']['s1']['assessmentState'] == 'computed'
    assert len(scorer.calls[-1][0]) == 17
    curated = curate_samples(scorer.calls[-1][0], gap_seconds=15)
    assert curated['cadence_seconds'].iloc[-1] == 2
    for _ in range(4):
        last = command(service, run, 'step')
    assert last['sensors']['s1']['latest']['gapBefore']
    assert last['sensors']['s1']['assessmentState'] == 'computed'
    assert last['pipeline']['gapCount'] == 1


def test_equal_timestamp_keeps_source_row_order():
    pairs = normalized_pairs(3, seconds=0)
    _, service, scorer, _ = setup(pairs)
    run = service.create_run('dataset-test', 'full', 1)
    for _ in pairs:
        command(service, run, 'step')
    curated = curate_samples(scorer.calls[-1][0], gap_seconds=15)
    assert list(curated.velocity_rms) == [1.0, 1.01, 1.02]


def test_episodes_and_lease_recovery_fencing():
    repository, service, scorer, clock = setup()
    scorer.status = 'watch'
    run = service.create_run('dataset-test', 'full', 1)
    for _ in range(4):
        context = command(service, run, 'step')
    assert len(context['events']) == 1
    event = context['events'][0]
    assert event['kind'] == 'sustained_watch'
    assert event['sensorIds'] == ['s1', 's2']
    frozen = repository.event_context(run['runId'], run['token'], event['eventId'])
    scorer.status = 'alert'
    context = command(service, run, 'step')
    assert len(context['events']) == 2
    assert repository.event_context(run['runId'], run['token'], event['eventId']) == frozen
    claim = repository.claim_event(run['runId'], run['token'], event['eventId'], owner='first', lease_seconds=10)
    assert claim['context'] == frozen
    assert repository.claim_event(run['runId'], run['token'], context['events'][1]['eventId'], owner='other') is None
    clock.now += timedelta(seconds=11)
    assert repository.claim_event(run['runId'], run['token'], event['eventId'], owner='second')
    assert_error(409, 'lease_conflict', lambda: repository.finish_event(run['runId'], run['token'], event['eventId'], owner='first', status='ready'))
    ready = repository.finish_event(run['runId'], run['token'], event['eventId'], owner='second', status='ready', recommendation={'answer': 'frozen'})
    assert repository.finish_event(run['runId'], run['token'], event['eventId'], owner='second', status='degraded') == ready
    scorer.status = 'insufficient_data'
    for _ in range(8):
        context = command(service, run, 'step')
    assert len(context['events']) == 2
    scorer.status = 'normal'
    for _ in range(6):
        context = command(service, run, 'step')
    assert context['events'][-1]['kind'] == 'recovery'
    command(service, run, 'restart')
    assert_error(404, 'event_not_found', lambda: repository.get_event(run['runId'], run['token'], event['eventId']))


def test_http_no_store_and_authorization():
    _, service, _, _ = setup()
    app = FastAPI()
    app.state.demo_service = service
    app.include_router(create_demo_router())
    with TestClient(app) as client:
        response = client.get('/api/demo/v1/datasets')
        assert response.headers['cache-control'] == 'no-store'
        run = client.post('/api/demo/v1/runs', json={'datasetId': 'dataset-test', 'scenario': 'full', 'speed': 1}).json()
        denied = client.get(f"/api/demo/v1/runs/{run['runId']}/context")
        assert denied.status_code == 404
        assert denied.headers['cache-control'] == 'no-store'
        valid = client.post(f"/api/demo/v1/runs/{run['runId']}/control", headers={'Authorization': 'Bearer ' + run['token']},
                            json={'action': 'step', 'commandId': 'a', 'expectedRevision': 0})
        assert valid.status_code == 200
        assert valid.json()['replay']['sourceRow'] == 1
        invalid = client.post('/api/demo/v1/runs', json={'datasetId': 'dataset-test', 'scenario': 'full', 'speed': 3})
        assert invalid.status_code == 422
        assert invalid.headers['cache-control'] == 'no-store'


def test_real_pinned_scorer_receives_raw_prefix_and_invalidates_gap():
    from twinops.ml.runtime import load_assessment_scorer
    root = Path(__file__).resolve().parents[4]
    actual = load_assessment_scorer(root / 'artifacts/ml/real-forzy',
        expected_manifest_hash='sha256:fe2cbd7e1b576f04b2c6380e41ecb7c97df7faa5084c39c4b0d16db786afe7f0',
        expected_model_hash='sha256:68d00121edbf8c4c01cf7cd231cd57c4c8eff25661135494e3c791ca78e562ba')
    pairs = normalized_pairs(5, seconds=2)
    pairs[1]['sensors'] = pairs[0]['sensors']
    pairs[4]['observedAt'] = '2026-05-19T00:01:00.000000Z'
    repository, service, _, clock = setup(pairs)
    service.scorer = actual
    run = service.create_run('dataset-test', 'full', 1)
    for _ in range(4):
        context = command(service, run, 'step')
    frames = [row for row in context['history'] if row['sensorId'] == 's1']
    assert len(frames) == 4
    expected = actual.assess([service._canonical(frame) for frame in frames], now=datetime(2026, 5, 19, 0, 0, 6, tzinfo=timezone.utc))
    projected = expected.model_dump(by_alias=True, mode='json')
    projected['window']['receivedAt'] = context['sensors']['s1']['latest']['receivedAt']
    assert context['sensors']['s1']['assessment'] == projected
    assert projected['window']['receivedAt'].startswith('2026-09-04')
    assert projected['window']['end'].startswith('2026-05-19')
    after_gap = command(service, run, 'step')
    assert after_gap['sensors']['s1']['assessment']['quality']['status'] == 'insufficient_data'
    assert after_gap['sensors']['s1']['latest']['gapBefore'] is True


def test_reused_assessment_preserves_arrival_and_ages_on_original_clock():
    repository, service, scorer, clock = setup(normalized_pairs(3, seconds=2, repeated=True))
    def score(samples, *, now):
        return {'window': {'start': samples[0].observed_at, 'end': samples[-1].observed_at,
                           'receivedAt': samples[-1].received_at, 'freshnessMs': 0.0},
                'quality': {'status': 'ok'}, 'assessment': {'status': 'watch', 'persistenceSeconds': 0}}
    scorer.assess = score
    run = service.create_run('dataset-test', 'full', 1)
    first = command(service, run, 'step')
    clock.now += timedelta(seconds=120)
    second = command(service, run, 'step')
    before = first['sensors']['s1']['assessment']['window']
    after = second['sensors']['s1']['assessment']['window']
    assert after['receivedAt'] == before['receivedAt']
    assert after['end'] == before['end']
    assert after['freshnessMs'] == 2000.0
    assert second['sensors']['s1']['latest']['receivedAt'] != after['receivedAt']


def history_rows():
    return [[''] * 9, ['', '', '', *EXPECTED], ['', '', '', *(['Double'] * 6)],
            ['2026-05-19T11:46:10.921', 'PRIVATE-PDI', 'PRIVATE-PDI', '1.2', '0.2', '30', '2.1', '0.3', '31'],
            ['2026-05-19T11:46:10.921', 'PRIVATE-PDI', 'PRIVATE-PDI', '1.2', '0.2', '30', '2.1', '0.3', '31']]


def test_import_csv_ooxml_signature_hash_idempotence_privacy(tmp_path):
    import csv
    from xml.sax.saxutils import escape
    rows = history_rows()
    csv_path = tmp_path / 'history.csv'
    with csv_path.open('w', encoding='utf-8-sig', newline='') as stream:
        csv.writer(stream, delimiter=';').writerows(rows)
    workbook = tmp_path / 'workbook-with-csv-extension.csv'
    with ZipFile(workbook, 'w') as archive:
        archive.writestr('xl/workbook.xml', '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets></workbook>')
        archive.writestr('xl/_rels/workbook.xml.rels', '<Relationships><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>')
        body = ''.join('<row>' + ''.join(f'<c r="{chr(65 + i)}{number}" t="inlineStr"><is><t>{escape(cell)}</t></is></c>' for i, cell in enumerate(row)) + '</row>' for number, row in enumerate(rows, 1))
        archive.writestr('xl/worksheets/sheet1.xml', '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>' + body + '</sheetData></worksheet>')
    csv_meta, csv_pairs = read_history(csv_path)
    xlsx_meta, xlsx_pairs = read_history(workbook)
    assert csv_pairs == xlsx_pairs
    assert csv_pairs[0]['observedAt'] == '2026-05-19T14:46:10.921000Z'
    assert xlsx_meta['sourceFormat'] == 'zip-ooxml'
    assert 'PRIVATE' not in encode(xlsx_pairs)
    assert [pair['sourceRow'] for pair in xlsx_pairs] == [1, 2]
    repository = DemoRepository('sqlite:///:memory:')
    for _ in range(2):
        import_history(workbook, repository, expected_hash=sha256(workbook.read_bytes()).hexdigest())
    assert len(repository.datasets()) == 1
    with pytest.raises(ValueError, match='hash mismatch'):
        read_history(workbook, expected_hash='f' * 64)


def test_import_rejects_nonfinite(tmp_path):
    rows = history_rows()
    rows[3][3] = 'NaN'
    path = tmp_path / 'bad.csv'
    path.write_text('\n'.join(';'.join(row) for row in rows), encoding='utf-8')
    with pytest.raises(ValueError, match='non-finite'):
        read_history(path)


def test_import_cli_sanitizes_missing_private_source_in_subprocess(tmp_path):
    import os
    import subprocess
    import sys
    root = Path(__file__).resolve().parents[4]
    sentinel = 'PRIVATE-SOURCE-PATH-SENTINEL'
    source = tmp_path / sentinel / 'absent.csv'
    environment = dict(os.environ, DEMO_DATABASE_URL='sqlite:///:memory:')
    result = subprocess.run([sys.executable, str(root / 'scripts/import_demo_history.py'), str(source),
                             '--expected-hash', 'f' * 64], capture_output=True, text=True,
                            env=environment, check=False)
    assert result.returncode == 1
    assert result.stdout == ''
    assert result.stderr.strip() == 'demo_import_failed'
    assert sentinel not in result.stdout + result.stderr
    assert 'Traceback' not in result.stderr


def test_import_cli_sanitizes_native_database_diagnostics(monkeypatch, capsys):
    import scripts.import_demo_history as command_module
    import sys
    def broken_repository(*args, **kwargs):
        raise RuntimeError('postgresql://PRIVATE-DSN-SENTINEL:secret@private-host/db')
    monkeypatch.setenv('DEMO_DATABASE_URL', 'postgresql://PRIVATE-DSN-SENTINEL:secret@private-host/db')
    monkeypatch.setattr(command_module, 'DemoRepository', broken_repository)
    monkeypatch.setattr(sys, 'argv', ['import_demo_history.py', 'unused', '--expected-hash', 'f' * 64])
    assert command_module.main() == 1
    output = capsys.readouterr()
    assert output.out == ''
    assert output.err.strip() == 'demo_import_failed'
    assert 'PRIVATE-DSN-SENTINEL' not in output.err


def test_import_cli_success_prints_only_public_metadata(tmp_path):
    import os
    import subprocess
    import sys
    root = Path(__file__).resolve().parents[4]
    source = tmp_path / 'PRIVATE-SOURCE-PATH-SENTINEL.csv'
    source.write_text('\n'.join(';'.join(row) for row in history_rows()), encoding='utf-8')
    environment = dict(os.environ, DEMO_DATABASE_URL='sqlite:///:memory:')
    result = subprocess.run([sys.executable, str(root / 'scripts/import_demo_history.py'), str(source),
                             '--expected-hash', sha256(source.read_bytes()).hexdigest(), '--initialize'],
                            capture_output=True, text=True, env=environment, check=False)
    assert result.returncode == 0
    assert result.stderr == ''
    assert json.loads(result.stdout)['pairCount'] == 2
    assert 'PRIVATE' not in result.stdout
