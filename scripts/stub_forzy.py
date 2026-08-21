"""Serve deterministic S1/S2 Forzy-shaped payloads for an authorized preview."""

import argparse
from collections.abc import Sequence
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import ssl


_PAYLOADS = {
    "/get_s1": {
        "dados1": {
            "Velocidade": 0.42,
            "Aceleração": 0.08,
            "Temperatura": 34.2,
        }
    },
    "/get_s2": {
        "dados2": {
            "Velocidade": 0.39,
            "Aceleração": 0.08,
            "Temperatura": 33.8,
        }
    },
}


class ForzyStubHandler(BaseHTTPRequestHandler):
    """Return only the two documented sensor payloads without request logging."""

    server_version = "TwinOpsForzyStub/1.0"
    sys_version = ""

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler protocol
        payload = _PAYLOADS.get(self.path)
        if payload is None:
            self._send_json(404, {"detail": "not_found"})
            return
        self._send_json(200, payload)

    def _send_json(self, status: int, payload: dict[str, object]) -> None:
        body = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("content-length", str(len(body)))
        self.send_header("cache-control", "no-store")
        self.send_header("x-content-type-options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


def create_server(
    host: str,
    port: int,
    *,
    certfile: Path | None = None,
    keyfile: Path | None = None,
) -> ThreadingHTTPServer:
    if (certfile is None) != (keyfile is None):
        raise ValueError("certfile and keyfile must be provided together")
    server = ThreadingHTTPServer((host, port), ForzyStubHandler)
    server.daemon_threads = True
    if certfile is not None and keyfile is not None:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certfile=certfile, keyfile=keyfile)
        server.socket = context.wrap_socket(server.socket, server_side=True)
    return server


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--certfile", type=Path)
    parser.add_argument("--keyfile", type=Path)
    args = parser.parse_args(argv)
    server = create_server(
        args.host,
        args.port,
        certfile=args.certfile,
        keyfile=args.keyfile,
    )
    scheme = "https" if args.certfile is not None else "http"
    bound_host, bound_port = server.server_address[:2]
    print(f"forzy_stub_ready scheme={scheme} host={bound_host} port={bound_port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
