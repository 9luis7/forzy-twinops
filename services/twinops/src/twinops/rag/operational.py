"""Trusted operational context projected only from a server-built v2 snapshot."""

from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from math import isfinite
from statistics import mean, median

from twinops.contracts.v2_models import DigitalTwinSnapshotV2


@dataclass(frozen=True)
class OperationalEvidence:
    evidence_id: str
    feature: str
    value: float
    unit: str
    window_seconds: float | None
    baseline: float | None = None
    deviation: float | None = None
    direction: str | None = None
    robust_scale: float | None = None
    normalized_distance: float | None = None
    anomaly_score_component: float | None = None
    positive_score_component: float | None = None

    @classmethod
    def from_evidence(cls, item):
        return cls(evidence_id=item.id, feature=item.feature, value=item.value,
                   unit=item.unit, window_seconds=item.window_seconds,
                   **{name: getattr(item, name, None) for name in (
                       "baseline", "deviation", "direction", "robust_scale", "normalized_distance",
                       "anomaly_score_component", "positive_score_component")})


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
    analysis_context: dict | None = None

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
                OperationalEvidence.from_evidence(item)
                for item in assessment.evidence
            ),
            quality_flags=tuple(assessment.quality.flags),
            analysis_context={
                "mode": "live", "assetId": snapshot.asset.asset_id,
                "origin": {"observedAt": assessment.window.end},
                "sensors": {assessment.sensor_id: {"assessment": assessment.model_dump(mode="json", by_alias=True)}},
            },
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

    def to_prompt_context(self) -> dict:
        """Detached essential context; expanded rows stay private until tool use."""
        if self.analysis_context is not None:
            return deepcopy({key: value for key, value in self.analysis_context.items()
                             if key != "historyRows"})
        return {
            "mode": self.operational_state, "assessmentId": self.assessment_id,
            "assessmentStatus": self.assessment_status, "qualityStatus": self.quality_status,
            "qualityFlags": list(self.quality_flags),
            "origin": {"observedAt": self.window_end.isoformat() if self.window_end else None},
            "evidence": [asdict(item) for item in self.evidence],
        }


def build_analysis_context(context: dict) -> dict:
    """Project trusted replay/history data, never events, raw payloads or secrets.

    Both source row and source time bound every row, including timestamp ties.
    Summaries describe the available historical coverage, not fabricated scores.
    """
    mode = context["mode"]
    selection = context.get("replay", {}) if mode == "replay" else context.get("selection", {})
    cutoff = selection.get("sourceTime") if mode == "replay" else selection.get("observedAt")
    end_row = selection.get("sourceRow") if mode == "replay" else selection.get("endRow")
    origin = {"datasetId": context.get("dataset", {}).get("datasetId"),
              "observedAt": cutoff, "sourceRow": end_row,
              "retrospective": True, "originalReceiptTimeKnown": False}
    if mode == "replay":
        origin.update(runId=selection.get("runId"), generation=selection.get("generation"))
    rows = []
    if cutoff is not None and end_row is not None:
        for row in context.get("history", []):
            if (row.get("sensorId") in ("s1", "s2") and row.get("observedAt")
                    and row.get("sourceRow", end_row + 1) <= end_row
                    and _timestamp(row["observedAt"]) <= _timestamp(cutoff)):
                rows.append({key: deepcopy(row[key]) for key in (
                    "sensorId", "sourceRow", "observedAt", "measurements", "qualityFlags", "gapBefore"
                ) if key in row})
    rows.sort(key=lambda row: (row["sourceRow"], row["sensorId"]))
    rows = rows[-600:]
    sensors = {}
    for sensor_id, component in (("s1", "motor WEG W22"), ("s2", "bomba")):
        source = context["sensors"][sensor_id]
        latest = source.get("latest") if cutoff is not None else None
        if latest and cutoff and (latest.get("sensorId") != sensor_id
                or latest["sourceRow"] > end_row or _timestamp(latest["observedAt"]) > _timestamp(cutoff)):
            raise ValueError("sensor latest exceeds analysis cutoff")
        assessment = source.get("assessment") if cutoff is not None else None
        if assessment:
            if assessment.get("sensorId") != sensor_id:
                raise ValueError("analysis assessment sensor mismatch")
            if cutoff and _timestamp(assessment["window"]["end"]) > _timestamp(cutoff):
                raise ValueError("future analysis assessment exceeds cutoff")
        sensor_rows = [row for row in rows if row["sensorId"] == sensor_id]
        calculation = (assessment or {}).get("assessment", {}).get("scoreCalculation") or {}
        sensors[sensor_id] = {
            "component": component, "positionAssumed": True,
            "manualCoverage": sensor_id == "s1",
            "latest": ({key: deepcopy(latest[key]) for key in (
                "sensorId", "sourceRow", "observedAt", "measurements", "qualityFlags", "gapBefore"
            ) if key in latest} if latest else None),
            "assessment": deepcopy(assessment), "assessmentState": source.get("assessmentState"),
            "lastFive": sensor_rows[-5:], "availableHistoryRows": len(sensor_rows),
            "windows": {"short": _window_summary(sensor_rows, cutoff, calculation.get("shortWindowSeconds", 10)),
                        "long": _window_summary(sensor_rows, cutoff, calculation.get("longWindowSeconds", 60))},
            "scoreHistoryAvailable": False,
        }
    return {"mode": mode, "assetId": context["assetId"], "revision": context["revision"],
            "origin": origin, "sensors": sensors, "historyRows": rows,
            "mlSemantics": {
                "score": "relative_to_historical_baseline_not_failure_probability",
                "anomaly": "maximum absolute normalized feature distance, clipped to 0..100; components are not summed",
                "deterioration": "EWMA of maximum positive normalized distance; exact operands in scoreCalculation when available",
                "accelerationIncludedInScore": False,
                "trend": "Measurement summaries are retrospective, not a sequence of prior ML scores. Repeated values are not independent trend evidence.",
            }}


def _window_summary(rows, cutoff, seconds):
    if not cutoff:
        return {"seconds": seconds, "count": 0, "coverageComplete": False}
    lower = _timestamp(cutoff) - timedelta(seconds=seconds)
    window = [row for row in rows if _timestamp(row["observedAt"]) >= lower]
    independent = [row for row in window if "duplicate_payload" not in row.get("qualityFlags", [])]
    gaps = sum(bool(row.get("gapBefore")) for row in window)
    summary = {"seconds": seconds, "count": len(window), "newInformationCount": len(independent),
               "repeatedCount": len(window) - len(independent), "gapCount": gaps,
               "coverageComplete": bool(rows and _timestamp(rows[0]["observedAt"]) <= lower and not gaps),
               "firstObservedAt": window[0]["observedAt"] if window else None,
               "lastObservedAt": window[-1]["observedAt"] if window else None,
               "measurements": {}}
    for name in ("vibrationVelocityRms", "vibrationAcceleration", "temperature"):
        metrics = [row.get("measurements", {}).get(name) for row in window]
        metrics = [metric for metric in metrics if isinstance(metric, dict)
                   and isinstance(metric.get("value"), (int, float))
                   and not isinstance(metric["value"], bool) and isfinite(metric["value"])]
        values = [metric["value"] for metric in metrics]
        if values:
            summary["measurements"][name] = {
                "unit": metrics[0].get("unit"),
                "min": min(values), "max": max(values), "mean": mean(values), "median": median(values),
                "first": values[0], "last": values[-1], "change": values[-1] - values[0],
            }
    return summary


def _timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
