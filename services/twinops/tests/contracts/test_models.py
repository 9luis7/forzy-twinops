import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from twinops.contracts.models import CanonicalSensorReading, DigitalTwinSnapshot


FIXTURES = Path("contracts/v1/fixtures")


@pytest.mark.parametrize(
    ("fixture_name", "model_type"),
    [
        ("canonical-sensor-reading-live-s1.valid.json", CanonicalSensorReading),
        ("digital-twin-snapshot-live.valid.json", DigitalTwinSnapshot),
        ("digital-twin-snapshot-replay.valid.json", DigitalTwinSnapshot),
    ],
)
def test_valid_fixture_round_trips_with_schema_aliases(fixture_name, model_type):
    payload = json.loads((FIXTURES / fixture_name).read_text(encoding="utf-8"))

    model = model_type.model_validate(payload)

    assert model.model_dump(mode="json", by_alias=True) == payload


def test_numeric_string_is_rejected():
    payload = json.loads(
        (FIXTURES / "canonical-sensor-reading-string.invalid.json").read_text(encoding="utf-8")
    )

    with pytest.raises(ValidationError):
        CanonicalSensorReading.model_validate(payload)
