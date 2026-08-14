"""Public projections from v2 audit readings to consumer-safe frames."""

from twinops.contracts.v2_models import (
    CanonicalSensorReadingV2,
    SensorTelemetryFrameV2,
)


def to_sensor_telemetry_frame_v2(
    reading: CanonicalSensorReadingV2,
) -> SensorTelemetryFrameV2:
    """Project only the public telemetry frame fields from a v2 reading."""

    return SensorTelemetryFrameV2.model_validate(
        {
            "schemaVersion": reading.schema_version,
            "frameId": reading.reading_id,
            "assetId": reading.asset_id,
            "sensorId": reading.sensor_id,
            "observedAt": reading.observed_at,
            "receivedAt": reading.received_at,
            "timestampQuality": reading.timestamp_quality,
            "measurements": reading.measurements.model_dump(
                mode="json", by_alias=True
            ),
            "qualityFlags": list(reading.quality_flags),
        }
    )
