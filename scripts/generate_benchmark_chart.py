#!/usr/bin/env python3
"""Generate the README benchmark chart from fresh, local ForgeAgent output.

Data is sourced by running exactly these commands from the repository root:
    python3 main.py --benchmark
    python3 main.py --evaluate
    python3 main.py --compare

No network, packages, API key, recorded metric, or example metric is used.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from xml.sax.saxutils import escape


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "benchmark-results.svg"
WIDTH, HEIGHT = 1600, 820
PANEL_WIDTH, PANEL_HEIGHT = 480, 570
PANEL_Y = 170
PANEL_X = (40, 560, 1080)
COLORS = {
    "ink": "#12263a",
    "muted": "#60758a",
    "line": "#d9e3ec",
    "panel": "#ffffff",
    "page": "#f5f8fb",
    "blue": "#246bce",
    "mint": "#19866a",
    "amber": "#b97916",
    "pale_blue": "#dceafe",
    "pale_mint": "#dff3ec",
    "pale_amber": "#fff0d8",
}


def run_json(*args: str) -> dict[str, object]:
    """Run one documented offline proof command and parse its JSON output."""
    completed = subprocess.run(
        [sys.executable, "main.py", *args],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    parsed = json.loads(completed.stdout)
    if not isinstance(parsed, dict):
        raise RuntimeError(f"Expected a JSON object from {' '.join(args)}")
    return parsed


def integer(value: object, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise RuntimeError(f"Expected integer '{name}' in command output")
    return value


def svg_text(x: float, y: float, value: object, size: int, color: str, weight: int = 400, anchor: str = "start") -> str:
    return f'<text x="{x}" y="{y}" fill="{color}" font-family="Inter, Arial, sans-serif" font-size="{size}" font-weight="{weight}" text-anchor="{anchor}">{escape(str(value))}</text>'


def bar(x: float, y: float, width: float, value: int, total: int, color: str, label: str, detail: str) -> str:
    ratio = value / total if total else 0
    filled = width * ratio
    return "\n".join((
        svg_text(x, y - 18, label, 17, COLORS["ink"], 650),
        svg_text(x + width, y - 18, detail, 17, COLORS["muted"], 600, "end"),
        f'<rect x="{x}" y="{y}" width="{width}" height="22" rx="11" fill="#e8eef4"/>',
        f'<rect x="{x}" y="{y}" width="{filled:.2f}" height="22" rx="11" fill="{color}"/>',
    ))


def panel(x: int, title: str, subtitle: str, body: str) -> str:
    return "\n".join((
        f'<rect x="{x}" y="{PANEL_Y}" width="{PANEL_WIDTH}" height="{PANEL_HEIGHT}" rx="18" fill="{COLORS["panel"]}" stroke="{COLORS["line"]}"/>',
        svg_text(x + 32, PANEL_Y + 48, title, 24, COLORS["ink"], 750),
        svg_text(x + 32, PANEL_Y + 78, subtitle, 15, COLORS["muted"]),
        body,
    ))


def render(benchmark: dict[str, object], evaluation: dict[str, object], comparison: dict[str, object]) -> str:
    benchmark_total = integer(benchmark.get("total"), "benchmark.total")
    benchmark_passed = integer(benchmark.get("passed"), "benchmark.passed")
    benchmark_results = benchmark.get("results")
    if not isinstance(benchmark_results, list):
        raise RuntimeError("Expected benchmark.results to be a list")
    attack_results = [item for item in benchmark_results if isinstance(item, dict) and item.get("expected") == "block"]
    attacks_total = len(attack_results)
    attacks_blocked = sum(item.get("passed") is True for item in attack_results)

    evaluation_total = integer(evaluation.get("total"), "evaluation.total")
    evaluation_passed = integer(evaluation.get("passed"), "evaluation.passed")
    unsafe_rejected = integer(evaluation.get("unsafe_rejected"), "evaluation.unsafe_rejected")
    evaluation_results = evaluation.get("results")
    if not isinstance(evaluation_results, list):
        raise RuntimeError("Expected evaluation.results to be a list")
    unsafe_total = sum(isinstance(item, dict) and item.get("expected") == "block" for item in evaluation_results)

    stateless = comparison.get("stateless_agent")
    forgeagent = comparison.get("forgeagent")
    if not isinstance(stateless, dict) or not isinstance(forgeagent, dict):
        raise RuntimeError("Expected both comparison conditions")
    stateless_new = integer(stateless.get("new_skills"), "stateless_agent.new_skills")
    stateless_reuses = integer(stateless.get("reuses"), "stateless_agent.reuses")
    forge_new = integer(forgeagent.get("new_skills"), "forgeagent.new_skills")
    forge_reuses = integer(forgeagent.get("reuses"), "forgeagent.reuses")

    trust_body = "\n".join((
        svg_text(PANEL_X[0] + 32, PANEL_Y + 138, f"{benchmark_passed} / {benchmark_total}", 52, COLORS["blue"], 800),
        svg_text(PANEL_X[0] + 32, PANEL_Y + 172, "entire trust-gate suite passed", 17, COLORS["muted"]),
        bar(PANEL_X[0] + 32, PANEL_Y + 245, PANEL_WIDTH - 64, attacks_blocked, attacks_total, COLORS["blue"], "Attack patterns blocked", f"{attacks_blocked} / {attacks_total}"),
        bar(PANEL_X[0] + 32, PANEL_Y + 330, PANEL_WIDTH - 64, benchmark_passed, benchmark_total, COLORS["mint"], "All benchmark checks passed", f"{benchmark_passed} / {benchmark_total}"),
        svg_text(PANEL_X[0] + 32, PANEL_Y + 455, "Source: python3 main.py --benchmark", 14, COLORS["muted"]),
    ))
    evaluation_body = "\n".join((
        svg_text(PANEL_X[1] + 32, PANEL_Y + 138, f"{evaluation_passed} / {evaluation_total}", 52, COLORS["mint"], 800),
        svg_text(PANEL_X[1] + 32, PANEL_Y + 172, "deterministic evaluation cases passed", 17, COLORS["muted"]),
        bar(PANEL_X[1] + 32, PANEL_Y + 245, PANEL_WIDTH - 64, evaluation_passed, evaluation_total, COLORS["mint"], "Evaluation cases passed", f"{evaluation_passed} / {evaluation_total}"),
        bar(PANEL_X[1] + 32, PANEL_Y + 330, PANEL_WIDTH - 64, unsafe_rejected, unsafe_total, COLORS["amber"], "Unsafe proposals rejected", f"{unsafe_rejected} / {unsafe_total}"),
        svg_text(PANEL_X[1] + 32, PANEL_Y + 455, "Source: python3 main.py --evaluate", 14, COLORS["muted"]),
    ))
    comparison_max = max(stateless_new, stateless_reuses, forge_new, forge_reuses, 1)
    chart_x, chart_y, chart_height = PANEL_X[2] + 48, PANEL_Y + 395, 185

    def comparison_bar(x: int, value: int, label: str, color: str) -> str:
        height = chart_height * value / comparison_max
        top = chart_y - height
        return "\n".join((
            f'<rect x="{x}" y="{top:.2f}" width="42" height="{height:.2f}" rx="6" fill="{color}"/>',
            svg_text(x + 21, top - 10, value, 15, COLORS["ink"], 750, "middle"),
            svg_text(x + 21, chart_y + 28, label, 13, COLORS["muted"], 600, "middle"),
        ))

    comparison_body = "\n".join((
        svg_text(PANEL_X[2] + 32, PANEL_Y + 138, "Recurring-workflow comparison", 22, COLORS["ink"], 750),
        svg_text(PANEL_X[2] + 32, PANEL_Y + 172, "One fresh --compare run", 17, COLORS["muted"]),
        f'<line x1="{chart_x}" y1="{chart_y}" x2="{PANEL_X[2] + PANEL_WIDTH - 32}" y2="{chart_y}" stroke="{COLORS["line"]}"/>',
        comparison_bar(chart_x + 40, stateless_new, "new", COLORS["blue"]),
        comparison_bar(chart_x + 94, stateless_reuses, "reuses", COLORS["blue"]),
        comparison_bar(chart_x + 230, forge_new, "new", COLORS["mint"]),
        comparison_bar(chart_x + 284, forge_reuses, "reuses", COLORS["mint"]),
        svg_text(chart_x + 68, chart_y + 70, "STATELESS", 14, COLORS["blue"], 750, "middle"),
        svg_text(chart_x + 258, chart_y + 70, "FORGEAGENT", 14, COLORS["mint"], 750, "middle"),
        svg_text(PANEL_X[2] + 32, PANEL_Y + 520, "Source: python3 main.py --compare", 14, COLORS["muted"]),
    ))
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}" role="img" aria-labelledby="title desc">
  <title id="title">ForgeAgent benchmark evidence</title>
  <desc id="desc">A reproducible visualization generated from local benchmark, evaluation, and comparison commands.</desc>
  <rect width="100%" height="100%" fill="{COLORS["page"]}"/>
  {svg_text(40, 68, "ForgeAgent — measured offline evidence", 34, COLORS["ink"], 800)}
  {svg_text(40, 104, "Generated directly from three zero-API-cost local commands", 18, COLORS["muted"])}
  {panel(PANEL_X[0], "Trust-gate benchmark", "Attack patterns and policy checks", trust_body)}
  {panel(PANEL_X[1], "Evaluation arena", "Key-free deterministic suite", evaluation_body)}
  {panel(PANEL_X[2], "Capability reuse", "Same recurring workflow", comparison_body)}
</svg>'''


def main() -> None:
    benchmark = run_json("--benchmark")
    evaluation = run_json("--evaluate")
    comparison = run_json("--compare")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(render(benchmark, evaluation, comparison), encoding="utf-8")
    print(f"Generated {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
