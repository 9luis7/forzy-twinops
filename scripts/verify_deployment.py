"""Run sanitized read-only probes against an authorized TwinOps deployment."""

import argparse
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import json
import sys
from urllib.parse import urlsplit, urlunsplit

import httpx


_ASSET_PATH = "/api/v2/assets/forzy-motor-01"
_HEALTH_PATH = "/api/v2/integration/health"
_MANIFEST_PATH = "/models/conjunto-motor-bomba.manifest.json"
_PREVIEW_PATH = "/models/conjunto-motor-bomba-preview.png"
_MODEL_PATH = "/models/conjunto-motor-bomba.glb"


@dataclass(frozen=True)
class DeploymentReport:
    health: str
    schema_version: str
    static_assets: int
    refresh: str
    assessment: str


class DeploymentVerificationError(RuntimeError):
    def __init__(self, stage: str, code: str):
        self.stage = stage
        self.code = code
        super().__init__(f"{stage}:{code}")


def verify_deployment(
    url: str,
    *,
    client: httpx.Client | None = None,
    allow_live_refresh: bool = False,
    timeout_seconds: float = 10.0,
) -> DeploymentReport:
    origin = _deployment_origin(url)
    owns_client = client is None
    http = client or httpx.Client(
        timeout=timeout_seconds,
        follow_redirects=False,
        headers={"accept": "application/json"},
    )
    try:
        health = _json_response(http, origin, _HEALTH_PATH, stage="health")
        integration_state = _validate_health(health)

        snapshot = _json_response(
            http,
            origin,
            f"{_ASSET_PATH}/snapshot",
            stage="snapshot",
        )
        assessment = _validate_snapshot(snapshot)

        manifest = _json_response(
            http,
            origin,
            _MANIFEST_PATH,
            stage="model_manifest",
        )
        _validate_manifest(manifest)
        _probe_static(http, origin, _MODEL_PATH, stage="model_glb")
        _probe_static(http, origin, _PREVIEW_PATH, stage="model_preview")

        refresh = "not_requested"
        if allow_live_refresh:
            if integration_state != "active":
                refresh = "skipped_window_closed"
            else:
                envelope = _json_response(
                    http,
                    origin,
                    f"{_ASSET_PATH}/refresh",
                    stage="refresh",
                    method="POST",
                )
                assessment = _validate_refresh(envelope)
                refresh = "passed"

        return DeploymentReport(
            health="ok",
            schema_version="2.0",
            static_assets=3,
            refresh=refresh,
            assessment=assessment,
        )
    finally:
        if owns_client:
            http.close()


def _deployment_origin(value: str) -> str:
    try:
        parsed = urlsplit(value)
        valid = (
            parsed.scheme == "https"
            and parsed.hostname is not None
            and parsed.username is None
            and parsed.password is None
            and parsed.path in {"", "/"}
            and not parsed.query
            and not parsed.fragment
        )
        if not valid:
            raise ValueError
        return urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))
    except (TypeError, ValueError):
        raise ValueError(
            "deployment URL must be a credential-free HTTPS origin"
        ) from None


def _json_response(
    client: httpx.Client,
    origin: str,
    path: str,
    *,
    stage: str,
    method: str = "GET",
) -> Mapping[str, object]:
    response = _request(client, method, f"{origin}{path}", stage=stage)
    if response.status_code != 200:
        raise DeploymentVerificationError(stage, "unexpected_status")
    try:
        payload = response.json()
    except (json.JSONDecodeError, ValueError):
        raise DeploymentVerificationError(stage, "invalid_json") from None
    if not isinstance(payload, Mapping):
        raise DeploymentVerificationError(stage, "invalid_shape")
    return payload


def _request(
    client: httpx.Client,
    method: str,
    url: str,
    *,
    stage: str,
    headers: Mapping[str, str] | None = None,
) -> httpx.Response:
    try:
        return client.request(method, url, headers=headers)
    except httpx.HTTPError:
        raise DeploymentVerificationError(stage, "request_failed") from None


def _validate_health(payload: Mapping[str, object]) -> str:
    if payload.get("status") != "ok":
        raise DeploymentVerificationError("health", "invalid_status")
    integration = payload.get("integration")
    if not isinstance(integration, Mapping):
        raise DeploymentVerificationError("health", "invalid_shape")
    state = integration.get("state")
    sensors = integration.get("sensors")
    if state not in {"active", "expected_idle"} or not isinstance(sensors, Mapping):
        raise DeploymentVerificationError("health", "invalid_shape")
    if set(sensors) != {"s1", "s2"}:
        raise DeploymentVerificationError("health", "invalid_sensors")
    return str(state)


