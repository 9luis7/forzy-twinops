"""Public projections from audit contracts to consumer-safe contracts."""

from twinops.contracts.models import CanonicalSensorReading, SensorTelemetryFrame


def to_sensor_telemetry_frame(
    reading: CanonicalSensorReading,
) -> SensorTelemetryFrame:
    """Project an auditable reading without raw payload, hashes, or provenance."""

    return SensorTelemetryFrame.model_validate(
        {
            "schemaVersion": reading.schema_version,
            "frameId": reading.reading_id,
            "assetTag": reading.asset_tag,
            "sensorId": reading.sensor_id,
            "sourceMode": "live" if reading.source == "forzy-live" else "historical",
            "observedAt": reading.observed_at,
            "receivedAt": reading.received_at,
            "timestampQuality": "source" if reading.observed_at is not None else "collector",
            "measurements": reading.measurements.model_dump(mode="json", by_alias=True),
            "qualityFlags": list(reading.quality_flags),
        }
    )
