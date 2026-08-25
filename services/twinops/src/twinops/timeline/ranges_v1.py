"""Range resolution for the read-only Timeline v1 overview."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

from twinops.contracts.timeline_v1_models import (
    TimelinePointV1,
    parse_public_utc_millis_v1,
    public_millisecond_successor_v1,
)


@dataclass(frozen=True)
class ResolvedTimelineRangesV1:
    requested_from: datetime | None
    requested_to: datetime | None
    effective_from: datetime | None
    effective_to: datetime | None
    available_from: datetime | None
    available_to: datetime | None

    def __post_init__(self) -> None:
        for value in (
            self.requested_from,
            self.requested_to,
            self.effective_from,
            self.effective_to,
            self.available_from,
            self.available_to,
        ):
            if value is not None:
                parse_public_utc_millis_v1(value)
        if (self.effective_from is None) != (self.effective_to is None):
            raise ValueError("effective timeline range must be wholly null or present")
        if (self.available_from is None) != (self.available_to is None):
            raise ValueError("available timeline range must be wholly null or present")


def _validated_bound(value: datetime | None, label: str) -> datetime | None:
    if value is None:
        return None
    if type(value) is not datetime:
        raise ValueError(f"{label} must be a canonical UTC millisecond")
    return parse_public_utc_millis_v1(value)


def resolve_timeline_ranges_v1(
    points: Sequence[TimelinePointV1],
    *,
    from_at: datetime | None,
    to_at: datetime | None,
) -> ResolvedTimelineRangesV1:
    """Resolve literal requested bounds against all available original points."""

    requested_from = _validated_bound(from_at, "timeline from")
    requested_to = _validated_bound(to_at, "timeline to")
    if (
        requested_from is not None
        and requested_to is not None
        and requested_from >= requested_to
    ):
        raise ValueError("timeline range must be non-empty and increasing")
    if any(not isinstance(point, TimelinePointV1) for point in points):
        raise ValueError("timeline ranges require original TimelinePointV1 values")

    if not points:
        return ResolvedTimelineRangesV1(
            requested_from=requested_from,
            requested_to=requested_to,
            effective_from=None,
            effective_to=None,
            available_from=None,
            available_to=None,
        )

    available_from = min(point.event_at for point in points)
    available_to = public_millisecond_successor_v1(
        max(point.event_at for point in points)
    )
    has_result = any(
        (requested_from is None or point.event_at >= requested_from)
        and (requested_to is None or point.event_at < requested_to)
        for point in points
    )
    return ResolvedTimelineRangesV1(
        requested_from=requested_from,
        requested_to=requested_to,
        effective_from=(
            (requested_from if requested_from is not None else available_from)
            if has_result
            else None
        ),
        effective_to=(
            (requested_to if requested_to is not None else available_to)
            if has_result
            else None
        ),
        available_from=available_from,
        available_to=available_to,
    )


__all__ = [
    "ResolvedTimelineRangesV1",
    "public_millisecond_successor_v1",
    "resolve_timeline_ranges_v1",
]
