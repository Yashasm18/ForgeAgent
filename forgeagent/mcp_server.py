"""Stdio MCP server exposing ForgeAgent Foundry inspection and governance tools."""

from __future__ import annotations

import json
import re
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

# Support both the documented module form (``python3 -m forgeagent.mcp_server``)
# and direct stdio execution of this file for MCP clients that only accept paths.
if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from forgeagent.agent import BLUEPRINTS
from forgeagent.control_plane import ControlPlane
from forgeagent.offline_intelligence import OfflineTemplateGenerator
from forgeagent.platform_store import PlatformStore
from forgeagent.repository_graph import RepositoryGraph
from forgeagent.sandbox import execute


# These tools operate in a team/project namespace. Their capability memory is
# exclusively the approval-aware PlatformStore/ControlPlane boundary; local
# ToolRegistry JSON belongs only to non-MCP CLI demonstrations.
PROJECT_SCOPED_TOOLS = frozenset({
    "forge_list_capabilities",
    "forge_get_audit_receipt",
    "forge_request_capability",
    "forge_run_trusted_capability",
    "forge_get_approval_status",
    "forge_get_metrics",
    "forge_report_capability_feedback",
    "forge_check_contract_drift",
})


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
        {"name": "forge_report_capability_feedback", "description": "Submit a reproducible correct/incorrect outcome. A reproduced incorrect result becomes a regression case and safely quarantines trusted reuse.", "inputSchema": {"type": "object", "properties": {"project_id": project, "capability_id": {"type": "string"}, "verdict": {"type": "string", "enum": ["correct", "incorrect"]}, "summary": {"type": "string"}, "payload": {"type": "object"}, "expected_output": {}}, "required": ["project_id", "capability_id", "verdict", "summary", "payload", "expected_output"]}},
        {"name": "forge_check_contract_drift", "description": "Replay persisted proof and feedback regressions for trusted capabilities; failures are quarantined, never silently reused.", "inputSchema": {"type": "object", "properties": {"project_id": project}, "required": ["project_id"]}},
    ]


def _project_store(store: PlatformStore, plane: ControlPlane | None) -> PlatformStore:
    """Use the approval-aware store owned by the project control plane."""
    return plane.store if plane else store


def _capability_name(task: str) -> str:
    blueprint = next((item for item in BLUEPRINTS if item.matches(task)), None)
    if blueprint:
        return blueprint.name
    template = OfflineTemplateGenerator.template_capability_name(task)
    if template:
        return template
    return "_".join(re.findall(r"[a-z0-9]+", task.lower())[:5]) or "unnamed_capability"


def _run_project_trusted_capability(store: PlatformStore, project_id: str, task: str, payload: dict[str, object]) -> dict[str, object] | None:
    """Run only an already-approved SQLite capability for an MCP namespace."""
    capability = _capability_name(task)
    # First honor exact request lineage.  A live model can give its verified
    # capability a name that differs from the task slug used by this server.
    record = store.trusted_for_task(project_id, task)
    if record is None:
        record = next((item for item in store.list(project_id, trusted_only=True) if item.name == capability), None)
    if record is None:
        return None
    # Reuse is also a maintenance checkpoint. A trusted record with retained
    # evidence is re-proved before it executes for another coding agent; a
    # mismatch quarantines it and blocks this run rather than deferring the
    # problem to a later periodic sweep.
    drift = store.check_contract_drift(project_id, record.id)
    check = drift["checks"][0] if drift["checks"] else None
    if not isinstance(check, dict) or check.get("status") != "passed":
        status = check.get("status", "unavailable") if isinstance(check, dict) else "unavailable"
        raise ValueError(
            f"Trusted capability cannot be reused: contract evidence is {status}. "
            "Re-prove or repair it before reuse."
        )
    result = execute(record.source, payload)
    exported = asdict(record)
    return {
        "task": task,
        "capability": record.name,
        "status": "reused",
        "result": result,
        "council": [
            {"role": "planner", "status": "complete", "detail": f"Task maps to capability '{record.name}'."},
            {"role": "builder", "status": "skipped", "detail": "An approved project capability already exists."},
            {"role": "governor", "status": "reused", "detail": f"Reused approved {record.name}@v{record.version} from project capability memory."},
        ],
        "inspection": {"impact": [], "existing_trusted_tool": exported, "match_count": 1},
        "threat_model": None,
        "proof": None,
        "memory_record": exported,
        "memory_source": "platform_store",
        "drift_check": check,
    }


def call(name: str, arguments: dict[str, Any], store: PlatformStore, plane: ControlPlane | None = None) -> object:
    project_store = _project_store(store, plane)
    if name == "forge_inspect_repository":
        graph = RepositoryGraph(".")
        graph.build()
        return {"matches": graph.query(arguments["capability"]), "impact": graph.impact(arguments["capability"])}
    if name == "forge_list_capabilities":
        return {"capabilities": [asdict(record) for record in project_store.list(arguments["project_id"])]}
    if name == "forge_get_audit_receipt":
        return project_store.receipt(arguments["project_id"])
    if name == "forge_decide_capability":
        return asdict(project_store.decide(arguments["capability_id"], arguments["decision"], arguments["reviewer"], arguments["reason"]))
    if name == "forge_request_capability":
        local_plane = plane or ControlPlane("data")
        project_id = str(arguments["project_id"])
        # Stdio clients run on a developer's machine, so bootstrap the local
        # principal. Remote HTTP clients use bearer-token RBAC instead.
        local_plane.create_project(project_id, "local-mcp")
        return local_plane.request_capability(project_id, "local-mcp", str(arguments["task"]), dict(arguments["payload"]), bool(arguments.get("production", True)))
    if name == "forge_run_trusted_capability":
        project_id = str(arguments["project_id"])
        reused = _run_project_trusted_capability(project_store, project_id, str(arguments["task"]), dict(arguments["payload"]))
        if reused is not None:
            return reused
        raise ValueError("No approved trusted capability exists in this project namespace. Request and approve it before reuse.")
    if name == "forge_get_approval_status":
        project_id = str(arguments["project_id"])
        return {"capabilities": [asdict(record) for record in project_store.list(project_id)], "receipt": project_store.receipt(project_id)}
    if name == "forge_get_metrics":
        local_plane = plane or ControlPlane("data")
        project_id = str(arguments["project_id"])
        local_plane.create_project(project_id, "local-mcp")
        return local_plane.metrics(project_id, "local-mcp")
    if name == "forge_report_capability_feedback":
        local_plane = plane or ControlPlane("data")
        project_id = str(arguments["project_id"])
        local_plane.create_project(project_id, "local-mcp")
        return local_plane.report_capability_feedback(
            project_id,
            "local-mcp",
            str(arguments["capability_id"]),
            str(arguments["verdict"]),
            str(arguments["summary"]),
            arguments["payload"],
            arguments["expected_output"],
        )
    if name == "forge_check_contract_drift":
        local_plane = plane or ControlPlane("data")
        project_id = str(arguments["project_id"])
        local_plane.create_project(project_id, "local-mcp")
        # Local stdio MCP is a developer-owned session. The bootstrap principal
        # is also used for review-only maintenance commands; remote API callers
        # must satisfy the explicit RBAC boundary in ControlPlane.
        local_plane.grant_role(project_id, "local-mcp", "local-mcp", "reviewer")
        return local_plane.check_contract_drift(project_id, "local-mcp")
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
