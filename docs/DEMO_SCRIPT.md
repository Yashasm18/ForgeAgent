# ForgeAgent — 2:30 Devpost demo script

Record a fresh terminal and browser session. Do not claim a live model call in
the key-free paths. If a command shows different elapsed timing on your
machine, narrate the number actually visible on screen rather than this
reference run.

## 0:00–0:10 — The problem

**Visual:** ForgeAgent README title or hosted hero.

**Narration:** “Coding agents can learn tools at runtime, but without a trust
layer they silently accumulate generated code that nobody proved safe. ForgeAgent
makes a skill earn memory before another agent can reuse it.”

## 0:10–0:40 — Create once, reuse after proof

**Terminal:**

```bash
python3 main.py --demo --reset
python3 main.py --demo
```

**Show:** the first run’s `GAP`, `BUILD`, `VERIFY`, and `TRUST` lines, then the
second run’s `REUSE` line.

**Narration:** “The first run creates only a verified capability. The second
does not regenerate it; it reuses the trusted version with its lineage.”

## 0:40–1:05 — Make the rejection visible

**Terminal:**

```bash
python3 main.py --benchmark
```

**Show:** `8 / 8` pass. Point to `import_alias_escape`, `dunder_escape`, and
`getattr_escape` as blocked with their precise policy findings.

**Narration:** “This is not a success-only demo. The trust gate blocks
filesystem, network, dynamic execution, missing contracts, and classic Python
sandbox escape attempts before they enter memory.”

## 1:05–1:35 — Hosted judge experience

**Browser:** [Forge Ledger](https://yashasm18.github.io/ForgeAgent/)

1. Click a graph node such as `pii_redactor@v1`.
2. Paste an incident containing an email, phone number, and `secret code 89789`.
3. Click **Run verified capabilities** and show the redacted ledger.
4. Open **Policy Attack Lab**, select **Filesystem access**, click
   **Evaluate candidate**.
5. Open **Production** and click **Run production preflight**.

**Narration:** “The hosted page is an honest browser demonstration. It shows
the evidence trail and production admission policy, while the repository holds
the actual subprocess and container enforcement.”

## 1:35–1:55 — Developer-tool integration

**Terminal:**

```bash
claude mcp add-json forgeagent-foundry \
  '{"type":"stdio","command":"python3","args":["/absolute/path/to/ForgeAgent/mcp_server.py"]}' \
  --scope project
claude mcp list
```

**Show:** the registered ForgeAgent server, then ask the coding agent:

```text
Inspect ForgeAgent capability memory before creating an invoice-ID extractor.
```

**Narration:** “Codex, Cursor, or Claude Code keeps its normal coding loop;
ForgeAgent supplies the governed capability layer through MCP.”

## 1:55–2:15 — Measured proof

**Terminal:**

```bash
python3 main.py --compare
python3 main.py --evaluate
```

**Recorded reference run:** stateless agent created 6 skills with 0 reuses in
352.0 ms; ForgeAgent created 3 skills with 3 reuses in 258.5 ms. That is 26.6%
lower elapsed time in that local run. Evaluation passed 50/50 deterministic
cases, rejected 10 unsafe proposals, made no API calls, and reported $0 API
cost. Use the numbers your own run prints when recording.

## 2:15–2:30 — Close

**Visual:** Forge Ledger graph or README proof block.

**Narration:** “ForgeAgent does not ask you to trust an agent because it sounds
capable. It gives agents a durable system for earning, proving, governing, and
reusing capabilities.”
