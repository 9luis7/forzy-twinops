import json

import httpx
import pytest

from scripts.verify_deployment import (
    DeploymentVerificationError,
    verify_deployment,
)


def _snapshot(*, assessment=None):
    return {
        "schemaVersion": "2.0",
        "asset": {
            "assetId": "forzy-motor-01",
            "displayName": "Conjunto motor-bomba monitorado",
            "officialTag": None,
        },
        "channels": [{"sensorId": "s1"}, {"sensorId": "s2"}],
        "assessment": assessment,
    }


def _assessment(*, status="insufficient_data"):
    return {
        "schemaVersion": "2.0",
        "assetId": "forzy-motor-01",
        "sensorId": "s1",
        "quality": {"status": "insufficient_data", "flags": []},
        "assessment": {
            "status": status,
            "scoreSemantics": (
                "relative_to_historical_baseline_not_failure_probability"
            ),
        },
        "model": {"name": "robust-baseline"},
    }


_DEFAULT_ASSESSMENT = object()


def _handler(
    *,
    integration_state="expected_idle",
    calls=None,
    secret_body=None,
    refresh_assessment=_DEFAULT_ASSESSMENT,
    empty_static=False,
    wrong_static_magic=False,
    manifest_content_type="application/json",
):
    calls = [] if calls is None else calls
    if refresh_assessment is _DEFAULT_ASSESSMENT:
        refresh_assessment = _assessment()

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        if request.url.path == "/api/v2/integration/health":
            if secret_body is not None:
                return httpx.Response(503, text=secret_body)
            return httpx.Response(
                200,
                json={
                    "status": "ok",
                    "integration": {
                        "state": integration_state,
                        "sensors": {"s1": {}, "s2": {}},
                    },
                },
            )
        if request.url.path == "/api/v2/assets/forzy-motor-01/snapshot":
            return httpx.Response(200, json=_snapshot())
        if request.url.path == "/api/v2/assets/forzy-motor-01/refresh":
            return httpx.Response(
                200,
                json={
                    "refreshAttempted": True,
                    "outcomes": {"s1": "stored", "s2": "unchanged"},
                    "snapshot": _snapshot(assessment=refresh_assessment),
                },
            )
        if request.url.path == "/models/conjunto-motor-bomba.manifest.json":
            manifest = {
                "schemaVersion": "1.0",
                "assetId": "forzy-motor-01",
                "modelUrl": "/models/conjunto-motor-bomba.glb",
            }
            return httpx.Response(
                200,
                content=json.dumps(manifest).encode(),
                headers={"content-type": manifest_content_type},
            )
        if request.url.path == "/models/conjunto-motor-bomba.glb":
            if empty_static:
                return httpx.Response(200)
            content = b"wrong" if wrong_static_magic else b"glTF\x02\x00\x00\x00"
            return httpx.Response(
                200,
                content=content,
                headers={"content-type": "model/gltf-binary"},
            )
        if request.url.path == "/models/conjunto-motor-bomba-preview.png":
            if empty_static:
                return httpx.Response(200)
            content = b"wrong" if wrong_static_magic else b"\x89PNG\r\n\x1a\n"
            return httpx.Response(
                200,
                content=content,
                headers={"content-type": "image/png"},
            )
        return httpx.Response(404)

    return handle


def test_read_only_probe_checks_api_and_all_three_static_assets_without_post():
    calls = []
    with httpx.Client(transport=httpx.MockTransport(_handler(calls=calls))) as client:
        report = verify_deployment("https://preview.invalid", client=client)

    assert report.health == "ok"
    assert report.schema_version == "2.0"
    assert report.static_assets == 3
    assert report.refresh == "not_requested"
    assert report.assessment == "not_yet_available"
    assert ("POST", "/api/v2/assets/forzy-motor-01/refresh") not in calls
    assert calls == [
        ("GET", "/api/v2/integration/health"),
        ("GET", "/api/v2/assets/forzy-motor-01/snapshot"),
        ("GET", "/models/conjunto-motor-bomba.manifest.json"),
        ("GET", "/models/conjunto-motor-bomba.glb"),
        ("GET", "/models/conjunto-motor-bomba-preview.png"),
    ]


