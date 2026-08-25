"""Causal historical assessment exporter with pinned artifact provenance."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json
from math import isfinite
from pathlib import Path
from typing import Sequence
from uuid import NAMESPACE_URL, uuid5

import pandas as pd

from twinops.contracts.timeline_v1_models import HistoricalAssessmentV1
from twinops.ingestion.history_profiles_v1 import (
    HistoricalStoredSampleV1,
    PreparedHistoricalBatchV1,
)
from twinops.ml.artifacts import compute_file_hash, load_artifact_bundle
from twinops.ml.backtest import (
    WalkForwardFold,
    WalkForwardRowAssessmentV1,
    build_walk_forward_folds,
    evaluate_walk_forward_rows,
)
from twinops.ml.features import FeatureConfig, compute_trailing_features
from twinops.storage.historical_repository_v1 import StoredHistoricalAssessmentV1


_BASE_LIMITATIONS = (
    "historical_source_participated_in_baseline_construction_and_evaluation",
    "relative_score_not_failure_probability_confidence_rul_or_diagnosis",
    "no_confirmed_failure_labels_available",
)
_CAUSAL_FEATURE_COLUMNS = (
    "velocity_ewma",
    "velocity_slope",
    "velocity_change_point",
    "temperature_deviation",
)


@dataclass(frozen=True)
class HistoricalAssessmentBuildV1:
    assessments: tuple[StoredHistoricalAssessmentV1, ...]
    artifact_sha256: str
    feature_manifest_sha256: str
    report_sha256: str
    config_sha256: str
    candidate_count: int
    validated_anchor_count: int
    validated_episode_count: int


def build_historical_assessments_v1(
    prepared_batch: PreparedHistoricalBatchV1,
    artifact_dir: Path,
    *,
    expected_artifact_sha256: str,
    expected_feature_manifest_sha256: str,
    expected_report_sha256: str,
    expected_config_sha256: str,
) -> HistoricalAssessmentBuildV1:
    """Build immutable contract rows without scoring any row with the final model."""

    source = Path(artifact_dir)
    bundle = load_artifact_bundle(
        source,
        expected_manifest_hash=expected_feature_manifest_sha256,
        expected_model_hash=expected_artifact_sha256,
    )
    if compute_file_hash(source / "backtest-report.json") != expected_report_sha256:
        raise ValueError("report hash does not match the pinned identity")
    if bundle.pipeline.config_hash != expected_config_sha256:
        raise ValueError("config hash does not match the pinned baseline configuration")
    if (
        bundle.pipeline.model_name != "robust-baseline"
        or bundle.pipeline.model_version != "1.0.1"
    ):
        raise ValueError("artifact model family/version is not supported")
    _validate_prepared_batch_identity(prepared_batch, source, bundle.config)

    feature_payload = bundle.config.get("features")
    if not isinstance(feature_payload, dict):
        raise ValueError("artifact config does not declare feature windows")
    feature_config = FeatureConfig(
        short_window_seconds=float(feature_payload["short_window_seconds"]),
        long_window_seconds=float(feature_payload["long_window_seconds"]),
        min_points=int(feature_payload["min_points"]),
    )
    holdout_count = int(bundle.config.get("holdoutCount", 2))
    frame, cycle_ids = _prepared_feature_frame(prepared_batch, feature_config)
    folds = build_walk_forward_folds(frame, holdout_count=holdout_count)
    evaluation = evaluate_walk_forward_rows(frame, bundle.pipeline, folds)
    validated_episode_count = _validate_causal_episode_rows(evaluation.rows, frame)
    _validate_report_folds(frame, folds, bundle.report)

    anchors_by_reading: dict[str, HistoricalStoredSampleV1] = {}
    for sample in prepared_batch.samples:
        reading_id = str(sample.reading.reading_id)
        if reading_id in anchors_by_reading:
            raise ValueError(
                f"historical reading is duplicated in the prepared batch: {reading_id}"
            )
        anchors_by_reading[reading_id] = sample

    assessments: list[StoredHistoricalAssessmentV1] = []
    for row in evaluation.rows:
        sample = anchors_by_reading.get(row.reading_id)
        if sample is None:
            raise ValueError(f"causal row has no exact original anchor: {row.reading_id}")
        reading = sample.reading
        expected_cycle_id = cycle_ids[
            int(
                frame.loc[
                    frame["reading_id"].eq(row.reading_id), "cycle_id"
                ].iloc[0]
            )
        ]
        if (
            str(reading.sensor_id) != row.sensor_id
            or str(reading.operating_cycle_id) != expected_cycle_id
            or _utc(reading.event_at) != row.anchor_event_at
        ):
            raise ValueError("causal row does not match its source sensor/cycle/event")
        assessment_id = str(
            uuid5(
                NAMESPACE_URL,
                "|".join(
                    (
                        "historical-assessment-v1",
                        str(prepared_batch.batch_id),
                        row.fold_id,
                        str(sample.point_id),
                    )
                ),
            )
        )
        candidate = row.status in {"watch", "alert"}
        limitations = [*_BASE_LIMITATIONS]
        if candidate:
            limitations.append("candidate_not_ground_truth")
        limitations.sort()
        assessment = HistoricalAssessmentV1.model_validate(
            {
                "schemaVersion": "1.0",
                "assessmentId": assessment_id,
                "foldId": row.fold_id,
                "sensorId": row.sensor_id,
                "operatingCycleId": str(reading.operating_cycle_id),
                "trainingWindow": {
                    "start": row.training_start,
                    "end": row.training_end,
                },
                "assessmentWindow": {
                    "start": row.window_start,
                    "end": row.window_end,
                },
                "assessmentAt": row.anchor_event_at,
                "anchorPointId": str(sample.point_id),
                "status": row.status,
                "anomalyScore": row.anomaly_score,
                "deteriorationScore": row.deterioration_score,
                "scoreSemantics": (
                    "relative_to_walk_forward_historical_baseline_not_failure_probability"
                ),
                "persistence": {
                    "episodeId": row.episode_id,
                    "episodeStartedAt": row.episode_started_at,
                    "persistenceSeconds": row.persistence_seconds,
                    "persistenceCount": row.persistence_count,
                },
                "quality": {
                    "status": row.quality_status,
                    "flags": list(row.quality_flags),
                },
                "evidence": [
                    item.model_dump(by_alias=True) for item in row.evidence
                ],
                "modelFamily": row.model_family,
                "modelVersion": row.model_version,
                "modelHash": expected_artifact_sha256,
                "foldHash": row.fold_model_hash,
                "reportHash": expected_report_sha256,
                "componentTag": None,
                "humanValidationRequired": True,
                "limitations": limitations,
            }
        )
        assessments.append(
            StoredHistoricalAssessmentV1(
                batch_id=prepared_batch.batch_id,
                assessment=assessment,
            )
        )

    assessments.sort(
        key=lambda stored: (
            stored.assessment.assessment_at,
            str(stored.assessment.anchor_point_id),
            stored.assessment.sensor_id,
            stored.assessment.fold_id,
        )
    )
    candidate_count = sum(
        stored.assessment.status in {"watch", "alert"} for stored in assessments
    )
    return HistoricalAssessmentBuildV1(
        assessments=tuple(assessments),
        artifact_sha256=expected_artifact_sha256,
        feature_manifest_sha256=expected_feature_manifest_sha256,
        report_sha256=expected_report_sha256,
        config_sha256=expected_config_sha256,
        candidate_count=candidate_count,
        validated_anchor_count=len(assessments),
        validated_episode_count=validated_episode_count,
    )


def _validate_prepared_batch_identity(
    prepared_batch: PreparedHistoricalBatchV1,
    artifact_dir: Path,
    config: dict[str, object],
) -> None:
    if not prepared_batch.samples:
        raise ValueError("prepared historical batch has no samples")
    actual_source_sha = "sha256:" + sha256(prepared_batch.source_bytes).hexdigest()
    if actual_source_sha != prepared_batch.source_sha256:
        raise ValueError("prepared source bytes do not match source hash")
    actual_manifest_sha = "sha256:" + sha256(
        prepared_batch.manifest_json.encode("utf-8")
    ).hexdigest()
    if actual_manifest_sha != prepared_batch.manifest_sha256:
        raise ValueError("prepared manifest bytes do not match manifest hash")
    if len({str(sample.point_id) for sample in prepared_batch.samples}) != len(
        prepared_batch.samples
    ):
        raise ValueError("prepared historical batch has duplicate point identities")
    if any(
        sample.batch_id != prepared_batch.batch_id
        for sample in prepared_batch.samples
    ):
        raise ValueError("prepared historical samples cross batch identity")
    dataset = config.get("dataset")
    if isinstance(dataset, dict):
        declared_rows = dataset.get("rows")
        if declared_rows is not None and int(declared_rows) != len(
            prepared_batch.samples
        ):
            raise ValueError("prepared sample count differs from artifact dataset")
        declared_source = dataset.get("sourceSha256")
        if (
            declared_source is not None
            and declared_source != prepared_batch.source_sha256
        ):
            raise ValueError("prepared source hash differs from artifact dataset")
        declared_cycles = dataset.get("cycleCount")
        actual_cycles = len(
            {str(sample.reading.operating_cycle_id) for sample in prepared_batch.samples}
        )
        if declared_cycles is not None and int(declared_cycles) != actual_cycles:
            raise ValueError("prepared cycle count differs from artifact dataset")
    summary_path = artifact_dir / "source-summary.json"
    if summary_path.is_file():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        if summary.get("sourceSha256") != prepared_batch.source_sha256:
            raise ValueError("prepared source hash differs from artifact source summary")
        if int(summary.get("canonicalSamples", -1)) != len(
            prepared_batch.samples
        ):
            raise ValueError("prepared sample count differs from artifact source summary")
        actual_cycles = len(
            {str(sample.reading.operating_cycle_id) for sample in prepared_batch.samples}
        )
        if int(summary.get("cycleCount", -1)) != actual_cycles:
            raise ValueError("prepared cycle count differs from artifact source summary")


def _validate_report_folds(
    frame: pd.DataFrame,
    folds: Sequence[WalkForwardFold],
    report: dict[str, object],
) -> None:
    declared = report.get("folds")
    if not isinstance(declared, list) or len(declared) != len(folds):
        raise ValueError("report fold definitions differ from reconstructed folds")
    for fold_index, (fold, record) in enumerate(zip(folds, declared, strict=True)):
        if not isinstance(record, dict):
            raise ValueError("report fold definition must be an object")
        expected = {
            "fold": fold_index,
            "train_cycle_ids": list(fold.train_cycle_ids),
            "test_cycle_ids": list(fold.test_cycle_ids),
            "frozen_holdout": fold.frozen_holdout,
        }
        if any(record.get(key) != value for key, value in expected.items()):
            raise ValueError("report fold definitions differ from reconstructed folds")
        calibration = frame.loc[
            frame["cycle_id"].isin(fold.train_cycle_ids)
            & frame["feature_valid"].fillna(False).astype(bool)
            & frame["operating_state"].eq("steady")
        ]
        trained_until = pd.to_datetime(calibration["event_at"], utc=True).max()
        if pd.Timestamp(record.get("trained_until")) != trained_until:
            raise ValueError("report trained_until differs from causal fold state")


def _validate_causal_episode_rows(
    rows: Sequence[WalkForwardRowAssessmentV1],
    frame: pd.DataFrame,
) -> int:
    source_by_reading: dict[str, tuple[str, int, datetime]] = {}
    cycles_by_sensor_event: dict[tuple[str, datetime], set[int]] = {}
    for source_row in frame.itertuples():
        reading_id = str(source_row.reading_id)
        facts = (
            str(source_row.sensor_id),
            int(source_row.cycle_id),
            _utc(source_row.event_at),
        )
        if reading_id in source_by_reading:
            raise ValueError("episode validation found a duplicated reading")
        source_by_reading[reading_id] = facts
        cycles_by_sensor_event.setdefault((facts[0], facts[2]), set()).add(facts[1])

    rows_by_fold_reading: dict[
        tuple[str, str], WalkForwardRowAssessmentV1
    ] = {}
    streams: set[tuple[str, str, int]] = set()
    for row in rows:
        source = source_by_reading.get(row.reading_id)
        if source is None:
            raise ValueError("episode validation found no source reading")
        sensor_id, cycle_id, event_at = source
        if sensor_id != row.sensor_id or event_at != row.anchor_event_at:
            raise ValueError("episode validation found crossed source facts")
        key = (row.fold_id, row.reading_id)
        if key in rows_by_fold_reading:
            raise ValueError("episode validation found a duplicated fold reading")
        rows_by_fold_reading[key] = row
        streams.add((row.fold_id, row.sensor_id, cycle_id))

    consumed: set[tuple[str, str]] = set()
    validated_candidate_count = 0
    for fold_id, sensor_id, cycle_id in sorted(streams):
        source_rows = frame.loc[
            frame["sensor_id"].astype(str).eq(sensor_id)
            & frame["cycle_id"].astype(int).eq(cycle_id)
        ].copy()
        source_rows = source_rows.assign(
            _reading_order=source_rows["reading_id"].fillna("").astype(str)
        ).sort_values(["event_at", "_reading_order"], kind="stable")
        episode_state: tuple[
            tuple[object, ...], str, datetime, int
        ] | None = None
        for source_row in source_rows.itertuples():
            reading_id = str(source_row.reading_id)
            key = (fold_id, reading_id)
            row = rows_by_fold_reading.get(key)
            if row is None:
                episode_state = None
                continue
            source_window = _eligible_source_window(source_row, row.training_end)
            if source_window is None:
                episode_state = None
                raise ValueError(
                    "episode validation found assessment for an ineligible source row"
                )
            source_window_start, source_window_end = source_window
            if (
                row.window_start != source_window_start
                or row.window_end != source_window_end
            ):
                raise ValueError("episode validation found crossed source window facts")
            consumed.add(key)
            boundary = (
                str(getattr(source_row, "source", "unknown")),
                _boundary_value(
                    getattr(source_row, "collection_policy_id", None)
                ),
                row.model_family,
                row.model_version,
                row.fold_id,
                row.sensor_id,
                cycle_id,
            )
            quality_flags = _quality_flags(
                getattr(source_row, "quality_flags", ())
            )
            if any("gap" in flag.lower() for flag in quality_flags):
                episode_state = None
            if episode_state is not None and episode_state[0] != boundary:
                episode_state = None

            if row.status == "normal":
                if (
                    row.episode_id is not None
                    or row.episode_started_at is not None
                    or row.persistence_seconds != 0
                    or row.persistence_count != 0
                ):
                    raise ValueError("normal row cannot carry causal episode facts")
                episode_state = None
                continue
            if row.episode_id is None or row.episode_started_at is None:
                raise ValueError("candidate row requires causal episode facts")
            if row.episode_started_at > row.anchor_event_at:
                raise ValueError("episode start cannot be in the future")
            if not (
                row.training_end
                < row.episode_started_at
                <= row.window_end
                == row.anchor_event_at
            ):
                raise ValueError("episode timestamps are not causal")
            start_cycles = cycles_by_sensor_event.get(
                (row.sensor_id, row.episode_started_at), set()
            )
            if start_cycles and cycle_id not in start_cycles:
                raise ValueError("episode start crosses an operating cycle")

            if episode_state is None:
                expected_id = row.episode_id
                expected_start = row.anchor_event_at
                expected_count = 1
            else:
                _, expected_id, expected_start, previous_count = episode_state
                expected_count = previous_count + 1
            expected_seconds = (
                row.anchor_event_at - expected_start
            ).total_seconds()
            if (
                row.episode_id != expected_id
                or row.episode_started_at != expected_start
                or row.persistence_count != expected_count
                or row.persistence_seconds != expected_seconds
            ):
                raise ValueError("episode crosses a causal boundary")
            episode_state = (
                boundary,
                row.episode_id,
                row.episode_started_at,
                row.persistence_count,
            )
            validated_candidate_count += 1

    if consumed != set(rows_by_fold_reading):
        raise ValueError("episode validation did not consume every assessment row")
    return validated_candidate_count


def _eligible_source_window(
    source_row: object,
    training_end: datetime,
) -> tuple[datetime, datetime] | None:
    reading_id = getattr(source_row, "reading_id", None)
    if (
        reading_id is None
        or _is_missing(reading_id)
        or not str(reading_id).strip()
    ):
        return None
    if not _is_true(getattr(source_row, "feature_valid", False)):
        return None
    if not _is_true(getattr(source_row, "is_new_information", True)):
        return None
    for feature in _CAUSAL_FEATURE_COLUMNS:
        try:
            if not isfinite(float(getattr(source_row, feature))):
                return None
        except (AttributeError, TypeError, ValueError):
            return None

    event_at = _optional_utc(getattr(source_row, "event_at", None))
    window_start = _optional_utc(
        getattr(source_row, "feature_window_start", None)
    )
    window_end = _optional_utc(getattr(source_row, "feature_window_end", None))
    if event_at is None or window_start is None or window_end is None:
        return None
    if not (_utc(training_end) < window_start <= window_end == event_at):
        return None
    return window_start, window_end


def _is_true(value: object) -> bool:
    return not _is_missing(value) and bool(value)


def _is_missing(value: object) -> bool:
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _optional_utc(value: object) -> datetime | None:
    if value is None or _is_missing(value):
        return None
    try:
        return _utc(value)
    except (TypeError, ValueError):
        return None


def _quality_flags(value: object) -> tuple[str, ...]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ()
    if isinstance(value, str):
        candidates = (value,)
    else:
        candidates = tuple(str(item) for item in value)
    return tuple(sorted(set(flag for flag in candidates if flag)))


def _boundary_value(value: object) -> object:
    if value is None or pd.isna(value):
        return None
    return value


def _prepared_feature_frame(
    prepared_batch: PreparedHistoricalBatchV1,
    feature_config: FeatureConfig,
) -> tuple[pd.DataFrame, dict[int, str]]:
    ordered_samples = sorted(
        prepared_batch.samples,
        key=lambda sample: (
            _utc(sample.reading.event_at),
            str(sample.reading.sensor_id),
            str(sample.reading.reading_id),
        ),
    )
    cycle_order: dict[str, int] = {}
    cycle_ids: dict[int, str] = {}
    previous_by_sensor: dict[str, tuple[datetime, bool, int]] = {}
    rows: list[dict[str, object]] = []
    for sample in ordered_samples:
        reading = sample.reading
        event_at = _utc(reading.event_at)
        cycle_uuid = str(reading.operating_cycle_id)
        if cycle_uuid not in cycle_order:
            cycle_index = len(cycle_order)
            cycle_order[cycle_uuid] = cycle_index
            cycle_ids[cycle_index] = cycle_uuid
        cycle_id = cycle_order[cycle_uuid]
        sensor_id = str(reading.sensor_id)
        velocity = float(reading.measurements.vibration_velocity_rms.value)
        active = velocity > 0.05
        previous = previous_by_sensor.get(sensor_id)
        if previous is None or previous[2] != cycle_id:
            cadence = (
                None
                if previous is None
                else (event_at - previous[0]).total_seconds()
            )
            operating_state = "startup" if active else "stopped"
        else:
            cadence = (event_at - previous[0]).total_seconds()
            operating_state = _operating_state(previous[1], active)
        previous_by_sensor[sensor_id] = (event_at, active, cycle_id)
        quality_flags = tuple(
            dict.fromkeys(str(flag) for flag in reading.quality_flags)
        )
        rows.append(
            {
                "received_at": _utc(reading.provenance.ingested_at),
                "event_at": event_at,
                "reading_id": str(reading.reading_id),
                "source": "forzy-csv",
                "asset_tag": prepared_batch.asset_id,
                "sensor_id": sensor_id,
                "velocity_rms": velocity,
                "acceleration": float(
                    reading.measurements.vibration_acceleration.value
                ),
                "temperature": float(reading.measurements.temperature.value),
                "payload_hash": str(reading.provenance.row_sha256),
                "quality_flags": quality_flags,
                "is_new_information": not any(
                    flag in {"unchanged_from_previous", "duplicate_payload"}
                    for flag in quality_flags
                ),
                "cadence_seconds": cadence,
                "cycle_id": cycle_id,
                "operating_state": operating_state,
                "state_estimated": True,
            }
        )
    frame = pd.DataFrame(rows)
    frame = compute_trailing_features(frame, feature_config)
    return frame, cycle_ids


def _operating_state(previous_active: bool, active: bool) -> str:
    if previous_active and active:
        return "steady"
    if previous_active and not active:
        return "shutdown"
    if not previous_active and active:
        return "startup"
    return "stopped"


def _utc(value: object) -> datetime:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("UTC")
    else:
        timestamp = timestamp.tz_convert("UTC")
    return timestamp.to_pydatetime()
