# ForgeAgent — verified skill memory for AI agents

> GPT-5.6 may propose a new agent capability. ForgeAgent decides whether it has
> earned trust.

## Live judge demo

**[Open the Forge Ledger →](https://yashasm18.github.io/ForageAgent/)** — a
no-install, judge-facing walkthrough of ForgeAgent. It presents the method,
clickable **ForageGraph**, an interactive browser capability run, the platform
governance model, an attack lab, and evidence from the evaluation suite.

Long-running agents need to acquire small capabilities as work changes, but
blindly executing generated code creates a memory full of unproven behavior.
ForgeAgent turns each capability gap into a disciplined loop: **propose →
policy-check → isolate → prove → persist → reuse**.

## Why it matters

An agent can now get better over time without quietly accumulating unverified
code. Every saved skill has source, deterministic test evidence, provenance,
reuse history, and an append-only decision record. Broken or policy-violating
candidates are rejected before they can enter memory.

## Quick demo (no API key)

```bash
python3 main.py --demo --reset
python3 main.py --demo
python3 main.py --serve
python3 main.py --benchmark
python3 main.py --evaluate
python3 main.py --platform-demo
python3 main.py --showcase --reset
python3 main.py --autonomy-demo --reset
python3 main.py --autonomy-demo
python3 main.py --compare
```

Open `http://127.0.0.1:8787` to see the **Forge Ledger**. The first demo run
creates two curated offline skills; the second proves that verified memory is
reused. The curated mode is intentionally labelled as a recording fallback—it
does not claim to be a live model call.

## Hosted judge demo

`demo/` is a no-install, static Forge Ledger designed for the Devpost
**judge-testing** field. Its design deliberately separates the claims into a
short judge path: understand the capability graph, run a private incident
through the trusted chain, inspect governance and marketplace boundaries, then
try an unsafe or regressing proposal in the **Policy Attack Lab**. Neither the
hosted page nor its interactive demo requires an API key.

The hosted interactive run is deterministic: paste an incident and execute PII
redaction, risk triage, and feedback-term extraction in the browser. The
ForageGraph is clickable and time-replayable; it shows the task, selected
capabilities, isolated proof, and audit receipt rather than a generic codebase
map. The attack lab makes filesystem access, network access, invalid contracts,
and post-promotion regressions visible as policy/proof decisions.

The interactive redactor removes emails, phone numbers, card-like values, and
explicitly labelled secrets such as secret codes, passwords, OTPs, API keys,
access tokens, and secret messages. `incident_analysis.py` provides the same
structured, audit-safe analysis path for arbitrary incident text in Python.

Use the hosted demo here:

```text
https://yashasm18.github.io/ForageAgent/
```

GitHub Pages serves the static `demo/` directory from the published `gh-pages`
branch. The deployment workflow builds the artifact from `demo/`; after a
website change is merged to `main`, verify the Pages deployment has completed
before sharing the hosted link. The full local ledger remains available through
`python3 main.py --serve`.

The dashboard now also shows the **Evidence Trail**: every capability request,
policy rejection, verification result, trusted reuse, and execution is stored
in `data/audit_log.jsonl`.

`--benchmark` evaluates the trust gate against five representative cases:
safe code, filesystem access, network access, dynamic execution, and a broken
tool contract. `--showcase` is the recording-ready workflow: redact sensitive
support data, explain customer risk, and reuse those proven capabilities on the
next pass.

### Judge walkthrough

1. Open the hosted demo and click a ForageGraph node to inspect its proof and lineage.
2. In **Interactive capability run**, paste or select an incident and run the chain.
3. In **Persistent memory with a control plane**, review the promotion and marketplace boundaries.
4. In **Policy Attack Lab**, inject `Filesystem access` or `Regression after promotion`.
5. Use the repository commands below to reproduce the full local platform and evaluation evidence.

## Capability Graph and task recovery

ForgeAgent's capability graph is its native memory model. It maps user tasks
to capability gaps, verified skill versions, proof evidence, dependencies,
repairs, supersessions, and rollbacks. It is not a generic codebase graph: it
answers **why this agent can safely perform this task now**.

`--autonomy-demo` runs a dependent incident workflow. Each step first looks
for an active trusted skill. A gap triggers forging; a failed proposal triggers
up to two repair attempts; only a repaired candidate that passes every test is
promoted. Verified replacement versions retain the older version for rollback.

`--compare` executes the same multi-step workflow twice as a stateless agent
and twice with ForgeAgent's persistent memory, reporting new-skill creation,
reuse, and elapsed time.

With an OpenAI API key, ForgeAgent can also receive an unknown user task and
ask GPT-5.6 to produce the dependency plan itself:

```bash
python3 main.py --autonomous-task "Redact this incident, assess its customer risk, and summarize recurring terms" \
  --payload '{"text":"Ava at ava@example.com cannot access the dashboard and may cancel."}'
```

For each planned step, a missing capability triggers code-and-test generation;
a failed candidate triggers repair attempts; an accepted repair creates a new
version while preserving the earlier trusted version for rollback.

## Live GPT-5.6 forge

Set an OpenAI API key, then ask ForgeAgent for a genuinely new capability:

```bash
export OPENAI_API_KEY="your-key"
python3 main.py --forge "Extract order IDs, normalize their case, and return unique values" \
  --payload '{"text":"Orders: ab-12, AB-12 and xy-99"}'
```

ForgeAgent asks GPT-5.6 to return a constrained `run(payload)` function plus
edge-case tests. It performs AST policy checks and runs every test in a fresh,
timeout-bounded subprocess. Only a passing candidate is stored in
`data/tool_registry.json` and becomes reusable.

## Test

```bash
python3 -m unittest discover -s tests -v
```

## Safety scope

This is defense in depth for a hackathon project, not hardened containment for
hostile code. Generated tools run in a fresh subprocess with a timeout, a
temporary working directory, a minimal environment, a restricted builtins set,
and an import/operation policy. The policy gate is exposed separately before
execution and every decision is recorded. Production deployment would require
stronger OS/container isolation, network controls, and human review policies.

## Persistent platform, governance, and MCP

ForgeAgent now includes a local-first SQLite platform store (`data/platform.sqlite3`).
It persists team/project namespaces, capability versions, proof cases, trust scores,
approval decisions, rollback events, and audit receipts. It deliberately stores no
raw incident payloads in its receipts.

The **Capability Marketplace** exports a capability with its provenance and proof
evidence in a tamper-evident HMAC-SHA256 package. Imports always enter a human
approval inbox; an imported skill cannot silently become trusted in another project.

```bash
python3 main.py --platform-demo
python3 main.py --evaluate
python3 main.py --mcp
```

`--evaluate` runs 20 deterministic cases across allowed transforms, unsafe proposal
rejection, and privacy-first incident analysis. It reports measured outcomes only;
it does not invent latency, cost, or completion figures.

`--mcp` starts a stdio JSON-RPC MCP server. Configure a compatible client such as
Codex, Cursor, or Claude Code with `python3 /absolute/path/to/mcp_server.py`.
Copy and edit [`mcp.config.example.json`](mcp.config.example.json) for a
client configuration starting point.
It exposes `forge_list_capabilities`, `forge_get_audit_receipt`,
`forge_approval_inbox`, and `forge_decide_capability`. The MCP boundary provides
memory and governance operations only—it cannot execute a marketplace package.

The evaluation also includes an actual two-pass stateless-versus-ForgeAgent
comparison for the dependent incident workflow, reporting local elapsed time,
new capabilities, and verified reuse. API cost is deliberately reported as
`null` in key-free runs rather than invented.

Governance rules are explicit: low-risk, fully proven text transforms can be
auto-promoted; sensitive domains require human review; and external-action
capabilities can be permanently blocked. A human reviewer can approve, reject, or
roll back any version while the audit timeline remains intact.

## OpenAI Build Week evidence

ForgeAgent is entered in **Developer Tools**. See [HACKATHON_SCOPE.md](HACKATHON_SCOPE.md)
for the boundary between the earlier prototype and Build Week work.

Codex accelerated the architecture, safety lifecycle, dashboard, tests, and
submission materials. GPT-5.6 can be used at runtime, with server-side API
credentials, to propose constrained tool code and deterministic test cases.
The hosted GitHub Pages demo is deliberately key-free and uses no live model
call. The demo video will show both the successful forge path and a deliberate
policy/test rejection.

## Judge testing path

- Supported platform: macOS, Linux, or Windows with Python 3.10+.
- Dependencies: none beyond the Python standard library.
- Offline proof: `python3 main.py --demo --reset`.
- Live GPT-5.6 proof: set `OPENAI_API_KEY` and use `--forge` as above.
- Visual inspection: `python3 main.py --serve`.
- Verification snapshot: `python3 -m unittest discover -s tests -v`.
