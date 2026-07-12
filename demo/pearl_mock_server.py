"""Stub Pearl API v2.0 server for the AV demo's --mock-pearl flag.

Serves canned responses for exactly the endpoints epiphan-mcp-server's
allowlisted demo tools touch (device identity, storage, recorders, recorder
status, channels, inputs) — shaped from epiphan-mcp-server's own
tests/fixtures/responses.py for schema accuracy. epiphan-mcp-server's source
is never modified: PEARL_DEVICES already accepts any "host:port" value, so
pointing it at this stub is a pure config change in the demo subprocess env.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# Narrative label for the demo: "room 320-B" maps to recorder-1 / channel-1.
_ROUTES: dict[str, dict] = {
    "/api/v2.0/device": {
        "status": "ok",
        "result": {
            "name": "Pearl-2-Room320B",
            "model": "Pearl-2",
            "serial": "DEMO0320B",
            "firmware": "4.14.2",
            "mac": "00:11:22:33:44:55",
        },
    },
    "/api/v2.0/storages": {
        "status": "ok",
        "result": [
            {
                "id": "storage-1",
                "name": "Internal Storage",
                "type": "internal",
                "total_bytes": 500_000_000_000,
                "used_bytes": 100_000_000_000,
                "free_bytes": 400_000_000_000,
                "percent_used": 20.0,
                "mounted": True,
            },
        ],
    },
    "/api/v2.0/recorders": {
        "status": "ok",
        "result": [
            {
                "id": "recorder-1",
                "name": "Room 320-B Recorder",
                "type": "mp4",
                "channel_id": "channel-1",
            },
        ],
    },
    "/api/v2.0/recorders/status": {
        "status": "ok",
        "result": [
            {"id": "recorder-1", "state": "recording", "duration": 1800, "file_size": 536_870_912},
        ],
    },
    "/api/v2.0/recorders/recorder-1/status": {
        "status": "ok",
        "result": {
            "id": "recorder-1",
            "state": "recording",
            "duration": 1800,
            "file_size": 536_870_912,
            "filename": "room_320b_2026-07-12_09-00-00.mp4",
            "bitrate": 8_000_000,
        },
    },
    "/api/v2.0/channels": {
        "status": "ok",
        "result": [{"id": "channel-1", "name": "Room 320-B Main"}],
    },
    "/api/v2.0/inputs": {
        "status": "ok",
        "result": [
            {
                "source_id": "hdmi-1",
                "name": "HDMI 1",
                "source_type": "hdmi",
                "connected": True,
                "resolution": "1920x1080",
                "framerate": 60.0,
                "has_signal": True,
            },
        ],
    },
}


class _MockPearlHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        body = _ROUTES.get(path)
        if body is None:
            payload = json.dumps({"status": "error", "message": "Resource not found"}).encode()
            self.send_response(404)
        else:
            payload = json.dumps(body).encode()
            self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format_str: str, *args: object) -> None:
        pass  # silence default stderr access log so demo output stays clean


def start_mock_pearl_server(port: int = 0) -> tuple[ThreadingHTTPServer, int]:
    """Start the mock Pearl server on a background daemon thread.

    Pass port=0 to let the OS assign a free port. Returns the server (call
    .shutdown() to stop it) and the port it actually bound to.
    """
    server = ThreadingHTTPServer(("127.0.0.1", port), _MockPearlHandler)
    bound_port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, bound_port
