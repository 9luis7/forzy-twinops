"""Frozen persistence boundary for immutable historical archive batches."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
import re
from types import MappingProxyType
from typing import Literal, Protocol
from uuid import NAMESPACE_URL, uuid5

from twinops.contracts.timeline_v1_models import (
    CollectionPolicyV1,
    HistoricalAssessmentV1,
    Sha256V1,
    TimelinePointV1,
    parse_public_utc_millis_v1,
)
from twinops.ingestion.history_profiles_v1 import PreparedHistoricalBatchV1
from twinops.storage.schema_migrations import (
    DeploymentIdentityV1,
    SchemaVerification,
)
from twinops.timeline.repository_v1 import TimelineReadRepositoryV1


BatchStatusV1 = Literal["staged", "active", "superseded"]
_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


class HistoricalBatchConflict(RuntimeError):
    """Raised when persisted historical evidence diverges from its identity."""


def historical_assessment_id_v1(
    batch_id: str,
    fold_id: str,
    anchor_point_id: str,
) -> str:
    """Return the frozen Task-1 identity for one persisted assessment."""

    return str(
        uuid5(
            NAMESPACE_URL,
            "|".join(
                (
                    "historical-assessment-v1",
                    batch_id,
                    fold_id,
                    anchor_point_id,
                )
            ),
        )
    )


@dataclass(frozen=True)
class StoredHistoricalAssessmentV1:
    batch_id: Sha256V1
    assessment: HistoricalAssessmentV1


@dataclass(frozen=True)
class HistoricalBatchSummaryV1:
    batch_id: Sha256V1
    asset_id: Literal["forzy-motor-01"]
    status: BatchStatusV1
    source_sha256: Sha256V1
    manifest_sha256: Sha256V1
    raw_row_count: int
    sample_count: int
    operating_cycle_count: int
    assessment_count: int
    assessment_manifest_sha256: Sha256V1 | None
    staged_at: datetime
    activated_at: datetime | None

    def __post_init__(self) -> None:
        for label, value in (
            ("batch ID", self.batch_id),
            ("source hash", self.source_sha256),
            ("manifest hash", self.manifest_sha256),
        ):
            if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
                raise ValueError(f"historical batch {label} is not canonical sha256")
        if self.asset_id != "forzy-motor-01":
            raise ValueError("historical batch summary has an unknown asset")
        if self.status not in {"staged", "active", "superseded"}:
            raise ValueError("historical batch summary has an invalid status")
        for label, value in (
            ("raw row count", self.raw_row_count),
            ("sample count", self.sample_count),
            ("operating cycle count", self.operating_cycle_count),
            ("assessment count", self.assessment_count),
        ):
            if type(value) is not int or value < 0:
                raise ValueError(f"historical batch {label} is invalid")
        if (self.assessment_count == 0) != (
            self.assessment_manifest_sha256 is None
        ):
            raise ValueError(
                "historical batch assessment materialization metadata is inconsistent"
            )
        if self.assessment_manifest_sha256 is not None and not _SHA256_RE.fullmatch(
            self.assessment_manifest_sha256
        ):
            raise ValueError(
                "historical batch assessment manifest is not canonical sha256"
            )
        parse_public_utc_millis_v1(self.staged_at)
        if self.activated_at is not None:
            parse_public_utc_millis_v1(self.activated_at)
        if (self.status == "staged") != (self.activated_at is None):
            raise ValueError(
                "historical batch summary status and activation time disagree"
            )
        if (
            self.activated_at is not None
            and self.activated_at < self.staged_at
        ):
            raise ValueError("historical batch activation precedes staging")


@dataclass(frozen=True)
class StageHistoryResultV1:
    batch: HistoricalBatchSummaryV1
    inserted: bool
    writes_performed: int


@dataclass(frozen=True)
class AssessmentStoreResultV1:
    batch_id: Sha256V1
    inserted_count: int
    existing_count: int
    total_count: int
    assessment_manifest_sha256: Sha256V1
    writes_performed: int


@dataclass(frozen=True)
class HistoricalAssessmentRangeQueryV1:
    asset_id: str
    batch_id: str
    from_at: datetime
    to_at: datetime
    sensor_id: Literal["s1", "s2"] | None = None

    def __post_init__(self) -> None:
        if self.asset_id != "forzy-motor-01":
            raise ValueError("unknown timeline asset")
        if not isinstance(self.batch_id, str) or not _SHA256_RE.fullmatch(
            self.batch_id
        ):
            raise ValueError("batch ID must be canonical sha256")
        if type(self.from_at) is not datetime or type(self.to_at) is not datetime:
            raise ValueError("assessment range requires canonical UTC milliseconds")
        parse_public_utc_millis_v1(self.from_at)
        parse_public_utc_millis_v1(self.to_at)
        if self.from_at >= self.to_at:
            raise ValueError("assessment range must be non-empty and increasing")
        if self.sensor_id not in {None, "s1", "s2"}:
            raise ValueError("sensor ID must be s1 or s2")


@dataclass(frozen=True)
class HistoricalAssessmentSliceV1:
    assessments: tuple[HistoricalAssessmentV1, ...]
    anchors_by_id: Mapping[str, TimelinePointV1]

    def __post_init__(self) -> None:
        if type(self.assessments) is not tuple or any(
            not isinstance(item, HistoricalAssessmentV1)
            for item in self.assessments
        ):
            raise ValueError("historical assessment slice requires typed assessments")
        keys = tuple(
            (
                item.assessment_at,
                str(item.anchor_point_id),
                item.sensor_id,
                str(item.assessment_id),
            )
            for item in self.assessments
        )
        if (
            keys != tuple(sorted(keys))
            or len({str(item.assessment_id) for item in self.assessments})
            != len(self.assessments)
            or len({str(item.anchor_point_id) for item in self.assessments})
            != len(self.assessments)
        ):
            raise ValueError("historical assessments must be uniquely ordered")
        if not isinstance(self.anchors_by_id, Mapping):
            raise ValueError("historical assessment anchors must be a mapping")
        anchors = dict(self.anchors_by_id)
        required = {str(item.anchor_point_id) for item in self.assessments}
        if set(anchors) != required or any(
            type(anchor_id) is not str
            or not isinstance(anchor, TimelinePointV1)
            or str(anchor.point_id) != anchor_id
            or anchor.source_kind != "historical_archive"
            for anchor_id, anchor in anchors.items()
        ):
            raise ValueError("historical assessment anchors are not exact originals")
        for assessment in self.assessments:
            anchor = anchors[str(assessment.anchor_point_id)]
            if not (
                anchor.sensor_id == assessment.sensor_id
                and anchor.operating_cycle_id == assessment.operating_cycle_id
                and anchor.event_at == assessment.assessment_at
            ):
                raise ValueError("historical assessment anchor facts are crossed")
        object.__setattr__(
            self,
            "anchors_by_id",
            MappingProxyType(dict(sorted(anchors.items()))),
        )


@dataclass(frozen=True)
class ActivateHistoryResultV1:
    asset_id: Literal["forzy-motor-01"]
    batch_id: Sha256V1
    previous_active_batch_id: Sha256V1 | None
    active_batch_id: Sha256V1
    activated: bool
    assessment_count: int
    assessment_manifest_sha256: Sha256V1 | None
    writes_performed: int


class HistoricalRepositoryV1(TimelineReadRepositoryV1, Protocol):
    def verify_schema(self, expected_version: str) -> SchemaVerification: ...

    def target_identity(self) -> DeploymentIdentityV1 | None: ...

    def stage_batch(self, batch: PreparedHistoricalBatchV1) -> StageHistoryResultV1: ...

    def store_assessments(
        self,
        batch_id: str,
        assessments: Sequence[StoredHistoricalAssessmentV1],
    ) -> AssessmentStoreResultV1: ...

    def historical_assessment_for_anchor(
        self,
        batch_id: str,
        anchor_point_id: str,
    ) -> HistoricalAssessmentV1 | None: ...

    def historical_assessments(
        self,
        query: HistoricalAssessmentRangeQueryV1,
    ) -> HistoricalAssessmentSliceV1: ...

    def activate_batch(
        self,
        *,
        asset_id: str,
        batch_id: str,
        expected_active_batch_id: str | None,
    ) -> ActivateHistoryResultV1: ...

    def active_batch(self, asset_id: str) -> HistoricalBatchSummaryV1 | None: ...

    def active_batch_summary(
        self, asset_id: str
    ) -> HistoricalBatchSummaryV1 | None: ...

    def reconstruct_source(self, batch_id: str) -> bytes: ...

    def collection_policy(self, policy_id: str) -> CollectionPolicyV1 | None: ...

    def collection_policies(
        self,
        policy_ids: set[str],
    ) -> dict[str, CollectionPolicyV1]: ...

    def effective_collection_policy(
        self,
        asset_id: str,
        at: datetime,
    ) -> CollectionPolicyV1 | None: ...
