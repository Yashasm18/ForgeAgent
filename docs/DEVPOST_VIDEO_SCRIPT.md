# ForgeAgent Devpost demo — 2 minutes 45 seconds

## Recording promise

This is a real, local ForgeAgent run: the Foundry, SQLite memory, policy gate,
sandbox proof, approval state, quarantine, repair, and reuse all execute on
camera. Do **not** say that GPT-5.6 generated this run; the API-backed provider
is optional and was not used for this recording.

## The Codex + GPT-5.6 story

Open with this distinction: **Codex helped build and harden ForgeAgent; GPT-5.6
supplies optional live capability intelligence; ForgeAgent is the system that
makes that intelligence safe to reuse.** Do not position ForgeAgent as merely
another chat wrapper.

- **GPT-5.6 Terra** is the live Foundry option for a complex unfamiliar task.
  It can consume the task plus matched repository context, generate a
  constrained capability proposal, explain whether it extends existing code,
  and author adversarial proof cases.
- **GPT-5.6 Luna** can use the exact same governed provider contract for a
  lower-cost, faster iteration. ForgeAgent does not automatically route between
  Terra and Luna: the developer selects the model explicitly.
- **Codex, Cursor, and Claude Code** all integrate through the same MCP server.
  Their model can propose work; ForgeAgent owns proof, policy, governance,
  versioning, audit, and reuse.

If a funded API key becomes available, record this exact Terra command once
and replace the offline-provider explanation in the video with its real output:

```bash
python3 main.py --foundry-task "Extract unique invoice IDs in INV-<digits> format" \
  --payload '{"text":"Invoices INV-2048, INV-2048 and INV-9910 require review."}' \
  --foundry-live --provider openai --model gpt-5.6-terra --adversarial-proof
```

To demonstrate a lower-cost Luna iteration, change only the model flag to
`--model gpt-5.6-luna`. Never represent an offline run as a live GPT run.

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
| 0:00–0:10 | Codex app beside ForgeAgent hero. | “We used Codex to build and harden ForgeAgent. But the product is not a coding demo: it is the trust layer for agents that write and run code.” |
| 0:10–0:22 | Architecture image. | “GPT-5.6 provides capability intelligence; ForgeAgent supplies repository context, policy, isolated proof, governance, and persistent memory. Any coding agent reaches this through MCP.” |
| 0:22–0:38 | **If funded:** real Terra terminal command and result. **Otherwise:** provider section in README plus `/judge`. | “Terra is the deep live Foundry option for complex new capabilities. Luna uses the identical governed contract for lower-cost iteration. The developer explicitly chooses the model.” |
| 0:38–0:50 | `/judge`: click **Reset** and then **Forge**. | “Here is a real local Foundry run. An agent requests an invoice-ID extractor that does not yet exist.” |
| 0:50–1:04 | Let planner, builder, security, evaluator, and governor events appear. | “The Foundry creates a constrained candidate, threat-models it, runs proof cases in isolation, then stores the evidence.” |
| 1:04–1:13 | Show pending evidence package and click **Approve**. | “Production policy does not silently promote it. A named human decision turns this proven candidate into trusted memory.” |
| 1:13–1:23 | Click **Reuse**. | “Now a later agent gets the trusted capability from persistent platform memory. It does not rebuild or re-verify the same tool.” |
| 1:23–1:37 | Click **Report failure**. Show quarantine/blocked state. | “Trust is reversible. We reproduce a duplicate-ID defect, retain it as regression evidence, and immediately quarantine the broken version.” |
| 1:37–1:49 | Click **Repair**, then **Reuse**. | “The Foundry repairs the candidate. Version two must pass the inherited failure case before it can be trusted and reused again.” |
| 1:49–2:01 | Switch to terminal; run `python3 main.py --benchmark`. | “The trust gate blocks filesystem access, network imports, dynamic execution, import-alias bypasses, and invalid tool contracts.” |
| 2:01–2:13 | Run `python3 main.py --compare`, then `python3 main.py --evaluate`. | “A stateless agent creates 36 skills. ForgeAgent creates four and reuses 32; its key-free evaluation passes 50 cases and rejects 10 unsafe proposals.” |
| 2:13–2:30 | Return to architecture or dashboard graph. | “Codex, Cursor, and Claude Code can call ForgeAgent through MCP. They receive either a verified capability or a governed proposal awaiting proof and approval.” |
| 2:30–2:45 | README evidence block and GitHub repository URL. | “ForgeAgent gives GPT-powered coding agents a system for earning, proving, governing, repairing, and reusing capabilities—without silently expanding permissions.” |

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

The project is offline-first: this video uses no API key. With a funded key,
GPT-5.6 Terra or Luna can propose unfamiliar capabilities through the optional
live-provider path; ForgeAgent remains responsible for policy, proof,
governance, versioning, audit, and reuse.

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
