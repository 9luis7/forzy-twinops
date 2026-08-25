from __future__ import annotations

from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid5

from twinops.contracts.timeline_v1_models import (
    CollectionPolicyV1,
    TimelinePointV1,
    serialize_public_utc_millis_v1,
)
from twinops.storage.collection_policy_v1 import initial_collection_policy
from twinops.timeline.repository_v1 import (
    TimelineReadQueryV1,
    TimelineSliceV1,
    timeline_order_key_v1,
)


BATCH_A = "sha256:" + "a" * 64


def uuid5_text(name: str) -> str:
    return str(uuid5(NAMESPACE_URL, name))


def make_point(
    index: int,
    *,
    event_at: datetime,
    sensor_id: str = "s1",
    source_kind: str = "historical_archive",
    pair_key: str | None = None,
    cycle_id: str | None = None,
    policy_id: str | None = "forzy-live-window-v1",
    velocity: float = 1.0,
    acceleration: float = 0.0,
    temperature: float = 30.0,
) -> TimelinePointV1:
    event_text = serialize_public_utc_millis_v1(event_at)
    pair_id = uuid5_text(f"vs2a-pair|{pair_key or index}")
    point_id = uuid5_text(
        f"vs2a-point|{source_kind}|{sensor_id}|{index}|{event_text}"
    )
    payload: dict[str, object] = {
        "schemaVersion": "1.0",
        "pointId": point_id,
        "samplePairId": pair_id,
        "operatingCycleId": (
            cycle_id
            if source_kind == "historical_archive"
            else None
        ),
        "assetId": "forzy-motor-01",
        "sensorId": sensor_id,
        "eventAt": event_text,
        "sourceKind": source_kind,
        "timestampQuality": (
            "source_without_offset_assumed_timezone"
            if source_kind == "historical_archive"
            else "assumed_from_retrieval"
        ),
        "measurements": {
            "vibrationVelocityRms": {
                "value": velocity,
                "unit": "mm/s",
                "semanticConfidence": "confirmed",
            },
            "vibrationAcceleration": {
                "value": acceleration,
                "unit": "g",
                "semanticConfidence": "confirmed",
                "statistic": "unknown",
            },
            "temperature": {
                "value": temperature,
                "unit": "degC",
                "semanticConfidence": "confirmed",
            },
        },
        "qualityFlags": [],
    }
    if source_kind == "historical_archive":
        payload["operatingCycleId"] = cycle_id or uuid5_text("vs2a-cycle|0")
        payload["provenance"] = {
            "sourceSystem": "forzy-csv",
            "batchId": BATCH_A,
            "sourceFileSha256": "sha256:" + "b" * 64,
            "recordOrdinal": index + 1,
            "sourceLineNumber": index + 4,
            "rowSha256": "sha256:" + f"{index + 1:064x}"[-64:],
            "ingestedAt": "2026-08-22T12:00:00.000Z",
        }
    elif source_kind == "live_collection":
        payload["provenance"] = {
            "sourceSystem": "forzy-api",
            "readingId": uuid5_text(f"vs2a-live-reading|{index}"),
            "scheduledAt": event_text,
            "receivedAt": event_text,
            "collectionPolicyId": policy_id,
        }
    else:
        raise ValueError("unknown source kind")
    return TimelinePointV1.model_validate(payload)


def make_policy(
    effective_from: datetime = datetime(2026, 8, 1, tzinfo=timezone.utc),
) -> CollectionPolicyV1:
    return initial_collection_policy(effective_from)


class FakeTimelineRepositoryV1:
    def __init__(
        self,
        *,
        archive: tuple[TimelinePointV1, ...] = (),
        live: tuple[TimelinePointV1, ...] = (),
        policies: tuple[CollectionPolicyV1, ...] = (),
        batch_id: str | None = BATCH_A,
    ) -> None:
        self.archive = archive
        self.live = live
        self.policies = {
            policy.collection_policy_id: policy for policy in policies
        }
        self.batch_id = batch_id
        self.archive_reads: list[TimelineReadQueryV1] = []
        self.live_reads: list[TimelineReadQueryV1] = []
        self.policy_reads: list[set[str]] = []
        self.point_reads: list[tuple[str, str]] = []
        self.pair_reads: list[tuple[str, str]] = []
        self.active_batch_id_calls = 0

    def active_batch_id(self, asset_id: str) -> str | None:
        assert asset_id == "forzy-motor-01"
        self.active_batch_id_calls += 1
        return self.batch_id

    def active_batch(self, asset_id: str):
        raise AssertionError("timeline reads must not call deep active_batch")

    @staticmethod
    def _read(
        points: tuple[TimelinePointV1, ...], query: TimelineReadQueryV1
    ) -> TimelineSliceV1:
        selected = [
            point
            for point in points
            if (query.from_at is None or point.event_at >= query.from_at)
            and (query.to_at is None or point.event_at < query.to_at)
            and (query.sensor_id is None or point.sensor_id == query.sensor_id)
            and (
                query.after is None
                or timeline_order_key_v1(point) > query.after
            )
        ]
        selected = selected[: query.limit + 1]
        return TimelineSliceV1(
            points=tuple(selected),
            has_more=len(selected) > query.limit,
        )

    def read_archive_points(self, query: TimelineReadQueryV1) -> TimelineSliceV1:
        self.archive_reads.append(query)
        return self._read(self.archive, query)

    def read_live_points(self, query: TimelineReadQueryV1) -> TimelineSliceV1:
        self.live_reads.append(query)
        return self._read(self.live, query)

    def collection_policies(
        self, policy_ids: set[str]
    ) -> dict[str, CollectionPolicyV1]:
        self.policy_reads.append(set(policy_ids))
        return {
            policy_id: self.policies[policy_id]
            for policy_id in sorted(policy_ids)
            if policy_id in self.policies
        }

    def point_by_id(self, asset_id: str, point_id: str):
        self.point_reads.append((asset_id, point_id))
        return next(
            (
                point
                for point in (*self.archive, *self.live)
                if str(point.point_id) == point_id
            ),
            None,
        )

    def points_for_pair(self, asset_id: str, sample_pair_id: str):
        self.pair_reads.append((asset_id, sample_pair_id))
        return tuple(
            sorted(
                (
                    point
                    for point in (*self.archive, *self.live)
                    if str(point.sample_pair_id) == sample_pair_id
                ),
                key=timeline_order_key_v1,
            )
        )

    def stage_batch(self, *args, **kwargs):
        raise AssertionError("overview must be read-only")

    def activate_batch(self, *args, **kwargs):
        raise AssertionError("overview must be read-only")

    def store_assessments(self, *args, **kwargs):
        raise AssertionError("overview must not create assessments")
