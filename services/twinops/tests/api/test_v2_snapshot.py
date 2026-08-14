from datetime import datetime, timedelta, timezone
import hashlib
import uuid

import pytest

from twinops.api.v2_snapshot import build_snapshot_v2
from twinops.contracts.models import AssetConditionAssessment
from twinops.contracts.v2_models import CanonicalSensorReadingV2
from twinops.storage.v2_repository import RepositorySensorHealthV2


NOW = datetime(2026, 8, 12, 15, 0, 1, tzinfo=timezone.utc)


def _reading(
    sensor_id: str,
    *,
    seconds: float = 1,
    velocity: float = 0.04,
    quality_flags: tuple[str, ...] = (),
) -> CanonicalSensorReadingV2:
    instant = datetime(2026, 8, 12, 15, tzinfo=timezone.utc) + timedelta(
        seconds=seconds
    )
    timestamp = instant.isoformat(timespec="milliseconds").replace("+00:00", "Z")
    reading_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{sensor_id}|{seconds}|{velocity}"))
    payload_hash = hashlib.sha256(f"{sensor_id}|{velocity}".encode()).hexdigest()
    return CanonicalSensorReadingV2.model_validate(
        {
            "schemaVersion": "2.0",
            "readingId": reading_id,
            "source": "forzy-live",
            "assetId": "forzy-motor-01",
            "sensorId": sensor_id,
            "scheduledAt": "2026-08-12T15:00:00.000Z",
            "observedAt": timestamp,
            "receivedAt": timestamp,
            "timestampQuality": "assumed_from_retrieval",
            "measurements": {
                "vibrationVelocityRms": {
                    "value": velocity,
                    "unit": "mm/s",
                    "semanticConfidence": "inferred_from_datasheet",
                },
                "vibrationAcceleration": {
                    "value": 0.0,
                    "unit": "g",
                    "statistic": "unknown",
                    "semanticConfidence": "unconfirmed",
                },
                "temperature": {
                    "value": 34.0,
                    "unit": "degC",
                    "semanticConfidence": "inferred_from_datasheet",
                },
            },
            "qualityFlags": list(quality_flags),
            "payloadHash": f"sha256:{payload_hash}",
            "raw": {},
            "provenance": {
                "sourceSystem": "forzy-api",
                "ingestedAt": timestamp,
                "sourceTimestampProvided": False,
            },
        }
    )


class _Repository:
    def __init__(self, available: tuple[str, ...]):
        self.available = available
        self.queries = []

    def history(self, query):
        self.queries.append(query)
        return [_reading(query.sensor_id)] if query.sensor_id in self.available else []

    def latest(self, asset_id):
        return [_reading(sensor_id) for sensor_id in self.available]

    def health(self, sensor_id):
        return None


class _Scorer:
    def __init__(self, statuses=None):
        self.statuses = statuses or {}

    def assess(self, samples, *, now):
        sensor_id = samples[0].sensor_id
        status = self.statuses.get(sensor_id)
        if status is None:
            raise AssertionError("unexpected assessment")
        return _assessment(sensor_id, status)


class _MissingAssessmentScorer:
    def assess(self, samples, *, now):
        sensor_id = samples[0].sensor_id
        return None if sensor_id == "s2" else _assessment(sensor_id, "alert")


class _FailingScorer:
    def __init__(self, error_type):
        self.error_type = error_type

    def assess(self, samples, *, now):
        sensor_id = samples[0].sensor_id
        if sensor_id == "s2":
            raise self.error_type("secret scorer internals")
        return _assessment(sensor_id, "alert")


class _FatalScorer:
    class FatalScorerError(BaseException):
        pass

    def assess(self, samples, *, now):
        raise self.FatalScorerError("fatal scorer signal")


class _CountingScorer(_Scorer):
    def __init__(self):
        super().__init__({"s1": "normal", "s2": "normal"})
        self.sample_counts = []

    def assess(self, samples, *, now):
        self.sample_counts.append(len(samples))
        return super().assess(samples, now=now)


class _LimitRepository(_Repository):
    def history(self, query):
        self.queries.append(query)
        return [_reading(query.sensor_id)] * query.limit


class _HealthRepository(_Repository):
    def health(self, sensor_id):
        if sensor_id == "s2":
            return None
        return RepositorySensorHealthV2(
            sensor_id="s1",
            last_attempt_at=NOW,
            last_success_at=NOW,
            latency_ms=125,
            error_code="upstream_unavailable",
            sample_count=7,
        )


class _MultiSampleRepository(_Repository):
    def __init__(self):
        super().__init__(("s1", "s2"))

    def latest(self, asset_id):
        return [
            _reading(
                "s1", seconds=4, velocity=0.08, quality_flags=("latest-s1",)
            ),
            _reading(
                "s2", seconds=5, velocity=0.05, quality_flags=("latest-s2",)
            ),
        ]

    def history(self, query):
        self.queries.append(query)
        if query.sensor_id == "s1":
            return [
                _reading("s1", seconds=2, velocity=0.08),
                _reading("s1", seconds=1, velocity=0.04),
            ]
        return [
            _reading("s2", seconds=3, velocity=0.05),
            _reading("s2", seconds=1.5, velocity=0.03),
        ]


