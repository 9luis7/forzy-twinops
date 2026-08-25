"""Focused cursor codec behavior."""

import base64
from dataclasses import replace
from datetime import datetime, timezone
from hashlib import sha256
import json

import pytest

from twinops.timeline.cursor_v1 import (
    TimelineCursorCodecV1,
    TimelineCursorConflict,
    timeline_query_fingerprint_v1,
)
from twinops.timeline.repository_v1 import TimelineOrderKeyV1, TimelineReadQueryV1


_BATCH = "sha256:" + "a" * 64
_OTHER_BATCH = "sha256:" + "b" * 64
_CURSOR_DOMAIN = b"twinops-timeline-cursor-v1\0"


def _query(**changes) -> TimelineReadQueryV1:
    query = TimelineReadQueryV1(
        asset_id="forzy-motor-01",
        from_at=datetime(2026, 8, 12, 15, tzinfo=timezone.utc),
        to_at=datetime(2026, 8, 12, 16, tzinfo=timezone.utc),
        sensor_id="s1",
        metric="vibrationVelocityRms",
        limit=200,
    )
    return replace(query, **changes)


def _last() -> TimelineOrderKeyV1:
    return TimelineOrderKeyV1(
        event_at=datetime(2026, 8, 12, 15, tzinfo=timezone.utc),
        sample_pair_id="00000000-0000-5000-8000-000000000001",
        sensor_id="s1",
        point_id="00000000-0000-5000-8000-000000000002",
    )


def _signed_cursor(payload: bytes) -> str:
    checksum = sha256(_CURSOR_DOMAIN + payload).digest()
    return base64.urlsafe_b64encode(payload + checksum).decode("ascii").rstrip("=")


def test_cursor_is_canonical_url_safe_and_bound_to_filters_and_batch() -> None:
    codec = TimelineCursorCodecV1()
    query = _query()
    fingerprint = timeline_query_fingerprint_v1(query)

    cursor = codec.encode(
        active_batch_id=_BATCH,
        query_fingerprint=fingerprint,
        last=_last(),
    )
    decoded = codec.decode(
        cursor,
        expected_active_batch_id=_BATCH,
        expected_query_fingerprint=fingerprint,
    )

    assert decoded == _last()
    assert "=" not in cursor
    raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
    payload = json.loads(raw[:-32])
    assert payload == {
        "v": "1",
        "activeBatchId": _BATCH,
        "queryFingerprint": fingerprint,
        "last": [
            "2026-08-12T15:00:00.000Z",
            "00000000-0000-5000-8000-000000000001",
            "s1",
            "00000000-0000-5000-8000-000000000002",
        ],
    }
    assert timeline_query_fingerprint_v1(_query(limit=500)) == fingerprint
    assert timeline_query_fingerprint_v1(_query(sensor_id=None)) != fingerprint

    for expected_batch, expected_fingerprint in (
        (_OTHER_BATCH, fingerprint),
        (_BATCH, "sha256:" + "c" * 64),
    ):
        with pytest.raises(TimelineCursorConflict):
            codec.decode(
                cursor,
                expected_active_batch_id=expected_batch,
                expected_query_fingerprint=expected_fingerprint,
            )


def test_cursor_rejects_corruption_noncanonical_payloads_and_oversize() -> None:
    codec = TimelineCursorCodecV1()
    fingerprint = timeline_query_fingerprint_v1(_query())
    cursor = codec.encode(
        active_batch_id=None,
        query_fingerprint=fingerprint,
        last=_last(),
    )

    corrupt = cursor[:-1] + ("A" if cursor[-1] != "A" else "B")
    raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
    payload = json.loads(raw[:-32])
    noncanonical = _signed_cursor(json.dumps(payload).encode("utf-8"))
    payload["unexpected"] = True
    extra_key = _signed_cursor(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    for candidate in (
        corrupt,
        cursor + "=",
        "x" * 4097,
        "***",
        noncanonical,
        extra_key,
    ):
        with pytest.raises(TimelineCursorConflict):
            codec.decode(
                candidate,
                expected_active_batch_id=None,
                expected_query_fingerprint=fingerprint,
            )


def test_cursor_translates_non_finite_json_numbers_to_domain_conflict() -> None:
    codec = TimelineCursorCodecV1()
    fingerprint = timeline_query_fingerprint_v1(_query())

    for number_token in ("1e999", "NaN", "Infinity", "-Infinity"):
        payload = (
            '{"activeBatchId":null,"last":['
            f'{number_token},"00000000-0000-5000-8000-000000000001",'
            '"s1","00000000-0000-5000-8000-000000000002"],'
            f'"queryFingerprint":"{fingerprint}","v":"1"}}'
        ).encode("utf-8")

        with pytest.raises(TimelineCursorConflict):
            codec.decode(
                _signed_cursor(payload),
                expected_active_batch_id=None,
                expected_query_fingerprint=fingerprint,
            )
