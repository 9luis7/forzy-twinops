"""Deterministic train/validation/test allocation by complete bearing."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass(frozen=True, slots=True)
class GroupedSplit:
    train_indices: tuple[int, ...]
    validation_indices: tuple[int, ...]
    test_indices: tuple[int, ...]
    train_bearings: tuple[str, ...]
    validation_bearings: tuple[str, ...]
    test_bearings: tuple[str, ...]
    group_field: str
    seed: int


def _field(row: Any, name: str) -> Any:
    if isinstance(row, Mapping):
        if name not in row:
            raise ValueError(f"row is missing group field {name!r}")
        return row[name]
    if not hasattr(row, name):
        raise ValueError(f"row is missing group field {name!r}")
    return getattr(row, name)


def grouped_splits(
    rows: Sequence[Any], *, group: str = "bearing_id", seed: int = 42
) -> GroupedSplit:
    """Split rows by group identity; never perform a random row split."""

    if not rows:
        raise ValueError("rows must not be empty")
    row_groups: list[str] = []
    for row in rows:
        value = _field(row, group)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{group} must be a non-empty string")
        row_groups.append(value.strip())

    groups = sorted(set(row_groups))
    if len(groups) < 3:
        raise ValueError("grouped split requires at least three distinct bearings")
    shuffled = list(np.random.default_rng(seed).permutation(groups))

    test_count = min(max(1, round(len(groups) * 0.2)), len(groups) - 2)
    remaining = len(groups) - test_count
    validation_count = min(max(1, round(len(groups) * 0.2)), remaining - 1)
    test = set(shuffled[:test_count])
    validation = set(shuffled[test_count : test_count + validation_count])
    train = set(shuffled[test_count + validation_count :])

    def indices(selected: set[str]) -> tuple[int, ...]:
        return tuple(index for index, value in enumerate(row_groups) if value in selected)

    return GroupedSplit(
        train_indices=indices(train),
        validation_indices=indices(validation),
        test_indices=indices(test),
        train_bearings=tuple(sorted(train)),
        validation_bearings=tuple(sorted(validation)),
        test_bearings=tuple(sorted(test)),
        group_field=group,
        seed=seed,
    )