class _RecordingScorer(_Scorer):
    def __init__(self):
        super().__init__({"s1": "normal", "s2": "normal"})
        self.now_values = []

    def assess(self, samples, *, now):
        self.now_values.append(now)
        return super().assess(samples, now=now)


def _assessment(sensor_id: str, status: str) -> AssetConditionAssessment:
    return AssetConditionAssessment.model_validate(
        {
            "schemaVersion": "1.0",
            "assessmentId": f"00000000-0000-4000-8000-00000000001{1 if sensor_id == 's1' else 2}",
            "assetTag": "forzy-motor-01",
            "sensorId": sensor_id,
            "window": {
                "start": "2026-08-12T15:00:00.000Z",
                "end": "2026-08-12T15:00:01.000Z",
                "receivedAt": "2026-08-12T15:00:01.000Z",
                "freshnessMs": 0.0,
            },
            "quality": {"status": "ok", "flags": []},
            "operatingContext": {"state": "steady", "estimated": True},
            "assessment": {
                "status": status,
                "anomalyScore": 0.5,
                "deteriorationScore": 0.25,
                "scoreSemantics": "relative_to_historical_baseline_not_failure_probability",
                "episodeId": None,
                "persistenceSeconds": 0.0,
            },
            "componentTag": None,
            "recommendation": None,
            "humanValidationRequired": True,
            "evidence": [],
            "model": {
                "name": "robust-baseline",
                "version": "1.0.1",
                "configHash": f"sha256:{'0' * 64}",
                "trainedUntil": "2026-08-12T14:59:00.000Z",
            },
            "limitations": [],
        }
    )


def test_partial_channels_never_report_normal():
    snapshot = build_snapshot_v2(
        repository=_Repository(("s2",)),
        scorer=_Scorer(),
        now=NOW,
        operational_state="received_now",
        freshness_basis="retrieval_time",
        twin3d_enabled=True,
    )

    assert snapshot.status == "insufficient_data"
    assert snapshot.channels[0].sensor_id == "s1"
    assert "unavailable" in snapshot.channels[0].quality_flags


def test_total_absence_returns_two_unavailable_channels_and_no_assessment():
    snapshot = build_snapshot_v2(
        repository=_Repository(()),
        scorer=_Scorer(),
        now=NOW,
        operational_state="unavailable",
        freshness_basis="none",
        twin3d_enabled=False,
    )

    assert snapshot.status == "insufficient_data"
    assert [channel.sensor_id for channel in snapshot.channels] == ["s1", "s2"]
    assert all(channel.timestamp_quality == "unavailable" for channel in snapshot.channels)
    assert snapshot.assessment is None
    assert snapshot.capabilities.twin_3d is False


def test_assessment_semantics_remain_relative():
    snapshot = build_snapshot_v2(
        repository=_Repository(("s1", "s2")),
        scorer=_Scorer({"s1": "normal", "s2": "watch"}),
        now=NOW,
        operational_state="received_now",
        freshness_basis="retrieval_time",
        twin3d_enabled=True,
    )

    assert snapshot.status == "watch"
    assert snapshot.assessment is not None
    assert (
        snapshot.assessment.assessment.score_semantics
        == "relative_to_historical_baseline_not_failure_probability"
    )


def test_missing_sensor_assessment_dominates_an_alert():
    snapshot = build_snapshot_v2(
        repository=_Repository(("s1", "s2")),
        scorer=_MissingAssessmentScorer(),
        now=NOW,
        operational_state="received_now",
        freshness_basis="retrieval_time",
        twin3d_enabled=True,
    )

    assert snapshot.status == "insufficient_data"
    assert snapshot.assessment is None


@pytest.mark.parametrize("error_type", [ValueError, RuntimeError, KeyError])
def test_ordinary_scorer_failure_is_an_absent_assessment(error_type, caplog):
    caplog.set_level("WARNING", logger="twinops.api")
    snapshot = build_snapshot_v2(
        repository=_HealthRepository(("s1", "s2")),
        scorer=_FailingScorer(error_type),
        now=NOW,
        operational_state="received_now",
        freshness_basis="retrieval_time",
        twin3d_enabled=True,
    )

    assert snapshot.status == "insufficient_data"
    assert snapshot.assessment is None
    assert [channel.sensor_id for channel in snapshot.channels] == ["s1", "s2"]
    assert snapshot.integration.sensors.s1.sample_count == 7
    assert "secret scorer internals" not in snapshot.model_dump_json()
    assert f"error_type={error_type.__name__} sensor=s2" in caplog.text
    assert "secret scorer internals" not in caplog.text


def test_scorer_base_exception_is_not_normalized():
    scorer = _FatalScorer()

    with pytest.raises(_FatalScorer.FatalScorerError):
        build_snapshot_v2(
            repository=_Repository(("s1", "s2")),
            scorer=scorer,
            now=NOW,
            operational_state="received_now",
            freshness_basis="retrieval_time",
            twin3d_enabled=True,
        )


