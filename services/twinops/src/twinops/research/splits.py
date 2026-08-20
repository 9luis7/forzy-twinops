"""Deterministic class-preserving holdout by complete bearing."""

from __future__ import annotations

import hashlib
import math
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import combinations
from typing import Any


@dataclass(frozen=True, slots=True)
class GroupedSplit:
    train_indices: tuple[int, ...]
    test_indices: tuple[int, ...]
    train_bearings: tuple[str, ...]
    test_bearings: tuple[str, ...]
    train_class_counts: Mapping[str, int]
    test_class_counts: Mapping[str, int]
    group_field: str
    label_field: str
    seed: int
    strategy: str
    limitations: tuple[str, ...]


def _field(row: Any, name: str) -> Any:
    if isinstance(row, Mapping):
        if name not in row:
            raise ValueError(f"row is missing field {name!r}")
        return row[name]
    if not hasattr(row, name):
        raise ValueError(f"row is missing field {name!r}")
    return getattr(row, name)


def grouped_splits(
    rows: Sequence[Any],
    *,
    group: str = "bearing_id",
    label: str = "window_state_label",
    seed: int = 42,
    test_fraction: float = 0.25,
) -> GroupedSplit:
    """Find a deterministic bearing holdout retaining every class on both sides."""

    if not rows:
        raise ValueError("rows must not be empty")
    if not 0 < test_fraction < 0.5:
        raise ValueError("test_fraction must be between 0 and 0.5")
    row_groups: list[str] = []
    row_labels: list[str] = []
    labels_by_group: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        group_value = _field(row, group)
        label_value = _field(row, label)
        if not isinstance(group_value, str) or not group_value.strip():
            raise ValueError(f"{group} must be a non-empty string")
        if not isinstance(label_value, str) or not label_value.strip():
            raise ValueError(f"{label} must be a non-empty string")
        group_name = group_value.strip()
        label_name = label_value.strip()
        row_groups.append(group_name)
        row_labels.append(label_name)
        labels_by_group[group_name].add(label_name)

    groups = sorted(labels_by_group)
    all_labels = sorted(set(row_labels))
    if len(groups) < 4:
        raise ValueError("grouped stratification is infeasible with fewer than four bearings")
    for class_name in all_labels:
        bearing_count = sum(class_name in labels for labels in labels_by_group.values())
        if bearing_count < 2:
            raise ValueError(
                f"grouped stratification is infeasible: class {class_name!r} occurs in {bearing_count} bearing"
            )

    test_count = min(max(2, round(len(groups) * test_fraction)), len(groups) - 2)
    candidate_count = math.comb(len(groups), test_count)
    if candidate_count > 1_000_000:
        raise ValueError(
            "exact grouped stratification search exceeds one million holdouts; "
            "use an explicit grouped cross-validation design"
        )

    global_counts = Counter(row_labels)
    global_total = len(row_labels)
    best: tuple[float, bytes, tuple[str, ...]] | None = None
    for raw_candidate in combinations(groups, test_count):
        candidate = tuple(raw_candidate)
        test_groups = set(candidate)
        train_groups = set(groups) - test_groups
        test_labels = [value for value, bearing in zip(row_labels, row_groups, strict=True) if bearing in test_groups]
        train_labels = [value for value, bearing in zip(row_labels, row_groups, strict=True) if bearing in train_groups]
        if set(test_labels) != set(all_labels) or set(train_labels) != set(all_labels):
            continue
        test_counts = Counter(test_labels)
        score = sum(
            abs((test_counts[name] / len(test_labels)) - (global_counts[name] / global_total))
            for name in all_labels
        )
        tie_break = hashlib.sha256(
            "\0".join((str(seed), *candidate)).encode("utf-8")
        ).digest()
        ranked = (score, tie_break, candidate)
        if best is None or ranked < best:
            best = ranked
    if best is None:
        raise ValueError(
            "grouped stratification is infeasible: no bearing holdout preserves every class"
        )

    test_set = set(best[2])
    train_set = set(groups) - test_set
    train_indices = tuple(index for index, value in enumerate(row_groups) if value in train_set)
    test_indices = tuple(index for index, value in enumerate(row_groups) if value in test_set)
    train_counts = Counter(row_labels[index] for index in train_indices)
    test_counts = Counter(row_labels[index] for index in test_indices)
    limitations: list[str] = []
    if any(len(values) > 1 for values in labels_by_group.values()):
        limitations.append("some bearings contain multiple window-state classes")
    return GroupedSplit(
        train_indices=train_indices,
        test_indices=test_indices,
        train_bearings=tuple(sorted(train_set)),
        test_bearings=tuple(sorted(test_set)),
        train_class_counts=dict(sorted(train_counts.items())),
        test_class_counts=dict(sorted(test_counts.items())),
        group_field=group,
        label_field=label,
        seed=seed,
        strategy="grouped_stratified_holdout",
        limitations=tuple(limitations),
    )
