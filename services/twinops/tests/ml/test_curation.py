from twinops.ml.curation import curate_samples


def test_gap_closes_cycle_and_resets_operating_state(sample_factory):
    samples = [
        sample_factory(second=0, velocity=0.01),
        sample_factory(second=2, velocity=0.20),
        sample_factory(second=120, velocity=0.01),
    ]

    frame = curate_samples(samples, gap_seconds=10)

    assert frame["cycle_id"].tolist() == [0, 0, 1]
    assert "gap_before" in frame.iloc[2].quality_flags
    assert frame["operating_state"].tolist() == ["stopped", "startup", "stopped"]
    assert frame.iloc[2].is_new_information


def test_duplicate_payload_is_flagged_not_counted_as_new_information(sample_factory):
    frame = curate_samples(
        [
            sample_factory(second=0, payload_hash="same"),
            sample_factory(second=5, payload_hash="same"),
        ],
        gap_seconds=10,
    )

    assert "duplicate_payload" in frame.iloc[1].quality_flags
    assert frame["is_new_information"].tolist() == [True, False]


def test_non_consecutive_payload_recurrence_is_preserved_as_new_information(sample_factory):
    frame = curate_samples(
        [
            sample_factory(second=0, velocity=0.1, payload_hash="payload-a"),
            sample_factory(second=1, velocity=0.2, payload_hash="payload-b"),
            sample_factory(second=2, velocity=0.1, payload_hash="payload-a"),
        ],
        gap_seconds=10,
    )

    assert frame["is_new_information"].tolist() == [True, True, True]
    assert all("duplicate_payload" not in flags for flags in frame["quality_flags"])


def test_identical_measurement_is_duplicate_even_with_unique_row_identity(sample_factory):
    frame = curate_samples(
        [
            sample_factory(second=0, velocity=0.1, payload_hash="row-a"),
            sample_factory(second=1, velocity=0.1, payload_hash="row-b"),
        ],
        gap_seconds=10,
    )

    assert frame["is_new_information"].tolist() == [True, False]
    assert "duplicate_payload" in frame.iloc[1].quality_flags


def test_samples_are_sorted_without_interpolating_missing_slots(sample_factory):
    frame = curate_samples(
        [sample_factory(second=4), sample_factory(second=0), sample_factory(second=2)],
        gap_seconds=10,
    )

    assert frame["received_at"].dt.second.tolist() == [0, 2, 4]
    assert len(frame) == 3
    assert frame["cadence_seconds"].tolist()[1:] == [2.0, 2.0]


def test_existing_quality_flags_and_sensor_identity_are_preserved(sample_factory):
    frame = curate_samples(
        [sample_factory(second=0, sensor_id="s2", quality_flags=["stale_source"])],
        gap_seconds=10,
    )

    assert frame.iloc[0].sensor_id == "s2"
    assert frame.iloc[0].quality_flags == ("stale_source",)
