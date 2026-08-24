"""Versioned collection-policy persistence with fail-closed reads."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import sqlite3

from twinops.contracts.timeline_v1_models import (
    CollectionPolicyV1,
    serialize_public_utc_millis_v1,
)


INITIAL_COLLECTION_POLICY_ID = "forzy-live-window-v1"
INITIAL_COLLECTION_POLICY_CONFIGURATION_HASH = (
    "sha256:89bde17193c7a34c80d48828f4e61fc5802caa92169d83f8a9fd8e4c282b1bce"
)
_POLICY_COLUMNS = (
    "schema_version",
    "policy_id",
    "asset_id",
    "timezone_name",
    "active_weekdays_json",
    "window_start_local",
    "window_end_local",
    "poll_interval_seconds",
    "gap_threshold_seconds",
    "effective_from",
    "effective_to",
    "configuration_hash",
)
_POLICY_SELECT = ",".join(_POLICY_COLUMNS)


@dataclass(frozen=True)
class CollectionPolicySeedResultV1:
    policy: CollectionPolicyV1
    inserted: bool
    writes_performed: int


def _is_sqlite(connection) -> bool:
    return isinstance(connection, sqlite3.Connection)


def _placeholder(connection) -> str:
    return "?" if _is_sqlite(connection) else "%s"


def _row_mapping(row) -> dict[str, object]:
    if isinstance(row, Mapping):
        return {column: row[column] for column in _POLICY_COLUMNS}
    if hasattr(row, "keys"):
        return {column: row[column] for column in _POLICY_COLUMNS}
    return dict(zip(_POLICY_COLUMNS, row, strict=True))


def _stored_timestamp(value: object) -> object:
    if isinstance(value, datetime):
        return serialize_public_utc_millis_v1(value)
    return value


def _policy_from_row(row) -> CollectionPolicyV1:
    stored = _row_mapping(row)
    weekdays_text = stored["active_weekdays_json"]
    if not isinstance(weekdays_text, str):
        raise ValueError("stored collection policy weekdays are not text")
    try:
        weekdays = json.loads(weekdays_text)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("stored collection policy weekdays are invalid") from exc
    canonical_weekdays = json.dumps(weekdays, separators=(",", ":"))
    if canonical_weekdays != weekdays_text:
        raise ValueError("stored collection policy weekdays are not canonical")
    payload = {
        "schemaVersion": stored["schema_version"],
        "collectionPolicyId": stored["policy_id"],
        "assetId": stored["asset_id"],
        "timezone": stored["timezone_name"],
        "activeWeekdays": weekdays,
        "windowStartLocal": stored["window_start_local"],
        "windowEndLocal": stored["window_end_local"],
        "pollIntervalSeconds": stored["poll_interval_seconds"],
        "gapThresholdSeconds": stored["gap_threshold_seconds"],
        "effectiveFrom": _stored_timestamp(stored["effective_from"]),
        "effectiveTo": _stored_timestamp(stored["effective_to"]),
        "configurationHash": stored["configuration_hash"],
    }
    try:
        return CollectionPolicyV1.model_validate(payload)
    except Exception as exc:
        raise ValueError("stored collection policy failed closed validation") from exc


def initial_collection_policy(effective_from: datetime) -> CollectionPolicyV1:
    effective_text = serialize_public_utc_millis_v1(effective_from)
    return CollectionPolicyV1.model_validate(
        {
            "schemaVersion": "1.0",
            "collectionPolicyId": INITIAL_COLLECTION_POLICY_ID,
            "assetId": "forzy-motor-01",
            "timezone": "America/Sao_Paulo",
            "activeWeekdays": ["monday", "tuesday", "wednesday"],
            "windowStartLocal": "12:00:00",
            "windowEndLocal": "14:00:00",
            "pollIntervalSeconds": 5,
            "gapThresholdSeconds": 15,
            "effectiveFrom": effective_text,
            "effectiveTo": None,
            "configurationHash": INITIAL_COLLECTION_POLICY_CONFIGURATION_HASH,
        }
    )


def read_collection_policy(
    connection,
    policy_id: str,
) -> CollectionPolicyV1 | None:
    marker = _placeholder(connection)
    row = connection.execute(
        f"SELECT {_POLICY_SELECT} FROM collection_policies_v1 "
        f"WHERE policy_id={marker}",
        (policy_id,),
    ).fetchone()
    return None if row is None else _policy_from_row(row)


def _policies_for_asset(connection, asset_id: str) -> list[CollectionPolicyV1]:
    marker = _placeholder(connection)
    rows = connection.execute(
        f"SELECT {_POLICY_SELECT} FROM collection_policies_v1 "
        f"WHERE asset_id={marker} ORDER BY effective_from, policy_id",
        (asset_id,),
    ).fetchall()
    return [_policy_from_row(row) for row in rows]


def _intervals_overlap(
    left: CollectionPolicyV1,
    right: CollectionPolicyV1,
) -> bool:
    left_before_right_end = (
        right.effective_to is None or left.effective_from < right.effective_to
    )
    right_before_left_end = (
        left.effective_to is None or right.effective_from < left.effective_to
    )
    return left_before_right_end and right_before_left_end


def insert_collection_policy(connection, policy: CollectionPolicyV1) -> bool:
    validated = CollectionPolicyV1.model_validate(policy.model_dump_public())
    existing = read_collection_policy(connection, validated.collection_policy_id)
    if existing is not None:
        if existing.model_dump_public() == validated.model_dump_public():
            return False
        raise ValueError("collection policy id conflict")

    for candidate in _policies_for_asset(connection, validated.asset_id):
        if _intervals_overlap(candidate, validated):
            raise ValueError("collection policy validity overlap")

    body = validated.model_dump_public()
    markers = ",".join([_placeholder(connection)] * len(_POLICY_COLUMNS))
    connection.execute(
        f"INSERT INTO collection_policies_v1 ({_POLICY_SELECT}) VALUES ({markers})",
        (
            body["schemaVersion"],
            body["collectionPolicyId"],
            body["assetId"],
            body["timezone"],
            json.dumps(body["activeWeekdays"], separators=(",", ":")),
            body["windowStartLocal"],
            body["windowEndLocal"],
            body["pollIntervalSeconds"],
            body["gapThresholdSeconds"],
            body["effectiveFrom"],
            body["effectiveTo"],
            body["configurationHash"],
        ),
    )
    return True


def ensure_initial_collection_policy(
    connection,
    *,
    effective_from: datetime,
) -> CollectionPolicySeedResultV1:
    expected = initial_collection_policy(effective_from)
    existing = read_collection_policy(connection, INITIAL_COLLECTION_POLICY_ID)
    if existing is not None:
        if existing.model_dump_public() != expected.model_dump_public():
            raise ValueError("initial collection policy conflict")
        return CollectionPolicySeedResultV1(
            policy=existing,
            inserted=False,
            writes_performed=0,
        )

    inserted = insert_collection_policy(connection, expected)
    stored = read_collection_policy(connection, INITIAL_COLLECTION_POLICY_ID)
    if not inserted or stored is None:
        raise RuntimeError("initial collection policy insert was not observable")
    if stored.model_dump_public() != expected.model_dump_public():
        raise ValueError("initial collection policy reread conflict")
    return CollectionPolicySeedResultV1(
        policy=stored,
        inserted=True,
        writes_performed=1,
    )


def _lookup_instant(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("policy lookup timestamp must be timezone-aware")
    return value.astimezone(timezone.utc)


def read_effective_collection_policy(
    connection,
    asset_id: str,
    at: datetime,
) -> CollectionPolicyV1 | None:
    instant = _lookup_instant(at)
    matches = [
        policy
        for policy in _policies_for_asset(connection, asset_id)
        if policy.effective_from <= instant
        and (policy.effective_to is None or instant < policy.effective_to)
    ]
    if len(matches) > 1:
        raise RuntimeError("multiple effective collection policies")
    return matches[0] if matches else None


effective_collection_policy = read_effective_collection_policy
