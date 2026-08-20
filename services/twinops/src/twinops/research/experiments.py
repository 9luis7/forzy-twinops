"""Small, honest diagnostic/prognostic baselines for cross-bench ablation."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    balanced_accuracy_score,
    confusion_matrix,
    f1_score,
    mean_absolute_error,
    recall_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from twinops.research.contracts import SignalWindow
from twinops.research.features import FeatureViews, extract_views


@dataclass(frozen=True, slots=True)
class ConfidenceInterval:
    low: float
    high: float
    confidence: float
    samples: int


@dataclass(frozen=True, slots=True)
class DiagnosticMetrics:
    macro_f1: float
    balanced_accuracy: float
    per_class_recall: Mapping[str, float]
    confusion_matrix: tuple[tuple[int, ...], ...]
    labels: tuple[str, ...]
    majority_baseline_accuracy: float
    confidence_intervals: Mapping[str, ConfidenceInterval]


@dataclass(frozen=True, slots=True)
class PrognosticMetrics:
    life_fraction_mae: float
    detection_lead_time_fraction: float | None
    lead_time_rule: str


@dataclass(frozen=True, slots=True)
class ViewResult:
    feature_names: tuple[str, ...]
    diagnostic: DiagnosticMetrics
    prognostic: PrognosticMetrics | None


@dataclass(frozen=True, slots=True)
class AblationReport:
    train_dataset_id: str
    test_dataset_id: str
    seed: int
    train_bearings: tuple[str, ...]
    test_bearings: tuple[str, ...]
    train_windows: int
    test_windows: int
    label_mapping: tuple[str, ...]
    bootstrap_unit: str
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


def _common_features(
    train: Sequence[FeatureViews], test: Sequence[FeatureViews], view: str
) -> tuple[str, ...]:
    feature_sets = [set(getattr(features, view)) for features in (*train, *test)]
    common = set.intersection(*feature_sets)
    if not common:
        raise ValueError(f"view {view!r} has no semantically common features across benches")
    return tuple(sorted(common))


def _matrix(features: Sequence[FeatureViews], view: str, names: tuple[str, ...]) -> np.ndarray:
    matrix = np.asarray(
        [[float(getattr(feature_views, view)[name]) for name in names] for feature_views in features],
        dtype=float,
    )
    if not np.isfinite(matrix).all():
        raise ValueError(f"view {view!r} produced non-finite model input")
    return matrix


def _bootstrap_intervals(
    truth: np.ndarray,
    predicted: np.ndarray,
    bearing_ids: Sequence[str],
    labels: tuple[str, ...],
    *,
    seed: int,
    samples: int = 500,
) -> dict[str, ConfidenceInterval]:
    """Bootstrap complete bearings, preserving all windows for each draw."""

    by_bearing: dict[str, list[int]] = defaultdict(list)
    for index, bearing_id in enumerate(bearing_ids):
        by_bearing[bearing_id].append(index)
    bearings = sorted(by_bearing)
    rng = np.random.default_rng(seed)
    macro_f1_values: list[float] = []
    balanced_values: list[float] = []
    for _ in range(samples):
        drawn = rng.choice(bearings, size=len(bearings), replace=True)
        indices = [index for bearing in drawn for index in by_bearing[str(bearing)]]
        sampled_truth = truth[indices]
        sampled_predicted = predicted[indices]
        macro_f1_values.append(
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
        balanced_values.append(
            float(
                np.mean(
                    recall_score(
                        sampled_truth,
                        sampled_predicted,
                        labels=labels,
                        average=None,
                        zero_division=0,
                    )
                )
            )
        )

    def interval(values: list[float]) -> ConfidenceInterval:
        low, high = np.percentile(values, [2.5, 97.5])
        return ConfidenceInterval(low=float(low), high=float(high), confidence=0.95, samples=samples)

    return {
        "macro_f1": interval(macro_f1_values),
        "balanced_accuracy": interval(balanced_values),
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
) -> DiagnosticMetrics:
    model = Pipeline(
        [
            ("scale", StandardScaler()),
            (
                "model",
                LogisticRegression(
                    class_weight="balanced",
                    max_iter=2_000,
                    random_state=seed,
                ),
            ),
        ]
    )
    model.fit(x_train, y_train)
    predicted = model.predict(x_test)
    recalls = recall_score(y_test, predicted, labels=labels, average=None, zero_division=0)
    majority_label = sorted(Counter(y_train).items(), key=lambda item: (-item[1], item[0]))[0][0]
    majority_accuracy = float(np.mean(y_test == majority_label))
    matrix = confusion_matrix(y_test, predicted, labels=labels)
    return DiagnosticMetrics(
        macro_f1=float(f1_score(y_test, predicted, labels=labels, average="macro", zero_division=0)),
        balanced_accuracy=float(balanced_accuracy_score(y_test, predicted)),
        per_class_recall={label: float(value) for label, value in zip(labels, recalls, strict=True)},
        confusion_matrix=tuple(tuple(int(value) for value in row) for row in matrix),
        labels=labels,
        majority_baseline_accuracy=majority_accuracy,
        confidence_intervals=_bootstrap_intervals(
            y_test, predicted, test_bearings, labels, seed=seed
        ),
    )


def _prognose(
    x_train: np.ndarray,
    train_windows: Sequence[SignalWindow],
    x_test: np.ndarray,
    test_windows: Sequence[SignalWindow],
    *,
    seed: int,
) -> PrognosticMetrics | None:
    if not all(window.life_fraction is not None for window in (*train_windows, *test_windows)):
        return None
    y_train = np.asarray([window.life_fraction for window in train_windows], dtype=float)
    y_test = np.asarray([window.life_fraction for window in test_windows], dtype=float)
    model = HistGradientBoostingRegressor(random_state=seed)
    model.fit(x_train, y_train)
    predicted = np.clip(model.predict(x_test), 0.0, 1.0)

    lead_times: list[float] = []
    by_bearing: dict[str, list[int]] = defaultdict(list)
    for index, window in enumerate(test_windows):
        by_bearing[window.bearing_id].append(index)
    for indices in by_bearing.values():
        ordered = sorted(
            indices,
            key=lambda index: (
                test_windows[index].started_at.isoformat()
                if test_windows[index].started_at is not None
                else "",
                test_windows[index].run_id,
            ),
        )
        detected = next((index for index in ordered if predicted[index] >= 0.8), None)
        if detected is not None:
            lead_times.append(1.0 - y_test[detected])

    return PrognosticMetrics(
        life_fraction_mae=float(mean_absolute_error(y_test, predicted)),
        detection_lead_time_fraction=float(np.mean(lead_times)) if lead_times else None,
        lead_time_rule=(
            "Per bearing, first window with predicted life_fraction >= 0.8; "
            "lead time is 1 - true life_fraction at that window."
        ),
    )


def run_ablation(
    train_dataset: Sequence[SignalWindow],
    test_dataset: Sequence[SignalWindow],
    *,
    seed: int = 42,
) -> AblationReport:
    """Train on one bench and evaluate three feature views on another bench."""

    train_all = tuple(train_dataset)
    test_all = tuple(test_dataset)
    train_dataset_id = _one_dataset(train_all, role="train")
    test_dataset_id = _one_dataset(test_all, role="test")
    train_bearing_names = {window.bearing_id for window in train_all}
    test_bearing_names = {window.bearing_id for window in test_all}
    if train_dataset_id == test_dataset_id and train_bearing_names & test_bearing_names:
        overlap = sorted(train_bearing_names & test_bearing_names)
        raise ValueError(f"bearing overlap between train and test: {overlap}")

    shared_labels = tuple(
        sorted(
            ({window.fault_label for window in train_all} & {window.fault_label for window in test_all})
            - {"unknown"}
        )
    )
    if len(shared_labels) < 2:
        raise ValueError("cross-bench evaluation requires at least two mappable labels")
    train = tuple(window for window in train_all if window.fault_label in shared_labels)
    test = tuple(window for window in test_all if window.fault_label in shared_labels)
    if len({window.fault_label for window in train}) < 2:
        raise ValueError("training data must retain at least two mappable labels")

    train_features = tuple(extract_views(window) for window in train)
    test_features = tuple(extract_views(window) for window in test)
    y_train = np.asarray([window.fault_label for window in train])
    y_test = np.asarray([window.fault_label for window in test])
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
                shared_labels,
                seed=seed,
            ),
            prognostic=_prognose(x_train, train, x_test, test, seed=seed),
        )

    return AblationReport(
        train_dataset_id=train_dataset_id,
        test_dataset_id=test_dataset_id,
        seed=seed,
        train_bearings=tuple(sorted(train_bearing_names)),
        test_bearings=tuple(sorted(test_bearing_names)),
        train_windows=len(train),
        test_windows=len(test),
        label_mapping=shared_labels,
        bootstrap_unit="bearing_id",
        views=results,
    )
