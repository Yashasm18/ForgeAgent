"""Stdio MCP server exposing ForgeAgent Foundry inspection and governance tools."""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from typing import Any

from control_plane import ControlPlane
from foundry import CapabilityFoundry
from platform_store import PlatformStore
from repository_graph import RepositoryGraph


def tools() -> list[dict[str, object]]:
    project = {"type": "string", "description": "Team/project namespace."}
    return [
        {"name": "forge_inspect_repository", "description": "Build and query the repository intelligence graph before proposing a capability.", "inputSchema": {"type": "object", "properties": {"capability": {"type": "string"}}, "required": ["capability"]}},
        {"name": "forge_list_capabilities", "description": "List capability memory in a project namespace.", "inputSchema": {"type": "object", "properties": {"project_id": project}, "required": ["project_id"]}},
        {"name": "forge_get_audit_receipt", "description": "Return the audit-safe decision timeline for a project namespace.", "inputSchema": {"type": "object", "properties": {"project_id": project}, "required": ["project_id"]}},
        {"name": "forge_decide_capability", "description": "Human approval/rejection gate for a pending capability.", "inputSchema": {"type": "object", "properties": {"capability_id": {"type": "string"}, "decision": {"type": "string", "enum": ["approved", "rejected"]}, "reviewer": {"type": "string"}, "reason": {"type": "string"}}, "required": ["capability_id", "decision", "reviewer", "reason"]}},
        {"name": "forge_request_capability", "description": "Request a governed capability lifecycle: inspect, propose, prove, and retain pending evidence under production policy.", "inputSchema": {"type": "object", "properties": {"project_id": project, "task": {"type": "string"}, "payload": {"type": "object"}, "production": {"type": "boolean"}}, "required": ["project_id", "task", "payload"]}},
        {"name": "forge_run_trusted_capability", "description": "Run or reuse an existing trusted capability locally; it never creates unrestricted external actions.", "inputSchema": {"type": "object", "properties": {"project_id": project, "task": {"type": "string"}, "payload": {"type": "object"}}, "required": ["project_id", "task", "payload"]}},
        {"name": "forge_get_approval_status", "description": "Return pending/trusted/rejected capability states and an integrity-hashed audit receipt.", "inputSchema": {"type": "object", "properties": {"project_id": project}, "required": ["project_id"]}},
        {"name": "forge_get_metrics", "description": "Return audit-safe capability, state, and control-plane activity metrics for a project.", "inputSchema": {"type": "object", "properties": {"project_id": project}, "required": ["project_id"]}},
    ]


def call(name: str, arguments: dict[str, Any], store: PlatformStore, plane: ControlPlane | None = None) -> object:
    if name == "forge_inspect_repository":
        graph = RepositoryGraph(".")
        graph.build()
        return {"matches": graph.query(arguments["capability"]), "impact": graph.impact(arguments["capability"])}
    if name == "forge_list_capabilities":
        return {"capabilities": [asdict(record) for record in store.list(arguments["project_id"])]}
    if name == "forge_get_audit_receipt":
        return store.receipt(arguments["project_id"])
    if name == "forge_decide_capability":
        return asdict(store.decide(arguments["capability_id"], arguments["decision"], arguments["reviewer"], arguments["reason"]))
    if name == "forge_request_capability":
        local_plane = plane or ControlPlane("data")
        project_id = str(arguments["project_id"])
        # Stdio clients run on a developer's machine, so bootstrap the local
        # principal. Remote HTTP clients use bearer-token RBAC instead.
        local_plane.create_project(project_id, "local-mcp")
        return local_plane.request_capability(project_id, "local-mcp", str(arguments["task"]), dict(arguments["payload"]), bool(arguments.get("production", True)))
    if name == "forge_run_trusted_capability":
        foundry = CapabilityFoundry("data/tool_registry.json", project_id=str(arguments["project_id"]), root=".")
        return foundry.run(str(arguments["task"]), dict(arguments["payload"]), approval_policy="auto")
    if name == "forge_get_approval_status":
        return {"capabilities": [asdict(record) for record in store.list(str(arguments["project_id"]))], "receipt": store.receipt(str(arguments["project_id"]))}
    if name == "forge_get_metrics":
        local_plane = plane or ControlPlane("data")
        project_id = str(arguments["project_id"])
        local_plane.create_project(project_id, "local-mcp")
        return local_plane.metrics(project_id, "local-mcp")
    raise ValueError(f"unknown tool: {name}")


def handle(request: dict[str, Any], store: PlatformStore, plane: ControlPlane | None = None) -> dict[str, object] | None:
    method, params, request_id = request.get("method"), request.get("params", {}), request.get("id")
    if method == "notifications/initialized":
        return None
    if method == "initialize":
        result: object = {"protocolVersion": params.get("protocolVersion", "2024-11-05"), "capabilities": {"tools": {}}, "serverInfo": {"name": "forgeagent-foundry", "version": "1.0.0"}}
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": tools()}
    elif method == "tools/call":
        value = call(params["name"], params.get("arguments", {}), store, plane)
        result = {"content": [{"type": "text", "text": json.dumps(value, sort_keys=True)}]}
    else:
        raise ValueError(f"method not found: {method}")
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def main() -> None:
    store = PlatformStore("data/foundry.sqlite3")
    plane = ControlPlane("data")
    for line in sys.stdin:
        try:
            response = handle(json.loads(line), store, plane)
            if response is not None:
                print(json.dumps(response), flush=True)
        except (KeyError, TypeError, ValueError) as exc:
            print(json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32602, "message": str(exc)}}), flush=True)


if __name__ == "__main__":
    main()
