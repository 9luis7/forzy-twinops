"""Transactional replay persistence and fenced, recoverable recommendation leases."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import hmac
import json
from pathlib import Path
import sqlite3
import threading


def utcnow():
    return datetime.now(timezone.utc)


def stamp(value):
    return value.astimezone(timezone.utc).isoformat(timespec='microseconds').replace('+00:00', 'Z')


def parse(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def encode(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':'))


class DemoError(Exception):
    def __init__(self, status_code, detail):
        self.status_code, self.detail = status_code, detail
        super().__init__(detail)


class DemoRepository:
    def __init__(self, database_url, *, clock=utcnow, initialize=None):
        self.clock = clock
        self.postgres = database_url.startswith(('postgresql://', 'postgres://'))
        self.database_url = database_url
        self._lock = threading.RLock()
        self._memory = None
        if not self.postgres:
            self.path = database_url.removeprefix('sqlite:///')
            if self.path == ':memory:':
                self._memory = sqlite3.connect(':memory:', check_same_thread=False)
                self._memory.row_factory = sqlite3.Row
            else:
                Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        if initialize is True or (initialize is None and not self.postgres):
            self.initialize()

    @contextmanager
    def transaction(self):
        if self.postgres:
            import psycopg
            from psycopg.rows import dict_row
            with psycopg.connect(self.database_url, row_factory=dict_row, connect_timeout=5) as connection:
                # Transaction-local settings also work through managed transaction poolers.
                connection.execute('SET LOCAL statement_timeout=10000')
                connection.execute('SET LOCAL lock_timeout=5000')
                connection.execute('SET LOCAL idle_in_transaction_session_timeout=15000')
                yield connection
        else:
            with self._lock:
                connection = self._memory or sqlite3.connect(self.path, timeout=30)
                connection.row_factory = sqlite3.Row
                try:
                    connection.execute('PRAGMA foreign_keys=ON')
                    connection.execute('BEGIN IMMEDIATE')
                    yield connection
                    connection.commit()
                except BaseException:
                    connection.rollback()
                    raise
                finally:
                    if connection is not self._memory:
                        connection.close()

    def sql(self, connection, query, params=()):
        return connection.execute(query.replace('?', '%s') if self.postgres else query, params)

    def initialize(self):
        migration = Path(__file__).parents[3] / 'migrations' / '004_demo_replay_v1.sql'
        with self.transaction() as connection:
            for statement in migration.read_text(encoding='utf-8').split(';'):
                if statement.strip():
                    self.sql(connection, statement)

    def import_dataset(self, metadata, pairs):
        with self.transaction() as connection:
            self.sql(connection, 'INSERT INTO demo_datasets(dataset_id,metadata,pairs) VALUES(?,?,?) ON CONFLICT(dataset_id) DO NOTHING',
                     (metadata['datasetId'], encode(metadata), encode(pairs)))

    def datasets(self):
        with self.transaction() as connection:
            return [json.loads(row['metadata']) for row in self.sql(connection, 'SELECT metadata FROM demo_datasets ORDER BY dataset_id').fetchall()]

    def dataset(self, connection, dataset_id):
        row = self.sql(connection, 'SELECT metadata,pairs FROM demo_datasets WHERE dataset_id=?', (dataset_id,)).fetchone()
        if not row:
            raise DemoError(503, 'dataset_unavailable')
        return json.loads(row['metadata']), json.loads(row['pairs'])

    def authorized(self, connection, run_id, token):
        suffix = ' FOR UPDATE' if self.postgres else ''
        row = self.sql(connection, 'SELECT * FROM demo_runs WHERE run_id=?' + suffix, (run_id,)).fetchone()
        if not row or not hmac.compare_digest(row['token_hash'], sha256(token.encode()).hexdigest()):
            raise DemoError(404, 'run_not_found')
        if self.clock() >= parse(row['expires_at']):
            raise DemoError(410, 'run_expired')
        return json.loads(row['state'])

    def save(self, connection, state):
        self.sql(connection, 'UPDATE demo_runs SET state=? WHERE run_id=?', (encode(state), state['public']['replay']['runId']))

    def cleanup_expired(self, limit=100):
        """Bounded cleanup of expired demo sessions only; foreign keys cascade children."""
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError('cleanup limit must be between 1 and 100')
        with self.transaction() as connection:
            suffix = ' FOR UPDATE SKIP LOCKED' if self.postgres else ''
            rows = self.sql(connection, 'SELECT run_id FROM demo_runs WHERE expires_at<=? ORDER BY expires_at LIMIT ?' + suffix,
                            (stamp(self.clock()), limit)).fetchall()
            for row in rows:
                self.sql(connection, 'DELETE FROM demo_runs WHERE run_id=?', (row['run_id'],))
            return len(rows)

    def public(self, connection, state):
        body = json.loads(encode(state['public']))
        replay = body['replay']
        body['events'] = [json.loads(row['payload']) for row in self.sql(connection,
            'SELECT payload FROM demo_events WHERE run_id=? AND generation=? ORDER BY event_id',
            (replay['runId'], replay['generation'])).fetchall()]
        body['events'].sort(key=lambda event: (event['sourceRow'], event['eventId']))
        return body

    def get_context(self, run_id, token):
        with self.transaction() as connection:
            return self.public(connection, self.authorized(connection, run_id, token))

    def trusted_context(self, run_id, token, expected_revision):
        context = self.get_context(run_id, token)
        if context['revision'] != expected_revision:
            raise DemoError(409, 'revision_conflict')
        return context

    def _event(self, connection, state, event_id):
        row = self.sql(connection, 'SELECT * FROM demo_events WHERE event_id=? AND run_id=? AND generation=?',
                       (event_id, state['public']['replay']['runId'], state['public']['replay']['generation'])).fetchone()
        if not row:
            raise DemoError(404, 'event_not_found')
        return row

    def get_event(self, run_id, token, event_id):
        with self.transaction() as connection:
            return json.loads(self._event(connection, self.authorized(connection, run_id, token), event_id)['payload'])

    def event_context(self, run_id, token, event_id):
        with self.transaction() as connection:
            return json.loads(self._event(connection, self.authorized(connection, run_id, token), event_id)['context'])

    def claim_event(self, run_id, token, event_id, *, owner, lease_seconds=60):
        with self.transaction() as connection:
            state = self.authorized(connection, run_id, token)
            row = self._event(connection, state, event_id)
            event = json.loads(row['payload'])
            if event['status'] in ('ready', 'degraded'):
                return None
            now = self.clock()
            # A restarted generation still waits for any in-flight provider call to finish/expire.
            leased = self.sql(connection, 'SELECT lease_until FROM demo_events WHERE run_id=? AND owner IS NOT NULL',
                              (run_id,)).fetchall()
            if any(item['lease_until'] and parse(item['lease_until']) > now for item in leased):
                return None
            event.update(status='processing', attempts=event['attempts'] + 1, retryable=False)
            self.sql(connection, 'UPDATE demo_events SET payload=?,owner=?,lease_until=? WHERE event_id=?',
                     (encode(event), owner, stamp(now + timedelta(seconds=lease_seconds)), event_id))
            return {'event': event, 'context': json.loads(row['context'])}

    def finish_event(self, run_id, token, event_id, *, owner, status, recommendation=None, error_code=None, retryable=False):
        if status not in ('ready', 'degraded', 'pending'):
            raise ValueError('invalid recommendation status')
        with self.transaction() as connection:
            state = self.authorized(connection, run_id, token)
            row = self._event(connection, state, event_id)
            event = json.loads(row['payload'])
            if event['status'] in ('ready', 'degraded'):
                return event
            if row['owner'] != owner or not row['lease_until'] or parse(row['lease_until']) <= self.clock():
                raise DemoError(409, 'lease_conflict')
            if retryable:
                status = 'pending'
            event.update(status=status, recommendation=recommendation, errorCode=error_code, retryable=retryable)
            self.sql(connection, 'UPDATE demo_events SET payload=?,owner=NULL,lease_until=NULL WHERE event_id=?', (encode(event), event_id))
            return event
