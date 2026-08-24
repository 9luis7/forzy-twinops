"""Backend-neutral contract for immutable historical repositories."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, fields, replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from inspect import Parameter, signature
import json
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Protocol
from uuid import NAMESPACE_URL, uuid5

import pytest

from twinops.contracts.timeline_v1_models import (
    CollectionPolicyV1,
    HistoricalAssessmentV1,
)
from twinops.ingestion.historical_import_v1 import (
    _prepare_historical_batch_for_profile,
)
from twinops.ingestion.history_profiles_v1 import (
    HistoryProfileV1,
    PreparedHistoricalBatchV1,
    registered_profile,
)
from twinops.storage.historical_repository_v1 import (
    ActivateHistoryResultV1,
    AssessmentStoreResultV1,
    HistoricalBatchConflict,
    HistoricalBatchSummaryV1,
    HistoricalRepositoryV1,
    StageHistoryResultV1,
    StoredHistoricalAssessmentV1,
)
from twinops.storage.schema_migrations import SchemaVerification


_HEADER_RECORDS = registered_profile(
    "forzy-history-2026-05-19-v1"
).header_records
_ROWS_BY_VARIANT = {
    0: (
        "2026-05-19T11:46:10.921;AQID;BAUG;0.04;0;27;0.05;0.01;34",
        "2026-05-19T11:46:20.921;CQoL;DA0O;0.06;0.02;28;0.07;0.03;35",
    ),
    1: (
        "2026-05-19T11:46:10.921;AQID;BAUG;0.14;0;27;0.05;0.01;34",
        "2026-05-19T11:46:20.921;CQoL;DA0O;0.16;0.02;28;0.07;0.03;35",
    ),
}
_INGESTED_AT = datetime(2026, 8, 22, 12, tzinfo=timezone.utc)
_POLICY_FROM = datetime(2026, 8, 22, 12, tzinfo=timezone.utc)
_INITIAL_POLICY_ID = "forzy-live-window-v1"


class RepositoryContractControl(Protocol):
    """Test-only storage controls supplied by each backend adapter."""

    def historical_counts(self) -> dict[str, int]: ...

    def live_counts(self) -> dict[str, int]: ...

    def snapshot(self) -> object: ...

    def statuses(self, asset_id: str) -> dict[str, str]: ...

    def tamper_batch_manifest(self, batch_id: str) -> None: ...

    def tamper_batch_count(self, batch_id: str) -> None: ...

    def tamper_raw_hash(self, batch_id: str) -> None: ...

    def tamper_raw_offset(self, batch_id: str) -> None: ...

    def tamper_sample_payload(self, batch_id: str) -> None: ...

    def delete_policy(self, policy_id: str) -> None: ...

    def insert_policy(self, policy: CollectionPolicyV1) -> None: ...

    def tamper_policy_hash(self, policy_id: str) -> None: ...

    def tamper_policy_field(self, policy_id: str) -> None: ...

    def interrupting_repository(
        self,
        operation: str,
        exception_type: type[BaseException],
    ) -> HistoricalRepositoryV1: ...


PreparedBatchFactory = Callable[[int], PreparedHistoricalBatchV1]


def run_activation_race(
    repository: HistoricalRepositoryV1,
    candidates: tuple[PreparedHistoricalBatchV1, PreparedHistoricalBatchV1],
) -> tuple[ActivateHistoryResultV1 | None, ActivateHistoryResultV1 | None]:
    """Race two CAS activations without treating a stale expectation as success."""

    def activate(candidate: PreparedHistoricalBatchV1) -> ActivateHistoryResultV1 | None:
        try:
            return repository.activate_batch(
                asset_id=candidate.asset_id,
                batch_id=candidate.batch_id,
                expected_active_batch_id=None,
            )
        except HistoricalBatchConflict:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        return tuple(pool.map(activate, candidates))


def synthetic_prepared_batch(variant: int = 0) -> PreparedHistoricalBatchV1:
    """Prepare a compact archive only through Task 3's private test seam."""

    rows = _ROWS_BY_VARIANT[variant]
    source_bytes = b"".join(_HEADER_RECORDS) + b"".join(
        row.encode("utf-8") + b"\r\n" for row in rows
    )
    profile = HistoryProfileV1(
        profile_id=f"synthetic-task-a4-v{variant}",
        source_size_bytes=len(source_bytes),
        source_sha256="sha256:" + sha256(source_bytes).hexdigest(),
        header_records=_HEADER_RECORDS,
        encoding="utf-8",
        delimiter=";",
        newline="CRLF",
        final_crlf_required=True,
        data_record_count=len(rows),
        sample_count=2 * len(rows),
        operating_cycle_count=1,
        timezone_name="America/Sao_Paulo",
        parser_version="forzy-history-parser-v1",
        contract_version="1.0",
        gap_seconds=15.0,
    )
    return _prepare_historical_batch_for_profile(
        source_bytes,
        profile=profile,
        asset_id="forzy-motor-01",
        ingested_at=_INGESTED_AT,
    )


