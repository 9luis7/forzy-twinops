import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from twinops.contracts.models import TelemetrySample, TwinSnapshot


FIXTURES = Path("contracts/v1/fixtures")


@pytest.mark.parametrize(
    ("fixture_name", "model_type"),
    [
        ("telemetry-live-s1.valid.json", TelemetrySample),
        ("twin-snapshot-live.valid.json", TwinSnapshot),
        ("twin-snapshot-replay.valid.json", TwinSnapshot),
    ],
)
def test_valid_fixture_round_trips_with_schema_aliases(fixture_name, model_type):
    payload = json.loads((FIXTURES / fixture_name).read_text(encoding="utf-8"))

    model = model_type.model_validate(payload)

    assert model.model_dump(mode="json", by_alias=True) == payload


def test_numeric_string_is_rejected():
    payload = json.loads(
        (FIXTURES / "telemetry-string.invalid.json").read_text(encoding="utf-8")
    )

    with pytest.raises(ValidationError):
        TelemetrySample.model_validate(payload)
