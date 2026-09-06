"""Bounded historical windows without replay sessions or simulated arrivals."""
from __future__ import annotations

from bisect import bisect_left, bisect_right
from datetime import datetime, timedelta, timezone
from hashlib import sha256

from twinops.demo.repository import DemoError, encode, parse, stamp, utcnow
from twinops.demo.service import ASSET_ID, SENSORS, DemoService


DATASET_FIELDS = ('datasetId', 'label', 'pairCount', 'readingCount', 'startAt', 'endAt', 'sourceFormat')
MEASUREMENTS = ('vibrationVelocityRms', 'vibrationAcceleration', 'temperature')
MEASUREMENT_FIELDS = ('value', 'unit', 'semanticConfidence', 'statistic')


class HistoryError(Exception):
    def __init__(self, status_code, detail):
        self.status_code, self.detail = status_code, detail
        super().__init__(detail)


def public_dataset(metadata):
    return {key: metadata[key] for key in DATASET_FIELDS if key in metadata}


def selection_time(value):
    if value is None:
        return None
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except (ValueError, AttributeError):
        raise HistoryError(400, 'invalid_historical_interval') from None
    if result.tzinfo is None or result.utcoffset() is None:
        raise HistoryError(400, 'historical_timezone_required')
    return result.astimezone(timezone.utc)


class HistoryService:
    def __init__(self, repository, scorer, clock=utcnow):
        self.repository, self.scorer, self.clock = repository, scorer, clock

    def datasets(self):
        return {'datasets': [public_dataset(item) for item in self.repository.datasets()]}

    def context(self, dataset_id, *, from_time=None, to_time=None, end_row=None, limit=300):
        if type(limit) is not int or not 1 <= limit <= 300:
            raise HistoryError(400, 'invalid_historical_limit')
        if end_row is not None and (type(end_row) is not int or end_row < 1):
            raise HistoryError(400, 'invalid_historical_end_row')
        start, end = selection_time(from_time), selection_time(to_time)
        if start is not None and end is not None and start > end:
            raise HistoryError(400, 'invalid_historical_interval')
        # Reuse the repository's bounded immutable dataset cache. No run, command,
        # event, cleanup, import or live telemetry operation occurs on this path.
        with self.repository.transaction() as connection:
            try:
                metadata, pairs = self.repository.dataset(connection, dataset_id)
            except DemoError as error:
                if error.detail == 'dataset_unavailable':
                    raise HistoryError(404, 'historical_dataset_not_found') from None
                raise
        times = [parse(pair['observedAt']) for pair in pairs]
        rows = [pair['sourceRow'] for pair in pairs]
        lower = bisect_left(times, start) if start is not None else 0
        upper = bisect_right(times, end) if end is not None else len(pairs)
        selected_end = min(upper, bisect_right(rows, end_row)) if end_row is not None else upper
        if selected_end <= lower:
            raise HistoryError(400, 'historical_selection_empty')
        selected_start = max(lower, selected_end - limit)
        last = pairs[selected_end - 1]
        observed = times[selected_end - 1]

        # Score once at the selected end, with the scorer's trailing horizon and
        # its predecessor. Date/display filters must not truncate ML warmup, and
        # source-row bounds exclude later samples even when timestamps are equal.
        horizon = max(
            getattr(getattr(self.scorer, 'feature_config', None), 'long_window_seconds', 60),
            getattr(getattr(getattr(self.scorer, 'baseline', None), 'config', None), 'persistence_seconds', 60),
        )
        score_start = max(0, bisect_left(times, observed - timedelta(seconds=horizon), 0, selected_end) - 1)
        history, sensors = [], {}
        for sensor_id in SENSORS:
            frames = {
                index: self._frame(metadata, pairs, times, index, sensor_id)
                for index in range(min(score_start, selected_start), selected_end)
            }
            samples = [DemoService._canonical(frames[index]) for index in range(score_start, selected_end)]
            assessment = self.scorer.assess(samples, now=observed)
            if hasattr(assessment, 'model_dump'):
                assessment = assessment.model_dump(by_alias=True, mode='json')
            if assessment is not None:
                # Preserve baseline, trainedUntil, score semantics and quality.
                # The scorer's internal virtual receipt clock is not a known
                # historical transport arrival, nor current collection freshness.
                if 'window' in assessment:
                    assessment['window'] = {**assessment['window'], 'receivedAt': None, 'freshnessMs': None}
                assessment['retrospective'] = True
            sensors[sensor_id] = {
                'latest': frames[selected_end - 1], 'assessment': assessment,
                'assessmentState': 'computed' if assessment is not None else 'unavailable',
                'newInformation': False,
            }
            history.extend(frames[index] for index in range(selected_start, selected_end))
        history.sort(key=lambda frame: (frame['sourceRow'], frame['sensorId']))
        statuses = [DemoService._status(sensor['assessment']) for sensor in sensors.values()]
        selection = {
            'from': stamp(start) if start is not None else None,
            'to': stamp(end) if end is not None else None,
            'endRow': last['sourceRow'], 'limit': limit, 'observedAt': last['observedAt'],
            'totalPairs': upper - lower, 'returnedPairs': selected_end - selected_start,
            'hasPrevious': selected_start > lower,
            'previousEndRow': pairs[selected_start - 1]['sourceRow'] if selected_start > lower else None,
            'hasNext': selected_end < upper,
            'nextEndRow': pairs[min(upper, selected_end + limit) - 1]['sourceRow'] if selected_end < upper else None,
        }
        identity = {
            'datasetId': metadata['datasetId'], 'selection': selection,
            'model': {sensor: sensors[sensor]['assessment'] for sensor in SENSORS},
        }
        return {
            'schemaVersion': 'historical-1.0', 'assetId': ASSET_ID, 'mode': 'historical',
            'revision': sha256(encode(identity).encode()).hexdigest(),
            'dataset': public_dataset(metadata), 'selection': selection,
            'sensors': sensors, 'history': history,
            'status': max(statuses, key=lambda value: {'unknown': 0, 'normal': 1, 'insufficient_data': 2, 'watch': 3, 'alert': 4}[value]),
            'generatedAt': stamp(self.clock()),
            'capabilities': {'twin3d': True, 'copilot': False, 'replayControls': False},
        }

    @staticmethod
    def _frame(metadata, pairs, times, index, sensor_id):
        pair = pairs[index]
        previous = pairs[index - 1] if index > 0 else None
        gap = previous is not None and (times[index] - times[index - 1]).total_seconds() > 15
        flags = list(pair.get('qualityFlags', []))
        if gap and 'gap_before' not in flags:
            flags.append('gap_before')
        if previous is not None and not gap and pair['sensors'][sensor_id] == previous['sensors'][sensor_id] and 'duplicate_payload' not in flags:
            flags.append('duplicate_payload')
        suffix = sha256((metadata['datasetId'] + sensor_id).encode()).hexdigest()[:12]
        return {
            'frameId': f"{pair['sourceRow']:08x}-0000-5000-8000-{suffix}",
            'sensorId': sensor_id, 'sourceRow': pair['sourceRow'], 'observedAt': pair['observedAt'],
            'receivedAt': None, 'preloaded': False,
            'measurements': {
                name: {key: value for key, value in pair['sensors'][sensor_id][name].items() if key in MEASUREMENT_FIELDS}
                for name in MEASUREMENTS
            },
            'qualityFlags': flags, 'gapBefore': gap,
        }
