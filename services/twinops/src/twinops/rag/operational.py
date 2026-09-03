"""Trusted operational context projected only from a server-built v2 snapshot."""

from dataclasses import dataclass
from datetime import datetime

from twinops.contracts.v2_models import DigitalTwinSnapshotV2


@dataclass(frozen=True)
class OperationalEvidence:
    evidence_id: str
    feature: str
    value: float
    unit: str
    window_seconds: float | None


@dataclass(frozen=True)
class TrustedOperationalContext:
    operational_state: str
    assessment_id: str | None
    assessment_status: str | None
    quality_status: str | None
    window_start: datetime | None
    window_end: datetime | None
    received_at: datetime | None
    freshness_ms: float | None
    evidence: tuple[OperationalEvidence, ...]
    quality_flags: tuple[str, ...] = ()

    @classmethod
    def from_snapshot(cls, snapshot: DigitalTwinSnapshotV2) -> "TrustedOperationalContext":
        assessment = snapshot.assessment
        if assessment is None:
            return cls.unavailable(operational_state=snapshot.operational_state)
        return cls(
            operational_state=snapshot.operational_state,
            assessment_id=assessment.assessment_id,
            assessment_status=assessment.assessment.status,
            quality_status=assessment.quality.status,
            window_start=_timestamp(assessment.window.start),
            window_end=_timestamp(assessment.window.end),
            received_at=_timestamp(assessment.window.received_at),
            freshness_ms=assessment.window.freshness_ms,
            evidence=tuple(
                OperationalEvidence(
                    evidence_id=item.id,
                    feature=item.feature,
                    value=item.value,
                    unit=item.unit,
                    window_seconds=item.window_seconds,
                )
                for item in assessment.evidence
            ),
            quality_flags=tuple(assessment.quality.flags),
        )

    @classmethod
    def unavailable(cls, *, operational_state: str) -> "TrustedOperationalContext":
        return cls(
            operational_state=operational_state,
            assessment_id=None,
            assessment_status=None,
            quality_status=None,
            window_start=None,
            window_end=None,
            received_at=None,
            freshness_ms=None,
            evidence=(),
            quality_flags=(),
        )

    @property
    def available(self) -> bool:
        return self.assessment_id is not None

    @property
    def stale(self) -> bool:
        return "stale_window" in self.quality_flags

    @property
    def outside_window(self) -> bool:
        return self.operational_state == "expected_idle"


def _timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
