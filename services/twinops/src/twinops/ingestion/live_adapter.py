"""Pure adapter from Forzy live payloads to the canonical audit contract."""

from datetime import datetime, timezone
import hashlib
import json
import math
from typing import Literal, Mapping
import uuid

from pydantic import ValidationError

from twinops.contracts.models import CanonicalSensorReading


class InvalidSensorPayload(ValueError):
    def __init__(self, sensor_id: str, reason: str):
        super().__init__(f"invalid payload for {sensor_id}: {reason}")
        self.sensor_id = sensor_id
        self.reason = reason


def _number(data: Mapping[str, object], key: str, sensor_id: str) -> float:
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InvalidSensorPayload(sensor_id, f"{key} must be a finite number")
    try:
        number = float(value)
    except (OverflowError, ValueError):
        raise InvalidSensorPayload(
            sensor_id, f"{key} must be a finite number"
        ) from None
    if not math.isfinite(number):
        raise InvalidSensorPayload(sensor_id, f"{key} must be a finite number")
    return number


def _utc(value: datetime, field: str) -> str:
    if value.tzinfo is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def adapt_live_payload(
    *,
    sensor_id: Literal["s1", "s2"],
    payload: Mapping[str, object],
    scheduled_at: datetime,
    received_at: datetime,
    asset_tag: str,
) -> CanonicalSensorReading:
    root = f"dados{sensor_id[-1]}"
    values = payload.get(root)
    if not isinstance(values, Mapping):
        raise InvalidSensorPayload(sensor_id, f"{root} must be an object")
    scheduled = _utc(scheduled_at, "scheduled_at")
    received = _utc(received_at, "received_at")
    velocity = _number(values, "Velocidade", sensor_id)
    acceleration = _number(values, "Aceleração", sensor_id)
    temperature = _number(values, "Temperatura", sensor_id)
    raw = dict(payload)
    canonical_raw = json.dumps(
        raw, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    try:
        return CanonicalSensorReading.model_validate(
            {
            "schemaVersion": "1.0",
            "readingId": str(uuid.uuid4()),
            "source": "forzy-live",
            "assetTag": asset_tag,
            "sensorId": sensor_id,
            "scheduledAt": scheduled,
            "observedAt": None,
            "receivedAt": received,
            "measurements": {
                "vibrationVelocityRms": {
                    "value": velocity,
                    "unit": "mm/s",
                    "semanticConfidence": "inferred_from_datasheet",
                },
                "vibrationAcceleration": {
                    "value": acceleration,
                    "unit": "g",
                    "statistic": "unknown",
                    "semanticConfidence": "unconfirmed",
                },
                "temperature": {
                    "value": temperature,
                    "unit": "degC",
                    "semanticConfidence": "inferred_from_datasheet",
                },
            },
            "qualityFlags": [],
            "payloadHash": f"sha256:{hashlib.sha256(canonical_raw).hexdigest()}",
            "raw": raw,
            "provenance": {"sourceSystem": "forzy-api", "ingestedAt": received},
            }
        )
    except ValidationError as exc:
        raise InvalidSensorPayload(
            sensor_id, "contract validation failed"
        ) from exc