def test_repository_exception_is_not_normalized_as_a_scorer_failure():
    repository = _Repository(("s1", "s2"))

    def fail_history(query):
        raise RuntimeError("repository unavailable")

    repository.history = fail_history
    with pytest.raises(RuntimeError, match="repository unavailable"):
        build_snapshot_v2(
            repository=repository,
            scorer=_Scorer({"s1": "normal", "s2": "normal"}),
            now=NOW,
            operational_state="last_known",
            freshness_basis="last_received",
            twin3d_enabled=True,
        )


def test_worst_real_severity_is_published():
    snapshot = build_snapshot_v2(
        repository=_Repository(("s1", "s2")),
        scorer=_Scorer({"s1": "alert", "s2": "watch"}),
        now=NOW,
        operational_state="received_now",
        freshness_basis="retrieval_time",
        twin3d_enabled=True,
    )

    assert snapshot.status == "alert"
    assert snapshot.assessment is not None
    assert snapshot.assessment.sensor_id == "s1"


def test_alert_dominates_scorer_insufficient_data_when_both_exist():
    snapshot = build_snapshot_v2(
        repository=_Repository(("s1", "s2")),
        scorer=_Scorer({"s1": "alert", "s2": "insufficient_data"}),
        now=NOW,
        operational_state="received_now",
        freshness_basis="retrieval_time",
        twin3d_enabled=True,
    )

    assert snapshot.status == "alert"
    assert snapshot.assessment is not None
    assert snapshot.assessment.sensor_id == "s1"


def test_both_scorers_insufficient_data_remain_insufficient():
    snapshot = build_snapshot_v2(
        repository=_Repository(("s1", "s2")),
        scorer=_Scorer({"s1": "insufficient_data", "s2": "insufficient_data"}),
        now=NOW,
        operational_state="received_now",
        freshness_basis="retrieval_time",
        twin3d_enabled=True,
    )

    assert snapshot.status == "insufficient_data"
    assert snapshot.assessment is not None


def test_history_and_scoring_are_bounded_to_1000_points_per_sensor():
    repository = _LimitRepository(("s1", "s2"))
    scorer = _CountingScorer()

    build_snapshot_v2(
        repository=repository,
        scorer=scorer,
        now=NOW,
        operational_state="received_now",
        freshness_basis="retrieval_time",
        twin3d_enabled=True,
    )

    assert [(query.sensor_id, query.limit) for query in repository.queries] == [
        ("s1", 1000),
        ("s2", 1000),
    ]
    assert scorer.sample_counts == [1000, 1000]


def test_latest_channels_are_separate_from_ordered_distinct_trend_history():
    snapshot = build_snapshot_v2(
        repository=_MultiSampleRepository(),
        scorer=_Scorer({"s1": "normal", "s2": "normal"}),
        now=NOW + timedelta(seconds=10),
        operational_state="received_now",
        freshness_basis="retrieval_time",
        twin3d_enabled=True,
    )

    assert [channel.received_at for channel in snapshot.channels] == [
        "2026-08-12T15:00:04.000Z",
        "2026-08-12T15:00:05.000Z",
    ]
    assert [channel.quality_flags for channel in snapshot.channels] == [
        ["latest-s1"],
        ["latest-s2"],
    ]
    assert [item.received_at for item in snapshot.history] == [
        "2026-08-12T15:00:03.000Z",
        "2026-08-12T15:00:02.000Z",
        "2026-08-12T15:00:01.500Z",
        "2026-08-12T15:00:01.000Z",
    ]
    assert all(item.observed_at == item.received_at for item in snapshot.history)
    assert all(
        item.timestamp_quality == "assumed_from_retrieval"
        for item in snapshot.channels + snapshot.history
    )


def test_generated_and_scoring_time_are_clamped_to_latest_received_at():
    repository = _MultiSampleRepository()
    scorer = _RecordingScorer()

    snapshot = build_snapshot_v2(
        repository=repository,
        scorer=scorer,
        now=datetime(2026, 8, 12, 15, 0, 3, tzinfo=timezone.utc),
        operational_state="received_now",
        freshness_basis="retrieval_time",
        twin3d_enabled=True,
    )

    expected = datetime(2026, 8, 12, 15, 0, 5, tzinfo=timezone.utc)
    assert snapshot.generated_at == "2026-08-12T15:00:05.000Z"
    assert scorer.now_values == [expected, expected]


def test_integration_health_comes_from_repository_with_honest_empty_default():
    snapshot = build_snapshot_v2(
        repository=_HealthRepository(()),
        scorer=_Scorer(),
        now=NOW,
        operational_state="unavailable",
        freshness_basis="none",
        twin3d_enabled=True,
    )

    assert snapshot.integration.sensors.s1.sample_count == 7
    assert snapshot.integration.sensors.s1.latency_ms == 125
    assert snapshot.integration.sensors.s1.error == "upstream_unavailable"
    assert snapshot.integration.sensors.s1.last_attempt_at == "2026-08-12T15:00:01.000Z"
    assert snapshot.integration.sensors.s2.sample_count == 0
    assert snapshot.integration.sensors.s2.last_attempt_at is None
