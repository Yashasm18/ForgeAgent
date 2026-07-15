"""CLI entry point for the ForgeAgent demo."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from agent import ForgeAgent
from benchmark import run_safety_benchmark
from dashboard import serve
from demo_tasks import DEMO_TASKS, SHOWCASE_TASKS
from generator import GPT56Generator, GeneratorError
from registry import ToolRegistry


def main() -> None:
    parser = argparse.ArgumentParser(description="ForgeAgent: self-extending, test-before-trust demo")
    parser.add_argument("--demo", action="store_true", help="Run the curated build -> reuse -> build sequence")
    parser.add_argument("--showcase", action="store_true", help="Run the judge-facing PII -> triage -> reuse workflow")
    parser.add_argument("--benchmark", action="store_true", help="Run ForgeAgent's repeatable trust-gate benchmark")
    parser.add_argument("--reset", action="store_true", help="Remove the demo registry before running")
    parser.add_argument("--list-tools", action="store_true", help="List registered verified tools")
    parser.add_argument("--task", help="One supported task")
    parser.add_argument("--text", help="Text input for --task")
    parser.add_argument("--forge", help="Create a new verified tool with GPT-5.6 for this capability")
    parser.add_argument("--payload", help="JSON payload used with --forge")
    parser.add_argument("--model", default="gpt-5.6", help="OpenAI model for live forging (default: gpt-5.6)")
    parser.add_argument("--serve", action="store_true", help="Open the zero-dependency Forge Ledger dashboard")
    parser.add_argument("--port", type=int, default=8787, help="Dashboard port (default: 8787)")
    args = parser.parse_args()
    registry_path = Path("data/tool_registry.json")
    if args.reset and registry_path.exists():
        registry_path.unlink()
    registry = ToolRegistry(registry_path)
    if args.serve:
        serve(registry_path, args.port)
        return
    if args.list_tools:
        print(json.dumps([{ "name": t.name, "description": t.description, "created_at": t.created_at } for t in registry.list()], indent=2))
        return
    if args.benchmark:
        print(json.dumps(run_safety_benchmark(), indent=2))
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
    parser.print_help()


if __name__ == "__main__":
    main()
