"""Pure adapter from Forzy live payloads to the version 2 audit contract."""

from datetime import datetime, timezone
import hashlib
import json
import math
from typing import Literal, Mapping
import uuid

from pydantic import ValidationError

from twinops.contracts.v2_models import CanonicalSensorReadingV2


class InvalidSensorPayloadV2(ValueError):
    def __init__(self, sensor_id: str, reason: str):
        super().__init__(f"invalid payload for {sensor_id}: {reason}")
        self.sensor_id = sensor_id
        self.reason = reason


def _number(data: Mapping[str, object], key: str, sensor_id: str) -> float:
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InvalidSensorPayloadV2(sensor_id, f"{key} must be a finite number")
    try:
        number = float(value)
    except (OverflowError, ValueError):
        raise InvalidSensorPayloadV2(
            sensor_id, f"{key} must be a finite number"
        ) from None
    if not math.isfinite(number):
        raise InvalidSensorPayloadV2(sensor_id, f"{key} must be a finite number")
    return number


def _utc(value: datetime, field: str) -> str:
    if value.tzinfo is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical_upstream_payload(payload: Mapping[str, object], sensor_id: str) -> bytes:
    try:
        return json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError):
        raise InvalidSensorPayloadV2(
            sensor_id, "payload must be canonical JSON"
        ) from None


def adapt_live_payload_v2(
    *,
    sensor_id: Literal["s1", "s2"],
    payload: Mapping[str, object],
    scheduled_at: datetime,
    received_at: datetime,
    asset_id: str = "forzy-motor-01",
) -> CanonicalSensorReadingV2:
    root = f"dados{sensor_id[-1]}"
    values = payload.get(root)
    if not isinstance(values, Mapping):
        raise InvalidSensorPayloadV2(sensor_id, f"{root} must be an object")

    scheduled = _utc(scheduled_at, "scheduled_at")
    received = _utc(received_at, "received_at")
    velocity = _number(values, "Velocidade", sensor_id)
    acceleration = _number(values, "Acelera\u00e7\u00e3o", sensor_id)
    temperature = _number(values, "Temperatura", sensor_id)
    payload_hash = hashlib.sha256(
        _canonical_upstream_payload(payload, sensor_id)
    ).hexdigest()

    try:
        return CanonicalSensorReadingV2.model_validate(
            {
                "schemaVersion": "2.0",
                "readingId": str(uuid.uuid4()),
                "source": "forzy-live",
                "assetId": asset_id,
                "sensorId": sensor_id,
                "scheduledAt": scheduled,
                "observedAt": received,
                "receivedAt": received,
                "timestampQuality": "assumed_from_retrieval",
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
                "payloadHash": f"sha256:{payload_hash}",
                "raw": {},
                "provenance": {
                    "sourceSystem": "forzy-api",
                    "ingestedAt": received,
                    "sourceTimestampProvided": False,
                },
            }
        )
    except ValidationError as exc:
        raise InvalidSensorPayloadV2(
            sensor_id, "contract validation failed"
        ) from exc
