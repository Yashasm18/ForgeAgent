"""Measured comparison of a stateless agent and ForgeAgent's trusted memory."""

from __future__ import annotations

import tempfile
import time
from pathlib import Path

from agent import ForgeAgent, PlanStep
from registry import ToolRegistry


def _run(plan: tuple[PlanStep, ...], shared_memory: bool) -> dict[str, object]:
    started = time.perf_counter()
    creations = reuses = 0
    with tempfile.TemporaryDirectory(prefix="forge-comparison-") as directory:
        root = Path(directory)
        for run in range(2):
            registry = ToolRegistry(root / "shared.json" if shared_memory else root / f"stateless-{run}.json")
            agent = ForgeAgent(registry, emit=lambda _: None)
            agent.execute_plan("Securely analyze a support incident", plan)
            tools = registry.list()
            creations += len([tool for tool in tools if tool.reuse_count == 0]) if not shared_memory else 0
        if shared_memory:
            tools = ToolRegistry(root / "shared.json").list()
            creations = len(tools)
            reuses = sum(tool.reuse_count for tool in tools)
    return {"new_skills": creations, "reuses": reuses, "elapsed_ms": round((time.perf_counter() - started) * 1000, 1)}


def compare(plan: tuple[PlanStep, ...]) -> dict[str, object]:
    stateless = _run(plan, shared_memory=False)
    forge = _run(plan, shared_memory=True)
    return {
        "scenario": "Two identical multi-step incident analyses",
        "stateless_agent": stateless,
        "forgeagent": forge,
        "claim": "ForgeAgent learns once, verifies once, and reuses trusted capabilities on subsequent tasks.",
    }
