"""A stdio JSON-RPC MCP server for ForgeAgent's persistent capability memory.

Run ``python3 mcp_server.py`` and configure it in a compatible coding agent.
It exposes only governance and audit operations; it never executes imported
capability source code through MCP.
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from typing import Any

from platform_store import PlatformStore


def tool_definitions() -> list[dict[str, Any]]:
    project = {"type": "string", "description": "Team/project namespace, for example team/support."}
    return [
        {"name": "forge_list_capabilities", "description": "List capability versions in a namespace.", "inputSchema": {"type": "object", "properties": {"project_id": project}, "required": ["project_id"]}},
        {"name": "forge_get_audit_receipt", "description": "Get the audit-safe capability and decision timeline for a namespace.", "inputSchema": {"type": "object", "properties": {"project_id": project}, "required": ["project_id"]}},
        {"name": "forge_approval_inbox", "description": "List capabilities that require a human decision.", "inputSchema": {"type": "object", "properties": {"project_id": project}, "required": ["project_id"]}},
        {"name": "forge_decide_capability", "description": "Approve or reject a pending capability after human review.", "inputSchema": {"type": "object", "properties": {"capability_id": {"type": "string"}, "decision": {"type": "string", "enum": ["approved", "rejected"]}, "reviewer": {"type": "string"}, "reason": {"type": "string"}}, "required": ["capability_id", "decision", "reviewer", "reason"]}},
    ]


def call_tool(store: PlatformStore, name: str, arguments: dict[str, Any]) -> object:
    if name == "forge_list_capabilities":
        return {"capabilities": [asdict(capability) for capability in store.list(arguments["project_id"])]}
    if name == "forge_get_audit_receipt":
        return store.receipt(arguments["project_id"])
    if name == "forge_approval_inbox":
        return {"pending": [asdict(capability) for capability in store.pending(arguments["project_id"])]}
    if name == "forge_decide_capability":
        return asdict(store.decide(arguments["capability_id"], arguments["decision"], arguments["reviewer"], arguments["reason"]))
    raise ValueError(f"unknown tool: {name}")


def handle_request(store: PlatformStore, request: dict[str, Any]) -> dict[str, Any] | None:
    """Handle the MCP initialize, ping, tools/list, and tools/call surface."""
    method, params, request_id = request.get("method"), request.get("params", {}), request.get("id")
    if method == "notifications/initialized":
        return None
    if method == "initialize":
        result: object = {"protocolVersion": params.get("protocolVersion", "2024-11-05"), "capabilities": {"tools": {}}, "serverInfo": {"name": "forgeagent", "version": "0.2.0"}}
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": tool_definitions()}
    elif method == "tools/call":
        result_value = call_tool(store, params["name"], params.get("arguments", {}))
        result = {"content": [{"type": "text", "text": json.dumps(result_value, sort_keys=True)}]}
    else:
        raise ValueError(f"method not found: {method}")
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def main() -> None:
    store = PlatformStore("data/platform.sqlite3")
    for line in sys.stdin:
        try:
            response = handle_request(store, json.loads(line))
            if response is not None:
                print(json.dumps(response), flush=True)
        except (KeyError, TypeError, ValueError) as exc:
            print(json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32602, "message": str(exc)}}), flush=True)


if __name__ == "__main__":
    main()
