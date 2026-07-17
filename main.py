"""CLI entry point for the ForgeAgent demo."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from agent import ForgeAgent
from benchmark import run_safety_benchmark
from capability_graph import CapabilityGraph
from api_server import serve as serve_api
from comparison import compare
from dashboard import serve
from demo_tasks import DEMO_TASKS, SHOWCASE_TASKS
from evaluation import run_evaluation_suite
from foundry import CapabilityFoundry
from generator import GPT56Generator, GeneratorError
from mcp_server import main as mcp_main
from repository_graph import RepositoryGraph
from registry import ToolRegistry
from workflows import INCIDENT_RECOVERY_PLAN


def main() -> None:
    parser = argparse.ArgumentParser(description="ForgeAgent: self-extending, test-before-trust demo")
    parser.add_argument("--demo", action="store_true", help="Run the curated build -> reuse -> build sequence")
    parser.add_argument("--showcase", action="store_true", help="Run the judge-facing PII -> triage -> reuse workflow")
    parser.add_argument("--benchmark", action="store_true", help="Run ForgeAgent's repeatable trust-gate benchmark")
    parser.add_argument("--autonomy-demo", action="store_true", help="Run a dependency-aware task recovery plan")
    parser.add_argument("--compare", action="store_true", help="Compare stateless execution with ForgeAgent memory")
    parser.add_argument("--graph", action="store_true", help="Export ForgeAgent's task-to-capability graph as JSON")
    parser.add_argument("--autonomous-task", help="Use GPT-5.6 to plan, forge, repair, and complete an unknown user task")
    parser.add_argument("--foundry-task", help="Run the Capability Foundry council on a task")
    parser.add_argument("--foundry-live", action="store_true", help="Use GPT-5.6-terra for Foundry planning and proposals")
    parser.add_argument("--project", default="local/default", help="Foundry project namespace")
    parser.add_argument("--approval-policy", choices=("auto", "review", "never", "production"), default="auto", help="Capability promotion policy (production always requires named human approval)")
    parser.add_argument("--adversarial-proof", action="store_true", help="Use live GPT-5.6 to generate adversarial proof cases for --foundry-task (requires --foundry-live and OPENAI_API_KEY)")
    parser.add_argument("--repo-graph", action="store_true", help="Export the repository intelligence graph")
    parser.add_argument("--evaluate", action="store_true", help="Run the 50-case Foundry Evaluation Arena")
    parser.add_argument("--mcp", action="store_true", help="Run ForgeAgent's stdio MCP server")
    parser.add_argument("--api", action="store_true", help="Run the local authenticated ForgeAgent control-plane HTTP API")
    parser.add_argument("--api-port", type=int, default=8090, help="Control-plane API port (default: 8090)")
    parser.add_argument("--api-host", default="127.0.0.1", help="Control-plane bind host (default: loopback only)")
    parser.add_argument("--reset", action="store_true", help="Remove the demo registry before running")
    parser.add_argument("--list-tools", action="store_true", help="List registered verified tools")
    parser.add_argument("--task", help="One supported task")
    parser.add_argument("--text", help="Text input for --task")
    parser.add_argument("--forge", help="Create a new verified tool with GPT-5.6 for this capability")
    parser.add_argument("--payload", help="JSON payload used with --forge")
    parser.add_argument("--model", default="gpt-5.6-terra", help="OpenAI model for live forging (default: gpt-5.6-terra)")
    parser.add_argument("--serve", action="store_true", help="Open the zero-dependency Forge Ledger dashboard")
    parser.add_argument("--port", type=int, default=8787, help="Dashboard port (default: 8787)")
    args = parser.parse_args()
    registry_path = Path("data/tool_registry.json")
    if args.reset:
        for artifact in (registry_path, registry_path.parent / "audit_log.jsonl", registry_path.parent / "capability_graph.json", registry_path.parent / "foundry.sqlite3"):
            if artifact.exists():
                artifact.unlink()
    registry = ToolRegistry(registry_path)
    if args.mcp:
        mcp_main()
        return
    if args.api:
        serve_api(args.api_port, host=args.api_host)
        return
    if args.serve:
        serve(registry_path, args.port)
        return
    if args.list_tools:
        print(json.dumps([{ "name": t.name, "description": t.description, "created_at": t.created_at } for t in registry.list()], indent=2))
        return
    if args.benchmark:
        print(json.dumps(run_safety_benchmark(), indent=2))
        return
    if args.evaluate:
        print(json.dumps(run_evaluation_suite(), indent=2))
        return
    if args.repo_graph:
        graph = RepositoryGraph(".")
        print(json.dumps(graph.build(), indent=2))
        return
    if args.foundry_task:
        try:
            payload = json.loads(args.payload) if args.payload else {"text": args.text or ""}
            generator = GPT56Generator(model=args.model) if args.foundry_live else None
            foundry = CapabilityFoundry(registry_path, project_id=args.project, generator=generator)
            print(json.dumps(foundry.run(args.foundry_task, payload, approval_policy=args.approval_policy, adversarial_proof=args.adversarial_proof), indent=2))
        except (json.JSONDecodeError, GeneratorError, RuntimeError) as exc:
            parser.error(str(exc))
        return
    if args.compare:
        print(json.dumps(compare(INCIDENT_RECOVERY_PLAN), indent=2))
        return
    if args.graph:
        print(json.dumps(CapabilityGraph(registry_path.parent / "capability_graph.json").export(), indent=2))
        return
    agent = ForgeAgent(registry)
    if args.demo:
        print("═" * 68 + "\n FORGEAGENT  |  self-extending tools, verified before trust\n" + "═" * 68)
        for task, payload in DEMO_TASKS:
            print(json.dumps(agent.complete(task, payload), indent=2))
        return
    if args.showcase:
        print("═" * 68 + "\n FORGEAGENT SHOWCASE  |  privacy -> risk -> trusted reuse\n" + "═" * 68)
        for task, payload in SHOWCASE_TASKS:
            print(json.dumps(agent.complete(task, payload), indent=2))
        return
    if args.autonomy_demo:
        print("═" * 68 + "\n FORGEAGENT AUTONOMY  |  task gap -> plan -> learn -> reuse\n" + "═" * 68)
        print(json.dumps(agent.execute_plan("Securely analyze a support incident", INCIDENT_RECOVERY_PLAN), indent=2))
        return
    if args.task and args.text is not None:
        print(json.dumps(agent.complete(args.task, {"text": args.text}), indent=2))
        return
    if args.forge and args.payload:
        try:
            payload = json.loads(args.payload)
            live_agent = ForgeAgent(registry, generator=GPT56Generator(model=args.model))
            print(json.dumps(live_agent.forge(args.forge, payload), indent=2))
        except (json.JSONDecodeError, GeneratorError, RuntimeError) as exc:
            parser.error(str(exc))
        return
    if args.autonomous_task and args.payload:
        try:
            payload = json.loads(args.payload)
            live_agent = ForgeAgent(registry, generator=GPT56Generator(model=args.model))
            print(json.dumps(live_agent.execute_user_task(args.autonomous_task, payload), indent=2))
        except (json.JSONDecodeError, GeneratorError, RuntimeError) as exc:
            parser.error(str(exc))
        return
    parser.print_help()


if __name__ == "__main__":
    main()
