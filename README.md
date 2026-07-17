# ForgeAgent — verified skill memory for AI agents

> GPT-5.6 may propose a new agent capability. ForgeAgent decides whether it has
> earned trust.

## Live judge demo

**[Open the Forge Ledger →](https://yashasm18.github.io/ForgeAgent/?v=57b69be)** — a
no-install judge walkthrough of ForgeAgent’s trust model. It includes a
clickable **ForageGraph**, an interactive browser capability run, a policy
attack lab, version lineage, and evidence-backed reuse.

Long-running agents need to acquire small capabilities as work changes, but
blindly executing generated code creates a memory full of unproven behavior.
ForgeAgent turns each capability gap into a disciplined loop: **propose →
policy-check → isolate → prove → persist → reuse**.

## Capability Foundry

ForgeAgent is now a **Capability Foundry**: a governed learning layer for
coding agents rather than a prompt-only assistant. Given a task, it builds a
repository intelligence graph, identifies whether a trusted capability already
exists, produces a constrained proposal, creates a threat model, runs proof
cases in isolation, records a governed decision, and either executes the
trusted capability or keeps the rejected evidence for review.

The Foundry Council makes that lifecycle explicit:

- **Planner** maps a task to a capability gap and dependency impact.
- **Builder** creates a constrained `run(payload)` tool.
- **Security** derives a threat model and checks the static policy boundary.
- **Evaluator** runs normal, edge, and contract proof cases in an isolated subprocess.
- **Governor** promotes, holds for review, rejects, or rolls back a version.

The local-first control plane uses SQLite for project namespaces, trust scores,
proof reports, approval decisions, audit receipts, and signed capability
packages. An optional live generator uses `gpt-5.6-terra`; the complete
offline lifecycle remains runnable without an API key.

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
python3 main.py --foundry-task "Find word frequency in this customer feedback" --payload '{"text":"tools tools reliable"}'
python3 main.py --repo-graph
python3 main.py --evaluate
python3 main.py --mcp
python3 main.py --showcase --reset
python3 main.py --autonomy-demo --reset
python3 main.py --autonomy-demo
python3 main.py --compare
```

Open `http://127.0.0.1:8787` to see the **Forge Ledger**. The first demo run
creates two curated offline skills; the second proves that verified memory is
reused. The curated mode is intentionally labelled as a recording fallback—it
does not claim to be a live model call.

`--foundry-task` runs the five-role council. With a supported capability it
uses the offline proposal path; add `--foundry-live` and `OPENAI_API_KEY` to
let `gpt-5.6-terra` plan and propose an unknown capability. `--repo-graph`
exports the repository graph, `--evaluate` runs 50 measured cases, and `--mcp`
starts the stdio MCP server for compatible coding agents.

## Production isolation and approvals

The default local runner is intentionally frictionless for the judge demo. For
an actual deployment, ForgeAgent now has a strict container profile: it runs a
single candidate with **no host mounts, no forwarded environment secrets, no
network egress, a read-only filesystem, dropped Linux capabilities, no-new-
privileges, PID/CPU/memory limits, and a non-root user**.

```bash
docker build -f Dockerfile.sandbox -t forgeagent-sandbox:local .
FORGEAGENT_SANDBOX=container FORGEAGENT_REQUIRE_CONTAINER=1 \
  python3 main.py --foundry-task "Find word frequency in this customer feedback" \
  --approval-policy production --payload '{"text":"tools tools reliable"}'
```

`compose.production.yml` is a deployable reference profile. The
`production` approval policy never auto-promotes: even a passing low-risk
candidate remains pending until a named reviewer records a substantive reason.
Policy violations are rejected, and receipts include an integrity SHA-256
digest without storing raw incident payloads. In a real deployment, run this
worker on a dedicated hardened host or orchestration runtime as an additional
boundary against container escapes.

## Hosted judge demo

`demo/` is a no-install, static Forge Ledger designed for the Devpost
**judge-testing** field. It follows a short judge path: inspect the capability
graph, run a private incident through the trusted chain, then inject a bad
candidate in the **Policy Attack Lab**. The interactive run performs
deterministic PII redaction, risk triage, and feedback-term extraction in the
browser. Neither requires an API key.

The interactive redactor removes emails, phone numbers, card-like values, and
explicitly labelled secrets such as secret codes, passwords, OTPs, API keys,
access tokens, and secret messages. `incident_analysis.py` provides the same
structured, audit-safe analysis path for arbitrary incident text in Python.

Use the hosted demo here:

```text
https://yashasm18.github.io/ForgeAgent/?v=57b69be
```

The versioned URL bypasses any cached GitHub Pages 404 response. GitHub Pages
deploys the static `demo/` directory through the repository workflow. The full
local ledger remains available through `python3 main.py --serve`.

The dashboard now also shows the **Evidence Trail**: every capability request,
policy rejection, verification result, trusted reuse, and execution is stored
in `data/audit_log.jsonl`.

`--benchmark` evaluates the trust gate against five representative cases:
safe code, filesystem access, network access, dynamic execution, and a broken
tool contract. `--showcase` is the recording-ready workflow: redact sensitive
support data, explain customer risk, and reuse those proven capabilities on the
next pass.

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

The evaluation arena is intentionally evidence-first: it runs 50 deterministic
cases (10 allowed tools, 10 unsafe proposals, and 30 privacy-first incidents),
reports actual pass/fail, latency, and blocked proposals, and reports API cost
as `null` when no model call was made.

## MCP and capability packages

`mcp_server.py` exposes a stdio MCP interface for repository inspection,
capability memory, audit receipts, and human approval decisions. Copy
[`mcp.config.example.json`](mcp.config.example.json), substitute the absolute
repository path, and register it in a compatible client such as Codex, Cursor,
or Claude Code.

The `PlatformStore` can export a trusted capability as an HMAC-SHA256 signed
package with source, provenance, and proof evidence. Imports always enter
review state in the receiving project; they cannot silently become trusted.

## Safety scope

This is defense in depth for a hackathon project, not hardened containment for
hostile code. Local generated tools run in a fresh subprocess with a timeout,
a temporary working directory, a minimal environment, a restricted builtins
set, and an import/operation policy. The production profile adds a rootless,
read-only container with disabled network egress and constrained resources.
The policy gate is exposed separately before execution and every decision is
recorded. A true hostile-code deployment also needs a hardened host, image
patching, runtime monitoring, and real organisational approval policy.

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
- Verification snapshot: `python3 -m unittest discover -s tests -v` (24 tests).
