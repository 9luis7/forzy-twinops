"""Read-only archive/live timeline repository contract."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Literal, Protocol
from uuid import UUID
from uuid import NAMESPACE_URL, uuid5

from twinops.contracts.timeline_v1_models import (
    CollectionPolicyV1,
    HistoricalAssessmentV1,
    HistoricalSensorReadingV1,
    TimelinePointV1,
    parse_public_utc_millis_v1,
    serialize_public_utc_millis_v1,
)
from twinops.contracts.v2_models import CanonicalSensorReadingV2


if TYPE_CHECKING:
    from twinops.storage.historical_repository_v1 import (
        HistoricalAssessmentRangeQueryV1,
        HistoricalAssessmentSliceV1,
        HistoricalBatchSummaryV1,
    )


TimelineSensorIdV1 = Literal["s1", "s2"]
TimelineMetricV1 = Literal[
    "vibrationVelocityRms",
    "vibrationAcceleration",
    "temperature",
]


def _require_uuid5(value: str, label: str) -> None:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a canonical UUIDv5")
    try:
        parsed = UUID(value)
    except ValueError as exc:
        raise ValueError(f"{label} must be a canonical UUIDv5") from exc
    if str(parsed) != value or parsed.version != 5:
        raise ValueError(f"{label} must be a canonical UUIDv5")


@dataclass(frozen=True, order=True)
class TimelineOrderKeyV1:
    event_at: datetime
    sample_pair_id: str
    sensor_id: TimelineSensorIdV1
    point_id: str

    def __post_init__(self) -> None:
        parse_public_utc_millis_v1(self.event_at)
        _require_uuid5(self.sample_pair_id, "sample pair ID")
        if self.sensor_id not in {"s1", "s2"}:
            raise ValueError("sensor ID must be s1 or s2")
        _require_uuid5(self.point_id, "point ID")


@dataclass(frozen=True)
class TimelineReadQueryV1:
    asset_id: str
    from_at: datetime | None
    to_at: datetime | None
    sensor_id: TimelineSensorIdV1 | None
    metric: TimelineMetricV1 | None
    after: TimelineOrderKeyV1 | None = None
    limit: int = 200

    def __post_init__(self) -> None:
        if self.asset_id != "forzy-motor-01":
            raise ValueError("unknown timeline asset")
        if self.from_at is not None:
            parse_public_utc_millis_v1(self.from_at)
        if self.to_at is not None:
            parse_public_utc_millis_v1(self.to_at)
        if (
            self.from_at is not None
            and self.to_at is not None
            and self.from_at >= self.to_at
        ):
            raise ValueError("timeline range must be non-empty and increasing")
        if self.sensor_id not in {None, "s1", "s2"}:
            raise ValueError("sensor ID must be s1 or s2")
        if self.metric not in {
            None,
            "vibrationVelocityRms",
            "vibrationAcceleration",
            "temperature",
        }:
            raise ValueError("unknown timeline metric")
        if type(self.limit) is not int or not 1 <= self.limit <= 500:
            raise ValueError("timeline limit must be between 1 and 500")


def timeline_order_key_v1(point: TimelinePointV1) -> TimelineOrderKeyV1:
    return TimelineOrderKeyV1(
        event_at=point.event_at,
        sample_pair_id=str(point.sample_pair_id),
        sensor_id=point.sensor_id,
        point_id=str(point.point_id),
    )


@dataclass(frozen=True)
class TimelineSliceV1:
    points: tuple[TimelinePointV1, ...]
    has_more: bool

    def __post_init__(self) -> None:
        keys = tuple(timeline_order_key_v1(point) for point in self.points)
        if keys != tuple(sorted(keys)) or len({point.point_id for point in self.points}) != len(
            self.points
        ):
            raise ValueError("timeline slice must be uniquely ordered")


def historical_timeline_point_v1(
    reading: HistoricalSensorReadingV1,
) -> TimelinePointV1:
    payload = reading.model_dump_public()
    payload["pointId"] = payload.pop("readingId")
    payload.pop("sourceTimestampText")
    return TimelinePointV1.model_validate(payload)


def historical_timeline_point_from_canonical_v1(
    canonical: dict[str, object],
) -> TimelinePointV1:
    if canonical.get("sourceKind") != "historical_archive":
        raise ValueError("sourceKind must be historical_archive")
    source_timestamp_text = canonical.get("sourceTimestampText")
    if type(source_timestamp_text) is not str or not source_timestamp_text:
        raise ValueError("sourceTimestampText must be non-empty text")
    payload = dict(canonical)
    payload["pointId"] = payload.pop("readingId")
    payload.pop("sourceTimestampText")
    return TimelinePointV1.model_validate(payload)


def public_live_millisecond_v1(value: str) -> tuple[datetime, str]:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("live timestamp must be persisted UTC text")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError("live timestamp is not projectable") from exc
    if parsed.utcoffset() is None:
        raise ValueError("live timestamp must be timezone-aware")
    projected = parsed.astimezone(timezone.utc).replace(
        microsecond=(parsed.microsecond // 1_000) * 1_000
    )
    return projected, serialize_public_utc_millis_v1(projected)


def live_point_id_v1(reading_id: str) -> str:
    return str(
        uuid5(
            NAMESPACE_URL,
            f"timeline-point-v1|live_collection|{reading_id}",
        )
    )


def live_sample_pair_id_v1(asset_id: str, scheduled_at: str) -> str:
    _, public_scheduled_at = public_live_millisecond_v1(scheduled_at)
    return str(
        uuid5(
            NAMESPACE_URL,
            "timeline-sample-pair-v1|live_collection|"
            f"{asset_id}|{public_scheduled_at}",
        )
    )


def live_timeline_point_v1(
    reading: CanonicalSensorReadingV2,
    *,
    collection_policy_id: str | None,
) -> TimelinePointV1:
    event_at, event_at_text = public_live_millisecond_v1(reading.received_at)
    _, scheduled_at_text = public_live_millisecond_v1(reading.scheduled_at)
    payload = {
        "schemaVersion": "1.0",
        "pointId": live_point_id_v1(reading.reading_id),
        "samplePairId": live_sample_pair_id_v1(
            reading.asset_id, reading.scheduled_at
        ),
        "operatingCycleId": None,
        "assetId": reading.asset_id,
        "sensorId": reading.sensor_id,
        "eventAt": event_at_text,
        "sourceKind": "live_collection",
        "timestampQuality": reading.timestamp_quality,
        "measurements": reading.measurements.model_dump(mode="json", by_alias=True),
        "qualityFlags": reading.quality_flags,
        "provenance": {
            "sourceSystem": "forzy-api",
            "readingId": reading.reading_id,
            "scheduledAt": scheduled_at_text,
            "receivedAt": serialize_public_utc_millis_v1(event_at),
            "collectionPolicyId": collection_policy_id,
        },
    }
    return TimelinePointV1.model_validate(payload)


class TimelineReadRepositoryV1(Protocol):
    def active_batch(
        self, asset_id: str
    ) -> HistoricalBatchSummaryV1 | None: ...

    def active_batch_summary(
        self, asset_id: str
    ) -> HistoricalBatchSummaryV1 | None: ...

    def active_batch_id(self, asset_id: str) -> str | None: ...

    def historical_assessment_for_anchor(
        self,
        batch_id: str,
        anchor_point_id: str,
    ) -> HistoricalAssessmentV1 | None: ...

    def historical_assessments(
        self,
        query: HistoricalAssessmentRangeQueryV1,
    ) -> HistoricalAssessmentSliceV1: ...

    def read_archive_points(self, query: TimelineReadQueryV1) -> TimelineSliceV1: ...

    def read_live_points(self, query: TimelineReadQueryV1) -> TimelineSliceV1: ...

    def point_by_id(self, asset_id: str, point_id: str) -> TimelinePointV1 | None: ...

    def points_for_pair(
        self, asset_id: str, sample_pair_id: str
    ) -> tuple[TimelinePointV1, ...]: ...

    def collection_policies(
        self, policy_ids: set[str]
    ) -> dict[str, CollectionPolicyV1]: ...