def _validate_snapshot(payload: Mapping[str, object]) -> str:
    if payload.get("schemaVersion") != "2.0":
        raise DeploymentVerificationError("snapshot", "invalid_schema")
    if _contains_key(payload, "assetTag"):
        raise DeploymentVerificationError("snapshot", "legacy_asset_tag")
    asset = payload.get("asset")
    channels = payload.get("channels")
    if not isinstance(asset, Mapping) or not isinstance(channels, list):
        raise DeploymentVerificationError("snapshot", "invalid_shape")
    if (
        asset.get("assetId") != "forzy-motor-01"
        or asset.get("displayName") != "Conjunto motor-bomba monitorado"
        or asset.get("officialTag") is not None
    ):
        raise DeploymentVerificationError("snapshot", "invalid_asset")
    sensor_ids = {
        channel.get("sensorId")
        for channel in channels
        if isinstance(channel, Mapping)
    }
    if len(channels) != 2 or sensor_ids != {"s1", "s2"}:
        raise DeploymentVerificationError("snapshot", "invalid_sensors")
    assessment = payload.get("assessment")
    if assessment is None:
        return "not_yet_available"
    if not isinstance(assessment, Mapping):
        raise DeploymentVerificationError("snapshot", "invalid_assessment")
    detail = assessment.get("assessment")
    model = assessment.get("model")
    if (
        not isinstance(detail, Mapping)
        or detail.get("scoreSemantics")
        != "relative_to_historical_baseline_not_failure_probability"
        or not isinstance(model, Mapping)
        or model.get("name") != "robust-baseline"
    ):
        raise DeploymentVerificationError("snapshot", "invalid_assessment")
    return "available"


def _validate_manifest(payload: Mapping[str, object]) -> None:
    if (
        payload.get("schemaVersion") != "1.0"
        or payload.get("assetId") != "forzy-motor-01"
        or payload.get("modelUrl") != _MODEL_PATH
    ):
        raise DeploymentVerificationError("model_manifest", "invalid_manifest")


def _probe_static(
    client: httpx.Client,
    origin: str,
    path: str,
    *,
    stage: str,
) -> None:
    response = _request(client, "HEAD", f"{origin}{path}", stage=stage)
    length = response.headers.get("content-length")
    if response.status_code == 200 and (length is None or _positive_length(length)):
        return
    if response.status_code not in {200, 405, 501}:
        raise DeploymentVerificationError(stage, "unexpected_status")
    response = _request(
        client,
        "GET",
        f"{origin}{path}",
        stage=stage,
        headers={"range": "bytes=0-0"},
    )
    if response.status_code not in {200, 206} or not response.content:
        raise DeploymentVerificationError(stage, "empty_asset")


def _positive_length(value: str) -> bool:
    try:
        return int(value) > 0
    except ValueError:
        return False


def _validate_refresh(payload: Mapping[str, object]) -> str:
    if payload.get("refreshAttempted") is not True:
        raise DeploymentVerificationError("refresh", "not_attempted")
    outcomes = payload.get("outcomes")
    if not isinstance(outcomes, Mapping) or set(outcomes) != {"s1", "s2"}:
        raise DeploymentVerificationError("refresh", "invalid_outcomes")
    if any(value not in {"stored", "unchanged"} for value in outcomes.values()):
        raise DeploymentVerificationError("refresh", "sensor_failed")
    snapshot = payload.get("snapshot")
    if not isinstance(snapshot, Mapping):
        raise DeploymentVerificationError("refresh", "invalid_snapshot")
    return _validate_snapshot(snapshot)


def _contains_key(value: object, key: str) -> bool:
    if isinstance(value, Mapping):
        return key in value or any(_contains_key(item, key) for item in value.values())
    if isinstance(value, list):
        return any(_contains_key(item, key) for item in value)
    return False


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--allow-live-refresh", action="store_true")
    parser.add_argument("--timeout-seconds", type=float, default=10.0)
    args = parser.parse_args(argv)
    try:
        report = verify_deployment(
            args.url,
            allow_live_refresh=args.allow_live_refresh,
            timeout_seconds=args.timeout_seconds,
        )
        print(
            "deployment_check_ok "
            f"health={report.health} schema={report.schema_version} "
            f"static_assets={report.static_assets} refresh={report.refresh} "
            f"assessment={report.assessment}"
        )
        return 0
    except DeploymentVerificationError as exc:
        print(
            f"deployment_check_failed stage={exc.stage} code={exc.code}",
            file=sys.stderr,
        )
        return 1
    except Exception as exc:
        print(
            f"deployment_check_failed error_type={type(exc).__name__}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
