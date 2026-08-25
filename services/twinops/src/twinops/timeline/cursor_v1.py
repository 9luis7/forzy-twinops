"""Opaque, query- and active-batch-bound timeline cursors."""

from __future__ import annotations

import base64
from dataclasses import replace
from hashlib import sha256
import hmac
from heapq import merge
import json
import re

from twinops.contracts.timeline_v1_models import (
    TimelinePageV1,
    parse_public_utc_millis_v1,
    serialize_public_utc_millis_v1,
)
from twinops.timeline.repository_v1 import (
    TimelineOrderKeyV1,
    TimelineReadQueryV1,
    TimelineReadRepositoryV1,
    timeline_order_key_v1,
)


_CURSOR_DOMAIN = b"twinops-timeline-cursor-v1\0"
_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_BASE64URL_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_CURSOR_KEYS = frozenset({"v", "activeBatchId", "queryFingerprint", "last"})
_MAX_CURSOR_CHARS = 4096
_MAX_PAYLOAD_BYTES = 1024


class TimelineCursorConflict(ValueError):
    """Raised when opaque cursor state cannot be safely reused."""


def _require_sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise TimelineCursorConflict(f"invalid {label}")
    return value


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def timeline_query_fingerprint_v1(query: TimelineReadQueryV1) -> str:
    payload = {
        "assetId": query.asset_id,
        "from": (
            None
            if query.from_at is None
            else serialize_public_utc_millis_v1(query.from_at)
        ),
        "metric": query.metric,
        "order": ["eventAt", "samplePairId", "sensorId", "pointId"],
        "sensorId": query.sensor_id,
        "to": (
            None
            if query.to_at is None
            else serialize_public_utc_millis_v1(query.to_at)
        ),
    }
    return "sha256:" + sha256(_canonical_json_bytes(payload)).hexdigest()


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise TimelineCursorConflict("duplicate cursor key")
        result[key] = value
    return result


class TimelineCursorCodecV1:
    def encode(
        self,
        *,
        active_batch_id: str | None,
        query_fingerprint: str,
        last: TimelineOrderKeyV1,
    ) -> str:
        if active_batch_id is not None:
            _require_sha256(active_batch_id, "active batch ID")
        _require_sha256(query_fingerprint, "query fingerprint")
        payload = _canonical_json_bytes(
            {
                "v": "1",
                "activeBatchId": active_batch_id,
                "queryFingerprint": query_fingerprint,
                "last": [
                    serialize_public_utc_millis_v1(last.event_at),
                    last.sample_pair_id,
                    last.sensor_id,
                    last.point_id,
                ],
            }
        )
        if len(payload) > _MAX_PAYLOAD_BYTES:
            raise TimelineCursorConflict("cursor payload is too large")
        checksum = sha256(_CURSOR_DOMAIN + payload).digest()
        return base64.urlsafe_b64encode(payload + checksum).decode("ascii").rstrip("=")

    def decode(
        self,
        cursor: str,
        *,
        expected_active_batch_id: str | None,
        expected_query_fingerprint: str,
    ) -> TimelineOrderKeyV1:
        if expected_active_batch_id is not None:
            _require_sha256(expected_active_batch_id, "expected active batch ID")
        _require_sha256(expected_query_fingerprint, "expected query fingerprint")
        if (
            type(cursor) is not str
            or not cursor
            or len(cursor) > _MAX_CURSOR_CHARS
            or _BASE64URL_RE.fullmatch(cursor) is None
        ):
            raise TimelineCursorConflict("invalid timeline cursor")
        try:
            raw = base64.b64decode(
                cursor + "=" * (-len(cursor) % 4),
                altchars=b"-_",
                validate=True,
            )
        except (ValueError, base64.binascii.Error) as exc:
            raise TimelineCursorConflict("invalid timeline cursor") from exc
        if (
            len(raw) <= 32
            or len(raw) - 32 > _MAX_PAYLOAD_BYTES
            or base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=") != cursor
        ):
            raise TimelineCursorConflict("invalid timeline cursor")
        payload_bytes, supplied_checksum = raw[:-32], raw[-32:]
        expected_checksum = sha256(_CURSOR_DOMAIN + payload_bytes).digest()
        if not hmac.compare_digest(supplied_checksum, expected_checksum):
            raise TimelineCursorConflict("invalid timeline cursor")
        try:
            payload = json.loads(
                payload_bytes.decode("utf-8"),
                object_pairs_hook=_unique_object,
                parse_constant=lambda value: (_ for _ in ()).throw(
                    ValueError(value)
                ),
            )
        except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
            raise TimelineCursorConflict("invalid timeline cursor") from exc
        if (
            type(payload) is not dict
            or frozenset(payload) != _CURSOR_KEYS
            or payload.get("v") != "1"
            or _canonical_json_bytes(payload) != payload_bytes
        ):
            raise TimelineCursorConflict("invalid timeline cursor")
        active_batch_id = payload["activeBatchId"]
        if active_batch_id is not None:
            _require_sha256(active_batch_id, "cursor active batch ID")
        query_fingerprint = _require_sha256(
            payload["queryFingerprint"], "cursor query fingerprint"
        )
        last = payload["last"]
        if type(last) is not list or len(last) != 4:
            raise TimelineCursorConflict("invalid timeline cursor")
        try:
            order_key = TimelineOrderKeyV1(
                event_at=parse_public_utc_millis_v1(last[0]),
                sample_pair_id=last[1],
                sensor_id=last[2],
                point_id=last[3],
            )
        except (TypeError, ValueError) as exc:
            raise TimelineCursorConflict("invalid timeline cursor") from exc
        if (
            not hmac.compare_digest(query_fingerprint, expected_query_fingerprint)
            or active_batch_id != expected_active_batch_id
        ):
            raise TimelineCursorConflict("timeline cursor state changed")
        return order_key


