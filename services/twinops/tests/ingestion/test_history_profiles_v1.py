from __future__ import annotations

from dataclasses import FrozenInstanceError
from importlib.util import find_spec

import pytest


_PROFILE_MODULE = "twinops.ingestion.history_profiles_v1"
_IMPORT_MODULE = "twinops.ingestion.historical_import_v1"
_IMPORTER_AVAILABLE = find_spec(_PROFILE_MODULE) is not None and find_spec(_IMPORT_MODULE) is not None

if _IMPORTER_AVAILABLE:
    from twinops.ingestion.history_profiles_v1 import (
        HistoryProfileV1,
        registered_profile,
    )


EXPECTED_HEADER_RECORDS = (
    b";1;2;4;5;6;7;8;9\r\n",
    (
        ";PDI;PDI;1.1. Velocidade;1.2. Aceleração;1.3. Temperatura;"
        "2.1. Velocidade;2.2. Aceleração;2.3. Temperatura"
    ).encode("utf-8")
    + b"\r\n",
    b";Byte[];Byte[];Double;Double;Double;Double;Double;Double\r\n",
)

requires_importer = pytest.mark.skipif(
    not _IMPORTER_AVAILABLE,
    reason="registered importer is the intentional Task A3 RED",
)


def test_registered_importer_surface_exists() -> None:
    assert _IMPORTER_AVAILABLE, "RED:A3:registered-importer-missing"


@requires_importer
def test_registered_profile_freezes_the_audited_source_contract() -> None:
    profile = registered_profile("forzy-history-2026-05-19-v1")

    assert profile == HistoryProfileV1(
        profile_id="forzy-history-2026-05-19-v1",
        source_size_bytes=1_096_042,
        source_sha256=(
            "sha256:f09a6613bf6ba3416555a15de6b381bd842474f5f3f33c20660416c7164f0be4"
        ),
        header_records=EXPECTED_HEADER_RECORDS,
        encoding="utf-8",
        delimiter=";",
        newline="CRLF",
        final_crlf_required=True,
        data_record_count=7_183,
        sample_count=14_366,
        operating_cycle_count=204,
        timezone_name="America/Sao_Paulo",
        parser_version="forzy-history-parser-v1",
        contract_version="1.0",
        gap_seconds=15.0,
    )

    with pytest.raises(FrozenInstanceError):
        profile.gap_seconds = 30.0  # type: ignore[misc]


@requires_importer
@pytest.mark.parametrize(
    "profile_id",
    [
        "",
        "forzy-history-2026-05-19",
        "forzy-history-2026-05-19-v2",
        "FORZY-HISTORY-2026-05-19-V1",
    ],
)
def test_profile_registry_has_no_fallback(profile_id: str) -> None:
    with pytest.raises(ValueError, match="unknown history profile"):
        registered_profile(profile_id)


@requires_importer
def test_profile_registry_returns_the_single_immutable_registration() -> None:
    first = registered_profile("forzy-history-2026-05-19-v1")
    second = registered_profile("forzy-history-2026-05-19-v1")

    assert first is second
