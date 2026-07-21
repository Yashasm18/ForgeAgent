#!/usr/bin/env python3
"""Run ForgeAgent's complete real trust lifecycle in a recording-friendly form.

This is deliberately a thin presenter over :class:`forgeagent.judge_mode.JudgeMode`.
It does not mock a model response, invent a result, or bypass ForgeAgent's
Foundry, governance, SQLite memory, sandbox proof, feedback, or repair paths.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from forgeagent.judge_mode import JUDGE_PAYLOAD, JUDGE_TASK, JudgeMode


def _line(label: str, detail: str) -> None:
    print(f"{label:<10} {detail}", flush=True)


def _pause(seconds: float) -> None:
    if seconds:
        time.sleep(seconds)


def _council(outcome: dict[str, object]) -> None:
    for decision in outcome.get("council", []):
        if not isinstance(decision, dict):
            continue
        _line(str(decision.get("role", "council")).upper(), str(decision.get("detail", "")))


def run(pause: float) -> None:
    root = Path(tempfile.mkdtemp(prefix="forgeagent-video-"))
    mode = JudgeMode(root, repository_root=ROOT)
    try:
        print("═" * 72)
        print(" FORGEAGENT | governed capability memory: complete live lifecycle")
        print("═" * 72)
        _line("TASK", JUDGE_TASK)
        _line("PAYLOAD", str(JUDGE_PAYLOAD))
        print()

        print("[1/6] AGENT REQUESTS A MISSING CAPABILITY")
        forged = mode.forge()
        _council(forged)
        proof = forged.get("proof", {})
        coverage = ", ".join(proof.get("coverage", [])) if isinstance(proof, dict) else "unavailable"
        _line("PROOF", f"passed={proof.get('passed')} coverage={coverage}" if isinstance(proof, dict) else "unavailable")
        _line("MEMORY", "stored as PENDING -- production policy requires a human decision")
        _pause(pause)
        print()

        print("[2/6] HUMAN REVIEWS AND APPROVES THE PROVEN CAPABILITY")
        approved = mode.approve()
        _line("APPROVAL", f"{approved['name']}@v{approved['version']} is now {approved['state']}")
        _pause(pause)
        print()

        print("[3/6] A LATER AGENT REUSES TRUSTED MEMORY -- NO REBUILD")
        reused = mode.reuse()
        _line("REUSE", f"source={reused['memory_source']} capability={reused['memory_record']['name']}@v{reused['memory_record']['version']}")
        _line("DRIFT", f"retained contract replay {reused['drift_check']['status']}")
        _line("RESULT", str(reused["result"]))
        _pause(pause)
        print()

        print("[4/6] A REAL REPRODUCED FAILURE REVOKES TRUST")
        feedback = mode.report_failure()
        _line("ACTUAL", str(feedback["execution"]["actual_output"]))
        _line("EXPECTED", "['INV-2048']")
        _line("GOVERNANCE", f"reproduced mismatch={feedback['status']}; quarantined={feedback['quarantined']}")
        try:
            mode.reuse()
        except ValueError as exc:
            _line("BLOCKED", str(exc))
        _pause(pause)
        print()

        print("[5/6] FOUNDRY REPAIRS THE CAPABILITY AGAINST THE RETAINED FAILURE")
        repaired = mode.repair()
        state = mode.state()
        coverage = ", ".join(state["evidence"]["proof"]["coverage"])
        _line("REPAIR", f"{repaired['name']}@v{repaired['version']} is {repaired['state']}")
        _line("PROOF", f"re-proved with inherited coverage={coverage}")
        _pause(pause)
        print()

        print("[6/6] ANOTHER AGENT REUSES THE REPAIRED VERSION")
        final = mode.reuse()
        _line("REUSE", f"source={final['memory_source']} capability={final['memory_record']['name']}@v{final['memory_record']['version']}")
        _line("DRIFT", f"retained contract replay {final['drift_check']['status']}")
        _line("RESULT", str(final["result"]))
        print()
        print("✓ COMPLETE: ForgeAgent compounds verified capabilities, not unverified code.")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the recording-friendly ForgeAgent lifecycle demo.")
    parser.add_argument("--pause", type=float, default=0.9, help="Seconds to pause after each live stage (default: 0.9).")
    args = parser.parse_args()
    run(max(0.0, args.pause))


if __name__ == "__main__":
    main()
