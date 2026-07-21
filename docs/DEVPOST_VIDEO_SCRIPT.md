# ForgeAgent Devpost demo — 2 minutes 45 seconds

## Recording promise

This is a real, local ForgeAgent run: the Foundry, SQLite memory, policy gate,
sandbox proof, approval state, quarantine, repair, and reuse all execute on
camera. Do **not** say that GPT-5.6 generated this run; the API-backed provider
is optional and was not used for this recording.

## Before recording

1. Use a 1920×1080 screen recording and increase terminal/browser zoom to a
   readable size.
2. Open two terminal panes in the repository root:

   ```bash
   cd /Users/yashas/Downloads/ForageAgent
   python3 main.py --serve
   ```

3. Open `http://127.0.0.1:8787/judge` in a browser. Keep the terminal visible
   in a second pane for the command proof shots below.
4. Do not show API keys, terminal history containing secrets, or an unfinished
   browser tab.

## Time-coded shot list and narration

| Time | Show | Say |
| --- | --- | --- |
| 0:00–0:08 | ForgeAgent hero / README title. | “AI coding agents can write tools quickly. The missing question is: who proves a generated tool is safe before another agent reuses it?” |
| 0:08–0:18 | Architecture image or the `/judge` page header. | “ForgeAgent is a capability memory layer for coding agents. A capability is not remembered because a model produced it—it is remembered only after policy, isolated proof, and governance.” |
| 0:18–0:28 | `/judge`: click **Reset** and then **Forge**. | “Here is a real local Foundry run. An agent requests an invoice-ID extractor that does not yet exist.” |
| 0:28–0:43 | Let planner, builder, security, evaluator, and governor events appear. | “The Foundry creates a constrained candidate, threat-models it, runs normal, edge, contract, and adversarial proof cases in isolation, then stores the evidence.” |
| 0:43–0:53 | Show the pending evidence package and click **Approve**. | “Production policy does not silently promote it. A named human decision turns this proven candidate into trusted memory.” |
| 0:53–1:03 | Click **Reuse**. | “Now a later agent gets the trusted capability from persistent platform memory. It does not rebuild or re-verify the same tool.” |
| 1:03–1:18 | Click **Report failure**. Show quarantine/blocked state. | “Trust is reversible. We reproduce a duplicate-ID defect, retain it as regression evidence, and immediately quarantine the broken version.” |
| 1:18–1:32 | Click **Repair**, then **Reuse**. | “The Foundry repairs the candidate. Version two must pass the inherited failure case before it can be trusted and reused again.” |
| 1:32–1:43 | Switch to terminal; run `python3 main.py --benchmark`. | “This is not a success-only story. The trust gate blocks filesystem access, network imports, dynamic execution, import-alias bypasses, and invalid tool contracts.” |
| 1:43–1:53 | Run `python3 -m unittest tests.test_sandbox_security -v`. | “These are regression tests for real sandbox escape classes: import aliasing, dunder traversal, and dynamic attribute access.” |
| 1:53–2:05 | Run `python3 main.py --compare`. | “Across the same recurring workload, a stateless agent repeatedly creates skills. ForgeAgent verifies once and reuses trusted capability memory.” |
| 2:05–2:16 | Run `python3 main.py --evaluate`. | “The deterministic evaluation arena runs 50 cases and records unsafe-proposal rejection as a first-class metric.” |
| 2:16–2:30 | Return to the architecture image or dashboard graph. | “Developers can connect through MCP from Codex, Cursor, or Claude Code. ForgeAgent supplies the governed capability layer; the coding agent keeps its own workflow.” |
| 2:30–2:45 | Show README evidence block and GitHub repository URL. | “ForgeAgent does not ask teams to trust an agent because it sounds capable. It gives agents a system for earning, proving, governing, repairing, and reusing capabilities.” |

## Exact commands for terminal shots

```bash
python3 main.py --benchmark
python3 -m unittest tests.test_sandbox_security -v
python3 main.py --compare
python3 main.py --evaluate
```

## YouTube upload package

**Title**

`ForgeAgent — AI capabilities that earn trust before reuse | OpenAI Build Week`

**Description**

```text
ForgeAgent is a governed capability-memory layer for AI coding agents.

In this real local demo, an agent requests a missing invoice-ID extractor. ForgeAgent creates a constrained candidate, proves it in isolation, requires human approval, reuses it from persistent memory, quarantines a reproduced failure, repairs it as v2, and reuses the repaired version.

The project is offline-first: this video uses no API key. The optional live-provider path can propose unfamiliar capabilities, while ForgeAgent remains responsible for policy, proof, governance, versioning, audit, and reuse.

Try the interactive demo: https://yashasm18.github.io/ForgeAgent/
Source and evidence: https://github.com/Yashasm18/ForgeAgent
```

**Suggested YouTube chapters**

```text
00:00 The trust problem
00:18 Forge, prove, and approve
00:53 Reuse, quarantine, and repair
01:32 Security proof
01:53 Measured reuse advantage
02:16 MCP developer workflow
02:30 Why ForgeAgent
```

## Final recording checks

- Keep the runtime under **2:45**.
- Show the full forge → approve → reuse → quarantine → repair → reuse sequence.
- Narrate only results visible on screen.
- Use the current command output; do not read historical timing values aloud.
- Upload as **Unlisted** to YouTube first, watch it once, then place that URL in Devpost’s video field.