def _point_matches_query(point, query: TimelineReadQueryV1) -> bool:
    return bool(
        point.asset_id == query.asset_id
        and (query.from_at is None or point.event_at >= query.from_at)
        and (query.to_at is None or point.event_at < query.to_at)
        and (query.sensor_id is None or point.sensor_id == query.sensor_id)
    )


class TimelinePaginatorV1:
    def __init__(
        self,
        repository: TimelineReadRepositoryV1,
        codec: TimelineCursorCodecV1,
    ) -> None:
        self._repository = repository
        self._codec = codec

    def page(
        self,
        query: TimelineReadQueryV1,
        *,
        cursor: str | None,
    ) -> TimelinePageV1:
        if query.after is not None:
            raise ValueError("public timeline pagination owns the exclusive boundary")
        active = self._repository.active_batch(query.asset_id)
        active_batch_id = None if active is None else str(active.batch_id)
        query_fingerprint = timeline_query_fingerprint_v1(query)
        after = None
        if cursor is not None:
            after = self._codec.decode(
                cursor,
                expected_active_batch_id=active_batch_id,
                expected_query_fingerprint=query_fingerprint,
            )
            boundary = self._repository.point_by_id(query.asset_id, after.point_id)
            if (
                boundary is None
                or timeline_order_key_v1(boundary) != after
                or not _point_matches_query(boundary, query)
                or (
                    boundary.source_kind == "historical_archive"
                    and boundary.provenance.batch_id != active_batch_id
                )
            ):
                raise TimelineCursorConflict("timeline cursor boundary is unavailable")
        read_query = replace(query, after=after)
        archive = self._repository.read_archive_points(read_query)
        live = self._repository.read_live_points(read_query)
        merged = list(
            merge(
                archive.points,
                live.points,
                key=timeline_order_key_v1,
            )
        )[: query.limit + 1]
        has_more = len(merged) > query.limit
        items = merged[: query.limit]
        next_cursor = None
        if has_more:
            next_cursor = self._codec.encode(
                active_batch_id=active_batch_id,
                query_fingerprint=query_fingerprint,
                last=timeline_order_key_v1(items[-1]),
            )
        return TimelinePageV1.model_validate(
            {
                "schemaVersion": "1.0",
                "assetId": query.asset_id,
                "queryFingerprint": query_fingerprint,
                "activeHistoricalBatchId": active_batch_id,
                "items": [item.model_dump_public() for item in items],
                "nextCursor": next_cursor,
                "hasMore": has_more,
                "limit": query.limit,
            }
        )