def test_live_refresh_is_skipped_until_backend_confirms_open_window():
    calls = []
    with httpx.Client(transport=httpx.MockTransport(_handler(calls=calls))) as client:
        report = verify_deployment(
            "https://preview.invalid",
            client=client,
            allow_live_refresh=True,
        )

    assert report.refresh == "skipped_window_closed"
    assert not any(method == "POST" for method, _ in calls)


def test_live_refresh_posts_only_after_active_health_confirmation():
    calls = []
    with httpx.Client(
        transport=httpx.MockTransport(
            _handler(integration_state="active", calls=calls)
        )
    ) as client:
        report = verify_deployment(
            "https://preview.invalid",
            client=client,
            allow_live_refresh=True,
        )

    assert report.refresh == "passed"
    assert report.assessment == "insufficient_data"
    assert calls[-1] == ("POST", "/api/v2/assets/forzy-motor-01/refresh")


def test_live_refresh_fails_when_both_sensors_succeed_but_assessment_is_null():
    with httpx.Client(
        transport=httpx.MockTransport(
            _handler(integration_state="active", refresh_assessment=None)
        )
    ) as client:
        with pytest.raises(
            DeploymentVerificationError,
            match="refresh:assessment_unavailable",
        ):
            verify_deployment(
                "https://preview.invalid",
                client=client,
                allow_live_refresh=True,
            )


def test_live_refresh_rejects_unknown_assessment_status():
    with httpx.Client(
        transport=httpx.MockTransport(
            _handler(
                integration_state="active",
                refresh_assessment=_assessment(status="unknown"),
            )
        )
    ) as client:
        with pytest.raises(
            DeploymentVerificationError,
            match="snapshot:invalid_assessment",
        ):
            verify_deployment(
                "https://preview.invalid",
                client=client,
                allow_live_refresh=True,
            )


def test_static_probe_rejects_head_200_without_a_confirmed_body():
    with httpx.Client(
        transport=httpx.MockTransport(_handler(empty_static=True))
    ) as client:
        with pytest.raises(
            DeploymentVerificationError,
            match="model_glb:empty_asset",
        ):
            verify_deployment("https://preview.invalid", client=client)


def test_static_probe_rejects_wrong_magic_even_with_nonempty_body():
    with httpx.Client(
        transport=httpx.MockTransport(_handler(wrong_static_magic=True))
    ) as client:
        with pytest.raises(
            DeploymentVerificationError,
            match="model_glb:invalid_magic",
        ):
            verify_deployment("https://preview.invalid", client=client)


def test_manifest_probe_rejects_non_json_content_type():
    with httpx.Client(
        transport=httpx.MockTransport(
            _handler(manifest_content_type="text/plain")
        )
    ) as client:
        with pytest.raises(
            DeploymentVerificationError,
            match="model_manifest:invalid_content_type",
        ):
            verify_deployment("https://preview.invalid", client=client)


def test_failures_never_include_response_body_or_url():
    secret = "postgresql://user:secret@private-pooler.neon.tech/database"
    with httpx.Client(
        transport=httpx.MockTransport(_handler(secret_body=secret))
    ) as client:
        with pytest.raises(DeploymentVerificationError) as captured:
            verify_deployment("https://preview.invalid", client=client)

    rendered = str(captured.value)
    assert rendered == "health:unexpected_status"
    assert secret not in rendered
    assert "preview.invalid" not in rendered


@pytest.mark.parametrize(
    "url",
    [
        "http://preview.invalid",
        "https://user:secret@preview.invalid",
        "https://preview.invalid/path",
        "https://preview.invalid?token=secret",
    ],
)
def test_remote_deployment_url_must_be_a_credential_free_https_origin(url):
    with pytest.raises(ValueError, match="credential-free HTTPS origin"):
        verify_deployment(url)
