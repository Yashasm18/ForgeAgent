"""Small authenticated HTTP control-plane API for local and container deployment.

It intentionally uses the Python standard library so the hackathon project is
immediately runnable.  The route shapes are stable and can be served by a
FastAPI/Postgres implementation later without changing MCP clients.
"""

from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import unquote

from forgeagent.control_plane import AuthorizationError, ControlPlane


class ControlPlaneHandler(BaseHTTPRequestHandler):
    plane: ControlPlane

    def log_message(self, *_: object) -> None:
        return

    def do_GET(self) -> None:  # noqa: N802
        try:
            if self.path == "/healthz":
                return self._send(HTTPStatus.OK, {"status": "ok", "service": "forgeagent-control-plane"})
            subject = self._subject()
            if project_id := self._project_for_suffix("/snapshot"):
                return self._send(HTTPStatus.OK, self.plane.project_snapshot(project_id, subject))
            if project_id := self._project_for_suffix("/metrics"):
                return self._send(HTTPStatus.OK, self.plane.metrics(project_id, subject))
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
            if project_id := self._project_for_suffix("/capability-requests"):
                return self._send(HTTPStatus.CREATED, self.plane.request_capability(project_id, subject, str(body["task"]), dict(body.get("payload", {})), bool(body.get("production", True))))
            if project_id := self._project_for_suffix("/members"):
                return self._send(HTTPStatus.CREATED, self.plane.grant_role(project_id, subject, str(body["subject"]), str(body["role"])).__dict__)
            if project_id := self._project_for_suffix("/contract-drift"):
                return self._send(HTTPStatus.OK, self.plane.check_contract_drift(project_id, subject))
            if decision_route := self._capability_decision_route():
                project_id, capability_id = decision_route
                return self._send(HTTPStatus.OK, self.plane.decide_capability(project_id, subject, capability_id, str(body["decision"]), str(body["reason"])))
            if feedback_route := self._capability_feedback_route():
                project_id, capability_id = feedback_route
                return self._send(
                    HTTPStatus.OK,
                    self.plane.report_capability_feedback(
                        project_id,
                        subject,
                        capability_id,
                        str(body["verdict"]),
                        str(body["summary"]),
                        body["payload"],
                        body["expected_output"],
                    ),
                )
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

    def _project_for_suffix(self, suffix: str) -> str | None:
        """Extract a project ID without assuming it contains no slashes.

        Project namespaces intentionally support IDs such as ``team/invoices``.
        They may be sent as literal path segments or percent-encoded.
        """
        prefix = "/v1/projects/"
        path = self.path.rstrip("/")
        if not path.startswith(prefix) or not path.endswith(suffix):
            return None
        project_id = path[len(prefix) : -len(suffix)]
        return unquote(project_id) if project_id else None

    def _capability_decision_route(self) -> tuple[str, str] | None:
        return self._capability_route(":decision")

    def _capability_feedback_route(self) -> tuple[str, str] | None:
        return self._capability_route("/feedback")

    def _capability_route(self, suffix: str) -> tuple[str, str] | None:
        prefix = "/v1/projects/"
        marker = "/capabilities/"
        path = self.path.rstrip("/")
        if not path.startswith(prefix) or not path.endswith(suffix):
            return None
        route = path[len(prefix) : -len(suffix)]
        if marker not in route:
            return None
        project_id, capability_id = route.rsplit(marker, 1)
        if not project_id or not capability_id:
            return None
        return unquote(project_id), unquote(capability_id)

    def _send(self, status: HTTPStatus, payload: object) -> None:
        raw = json.dumps(payload, sort_keys=True, default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def serve(port: int = 8090, data_root: str = "data", host: str = "127.0.0.1") -> None:
    ControlPlaneHandler.plane = ControlPlane(data_root)
    # The local control plane intentionally owns one SQLite connection. Serve
    # requests in that same loop rather than passing that connection into
    # ThreadingHTTPServer worker threads, which SQLite correctly rejects.
    # A production remote implementation should use a request-safe database
    # pool; this local reference prioritises correct, deterministic behavior.
    server = HTTPServer((host, port), ControlPlaneHandler)
    print(f"ForgeAgent control plane listening on http://{host}:{port}")
    server.serve_forever()
