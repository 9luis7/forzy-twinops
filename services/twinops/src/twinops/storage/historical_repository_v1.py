"""Frozen persistence boundary for immutable historical archive batches."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

from twinops.contracts.timeline_v1_models import (
    CollectionPolicyV1,
    HistoricalAssessmentV1,
    Sha256V1,
)
from twinops.ingestion.history_profiles_v1 import PreparedHistoricalBatchV1
from twinops.storage.schema_migrations import (
    DeploymentIdentityV1,
    SchemaVerification,
)
from twinops.timeline.repository_v1 import TimelineReadRepositoryV1


BatchStatusV1 = Literal["staged", "active", "superseded"]


class HistoricalBatchConflict(RuntimeError):
    """Raised when persisted historical evidence diverges from its identity."""


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

    def activate_batch(
        self,
        *,
        asset_id: str,
        batch_id: str,
        expected_active_batch_id: str | None,
    ) -> ActivateHistoryResultV1: ...

    def active_batch(self, asset_id: str) -> HistoricalBatchSummaryV1 | None: ...

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
