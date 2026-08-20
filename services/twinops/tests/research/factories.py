from __future__ import annotations

from collections.abc import Mapping

import numpy as np

from twinops.research.contracts import SignalWindow


def make_window(
    *,
    dataset_id: str = "synthetic-a",
    bearing_id: str = "bearing-1",
    run_id: str = "run-1",
    sequence_index: int = 0,
    axes: Mapping[str, np.ndarray] | None = None,
    window_state_label: str = "normal",
    terminal_failure_mode: str | None = None,
    life_fraction: float | None = None,
    temperature_c: float | None = None,
) -> SignalWindow:
    return SignalWindow(
        dataset_id=dataset_id,
        bearing_id=bearing_id,
        run_id=run_id,
        sampling_hz=1_024,
        acceleration=axes or {"radial": np.array([0.1, -0.1, 0.2, -0.2])},
        acceleration_unit="g",
        window_state_label=window_state_label,
        terminal_failure_mode=terminal_failure_mode,
        sequence_index=sequence_index,
        started_at=None,
        timestamp_quality="unavailable",
        source_relative_path=f"raw/{bearing_id}/{run_id}.csv",
        metadata_sha256="a" * 64,
        life_fraction=life_fraction,
        temperature_c=temperature_c,
    )
