"""Dataset transfer bounds and isolation; entirely offline SQLite/local doubles."""
from concurrent.futures import ThreadPoolExecutor
import json
import threading

import pytest

from twinops.demo.repository import DemoError, DemoRepository, encode
from twinops.demo.service import DemoService
from services.twinops.tests.demo.test_demo_replay import Clock, Scorer, command, normalized_pairs


def dataset(dataset_id='a'):
    return {'datasetId': dataset_id, 'label': 'Histórico', 'sourceHash': 'sha256:' + 'a' * 64}, [
        {'sourceRow': 1, 'sensors': {'s1': {'value': 1.0}}, 'qualityFlags': []}]


def counted_repository(**kwargs):
    repository = DemoRepository('sqlite:///:memory:', **kwargs)
    actual_sql = repository.sql
    repository.payload_reads = 0
    def sql(connection, query, params=()):
        if query.startswith('SELECT metadata,pairs'):
            repository.payload_reads += 1
        return actual_sql(connection, query, params)
    repository.sql = sql
    return repository


def read(repository, dataset_id='a'):
    with repository.transaction() as connection:
        return repository.dataset(connection, dataset_id)


def test_repeated_reads_transfer_once_and_return_isolated_nested_copies():
    repository = counted_repository()
    original = dataset()
    repository.import_dataset(*original)
    first = read(repository)
    first[0]['label'] = 'consumer changed metadata'
    first[1][0]['sensors']['s1']['value'] = 999.0
    first[1][0]['qualityFlags'].append('consumer change')
    second = read(repository)
    assert second == original
    second[1].clear()
    assert read(repository) == original
    assert repository.payload_reads == 1


def test_entry_limit_uses_lru_and_instances_do_not_share_cache():
    repository = counted_repository(dataset_cache_max_entries=2)
    for name in ('a', 'b', 'c'):
        repository.import_dataset(*dataset(name))
    for name in ('a', 'b', 'a', 'c', 'a'):
        read(repository, name)
    assert repository.payload_reads == 3
    read(repository, 'b')  # b was least recently used when c arrived
    assert repository.payload_reads == 4
    assert len(repository._dataset_cache) == 2
    other = counted_repository()
    different = dataset('a')
    different[0]['label'] = 'another database instance'
    other.import_dataset(*different)
    assert read(other) == different
    assert other.payload_reads == 1


def test_utf8_byte_limit_evicts_even_when_entry_limit_allows_more():
    meta, pairs = dataset()
    size = len(encode(meta).encode('utf-8')) + len(encode(pairs).encode('utf-8'))
    repository = counted_repository(dataset_cache_max_entries=10, dataset_cache_max_bytes=size)
    repository.import_dataset(meta, pairs)
    repository.import_dataset(*dataset('b'))
    read(repository, 'a')
    read(repository, 'b')
    read(repository, 'a')
    assert repository.payload_reads == 3
    assert len(repository._dataset_cache) == 1
    assert repository._dataset_cache_bytes == size


@pytest.mark.parametrize('options', [
    {'dataset_cache_max_entries': 0}, {'dataset_cache_max_bytes': 0}, {'dataset_cache_max_bytes': 1},
])
def test_disabled_or_oversized_payload_is_returned_without_caching(options):
    repository = counted_repository(**options)
    repository.import_dataset(*dataset())
    assert read(repository) == dataset()
    assert read(repository) == dataset()
    assert repository.payload_reads == 2
    assert repository._dataset_cache_bytes == 0
    assert not repository._dataset_cache


