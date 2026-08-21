from contextlib import contextmanager
from threading import Thread

import httpx
import pytest

from scripts.stub_forzy import create_server


@contextmanager
def running_stub():
    server = create_server("127.0.0.1", 0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.parametrize(
    ("path", "root", "velocity", "temperature"),
    [
        ("/get_s1", "dados1", 0.42, 34.2),
        ("/get_s2", "dados2", 0.39, 33.8),
    ],
)
def test_stub_serves_only_deterministic_forzy_sensor_payloads(
    path, root, velocity, temperature
):
    with running_stub() as base_url:
        response = httpx.get(f"{base_url}{path}")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        root: {
            "Velocidade": velocity,
            "Aceleração": 0.08,
            "Temperatura": temperature,
        }
    }


def test_stub_rejects_unknown_paths_without_echoing_them():
    with running_stub() as base_url:
        response = httpx.get(f"{base_url}/private-value")

    assert response.status_code == 404
    assert response.json() == {"detail": "not_found"}
    assert "private-value" not in response.text


def test_stub_requires_certificate_and_key_together(tmp_path):
    with pytest.raises(ValueError, match="provided together"):
        create_server("127.0.0.1", 0, certfile=tmp_path / "stub.crt")
