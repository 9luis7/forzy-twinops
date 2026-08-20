"""Auditable diagnostic and prognostic cross-bench baselines."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import confusion_matrix, f1_score, mean_absolute_error, recall_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from twinops.research.contracts import FeaturePolicy, LabelMappingPolicy, SignalWindow
from twinops.research.features import FeatureViews, extract_views


@dataclass(frozen=True, slots=True)
class ConfidenceInterval:
    status: str
    low: float | None
    high: float | None
    confidence: float
    samples: int
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class BaselineMetrics:
    accuracy: float
    macro_f1: float
    balanced_accuracy: float
    predicted_label: str


@dataclass(frozen=True, slots=True)
class DiagnosticMetrics:
    macro_f1: float
    balanced_accuracy: float
    per_class_recall: Mapping[str, float]
    confusion_matrix: tuple[tuple[int, ...], ...]
    labels: tuple[str, ...]
    majority_baseline: BaselineMetrics
    confidence_intervals: Mapping[str, ConfidenceInterval]


@dataclass(frozen=True, slots=True)
class PrognosticMetrics:
    status: str
    reason: str | None
    life_fraction_mae: float | None
    detection_lead_time_fraction: float | None
    detection_lead_time_status: str
    detection_lead_time_reason: str | None
    lead_time_rule: str
    lead_time_detected_bearings: int
    lead_time_total_bearings: int
    lead_time_detection_coverage: float | None
    undetected_bearing_ids: tuple[str, ...]
    confidence_intervals: Mapping[str, ConfidenceInterval]


@dataclass(frozen=True, slots=True)
class LabelCoverage:
    input_windows: int
    included_windows: int
    excluded_windows: int
    input_bearings: int
    included_bearings: int
    excluded_bearings: int
    window_coverage: float
    bearing_coverage: float
    included_labels: tuple[str, ...]
    excluded_by_label: Mapping[str, int]
    excluded_labels: tuple[str, ...]
    bearings_with_excluded_windows: tuple[str, ...]
    fully_excluded_bearing_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ViewResult:
    feature_names: tuple[str, ...]
    diagnostic: DiagnosticMetrics
    prognostic: PrognosticMetrics


@dataclass(frozen=True, slots=True)
class AblationReport:
    train_dataset_id: str
    test_dataset_id: str
    seed: int
    train_bearings: tuple[str, ...]
    test_bearings: tuple[str, ...]
    train_windows: int
    test_windows: int
    label_mapping_version: str
    feature_policy_id: str
    label_mapping: Mapping[str, str | None]
    train_coverage: LabelCoverage
    test_coverage: LabelCoverage
    bootstrap_unit: str
    bootstrap_samples: int
    views: Mapping[str, ViewResult]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _one_dataset(windows: Sequence[SignalWindow], *, role: str) -> str:
    if not windows:
        raise ValueError(f"{role} dataset must not be empty")
    dataset_ids = {window.dataset_id for window in windows}
    if len(dataset_ids) != 1:
        raise ValueError(f"{role} input must contain exactly one dataset, got {sorted(dataset_ids)}")
    return next(iter(dataset_ids))


def _map_labels(
    windows: Sequence[SignalWindow], policy: LabelMappingPolicy, *, role: str
) -> tuple[tuple[SignalWindow, ...], np.ndarray, LabelCoverage]:
    included: list[SignalWindow] = []
    labels: list[str] = []
    excluded = Counter()
    bearings_with_exclusions: set[str] = set()
    for window in windows:
        source_label = window.window_state_label
        if source_label not in policy.mapping:
            raise ValueError(f"{role}: unexpected label {source_label!r} is absent from mapping {policy.version}")
        target = policy.mapping[source_label]
        if target is None:
            excluded[source_label] += 1
            bearings_with_exclusions.add(window.bearing_id)
            continue
        included.append(window)
        labels.append(target)
    if not included:
        raise ValueError(f"{role}: label mapping excluded every window")
    input_bearings = {window.bearing_id for window in windows}
    included_bearings = {window.bearing_id for window in included}
    coverage = LabelCoverage(
        input_windows=len(windows),
        included_windows=len(included),
        excluded_windows=len(windows) - len(included),
        input_bearings=len(input_bearings),
        included_bearings=len(included_bearings),
        excluded_bearings=len(input_bearings - included_bearings),
        window_coverage=len(included) / len(windows),
        bearing_coverage=len(included_bearings) / len(input_bearings),
        included_labels=tuple(sorted(set(labels))),
        excluded_by_label=dict(sorted(excluded.items())),
        excluded_labels=tuple(sorted(excluded)),
        bearings_with_excluded_windows=tuple(sorted(bearings_with_exclusions)),
        fully_excluded_bearing_ids=tuple(sorted(input_bearings - included_bearings)),
    )
    return tuple(included), np.asarray(labels), coverage


def _common_features(
    train: Sequence[FeatureViews], test: Sequence[FeatureViews], view: str
) -> tuple[str, ...]:
    common = set.intersection(*(set(getattr(item, view)) for item in (*train, *test)))
    if not common:
        raise ValueError(f"view {view!r} has no semantically common features across benches")
    return tuple(sorted(common))


def _matrix(features: Sequence[FeatureViews], view: str, names: tuple[str, ...]) -> np.ndarray:
    matrix = np.asarray(
        [[float(getattr(item, view)[name]) for name in names] for item in features], dtype=float
    )
    if not np.isfinite(matrix).all():
        raise ValueError(f"view {view!r} produced non-finite model input")
    return matrix


def _balanced_accuracy(truth: np.ndarray, predicted: np.ndarray, labels: tuple[str, ...]) -> float:
    recalls = recall_score(truth, predicted, labels=labels, average=None, zero_division=0)
    return float(np.mean(recalls))


def _completed_interval(values: Sequence[float], samples: int) -> ConfidenceInterval:
    low, high = np.percentile(values, [2.5, 97.5])
    return ConfidenceInterval("completed", float(low), float(high), 0.95, samples)


def _unavailable_interval(reason: str) -> ConfidenceInterval:
    return ConfidenceInterval("not_available", None, None, 0.95, 0, reason)


def _classification_bootstrap(
    truth: np.ndarray,
    predicted: np.ndarray,
    bearing_ids: Sequence[str],
    labels: tuple[str, ...],
    *,
    seed: int,
    samples: int,
) -> dict[str, ConfidenceInterval]:
    by_bearing: dict[str, list[int]] = defaultdict(list)
    for index, bearing_id in enumerate(bearing_ids):
        by_bearing[bearing_id].append(index)
    bearings = sorted(by_bearing)
    rng = np.random.default_rng(seed)
    macro_values: list[float] = []
    balanced_values: list[float] = []
    attempts = 0
    while len(macro_values) < samples and attempts < samples * 100:
        attempts += 1
        drawn = rng.choice(bearings, size=len(bearings), replace=True)
        indices = [index for bearing in drawn for index in by_bearing[str(bearing)]]
        sampled_truth = truth[indices]
        if set(sampled_truth) != set(labels):
            continue
        sampled_predicted = predicted[indices]
        macro_values.append(
            float(
                f1_score(
                    sampled_truth,
                    sampled_predicted,
                    labels=labels,
                    average="macro",
                    zero_division=0,
                )
            )
        )
        balanced_values.append(_balanced_accuracy(sampled_truth, sampled_predicted, labels))
    if len(macro_values) < samples:
        reason = "insufficient class-preserving bearing bootstrap samples"
        unavailable = _unavailable_interval(reason)
        return {"macro_f1": unavailable, "balanced_accuracy": unavailable}
    return {
        "macro_f1": _completed_interval(macro_values, samples),
        "balanced_accuracy": _completed_interval(balanced_values, samples),
    }


def _diagnose(
    x_train: np.ndarray,
    y_train: np.ndarray,
    x_test: np.ndarray,
    y_test: np.ndarray,
    test_bearings: Sequence[str],
    labels: tuple[str, ...],
    *,
    seed: int,
    bootstrap_samples: int,
) -> DiagnosticMetrics:
    model = Pipeline(
        [
            ("scale", StandardScaler()),
            (
                "model",
                LogisticRegression(
                    class_weight="balanced", max_iter=2_000, random_state=seed
                ),
            ),
        ]
    )
    model.fit(x_train, y_train)
    predicted = model.predict(x_test)
    recalls = recall_score(y_test, predicted, labels=labels, average=None, zero_division=0)
    majority_label = sorted(Counter(y_train).items(), key=lambda item: (-item[1], item[0]))[0][0]
    majority_predicted = np.full(y_test.shape, majority_label)
    majority = BaselineMetrics(
        accuracy=float(np.mean(y_test == majority_predicted)),
        macro_f1=float(
            f1_score(
                y_test,
                majority_predicted,
                labels=labels,
                average="macro",
                zero_division=0,
            )
        ),
        balanced_accuracy=_balanced_accuracy(y_test, majority_predicted, labels),
        predicted_label=str(majority_label),
    )
    matrix = confusion_matrix(y_test, predicted, labels=labels)
    return DiagnosticMetrics(
        macro_f1=float(
            f1_score(y_test, predicted, labels=labels, average="macro", zero_division=0)
        ),
        balanced_accuracy=_balanced_accuracy(y_test, predicted, labels),
        per_class_recall={label: float(value) for label, value in zip(labels, recalls, strict=True)},
        confusion_matrix=tuple(tuple(int(value) for value in row) for row in matrix),
        labels=labels,
        majority_baseline=majority,
        confidence_intervals=_classification_bootstrap(
            y_test,
            predicted,
            test_bearings,
            labels,
            seed=seed,
            samples=bootstrap_samples,
        ),
    )


def _validate_life_trajectory(windows: Sequence[SignalWindow], *, role: str) -> None:
    by_bearing: dict[str, list[SignalWindow]] = defaultdict(list)
    for window in windows:
        by_bearing[window.bearing_id].append(window)
    for bearing, bearing_windows in by_bearing.items():
        sequences = [window.sequence_index for window in bearing_windows]
        if any(sequence is None for sequence in sequences) or len(set(sequences)) != len(sequences):
            raise ValueError(f"{role}: prognosis requires unique typed sequence_index for {bearing}")
        ordered = sorted(bearing_windows, key=lambda window: int(window.sequence_index))
        life = [float(window.life_fraction) for window in ordered]
        if any(later < earlier for earlier, later in zip(life, life[1:])):
            raise ValueError(f"{role}: life_fraction must be non-decreasing by sequence_index for {bearing}")


def _bearing_lead_times(
    predicted: np.ndarray, truth: np.ndarray, windows: Sequence[SignalWindow]
) -> dict[str, float]:
    by_bearing: dict[str, list[int]] = defaultdict(list)
    for index, window in enumerate(windows):
        by_bearing[window.bearing_id].append(index)
    lead_times: dict[str, float] = {}
    for bearing, indices in by_bearing.items():
        ordered = sorted(indices, key=lambda index: int(windows[index].sequence_index))
        detected = next((index for index in ordered if predicted[index] >= 0.8), None)
        if detected is not None:
            lead_times[bearing] = 1.0 - float(truth[detected])
    return lead_times


def _prognose(
    x_train: np.ndarray,
    train_windows: Sequence[SignalWindow],
    x_test: np.ndarray,
    test_windows: Sequence[SignalWindow],
    *,
    seed: int,
    bootstrap_samples: int,
) -> PrognosticMetrics:
    availability = [window.life_fraction is not None for window in (*train_windows, *test_windows)]
    rule = (
        "Per bearing ordered only by typed sequence_index, first window with predicted "
        "life_fraction >= 0.8; lead time is 1 - true life_fraction at that window. "
        "The metric is available only when every test bearing crosses the threshold."
    )
    test_bearing_ids = tuple(sorted({window.bearing_id for window in test_windows}))
    if not any(availability):
        reason = "life_fraction is unavailable for all mapped windows"
        unavailable = _unavailable_interval(reason)
        return PrognosticMetrics(
            status="not_available",
            reason=reason,
            life_fraction_mae=None,
            detection_lead_time_fraction=None,
            detection_lead_time_status="not_available",
            detection_lead_time_reason=reason,
            lead_time_rule=rule,
            lead_time_detected_bearings=0,
            lead_time_total_bearings=len(test_bearing_ids),
            lead_time_detection_coverage=None,
            undetected_bearing_ids=test_bearing_ids,
            confidence_intervals={
                "life_fraction_mae": unavailable,
                "detection_lead_time_fraction": unavailable,
            },
        )
    if not all(availability):
        raise ValueError("life_fraction is partially available; prognosis cannot mix missing targets")
    _validate_life_trajectory(train_windows, role="train")
    _validate_life_trajectory(test_windows, role="test")
    y_train = np.asarray([window.life_fraction for window in train_windows], dtype=float)
    y_test = np.asarray([window.life_fraction for window in test_windows], dtype=float)
    model = HistGradientBoostingRegressor(random_state=seed)
    model.fit(x_train, y_train)
    predicted = np.clip(model.predict(x_test), 0.0, 1.0)
    mae = float(mean_absolute_error(y_test, predicted))
    lead_times = _bearing_lead_times(predicted, y_test, test_windows)

    by_bearing: dict[str, list[int]] = defaultdict(list)
    for index, window in enumerate(test_windows):
        by_bearing[window.bearing_id].append(index)
    bearings = sorted(by_bearing)
    undetected_bearings = tuple(sorted(set(bearings) - set(lead_times)))
    detected_bearings = len(lead_times)
    total_bearings = len(bearings)
    detection_coverage = detected_bearings / total_bearings
    rng = np.random.default_rng(seed + 10_003)
    mae_values: list[float] = []
    lead_values: list[float] = []
    for _ in range(bootstrap_samples):
        drawn = [str(value) for value in rng.choice(bearings, size=len(bearings), replace=True)]
        indices = [index for bearing in drawn for index in by_bearing[bearing]]
        mae_values.append(float(mean_absolute_error(y_test[indices], predicted[indices])))
        if not undetected_bearings:
            drawn_leads = [lead_times[bearing] for bearing in drawn]
            lead_values.append(float(np.mean(drawn_leads)))
    if undetected_bearings:
        lead_reason = (
            f"threshold detection available for {detected_bearings} of {total_bearings} "
            f"test bearings; missing {list(undetected_bearings)}"
        )
        lead_point = None
        lead_status = "not_available"
        lead_interval = _unavailable_interval(lead_reason)
    else:
        lead_point = float(np.mean(list(lead_times.values())))
        lead_status = "completed"
        lead_reason = None
        lead_interval = _completed_interval(lead_values, bootstrap_samples)
    return PrognosticMetrics(
        status="completed",
        reason=None,
        life_fraction_mae=mae,
        detection_lead_time_fraction=lead_point,
        detection_lead_time_status=lead_status,
        detection_lead_time_reason=lead_reason,
        lead_time_rule=rule,
        lead_time_detected_bearings=detected_bearings,
        lead_time_total_bearings=total_bearings,
        lead_time_detection_coverage=detection_coverage,
        undetected_bearing_ids=undetected_bearings,
        confidence_intervals={
            "life_fraction_mae": _completed_interval(mae_values, bootstrap_samples),
            "detection_lead_time_fraction": lead_interval,
        },
    )


def run_ablation(
    train_dataset: Sequence[SignalWindow],
    test_dataset: Sequence[SignalWindow],
    *,
    feature_policy: FeaturePolicy,
    label_policy: LabelMappingPolicy,
    seed: int = 42,
    bootstrap_samples: int = 500,
) -> AblationReport:
    """Train on one bench and evaluate three nested feature masks on another."""

    if bootstrap_samples < 20:
        raise ValueError("bootstrap_samples must be at least 20")
    train_all = tuple(train_dataset)
    test_all = tuple(test_dataset)
    train_dataset_id = _one_dataset(train_all, role="train")
    test_dataset_id = _one_dataset(test_all, role="test")
    train_bearing_names = {window.bearing_id for window in train_all}
    test_bearing_names = {window.bearing_id for window in test_all}
    if train_dataset_id == test_dataset_id and train_bearing_names & test_bearing_names:
        overlap = sorted(train_bearing_names & test_bearing_names)
        raise ValueError(f"bearing overlap between train and test: {overlap}")

    train, y_train, train_coverage = _map_labels(train_all, label_policy, role="train")
    test, y_test, test_coverage = _map_labels(test_all, label_policy, role="test")
    train_labels = set(y_train)
    test_labels = set(y_test)
    if train_labels != test_labels or len(train_labels) < 2:
        raise ValueError(
            f"cross-bench evaluation requires at least two identical mappable label sets; "
            f"train={sorted(train_labels)}, test={sorted(test_labels)}"
        )
    labels = tuple(sorted(train_labels))

    train_features = tuple(extract_views(window, policy=feature_policy) for window in train)
    test_features = tuple(extract_views(window, policy=feature_policy) for window in test)
    test_bearings = tuple(f"{window.dataset_id}:{window.bearing_id}" for window in test)
    results: dict[str, ViewResult] = {}
    for view in ("full", "aggregate", "forzy"):
        feature_names = _common_features(train_features, test_features, view)
        x_train = _matrix(train_features, view, feature_names)
        x_test = _matrix(test_features, view, feature_names)
        results[view] = ViewResult(
            feature_names=feature_names,
            diagnostic=_diagnose(
                x_train,
                y_train,
                x_test,
                y_test,
                test_bearings,
                labels,
                seed=seed,
                bootstrap_samples=bootstrap_samples,
            ),
            prognostic=_prognose(
                x_train,
                train,
                x_test,
                test,
                seed=seed,
                bootstrap_samples=bootstrap_samples,
            ),
        )
    return AblationReport(
        train_dataset_id=train_dataset_id,
        test_dataset_id=test_dataset_id,
        seed=seed,
        train_bearings=tuple(sorted({window.bearing_id for window in train})),
        test_bearings=tuple(sorted({window.bearing_id for window in test})),
        train_windows=len(train),
        test_windows=len(test),
        label_mapping_version=label_policy.version,
        feature_policy_id=feature_policy.policy_id,
        label_mapping=dict(label_policy.mapping),
        train_coverage=train_coverage,
        test_coverage=test_coverage,
        bootstrap_unit="bearing_id",
        bootstrap_samples=bootstrap_samples,
        views=results,
    )
