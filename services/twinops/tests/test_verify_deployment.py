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


def _handler(*, integration_state="expected_idle", calls=None, secret_body=None):
    calls = [] if calls is None else calls

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
                    "snapshot": _snapshot(),
                },
            )
        if request.url.path == "/models/conjunto-motor-bomba.manifest.json":
            return httpx.Response(
                200,
                json={
                    "schemaVersion": "1.0",
                    "assetId": "forzy-motor-01",
                    "modelUrl": "/models/conjunto-motor-bomba.glb",
                },
            )
        if request.url.path in {
            "/models/conjunto-motor-bomba.glb",
            "/models/conjunto-motor-bomba-preview.png",
        }:
            return httpx.Response(200, headers={"content-length": "123"})
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
        ("HEAD", "/models/conjunto-motor-bomba.glb"),
        ("HEAD", "/models/conjunto-motor-bomba-preview.png"),
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
    assert calls[-1] == ("POST", "/api/v2/assets/forzy-motor-01/refresh")


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
