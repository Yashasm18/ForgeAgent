"""Small authenticated HTTP control-plane API for local and container deployment.

It intentionally uses the Python standard library so the hackathon project is
immediately runnable.  The route shapes are stable and can be served by a
FastAPI/Postgres implementation later without changing MCP clients.
"""

from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from control_plane import AuthorizationError, ControlPlane


class ControlPlaneHandler(BaseHTTPRequestHandler):
    plane: ControlPlane

    def log_message(self, *_: object) -> None:
        return

    def do_GET(self) -> None:  # noqa: N802
        try:
            if self.path == "/healthz":
                return self._send(HTTPStatus.OK, {"status": "ok", "service": "forgeagent-control-plane"})
            subject = self._subject()
            parts = self.path.strip("/").split("/")
            if len(parts) == 4 and parts[:2] == ["v1", "projects"] and parts[3] == "snapshot":
                return self._send(HTTPStatus.OK, self.plane.project_snapshot(parts[2], subject))
            if len(parts) == 4 and parts[:2] == ["v1", "projects"] and parts[3] == "metrics":
                return self._send(HTTPStatus.OK, self.plane.metrics(parts[2], subject))
            return self._send(HTTPStatus.NOT_FOUND, {"error": "route not found"})
        except (AuthorizationError, PermissionError) as exc:
            self._send(HTTPStatus.FORBIDDEN, {"error": str(exc)})
        except ValueError as exc:
            self._send(HTTPStatus.BAD_REQUEST, {"error": str(exc)})

    def do_POST(self) -> None:  # noqa: N802
        try:
            body = self._body()
            if self.path == "/v1/projects":
                principal = self.plane.create_project(str(body["project_id"]), str(body["owner"]))
                token = self.plane.issue_token(principal.subject, "bootstrap")
                return self._send(HTTPStatus.CREATED, {"project_id": body["project_id"], "principal": principal.__dict__, "bootstrap_token": token})
            subject = self._subject()
            parts = self.path.strip("/").split("/")
            if len(parts) == 5 and parts[:2] == ["v1", "projects"] and parts[3:] == ["capability-requests", ""]:
                return self._send(HTTPStatus.CREATED, self.plane.request_capability(parts[2], subject, str(body["task"]), dict(body.get("payload", {})), bool(body.get("production", True))))
            if len(parts) == 4 and parts[:2] == ["v1", "projects"] and parts[3] == "capability-requests":
                return self._send(HTTPStatus.CREATED, self.plane.request_capability(parts[2], subject, str(body["task"]), dict(body.get("payload", {})), bool(body.get("production", True))))
            if len(parts) == 4 and parts[:2] == ["v1", "projects"] and parts[3] == "members":
                return self._send(HTTPStatus.CREATED, self.plane.grant_role(parts[2], subject, str(body["subject"]), str(body["role"])).__dict__)
            if len(parts) == 5 and parts[:2] == ["v1", "projects"] and parts[3] == "capabilities" and parts[4].endswith(":decision"):
                capability_id = parts[4].removesuffix(":decision")
                return self._send(HTTPStatus.OK, self.plane.decide_capability(parts[2], subject, capability_id, str(body["decision"]), str(body["reason"])))
            return self._send(HTTPStatus.NOT_FOUND, {"error": "route not found"})
        except (AuthorizationError, PermissionError) as exc:
            self._send(HTTPStatus.FORBIDDEN, {"error": str(exc)})
        except (KeyError, TypeError, ValueError, RuntimeError) as exc:
            self._send(HTTPStatus.BAD_REQUEST, {"error": str(exc)})

    def _subject(self) -> str:
        value = self.headers.get("Authorization", "")
        if not value.startswith("Bearer "):
            raise AuthorizationError("Bearer API token required")
        return self.plane.authenticate(value.removeprefix("Bearer "))

    def _body(self) -> dict[str, Any]:
        size = int(self.headers.get("Content-Length", "0"))
        if not 0 < size <= 1_000_000:
            raise ValueError("request body must be between 1 byte and 1 MB")
        value = json.loads(self.rfile.read(size))
        if not isinstance(value, dict):
            raise ValueError("JSON object body required")
        return value

    def _send(self, status: HTTPStatus, payload: object) -> None:
        raw = json.dumps(payload, sort_keys=True, default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def serve(port: int = 8090, data_root: str = "data", host: str = "127.0.0.1") -> None:
    ControlPlaneHandler.plane = ControlPlane(data_root)
    server = ThreadingHTTPServer((host, port), ControlPlaneHandler)
    print(f"ForgeAgent control plane listening on http://{host}:{port}")
    server.serve_forever()