def _expected_batch_id(batch: PreparedHistoricalBatchV1, asset_id: str) -> str:
    manifest = json.loads(batch.manifest_json)
    identity = json.dumps(
        {
            "assetId": asset_id,
            "contractVersion": manifest["contractVersion"],
            "parserVersion": manifest["parserVersion"],
            "sourceSha256": batch.source_sha256,
            "timezone": manifest["timezone"],
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return "sha256:" + sha256(identity).hexdigest()


def _policy(
    policy_id: str,
    *,
    effective_from: datetime,
    effective_to: datetime | None,
) -> CollectionPolicyV1:
    selected = {
        "schemaVersion": "1.0",
        "collectionPolicyId": policy_id,
        "assetId": "forzy-motor-01",
        "timezone": "America/Sao_Paulo",
        "activeWeekdays": ["monday", "tuesday", "wednesday"],
        "windowStartLocal": "12:00:00",
        "windowEndLocal": "14:00:00",
        "pollIntervalSeconds": 5,
        "gapThresholdSeconds": 15,
    }
    digest = "sha256:" + sha256(
        json.dumps(
            selected,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return CollectionPolicyV1.model_validate(
        {
            **selected,
            "effectiveFrom": effective_from,
            "effectiveTo": effective_to,
            "configurationHash": digest,
        }
    )


def _assessment(
    batch: PreparedHistoricalBatchV1,
    *,
    model_version: str = "1.0",
) -> StoredHistoricalAssessmentV1:
    anchor = next(
        sample.reading for sample in batch.samples if sample.reading.sensor_id == "s1"
    )
    event_at = anchor.event_at
    assessment_id = uuid5(
        NAMESPACE_URL,
        f"forzy://twinops/task-a4-assessment/{batch.batch_id}/s1",
    )
    assessment = HistoricalAssessmentV1.model_validate(
        {
            "schemaVersion": "1.0",
            "assessmentId": str(assessment_id),
            "foldId": "synthetic-fold-1",
            "sensorId": "s1",
            "operatingCycleId": str(anchor.operating_cycle_id),
            "trainingWindow": {
                "start": event_at - timedelta(hours=3),
                "end": event_at - timedelta(hours=2),
            },
            "assessmentWindow": {
                "start": event_at - timedelta(hours=2) + timedelta(milliseconds=1),
                "end": event_at - timedelta(minutes=1),
            },
            "assessmentAt": event_at,
            "anchorPointId": str(anchor.reading_id),
            "status": "normal",
            "anomalyScore": 0.1,
            "deteriorationScore": 0.2,
            "scoreSemantics": (
                "relative_to_walk_forward_historical_baseline_not_failure_probability"
            ),
            "persistence": {
                "episodeId": None,
                "episodeStartedAt": None,
                "persistenceSeconds": 0,
                "persistenceCount": 0,
            },
            "quality": {"status": "ok", "flags": []},
            "evidence": [],
            "modelFamily": "robust-baseline",
            "modelVersion": model_version,
            "modelHash": "sha256:" + "d" * 64,
            "foldHash": "sha256:" + "e" * 64,
            "reportHash": "sha256:" + "f" * 64,
            "componentTag": None,
            "humanValidationRequired": True,
            "limitations": [],
        }
    )
    return StoredHistoricalAssessmentV1(
        batch_id=batch.batch_id,
        assessment=assessment,
    )


class HistoricalRepositoryContract:
    """Tests inherited by every historical repository backend."""

    def test_schema_identity_and_result_types_are_frozen(
        self,
        historical_repository: HistoricalRepositoryV1,
        prepared_batch_factory: PreparedBatchFactory,
    ) -> None:
        expected_result_fields = {
            HistoricalBatchSummaryV1: (
                "batch_id",
                "asset_id",
                "status",
                "source_sha256",
                "manifest_sha256",
                "raw_row_count",
                "sample_count",
                "operating_cycle_count",
                "assessment_count",
                "assessment_manifest_sha256",
                "staged_at",
                "activated_at",
            ),
            StageHistoryResultV1: (
                "batch",
                "inserted",
                "writes_performed",
            ),
            AssessmentStoreResultV1: (
                "batch_id",
                "inserted_count",
                "existing_count",
                "total_count",
                "assessment_manifest_sha256",
                "writes_performed",
            ),
            ActivateHistoryResultV1: (
                "asset_id",
                "batch_id",
                "previous_active_batch_id",
                "active_batch_id",
                "activated",
                "assessment_count",
                "assessment_manifest_sha256",
                "writes_performed",
            ),
        }
        for result_type, expected_fields in expected_result_fields.items():
            assert result_type.__dataclass_params__.frozen is True
            assert tuple(field.name for field in fields(result_type)) == expected_fields

        positional = Parameter.POSITIONAL_OR_KEYWORD
        keyword_only = Parameter.KEYWORD_ONLY
        expected_protocol_parameters = {
            "verify_schema": (("self", positional), ("expected_version", positional)),
            "target_identity": (("self", positional),),
            "stage_batch": (("self", positional), ("batch", positional)),
            "store_assessments": (
                ("self", positional),
                ("batch_id", positional),
                ("assessments", positional),
            ),
            "activate_batch": (
                ("self", positional),
                ("asset_id", keyword_only),
                ("batch_id", keyword_only),
                ("expected_active_batch_id", keyword_only),
            ),
            "active_batch": (("self", positional), ("asset_id", positional)),
            "reconstruct_source": (("self", positional), ("batch_id", positional)),
            "collection_policy": (("self", positional), ("policy_id", positional)),
            "collection_policies": (("self", positional), ("policy_ids", positional)),
            "effective_collection_policy": (
                ("self", positional),
                ("asset_id", positional),
                ("at", positional),
            ),
        }
        protocol_methods = tuple(
            name
            for name, member in HistoricalRepositoryV1.__dict__.items()
            if callable(member) and not name.startswith("_")
        )
        assert protocol_methods == tuple(expected_protocol_parameters)
        for method_name, expected_parameters in expected_protocol_parameters.items():
            parameters = tuple(
                signature(getattr(HistoricalRepositoryV1, method_name)).parameters.values()
            )
            assert tuple((parameter.name, parameter.kind) for parameter in parameters) == (
                expected_parameters
            )
            assert all(parameter.default is Parameter.empty for parameter in parameters)

        verification = historical_repository.verify_schema("003")

        assert isinstance(verification, SchemaVerification)
        assert verification.expected_version == "003"
        assert verification.current_version == "003"
        assert verification.is_current is True
        assert historical_repository.target_identity() is None

        result = historical_repository.stage_batch(prepared_batch_factory(0))

        assert isinstance(result, StageHistoryResultV1)
        assert not isinstance(result, dict)
        assert isinstance(result.batch, HistoricalBatchSummaryV1)
        with pytest.raises(FrozenInstanceError):
            result.inserted = False  # type: ignore[misc]

    def test_stage_is_atomic_typed_and_preserves_live_tables(
        self,
        historical_repository: HistoricalRepositoryV1,
        prepared_batch_factory: PreparedBatchFactory,
        repository_control: RepositoryContractControl,
    ) -> None:
        batch = prepared_batch_factory(0)
        live_before = repository_control.live_counts()

        result = historical_repository.stage_batch(batch)

        assert isinstance(result, StageHistoryResultV1)
        assert result.inserted is True
        assert result.writes_performed == 1 + len(batch.raw_rows) + len(batch.samples)
        assert result.batch == HistoricalBatchSummaryV1(
            batch_id=batch.batch_id,
            asset_id=batch.asset_id,
            status="staged",
            source_sha256=batch.source_sha256,
            manifest_sha256=batch.manifest_sha256,
            raw_row_count=len(batch.raw_rows),
            sample_count=len(batch.samples),
            operating_cycle_count=len(
                {sample.reading.operating_cycle_id for sample in batch.samples}
            ),
            assessment_count=0,
            assessment_manifest_sha256=None,
            staged_at=result.batch.staged_at,
            activated_at=None,
        )
        assert result.batch.staged_at.tzinfo is not None
        assert result.batch.staged_at.utcoffset() == timedelta(0)
        assert result.batch.staged_at.microsecond % 1_000 == 0
        assert repository_control.historical_counts() == {
            "historical_import_batches_v1": 1,
            "historical_raw_rows_v1": len(batch.raw_rows),
            "historical_samples_v1": len(batch.samples),
            "historical_assessments_v1": 0,
        }
        assert historical_repository.reconstruct_source(batch.batch_id) == batch.source_bytes
        assert repository_control.live_counts() == live_before

    def test_exact_existing_batch_is_a_zero_write_fully_revalidated_noop(
        self,
        historical_repository: HistoricalRepositoryV1,
        prepared_batch_factory: PreparedBatchFactory,
        repository_control: RepositoryContractControl,
    ) -> None:
        batch = prepared_batch_factory(0)
        first = historical_repository.stage_batch(batch)
        before = repository_control.snapshot()

        second = historical_repository.stage_batch(batch)

        assert second == StageHistoryResultV1(
            batch=first.batch,
            inserted=False,
            writes_performed=0,
        )
        assert repository_control.snapshot() == before

    def test_same_source_and_batch_id_cannot_be_reused_for_another_asset(
        self,
        historical_repository: HistoricalRepositoryV1,
        prepared_batch_factory: PreparedBatchFactory,
        repository_control: RepositoryContractControl,
    ) -> None:
        batch = prepared_batch_factory(0)
        other_asset_id = "forzy-motor-02"

        assert _expected_batch_id(batch, other_asset_id) != batch.batch_id
        crossed = replace(batch, asset_id=other_asset_id)

        with pytest.raises(HistoricalBatchConflict):
            historical_repository.stage_batch(crossed)
        assert repository_control.historical_counts() == {
            "historical_import_batches_v1": 0,
            "historical_raw_rows_v1": 0,
            "historical_samples_v1": 0,
            "historical_assessments_v1": 0,
        }

    @pytest.mark.parametrize(
        "tamper_method",
        [
            "tamper_batch_manifest",
            "tamper_batch_count",
            "tamper_raw_hash",
            "tamper_raw_offset",
            "tamper_sample_payload",
        ],
    )
    def test_divergent_existing_batch_fails_closed_without_repair(
        self,
        tamper_method: str,
        historical_repository: HistoricalRepositoryV1,
        prepared_batch_factory: PreparedBatchFactory,
        repository_control: RepositoryContractControl,
    ) -> None:
        batch = prepared_batch_factory(0)
        historical_repository.stage_batch(batch)
        getattr(repository_control, tamper_method)(batch.batch_id)
        corrupted = repository_control.snapshot()

        with pytest.raises(HistoricalBatchConflict):
            historical_repository.stage_batch(batch)

        assert repository_control.snapshot() == corrupted

    def test_reconstruction_rereads_exact_row_hashes_and_offsets(
        self,
        historical_repository: HistoricalRepositoryV1,
        prepared_batch_factory: PreparedBatchFactory,
        repository_control: RepositoryContractControl,
    ) -> None:
        first = prepared_batch_factory(0)
        historical_repository.stage_batch(first)
        assert historical_repository.reconstruct_source(first.batch_id) == first.source_bytes

        repository_control.tamper_raw_offset(first.batch_id)
        with pytest.raises(HistoricalBatchConflict):
            historical_repository.reconstruct_source(first.batch_id)

    @pytest.mark.parametrize(
        "exception_type",
        [Exception, KeyboardInterrupt, SystemExit],
        ids=["exception", "keyboard-interrupt", "system-exit"],
    )
    def test_stage_rolls_back_all_rows_for_every_base_exception(
        self,
        exception_type: type[BaseException],
        prepared_batch_factory: PreparedBatchFactory,
        repository_control: RepositoryContractControl,
    ) -> None:
        batch = prepared_batch_factory(0)
        interrupted = repository_control.interrupting_repository(
            "stage",
            exception_type,
        )

        with pytest.raises(exception_type):
            interrupted.stage_batch(batch)

        assert repository_control.historical_counts() == {
            "historical_import_batches_v1": 0,
            "historical_raw_rows_v1": 0,
            "historical_samples_v1": 0,
            "historical_assessments_v1": 0,
        }

    def test_activation_obeys_compare_and_swap_and_leaves_one_active_batch(
        self,
        historical_repository: HistoricalRepositoryV1,
        prepared_batch_factory: PreparedBatchFactory,
        repository_control: RepositoryContractControl,
    ) -> None:
        first = prepared_batch_factory(0)
        second = prepared_batch_factory(1)
        historical_repository.stage_batch(first)
        historical_repository.stage_batch(second)

        activated_first = historical_repository.activate_batch(
            asset_id=first.asset_id,
            batch_id=first.batch_id,
            expected_active_batch_id=None,
        )

        assert isinstance(activated_first, ActivateHistoryResultV1)
        assert not isinstance(activated_first, dict)
        assert activated_first == ActivateHistoryResultV1(
            asset_id=first.asset_id,
            batch_id=first.batch_id,
            previous_active_batch_id=None,
            active_batch_id=first.batch_id,
            activated=True,
            assessment_count=0,
            assessment_manifest_sha256=None,
            writes_performed=1,
        )
        assert repository_control.statuses(first.asset_id) == {
            first.batch_id: "active",
            second.batch_id: "staged",
        }

        before_mismatch = repository_control.snapshot()
        with pytest.raises(HistoricalBatchConflict):
            historical_repository.activate_batch(
                asset_id=second.asset_id,
                batch_id=second.batch_id,
                expected_active_batch_id=None,
            )
        assert repository_control.snapshot() == before_mismatch

        activated_second = historical_repository.activate_batch(
            asset_id=second.asset_id,
            batch_id=second.batch_id,
            expected_active_batch_id=first.batch_id,
        )

        assert activated_second == ActivateHistoryResultV1(
            asset_id=second.asset_id,
            batch_id=second.batch_id,
            previous_active_batch_id=first.batch_id,
            active_batch_id=second.batch_id,
            activated=True,
            assessment_count=0,
            assessment_manifest_sha256=None,
            writes_performed=2,
        )
        assert repository_control.statuses(first.asset_id) == {
            first.batch_id: "superseded",
            second.batch_id: "active",
        }
        assert historical_repository.active_batch(first.asset_id).batch_id == second.batch_id

        noop = historical_repository.activate_batch(
            asset_id=second.asset_id,
            batch_id=second.batch_id,
            expected_active_batch_id=second.batch_id,
        )
        assert noop.activated is False
        assert noop.writes_performed == 0
        assert repository_control.statuses(first.asset_id) == {
            first.batch_id: "superseded",
            second.batch_id: "active",
        }

        with pytest.raises(HistoricalBatchConflict):
            historical_repository.activate_batch(
                asset_id=first.asset_id,
                batch_id=first.batch_id,
                expected_active_batch_id=second.batch_id,
            )

    def test_assessment_storage_is_typed_idempotent_and_bound_to_activation(
        self,
        historical_repository: HistoricalRepositoryV1,
        prepared_batch_factory: PreparedBatchFactory,
        repository_control: RepositoryContractControl,
    ) -> None:
        batch = prepared_batch_factory(0)
        historical_repository.stage_batch(batch)
        assessment = _assessment(batch)

        inserted = historical_repository.store_assessments(
            batch.batch_id,
            [assessment],
        )

        assert isinstance(inserted, AssessmentStoreResultV1)
        assert not isinstance(inserted, dict)
        assert inserted.batch_id == batch.batch_id
        assert inserted.inserted_count == 1
        assert inserted.existing_count == 0
        assert inserted.total_count == 1
        assert inserted.writes_performed == 2
        assert inserted.assessment_manifest_sha256.startswith("sha256:")
        assert repository_control.historical_counts()[
            "historical_assessments_v1"
        ] == 1

        before_noop = repository_control.snapshot()
        replay = historical_repository.store_assessments(
            batch.batch_id,
            [assessment],
        )
        assert replay == AssessmentStoreResultV1(
            batch_id=batch.batch_id,
            inserted_count=0,
            existing_count=1,
            total_count=1,
            assessment_manifest_sha256=inserted.assessment_manifest_sha256,
            writes_performed=0,
        )
        assert repository_control.snapshot() == before_noop

        divergent = _assessment(batch, model_version="1.1")
        before_conflict = repository_control.snapshot()
        with pytest.raises(HistoricalBatchConflict):
            historical_repository.store_assessments(
                batch.batch_id,
                [divergent],
            )
        assert repository_control.snapshot() == before_conflict

        activated = historical_repository.activate_batch(
            asset_id=batch.asset_id,
            batch_id=batch.batch_id,
            expected_active_batch_id=None,
        )
        assert activated.assessment_count == 1
        assert (
            activated.assessment_manifest_sha256
            == inserted.assessment_manifest_sha256
        )

    def test_assessment_identity_is_globally_bound_to_its_original_batch(
        self,
        historical_repository: HistoricalRepositoryV1,
        prepared_batch_factory: PreparedBatchFactory,
        repository_control: RepositoryContractControl,
    ) -> None:
        first = prepared_batch_factory(0)
        second = prepared_batch_factory(1)
        historical_repository.stage_batch(first)
        historical_repository.stage_batch(second)
        first_assessment = _assessment(first)
        second_assessment = _assessment(second)
        historical_repository.store_assessments(
            first.batch_id,
            [first_assessment],
        )
        historical_repository.store_assessments(
            second.batch_id,
            [second_assessment],
        )
        crossed = replace(first_assessment, batch_id=second.batch_id)
        assert crossed.assessment is first_assessment.assessment
        before = repository_control.snapshot()

        with pytest.raises(HistoricalBatchConflict):
            historical_repository.store_assessments(
                second.batch_id,
                [crossed],
            )

        assert repository_control.snapshot() == before

    @pytest.mark.parametrize(
        "exception_type",
        [Exception, KeyboardInterrupt, SystemExit],
        ids=["exception", "keyboard-interrupt", "system-exit"],
    )
    def test_assessment_storage_rolls_back_for_every_base_exception(
        self,
        exception_type: type[BaseException],
        historical_repository: HistoricalRepositoryV1,
        prepared_batch_factory: PreparedBatchFactory,
        repository_control: RepositoryContractControl,
    ) -> None:
        batch = prepared_batch_factory(0)
        historical_repository.stage_batch(batch)
        assessment = _assessment(batch)
        before = repository_control.snapshot()
        interrupted = repository_control.interrupting_repository(
            "assessment",
            exception_type,
        )

        with pytest.raises(exception_type):
            interrupted.store_assessments(
                batch.batch_id,
                [assessment],
            )

        assert repository_control.snapshot() == before

    def test_activation_validates_target_before_superseding_current_batch(
        self,
        historical_repository: HistoricalRepositoryV1,
        prepared_batch_factory: PreparedBatchFactory,
        repository_control: RepositoryContractControl,
    ) -> None:
        first = prepared_batch_factory(0)
        second = prepared_batch_factory(1)
        historical_repository.stage_batch(first)
        historical_repository.stage_batch(second)
        historical_repository.activate_batch(
            asset_id=first.asset_id,
            batch_id=first.batch_id,
            expected_active_batch_id=None,
        )
        repository_control.tamper_sample_payload(second.batch_id)
        before = repository_control.snapshot()

        with pytest.raises(HistoricalBatchConflict):
            historical_repository.activate_batch(
                asset_id=second.asset_id,
                batch_id=second.batch_id,
                expected_active_batch_id=first.batch_id,
            )

        assert repository_control.snapshot() == before
        assert repository_control.statuses(first.asset_id)[first.batch_id] == "active"

    @pytest.mark.parametrize(
        "exception_type",
        [Exception, KeyboardInterrupt, SystemExit],
        ids=["exception", "keyboard-interrupt", "system-exit"],
    )
    def test_activation_rolls_back_supersede_for_every_base_exception(
        self,
        exception_type: type[BaseException],
        historical_repository: HistoricalRepositoryV1,
        prepared_batch_factory: PreparedBatchFactory,
        repository_control: RepositoryContractControl,
    ) -> None:
        first = prepared_batch_factory(0)
        second = prepared_batch_factory(1)
        historical_repository.stage_batch(first)
        historical_repository.stage_batch(second)
        historical_repository.activate_batch(
            asset_id=first.asset_id,
            batch_id=first.batch_id,
            expected_active_batch_id=None,
        )
        interrupted = repository_control.interrupting_repository(
            "activation",
            exception_type,
        )

        with pytest.raises(exception_type):
            interrupted.activate_batch(
                asset_id=second.asset_id,
                batch_id=second.batch_id,
                expected_active_batch_id=first.batch_id,
            )

        assert repository_control.statuses(first.asset_id) == {
            first.batch_id: "active",
            second.batch_id: "staged",
        }

    def test_policy_reads_are_typed_requested_only_and_side_effect_free(
        self,
        historical_repository: HistoricalRepositoryV1,
        repository_control: RepositoryContractControl,
    ) -> None:
        hidden = _policy(
            "hidden-invalid-policy",
            effective_from=_POLICY_FROM + timedelta(days=1),
            effective_to=None,
        )
        repository_control.insert_policy(hidden)
        repository_control.tamper_policy_hash(hidden.collection_policy_id)
        before = repository_control.snapshot()

        initial = historical_repository.collection_policy(_INITIAL_POLICY_ID)
        selected = historical_repository.collection_policies(
            {_INITIAL_POLICY_ID, "missing-policy"}
        )
        empty = historical_repository.collection_policies(set())

        assert isinstance(initial, CollectionPolicyV1)
        assert selected == {_INITIAL_POLICY_ID: initial}
        assert empty == {}
        assert historical_repository.collection_policy("missing-policy") is None
        assert repository_control.snapshot() == before

        with pytest.raises(ValueError):
            historical_repository.collection_policy(hidden.collection_policy_id)
        with pytest.raises(ValueError):
            historical_repository.collection_policies(
                {_INITIAL_POLICY_ID, hidden.collection_policy_id}
            )

    @pytest.mark.parametrize(
        "tamper_method",
        ["tamper_policy_hash", "tamper_policy_field"],
    )
    def test_policy_reads_run_full_pydantic_and_hash_validation(
        self,
        tamper_method: str,
        historical_repository: HistoricalRepositoryV1,
        repository_control: RepositoryContractControl,
    ) -> None:
        getattr(repository_control, tamper_method)(_INITIAL_POLICY_ID)

        with pytest.raises(ValueError):
            historical_repository.collection_policy(_INITIAL_POLICY_ID)
        with pytest.raises(ValueError):
            historical_repository.collection_policies({_INITIAL_POLICY_ID})
        with pytest.raises(ValueError):
            historical_repository.effective_collection_policy(
                "forzy-motor-01",
                _POLICY_FROM,
            )

    def test_missing_policy_never_substitutes_the_runtime_default(
        self,
        historical_repository: HistoricalRepositoryV1,
        repository_control: RepositoryContractControl,
    ) -> None:
        repository_control.delete_policy(_INITIAL_POLICY_ID)
        before = repository_control.snapshot()

        assert historical_repository.collection_policy(_INITIAL_POLICY_ID) is None
        assert historical_repository.collection_policies({_INITIAL_POLICY_ID}) == {}
        assert (
            historical_repository.effective_collection_policy(
                "forzy-motor-01",
                _POLICY_FROM,
            )
            is None
        )
        assert repository_control.snapshot() == before

    def test_effective_policy_uses_half_open_intervals_and_multiple_match_fails_closed(
        self,
        historical_repository: HistoricalRepositoryV1,
        repository_control: RepositoryContractControl,
    ) -> None:
        repository_control.delete_policy(_INITIAL_POLICY_ID)
        boundary = _POLICY_FROM + timedelta(days=1)
        first = _policy(
            "policy-first",
            effective_from=_POLICY_FROM,
            effective_to=boundary,
        )
        second = _policy(
            "policy-second",
            effective_from=boundary,
            effective_to=None,
        )
        repository_control.insert_policy(first)
        repository_control.insert_policy(second)
        before = repository_control.snapshot()

        assert (
            historical_repository.effective_collection_policy(
                "forzy-motor-01",
                _POLICY_FROM - timedelta(milliseconds=1),
            )
            is None
        )
        assert historical_repository.effective_collection_policy(
            "forzy-motor-01",
            _POLICY_FROM,
        ) == first
        assert historical_repository.effective_collection_policy(
            "forzy-motor-01",
            boundary - timedelta(milliseconds=1),
        ) == first
        assert historical_repository.effective_collection_policy(
            "forzy-motor-01",
            boundary,
        ) == second
        assert repository_control.snapshot() == before

        overlapping = _policy(
            "policy-overlapping",
            effective_from=boundary - timedelta(hours=1),
            effective_to=boundary + timedelta(hours=1),
        )
        repository_control.insert_policy(overlapping)
        corrupted = repository_control.snapshot()

        with pytest.raises(RuntimeError, match="multiple effective"):
            historical_repository.effective_collection_policy(
                "forzy-motor-01",
                boundary,
            )
        assert repository_control.snapshot() == corrupted
