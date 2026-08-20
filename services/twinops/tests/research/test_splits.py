from __future__ import annotations

import random

import pytest

from twinops.research.splits import grouped_splits


@pytest.fixture
def rows() -> list[dict[str, object]]:
    return [
        {
            "bearing_id": f"bearing-{label}-{bearing:02d}",
            "window_state_label": label,
            "window": window,
        }
        for label in ("normal", "outer_race")
        for bearing in range(6)
        for window in range(3)
    ]


def test_grouped_stratified_holdout_has_no_leakage_and_preserves_classes(rows) -> None:
    split = grouped_splits(rows, seed=42)

    assert set(split.train_bearings).isdisjoint(split.test_bearings)
    assert len(split.train_indices) + len(split.test_indices) == len(rows)
    assert set(split.train_class_counts) == {"normal", "outer_race"}
    assert set(split.test_class_counts) == {"normal", "outer_race"}
    assert split.strategy == "grouped_stratified_holdout"
    assert not hasattr(split, "validation_indices")


def test_group_split_is_deterministic_after_rows_are_shuffled(rows) -> None:
    expected = grouped_splits(rows, seed=17)
    shuffled = rows.copy()
    random.Random(999).shuffle(shuffled)

    actual = grouped_splits(shuffled, seed=17)

    assert actual.train_bearings == expected.train_bearings
    assert actual.test_bearings == expected.test_bearings


def test_group_split_reports_when_class_preserving_holdout_is_infeasible() -> None:
    rows = [
        {"bearing_id": "normal-a", "window_state_label": "normal"},
        {"bearing_id": "normal-b", "window_state_label": "normal"},
        {"bearing_id": "normal-c", "window_state_label": "normal"},
        {"bearing_id": "only-fault", "window_state_label": "outer_race"},
    ]

    with pytest.raises(ValueError, match="infeasible"):
        grouped_splits(rows, seed=42)