def test_missing_dataset_and_decode_errors_are_not_cached():
    repository = counted_repository()
    for _ in range(2):
        with pytest.raises(DemoError) as missing:
            read(repository)
        assert missing.value.detail == 'dataset_unavailable'
    assert repository.payload_reads == 2
    with repository.transaction() as connection:
        repository.sql(connection, 'INSERT INTO demo_datasets(dataset_id,metadata,pairs) VALUES(?,?,?)',
                       ('a', encode(dataset()[0]), 'invalid JSON'))
    for _ in range(2):
        with pytest.raises(json.JSONDecodeError):
            read(repository)
    assert repository.payload_reads == 4
    assert not repository._dataset_cache
    with repository.transaction() as connection:
        repository.sql(connection, 'UPDATE demo_datasets SET pairs=? WHERE dataset_id=?', (encode(dataset()[1]), 'a'))
    assert read(repository) == dataset()
    assert read(repository) == dataset()
    assert repository.payload_reads == 5


def test_transient_query_failure_does_not_poison_cache():
    repository = counted_repository()
    repository.import_dataset(*dataset())
    actual_sql = repository.sql
    failed = False
    def flaky(connection, query, params=()):
        nonlocal failed
        if query.startswith('SELECT metadata,pairs') and not failed:
            failed = True
            raise RuntimeError('simulated transport failure')
        return actual_sql(connection, query, params)
    repository.sql = flaky
    with pytest.raises(RuntimeError):
        read(repository)
    assert not repository._dataset_cache
    assert read(repository) == dataset()
    assert read(repository) == dataset()
    assert repository.payload_reads == 1


def test_concurrent_cold_calls_perform_one_payload_query():
    repository = counted_repository()
    barrier = threading.Barrier(8)
    metadata, pairs = dataset()
    reads = []
    class Cursor:
        def fetchone(self):
            return {'metadata': encode(metadata), 'pairs': encode(pairs)}
    def query(connection, sql, params):
        reads.append(1)
        return Cursor()
    repository.sql = query
    def load(_):
        barrier.wait(timeout=5)
        return repository.dataset(object(), 'a')
    with ThreadPoolExecutor(max_workers=8) as workers:
        results = list(workers.map(load, range(8)))
    assert len(reads) == 1
    assert all(result == (metadata, pairs) for result in results)
    assert len({id(result[0]) for result in results}) == 8
    assert len({id(result[1]) for result in results}) == 8


def test_replay_uses_cache_but_session_authority_and_isolation_stay_in_database():
    clock = Clock()
    repository = counted_repository(clock=clock)
    pairs = normalized_pairs(10)
    metadata = {'datasetId': 'a', 'label': 'Offline', 'pairCount': len(pairs), 'readingCount': len(pairs) * 2,
                'sourceHash': 'sha256:' + 'a' * 64, 'sourceFormat': 'csv',
                'startAt': pairs[0]['observedAt'], 'endAt': pairs[-1]['observedAt']}
    repository.import_dataset(metadata, pairs)
    service = DemoService(repository, Scorer(), clock)
    first = service.create_run('a', 'full', 1)
    second = service.create_run('a', 'full', 1)
    for _ in range(3):
        command(service, first, 'step')
    assert repository.payload_reads == 1
    assert service.context(second['runId'], second['token'])['replay']['cursor'] == 0
    with pytest.raises(DemoError) as denied:
        service.context(first['runId'], second['token'])
    assert denied.value.status_code == 404
    with repository.transaction() as connection:
        state = repository.authorized(connection, first['runId'], first['token'])
        state['public']['revision'] += 10
        repository.save(connection, state)
    with pytest.raises(DemoError) as conflict:
        service.control(first['runId'], first['token'], {'commandId': 'stale', 'expectedRevision': 3, 'action': 'step'})
    assert conflict.value.detail == 'revision_conflict'


@pytest.mark.parametrize('options', [
    {'dataset_cache_max_entries': -1}, {'dataset_cache_max_entries': True},
    {'dataset_cache_max_bytes': -1}, {'dataset_cache_max_bytes': 1.5},
])
def test_invalid_cache_limits_fail_explicitly(options):
    with pytest.raises(ValueError, match='dataset cache limits'):
        DemoRepository('sqlite:///:memory:', **options)
