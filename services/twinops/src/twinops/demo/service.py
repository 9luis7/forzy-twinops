"""Causal replay with atomic commands, raw cadence, and source-clock episodes."""
from __future__ import annotations

from datetime import timedelta
from hashlib import sha256
import json
import secrets
import time
import uuid

from twinops.contracts.models import CanonicalSensorReading
from .repository import DemoError, encode, parse, stamp, utcnow

ASSET_ID = 'forzy-motor-01'
SENSORS = ('s1', 's2')


class DemoService:
    def __init__(self, repository, scorer, clock=utcnow):
        self.repository, self.scorer, self.clock = repository, scorer, clock

    def datasets(self):
        return {'datasets': self.repository.datasets()}

    def create_run(self, dataset_id, scenario, speed):
        self._validate(scenario, speed)
        repository = self.repository
        repository.cleanup_expired()
        with repository.transaction() as connection:
            metadata, pairs = repository.dataset(connection, dataset_id)
            if scenario == 'guided' and len(pairs) < 440:
                raise DemoError(503, 'guided_dataset_unavailable')
            run_id, token = str(uuid.uuid4()), secrets.token_urlsafe(32)
            now = self.clock()
            state = self._initial(metadata, pairs, run_id, scenario, speed, 0, stamp(now + timedelta(hours=24)))
            repository.sql(connection, 'INSERT INTO demo_runs(run_id,token_hash,expires_at,state) VALUES(?,?,?,?)',
                (run_id, sha256(token.encode()).hexdigest(), state['public']['replay']['expiresAt'], encode(state)))
            return {'runId': run_id, 'token': token, 'context': repository.public(connection, state)}

    def context(self, run_id, token):
        return self.repository.get_context(run_id, token)

    def control(self, run_id, token, body):
        return self._command(run_id, token, body, advance=False)

    def advance(self, run_id, token, body):
        return self._command(run_id, token, body, advance=True)

    @staticmethod
    def _validate(scenario, speed):
        if scenario not in ('guided', 'full') or type(speed) is not int or speed not in (1, 2, 5):
            raise DemoError(422, 'invalid_replay_options')

    def _initial(self, metadata, pairs, run_id, scenario, speed, generation, expires):
        start, end = (141, 440) if scenario == 'guided' else (1, len(pairs))
        state = {'public': {
            'schemaVersion': 'demo-1.0', 'assetId': ASSET_ID, 'mode': 'replay', 'revision': 0,
            'generatedAt': stamp(self.clock()), 'status': 'insufficient_data',
            'replay': {'runId': run_id, 'generation': generation, 'state': 'paused', 'scenario': scenario,
                       'speed': speed, 'cursor': 0, 'totalPairs': end - start + 1, 'startRow': start,
                       'endRow': end, 'sourceRow': None, 'sourceTime': None, 'arrivalTime': None,
                       'expiresAt': expires, 'warmupPairs': 0},
            'dataset': {key: value for key, value in metadata.items() if key != 'guided'},
            'sensors': {sensor: {'latest': None, 'assessment': None, 'assessmentState': 'unavailable',
                                 'newInformation': False} for sensor in SENSORS},
            'history': [], 'events': [],
            'pipeline': {'receivedPairs': 0, 'receivedReadings': 0, 'newInformationReadings': 0,
                         'repeatedReadings': 0, 'gapCount': 0, 'assessmentsComputed': 0,
                         'eventsCreated': 0, 'lastAdvanceMs': None},
            'capabilities': {'copilot': True, 'twin3d': True, 'replayControls': True}},
            'prefix': {sensor: [] for sensor in SENSORS}, 'computedAt': {}, 'episodes': {}}
        if scenario == 'guided':
            lower = parse(pairs[start - 1]['observedAt']) - timedelta(seconds=60)
            first = start - 1
            while first > 0 and parse(pairs[first - 1]['observedAt']) >= lower:
                first -= 1
            if first > 0:
                first -= 1  # predecessor preserves the first cadence/gap
            warmup = pairs[first:start - 1]
            for pair in warmup:
                self._pair(state, pair, preloaded=True)
            state['public']['replay']['warmupPairs'] = len(warmup)
        state['episodes'] = {}
        return state

    def _command(self, run_id, token, body, *, advance):
        if hasattr(body, 'model_dump'):
            body = body.model_dump(by_alias=True, exclude_none=True)
        command_id = body.get('commandId')
        if not isinstance(command_id, str) or not 1 <= len(command_id) <= 128 or type(body.get('expectedRevision')) is not int:
            raise DemoError(422, 'invalid_command')
        repository = self.repository
        fingerprint = sha256(encode({'advance': advance, 'body': body}).encode()).hexdigest()
        with repository.transaction() as connection:
            state = repository.authorized(connection, run_id, token)
            cached = repository.sql(connection, 'SELECT * FROM demo_commands WHERE run_id=? AND command_id=?', (run_id, command_id)).fetchone()
            if cached:
                if cached['fingerprint'] != fingerprint:
                    raise DemoError(409, 'command_id_conflict')
                if not cached['response']:
                    raise DemoError(409, 'command_response_expired')
                return json.loads(cached['response'])
            public = state['public']
            if public['revision'] != body['expectedRevision']:
                raise DemoError(409, 'revision_conflict')
            metadata, pairs = repository.dataset(connection, public['dataset']['datasetId'])
            replay = public['replay']
            action = 'advance' if advance else body.get('action')
            steps = 0
            if action == 'advance':
                if replay['state'] == 'running':
                    steps = replay['speed']
            elif action == 'step':
                if replay['state'] != 'paused':
                    raise DemoError(409, 'run_not_paused')
                steps = 1
            elif action in ('play', 'resume'):
                if replay['state'] != 'completed':
                    replay['state'] = 'running'
            elif action == 'pause':
                if replay['state'] != 'completed':
                    replay['state'] = 'paused'
            elif action == 'speed':
                self._validate(replay['scenario'], body.get('speed'))
                replay['speed'] = body['speed']
            elif action == 'restart':
                revision = public['revision']
                state = self._initial(metadata, pairs, run_id, replay['scenario'], replay['speed'], replay['generation'] + 1, replay['expiresAt'])
                public = state['public']
                public['revision'] = revision
                replay = public['replay']
            else:
                raise DemoError(422, 'invalid_action')
            public['revision'] += 1
            started = time.perf_counter()
            for _ in range(min(steps, replay['totalPairs'] - replay['cursor'])):
                pair = pairs[replay['startRow'] - 1 + replay['cursor']]
                candidates = self._pair(state, pair)
                replay['cursor'] += 1
                replay.update(sourceRow=pair['sourceRow'], sourceTime=pair['observedAt'], arrivalTime=public['generatedAt'])
                if replay['cursor'] >= replay['totalPairs']:
                    replay['state'] = 'completed'
                for kind, sensor_ids in candidates.items():
                    event = {'eventId': str(uuid.uuid4()), 'generation': replay['generation'], 'kind': kind,
                             'sourceRow': pair['sourceRow'], 'observedAt': pair['observedAt'], 'receivedAt': public['generatedAt'],
                             'contextRevision': public['revision'], 'sensorIds': sensor_ids, 'status': 'pending',
                             'attempts': 0, 'retryable': False, 'recommendation': None, 'errorCode': None}
                    public['pipeline']['eventsCreated'] += 1
                    frozen = repository.public(connection, state)
                    frozen['events'].append(event)
                    repository.sql(connection, 'INSERT INTO demo_events(event_id,run_id,generation,payload,context) VALUES(?,?,?,?,?)',
                                   (event['eventId'], run_id, replay['generation'], encode(event), encode(frozen)))
            if steps:
                public['pipeline']['lastAdvanceMs'] = round((time.perf_counter() - started) * 1000, 3)
            public['generatedAt'] = stamp(self.clock())
            repository.save(connection, state)
            response = repository.public(connection, state)
            repository.sql(connection, 'INSERT INTO demo_commands(run_id,command_id,fingerprint,revision,response) VALUES(?,?,?,?,?)',
                           (run_id, command_id, fingerprint, public['revision'], encode(response)))
            # Keep identities until session expiry, and only eight large exact responses.
            repository.sql(connection, 'UPDATE demo_commands SET response=NULL WHERE run_id=? AND revision<?', (run_id, public['revision'] - 7))
            return response

    def _pair(self, state, pair, *, preloaded=False):
        public = state['public']
        received = stamp(self.clock())
        public['generatedAt'] = received
        source_time = parse(pair['observedAt'])
        candidates = {}
        pair_gap = False
        for sensor_id in SENSORS:
            sensor = public['sensors'][sensor_id]
            previous = sensor['latest']
            gap = previous is not None and (source_time - parse(previous['observedAt'])).total_seconds() > 15
            pair_gap |= gap
            new = previous is None or gap or pair['sensors'][sensor_id] != previous['measurements']
            # UUID canonical shape plus source-order-leading integer: curation sorts timestamp ties by ID.
            suffix = sha256((public['dataset']['datasetId'] + sensor_id).encode()).hexdigest()[:12]
            reading_id = f"{pair['sourceRow']:08x}-0000-5000-8000-{suffix}"
            flags = list(pair.get('qualityFlags', []))
            if gap:
                flags.append('gap_before')
            if not new:
                flags.append('duplicate_payload')
            latest = {'frameId': reading_id, 'sensorId': sensor_id, 'sourceRow': pair['sourceRow'],
                      'observedAt': pair['observedAt'], 'receivedAt': received,
                      'measurements': pair['sensors'][sensor_id], 'qualityFlags': flags,
                      'gapBefore': gap, 'preloaded': preloaded}
            prefix = state['prefix'][sensor_id]
            prefix.append(latest)
            # Causal trailing 60 seconds plus predecessor; do not remove duplicate rows.
            threshold = source_time - timedelta(seconds=60)
            first = 0
            while first < len(prefix) - 1 and parse(prefix[first]['observedAt']) < threshold:
                first += 1
            state['prefix'][sensor_id] = prefix = prefix[max(0, first - 1):]
            computed_at = state['computedAt'].get(sensor_id)
            reusable = not new and not gap and computed_at is not None and (source_time - parse(computed_at)).total_seconds() <= 30
            if reusable:
                assessment_state = 'reused'
                if sensor['assessment'] and 'window' in sensor['assessment']:
                    sensor['assessment']['window']['freshnessMs'] = max(0.0, (source_time - parse(computed_at)).total_seconds() * 1000)
            else:
                samples = [self._canonical(frame) for frame in prefix]
                assessment = self.scorer.assess(samples, now=source_time)
                sensor['assessment'] = assessment.model_dump(by_alias=True, mode='json') if hasattr(assessment, 'model_dump') else assessment
                if sensor['assessment'] and 'window' in sensor['assessment']:
                    # Project the real transport arrival after scoring on its virtual clock.
                    sensor['assessment']['window']['receivedAt'] = received
                state['computedAt'][sensor_id] = pair['observedAt']
                assessment_state = 'computed'
                if not preloaded:
                    public['pipeline']['assessmentsComputed'] += 1
            sensor.update(latest=latest, assessmentState=assessment_state, newInformation=new)
            public['history'].append(latest)
            if not preloaded:
                public['pipeline']['newInformationReadings' if new else 'repeatedReadings'] += 1
                kind = self._episode(state, sensor_id, source_time, new, gap)
                if kind:
                    candidates.setdefault(kind, []).append(sensor_id)
        public['history'] = public['history'][-600:]
        statuses = [self._status(public['sensors'][sensor]['assessment']) for sensor in SENSORS]
        public['status'] = max(statuses, key=lambda value: {'unknown': 0, 'normal': 1, 'insufficient_data': 2, 'watch': 3, 'alert': 4}[value])
        if not preloaded:
            public['pipeline']['receivedPairs'] += 1
            public['pipeline']['receivedReadings'] += 2
            public['pipeline']['gapCount'] += int(pair_gap)
        return candidates

    @staticmethod
    def _canonical(frame):
        # ML evaluates freshness on original time; public transport arrival remains current.
        return CanonicalSensorReading.model_validate({
            'schemaVersion': '1.0', 'readingId': frame['frameId'], 'source': 'forzy-csv',
            'assetTag': ASSET_ID, 'sensorId': frame['sensorId'], 'scheduledAt': None,
            'observedAt': frame['observedAt'], 'receivedAt': frame['observedAt'],
            'measurements': frame['measurements'], 'qualityFlags': frame['qualityFlags'],
            'payloadHash': 'sha256:' + sha256(encode(frame['measurements']).encode()).hexdigest(),
            'raw': {}, 'provenance': {'sourceSystem': 'forzy-history-export', 'ingestedAt': frame['observedAt']}})

    @staticmethod
    def _status(assessment):
        if not assessment:
            return 'unknown'
        if assessment.get('quality', {}).get('status') == 'insufficient_data':
            return 'insufficient_data'
        status = assessment.get('assessment', {}).get('status', 'unknown')
        return status if status in ('normal', 'watch', 'alert', 'insufficient_data') else 'unknown'

    def _episode(self, state, sensor_id, now, new, gap):
        episode = state['episodes'].setdefault(sensor_id, {'active': False, 'alerted': False, 'streak': None, 'since': None, 'count': 0})
        assessment = state['public']['sensors'][sensor_id]['assessment']
        status = self._status(assessment)
        if gap or status in ('unknown', 'insufficient_data'):
            episode.update(streak=None, since=None, count=0)
            return None
        streak = 'watch' if status in ('watch', 'alert') else 'normal'
        if episode['streak'] != streak:
            episode.update(streak=streak, since=stamp(now), count=0)
        if new:
            episode['count'] += 1
        elapsed = (now - parse(episode['since'])).total_seconds()
        if streak == 'watch' and not episode['active'] and elapsed >= 5 and episode['count'] >= 3:
            episode['active'] = True
            return 'sustained_watch'
        if status == 'alert' and episode['active'] and not episode['alerted'] and assessment['assessment'].get('persistenceSeconds', 0) >= 30:
            episode['alerted'] = True
            return 'escalation'
        if streak == 'normal' and episode['active'] and elapsed >= 10 and episode['count'] >= 3:
            episode.update(active=False, alerted=False)
            return 'recovery'
        return None
