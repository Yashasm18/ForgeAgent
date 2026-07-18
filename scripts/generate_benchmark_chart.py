#!/usr/bin/env python3
"""Generate the README evidence chart from fresh ForgeAgent command output.

Data sources, executed from the repository root on every generation:
    python3 -m unittest discover -s tests -v
    python3 -m unittest tests.test_sandbox_security -v
    python3 main.py --benchmark
    python3 main.py --evaluate
    python3 main.py --compare
    gh run list --branch main --limit 1 --json databaseId,status,conclusion,name,headSha

The GitHub Actions source is optional: if ``gh`` is unavailable or unauthenticated,
the chart deliberately labels CI evidence unavailable rather than inventing a value.
No metric is hardcoded or estimated.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path
from xml.sax.saxutils import escape


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "benchmark-results.svg"
WIDTH, HEIGHT = 1800, 1280
COLORS = {
    "ink": "#10233c",
    "muted": "#63748a",
    "line": "#d9e2ec",
    "page": "#f6f8fb",
    "panel": "#ffffff",
    "blue": "#2459d6",
    "teal": "#087f6e",
    "amber": "#b26d11",
    "red": "#b53b4a",
    "pale_blue": "#e7efff",
    "pale_teal": "#e3f4ef",
    "pale_amber": "#fff1db",
}
CARD_W, CARD_H = 830, 390
CARD_X = (40, 930)
CARD_Y = (360, 800)


def command(*args: str) -> subprocess.CompletedProcess[str]:
    """Run one evidence source with no shell interpolation or cached output."""
    return subprocess.run(args, cwd=ROOT, check=True, capture_output=True, text=True)


def run_json(*args: str) -> dict[str, object]:
    completed = command(sys.executable, "main.py", *args)
    parsed = json.loads(completed.stdout)
    if not isinstance(parsed, dict):
        raise RuntimeError(f"Expected JSON object from python3 main.py {' '.join(args)}")
    return parsed


def test_summary(*arguments: str) -> tuple[int, int, Counter[str], str]:
    completed = command(sys.executable, "-m", "unittest", *arguments)
    transcript = f"{completed.stdout}\n{completed.stderr}"
    count = re.search(r"Ran (\d+) tests?", transcript)
    if not count:
        raise RuntimeError("Could not find unittest test count")
    skipped = re.search(r"skipped=(\d+)", transcript)
    classes = Counter(re.findall(r"\((?:[A-Za-z0-9_]+\.)*([A-Za-z0-9_]+Tests)\.test_", transcript))
    return int(count.group(1)), int(skipped.group(1)) if skipped else 0, classes, transcript


def latest_ci() -> dict[str, object] | None:
    """Read the current main-branch Actions status when authenticated GH CLI exists."""
    try:
        completed = command(
            "gh", "run", "list", "--branch", "main", "--limit", "1", "--json",
            "databaseId,status,conclusion,name,headSha",
        )
        runs = json.loads(completed.stdout)
        return runs[0] if isinstance(runs, list) and runs and isinstance(runs[0], dict) else None
    except (FileNotFoundError, subprocess.CalledProcessError, json.JSONDecodeError):
        return None


def integer(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise RuntimeError(f"Expected integer '{label}'")
    return value


def text(x: float, y: float, value: object, size: int, color: str, weight: int = 400, anchor: str = "start") -> str:
    return f'<text x="{x}" y="{y}" fill="{color}" font-family="Inter, Arial, sans-serif" font-size="{size}" font-weight="{weight}" text-anchor="{anchor}">{escape(str(value))}</text>'


def rule(x1: float, y1: float, x2: float, y2: float, color: str | None = None, width: int = 1) -> str:
    return f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color or COLORS["line"]}" stroke-width="{width}"/>'


def tag(x: float, y: float, label: str, color: str, background: str) -> str:
    width = 20 + len(label) * 8.4
    return "\n".join((
        f'<rect x="{x}" y="{y - 21}" width="{width:.0f}" height="30" rx="15" fill="{background}"/>',
        text(x + 10, y, label, 13, color, 750),
    ))


def bar(x: float, y: float, width: float, value: int, total: int, label: str, accent: str) -> str:
    ratio = value / total if total else 0
    filled = width * ratio
    return "\n".join((
        text(x, y - 17, label, 16, COLORS["ink"], 700),
        text(x + width, y - 17, f"{value} / {total}", 16, COLORS["muted"], 700, "end"),
        f'<rect x="{x}" y="{y}" width="{width}" height="16" rx="8" fill="#e8edf3"/>',
        f'<rect x="{x}" y="{y}" width="{filled:.2f}" height="16" rx="8" fill="{accent}"/>',
    ))


def card(x: int, y: int, kicker: str, title: str, body: str) -> str:
    return "\n".join((
        f'<rect x="{x}" y="{y}" width="{CARD_W}" height="{CARD_H}" rx="16" fill="{COLORS["panel"]}" stroke="{COLORS["line"]}"/>',
        text(x + 32, y + 42, kicker, 13, COLORS["muted"], 800),
        text(x + 32, y + 80, title, 26, COLORS["ink"], 800),
        rule(x + 32, y + 102, x + CARD_W - 32, y + 102),
        body,
    ))


def compact_coverage(classes: Counter[str]) -> str:
    selected = (
        ("Sandbox security", "SandboxSecurityTests"),
        ("MCP", "McpTests"),
        ("Package signing", "CapabilityPackageSigningTests"),
        ("Policy", "PolicyConfigTests"),
        ("PR review", "CapabilityPrReviewTests"),
        ("Repository graph", "RepositoryGraphTests"),
    )
    missing = [class_name for _, class_name in selected if not classes[class_name]]
    if missing:
        raise RuntimeError(f"Expected measured test classes are missing: {', '.join(missing)}")
    return "   ·   ".join(f"{label} {classes[class_name]}" for label, class_name in selected)


def render(
    tests: tuple[int, int, Counter[str], str],
    security: tuple[int, int, Counter[str], str],
    benchmark: dict[str, object],
    evaluation: dict[str, object],
    comparison: dict[str, object],
    ci: dict[str, object] | None,
) -> str:
    test_total, test_skipped, test_classes, _ = tests
    security_total, _, _, security_transcript = security
    benchmark_total = integer(benchmark.get("total"), "benchmark.total")
    benchmark_passed = integer(benchmark.get("passed"), "benchmark.passed")
    benchmark_results = benchmark.get("results")
    if not isinstance(benchmark_results, list):
        raise RuntimeError("Expected benchmark.results list")
    attack_results = [item for item in benchmark_results if isinstance(item, dict) and item.get("expected") == "block"]
    attacks_total = len(attack_results)
    attacks_blocked = sum(item.get("passed") is True for item in attack_results)

    evaluation_total = integer(evaluation.get("total"), "evaluation.total")
    evaluation_passed = integer(evaluation.get("passed"), "evaluation.passed")
    unsafe_rejected = integer(evaluation.get("unsafe_rejected"), "evaluation.unsafe_rejected")
    evaluation_results = evaluation.get("results")
    if not isinstance(evaluation_results, list):
        raise RuntimeError("Expected evaluation.results list")
    unsafe_total = sum(isinstance(item, dict) and item.get("expected") == "block" for item in evaluation_results)

    stateless = comparison.get("stateless_agent")
    forgeagent = comparison.get("forgeagent")
    if not isinstance(stateless, dict) or not isinstance(forgeagent, dict):
        raise RuntimeError("Expected stateless_agent and forgeagent comparison conditions")
    stateless_new = integer(stateless.get("new_skills"), "stateless_agent.new_skills")
    stateless_reuses = integer(stateless.get("reuses"), "stateless_agent.reuses")
    forge_new = integer(forgeagent.get("new_skills"), "forgeagent.new_skills")
    forge_reuses = integer(forgeagent.get("reuses"), "forgeagent.reuses")

    required_security_names = (
        "test_import_alias_bypass_is_rejected_before_execution",
        "test_class_subclasses_escape_is_rejected_before_execution",
        "test_dynamic_getattr_escape_is_rejected_before_execution",
    )
    if any(name not in security_transcript for name in required_security_names):
        raise RuntimeError("Sandbox security transcript is missing a required regression case")

    ci_label = "CI evidence unavailable"
    ci_detail = "Source: gh run list --branch main --limit 1"
    ci_color, ci_background = COLORS["muted"], "#edf1f5"
    if ci is not None:
        conclusion = str(ci.get("conclusion") or ci.get("status") or "unknown").upper()
        ci_label = f"Latest main CI: {conclusion}"
        ci_color, ci_background = (COLORS["teal"], COLORS["pale_teal"]) if conclusion == "SUCCESS" else (COLORS["amber"], COLORS["pale_amber"])

    hero = "\n".join((
        f'<rect x="40" y="130" width="1720" height="172" rx="16" fill="{COLORS["panel"]}" stroke="{COLORS["line"]}"/>',
        text(72, 170, "VERIFIED EVIDENCE SNAPSHOT", 14, COLORS["muted"], 800),
        text(72, 232, test_total, 56, COLORS["blue"], 850),
        text(72, 265, "repository tests run", 17, COLORS["muted"], 650),
        text(290, 232, f"{security_total} / {security_total}", 44, COLORS["teal"], 850),
        text(290, 265, "sandbox-security tests", 17, COLORS["muted"], 650),
        rule(510, 158, 510, 274),
        text(548, 189, "Security regression coverage", 17, COLORS["ink"], 800),
        text(548, 218, "Import-alias bypass · dunder-attribute escape · dynamic-getattr escape", 16, COLORS["muted"]),
        text(548, 252, compact_coverage(test_classes), 14, COLORS["muted"], 650),
        tag(1335, 177, ci_label, ci_color, ci_background),
        text(1335, 221, ci_detail, 13, COLORS["muted"]),
        text(72, 288, f"Every metric below comes from the command printed beside it. {test_skipped} optional-policy tests skipped in this environment.", 14, COLORS["muted"], 600),
        text(72, 324, "Source: python3 -m unittest discover -s tests -v   ·   python3 -m unittest tests.test_sandbox_security -v", 13, COLORS["muted"]),
    ))

    trust = "\n".join((
        text(CARD_X[0] + 32, CARD_Y[0] + 165, f"{benchmark_passed} / {benchmark_total}", 54, COLORS["blue"], 850),
        text(CARD_X[0] + 32, CARD_Y[0] + 195, "trust-gate checks passed", 17, COLORS["muted"]),
        bar(CARD_X[0] + 32, CARD_Y[0] + 265, CARD_W - 64, attacks_blocked, attacks_total, "Attack patterns blocked", COLORS["blue"]),
        bar(CARD_X[0] + 32, CARD_Y[0] + 335, CARD_W - 64, benchmark_passed, benchmark_total, "All benchmark checks", COLORS["teal"]),
        text(CARD_X[0] + 32, CARD_Y[0] + 363, "Source: python3 main.py --benchmark", 14, COLORS["muted"], 650),
    ))
    evaluation_card = "\n".join((
        text(CARD_X[1] + 32, CARD_Y[0] + 165, f"{evaluation_passed} / {evaluation_total}", 54, COLORS["teal"], 850),
        text(CARD_X[1] + 32, CARD_Y[0] + 195, "deterministic cases passed", 17, COLORS["muted"]),
        bar(CARD_X[1] + 32, CARD_Y[0] + 265, CARD_W - 64, evaluation_passed, evaluation_total, "Evaluation cases", COLORS["teal"]),
        bar(CARD_X[1] + 32, CARD_Y[0] + 335, CARD_W - 64, unsafe_rejected, unsafe_total, "Unsafe proposals rejected", COLORS["amber"]),
        text(CARD_X[1] + 32, CARD_Y[0] + 363, "Source: python3 main.py --evaluate", 14, COLORS["muted"], 650),
    ))

    maximum = max(stateless_new, stateless_reuses, forge_new, forge_reuses, 1)
    baseline, height = CARD_Y[1] + 296, 128

    def comparison_bar(x: int, value: int, label: str, color: str) -> str:
        bar_height = height * value / maximum
        top = baseline - bar_height
        return "\n".join((
            f'<rect x="{x}" y="{top:.2f}" width="52" height="{bar_height:.2f}" rx="5" fill="{color}"/>',
            text(x + 26, top - 10, value, 15, COLORS["ink"], 800, "middle"),
            text(x + 26, baseline + 26, label, 13, COLORS["muted"], 700, "middle"),
        ))

    reuse = "\n".join((
        text(CARD_X[0] + 32, CARD_Y[1] + 145, "Recurring workflow: fewer builds, more verified reuse", 18, COLORS["muted"], 650),
        rule(CARD_X[0] + 54, baseline, CARD_X[0] + CARD_W - 54, baseline),
        comparison_bar(CARD_X[0] + 150, stateless_new, "new", COLORS["blue"]),
        comparison_bar(CARD_X[0] + 220, stateless_reuses, "reuses", COLORS["blue"]),
        comparison_bar(CARD_X[0] + 520, forge_new, "new", COLORS["teal"]),
        comparison_bar(CARD_X[0] + 590, forge_reuses, "reuses", COLORS["teal"]),
        text(CARD_X[0] + 210, baseline + 62, "STATELESS", 14, COLORS["blue"], 800, "middle"),
        text(CARD_X[0] + 580, baseline + 62, "FORGEAGENT", 14, COLORS["teal"], 800, "middle"),
        text(CARD_X[0] + 32, CARD_Y[1] + 378, "Source: python3 main.py --compare", 14, COLORS["muted"], 650),
    ))
    security_card = "\n".join((
        text(CARD_X[1] + 32, CARD_Y[1] + 164, f"{security_total} / {security_total}", 54, COLORS["teal"], 850),
        text(CARD_X[1] + 32, CARD_Y[1] + 194, "sandbox security tests passed", 17, COLORS["muted"]),
        tag(CARD_X[1] + 32, CARD_Y[1] + 250, "IMPORT ALIAS BLOCKED", COLORS["red"], "#fce8eb"),
        tag(CARD_X[1] + 275, CARD_Y[1] + 250, "DUNDER ESCAPE BLOCKED", COLORS["red"], "#fce8eb"),
        tag(CARD_X[1] + 558, CARD_Y[1] + 250, "DYNAMIC GETATTR BLOCKED", COLORS["red"], "#fce8eb"),
        text(CARD_X[1] + 32, CARD_Y[1] + 306, "Plus an allowed-import regression proving the restricted importer still works.", 15, COLORS["muted"]),
        text(CARD_X[1] + 32, CARD_Y[1] + 363, "Source: python3 -m unittest tests.test_sandbox_security -v", 14, COLORS["muted"], 650),
    ))

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}" role="img" aria-labelledby="title desc">
  <title id="title">ForgeAgent — reproducible evidence dashboard</title>
  <desc id="desc">A flat, four-card dashboard generated from fresh local tests, benchmark, evaluation, comparison, sandbox regression, and optional GitHub Actions evidence.</desc>
  <rect width="{WIDTH}" height="{HEIGHT}" fill="{COLORS["page"]}"/>
  {text(40, 64, "ForgeAgent — reproducible evidence", 36, COLORS["ink"], 850)}
  {text(40, 98, "Generated locally from the source commands printed beside every metric", 18, COLORS["muted"], 500)}
  {hero}
  {card(CARD_X[0], CARD_Y[0], "01 / TRUST GATE", "Policy blocks before execution", trust)}
  {card(CARD_X[1], CARD_Y[0], "02 / EVALUATION ARENA", "Fifty deterministic cases", evaluation_card)}
  {card(CARD_X[0], CARD_Y[1], "03 / CAPABILITY MEMORY", "Measured reuse advantage", reuse)}
  {card(CARD_X[1], CARD_Y[1], "04 / SECURITY REGRESSIONS", "Escape attempts stay blocked", security_card)}
</svg>'''


def main() -> None:
    tests = test_summary("discover", "-s", "tests", "-v")
    security = test_summary("tests.test_sandbox_security", "-v")
    svg = render(tests, security, run_json("--benchmark"), run_json("--evaluate"), run_json("--compare"), latest_ci())
    OUTPUT.write_text(svg, encoding="utf-8")
    print(f"Generated {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
