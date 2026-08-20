from __future__ import annotations

import random

import pytest

from twinops.research.splits import grouped_splits


@pytest.fixture
def rows() -> list[dict[str, object]]:
    return [
        {"bearing_id": f"bearing-{bearing:02d}", "window": window}
        for bearing in range(12)
        for window in range(3)
    ]


def test_no_bearing_crosses_split(rows) -> None:
    split = grouped_splits(rows, seed=42)

    assert set(split.train_bearings).isdisjoint(split.validation_bearings)
    assert set(split.train_bearings).isdisjoint(split.test_bearings)
    assert set(split.validation_bearings).isdisjoint(split.test_bearings)
    assert len(split.train_indices) + len(split.validation_indices) + len(split.test_indices) == len(rows)


def test_group_split_is_deterministic_after_rows_are_shuffled(rows) -> None:
    expected = grouped_splits(rows, seed=17)
    shuffled = rows.copy()
    random.Random(999).shuffle(shuffled)

    actual = grouped_splits(shuffled, seed=17)

    assert actual.train_bearings == expected.train_bearings
    assert actual.validation_bearings == expected.validation_bearings
    assert actual.test_bearings == expected.test_bearings


def test_group_split_requires_three_distinct_bearings() -> None:
    with pytest.raises(ValueError, match="three distinct"):
        grouped_splits([{"bearing_id": "a"}, {"bearing_id": "b"}])
