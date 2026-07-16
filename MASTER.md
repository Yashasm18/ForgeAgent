# ForgeAgent — Master Project Guide

## 1. Executive summary

ForgeAgent is a verified capability-memory system for autonomous agents.
Instead of allowing an agent to keep every generated tool, it promotes a tool
to reusable memory only after it passes policy checks and deterministic proof.

The central promise is:

> A capability may be proposed by a model, but it earns trust only through
> evidence.

ForgeAgent addresses a practical agent problem: long-running agents need new
small capabilities, yet blindly storing generated code compounds failure and
risk. ForgeAgent uses the loop:

```text
capability gap → proposal → policy gate → isolated proof → versioned memory → reuse
```

## 2. What the project demonstrates

### Core autonomy lifecycle

- Multi-step, dependency-ordered task planning.
- Capability-gap detection and tool reuse.
- Optional GPT-5.6 proposal generation through the OpenAI Responses API.
- Deterministic proof cases before a candidate becomes trusted.
- Repair after a failed candidate.
- Version history, supersession, and rollback.
- A capability dependency graph and append-only audit log.

### Privacy-first incident analysis

`incident_analysis.py` accepts arbitrary support-incident text and returns a
structured result:

- redacted text;
- categories that were removed;
- explainable risk level and signals;
- recurring terms;
- an audit-safe payload that intentionally excludes raw input.

Supported redaction includes emails, phone numbers, card-like numbers, and
explicitly labelled secrets: secret code/key, password, passcode, OTP, PIN,
API key, access token, and secret/confidential messages. It avoids blanket
removal of ordinary prose or unlabelled identifiers.

## 3. Architecture

```text
main.py
  ├─ ForgeAgent (agent.py)
  │    ├─ Proposal generator (generator.py)
  │    ├─ Policy + isolated execution (sandbox.py)
  │    ├─ Tool/version registry (registry.py)
  │    ├─ Capability graph (capability_graph.py)
  │    └─ Audit log (audit.py)
  ├─ Benchmarks (benchmark.py)
  ├─ Comparisons (comparison.py)
  ├─ Local dashboard server (dashboard.py)
  └─ Incident analysis (incident_analysis.py)

demo/index.html
  └─ Static GitHub Pages judge experience
```

### Important files

| File | Responsibility |
| --- | --- |
| `agent.py` | Forge/reuse/repair/rollback workflow and curated tool blueprints. |
| `generator.py` | Optional GPT-5.6 Responses API proposal and planning client. |
| `sandbox.py` | AST policy enforcement and timeout-bounded isolated execution. |
| `registry.py` | Persistent trusted-tool versions, evidence, provenance, reuse counts. |
| `capability_graph.py` | Task-to-skill dependency, replacement, and rollback graph. |
| `audit.py` | Append-only JSONL decision record. |
| `incident_analysis.py` | Structured privacy-safe analysis for arbitrary incident text. |
| `benchmark.py` | Safety gate benchmark against representative unsafe proposals. |
| `dashboard.py` | Local live trust-ledger HTTP dashboard. |
| `demo/index.html` | API-key-free interactive hosted judge demo. |

## 4. Safety model

ForgeAgent is defense in depth for a hackathon prototype:

1. Generated source is inspected before execution.
2. Filesystem, network, dynamic execution, unsafe imports, and missing tool
   contracts are rejected by policy.
3. Every deterministic proof case runs in a fresh, timeout-bound subprocess.
4. Rejected candidates never enter trusted memory.
5. Repairs must pass the same gate before promotion.
6. Sensitive incident data is redacted before downstream analysis and raw text
   is omitted from the structured audit-safe result.

This is not claimed to be hardened hostile-code containment. A production
version would add container isolation, network egress controls, tenant
separation, rate limits, and human approvals.

## 5. How to run locally

Requirements: Python 3.10+; no third-party dependencies for offline mode.

```bash
# Run curated offline skill creation and reuse
python3 main.py --demo --reset
python3 main.py --demo

# Run dependent incident-autonomy workflow
python3 main.py --autonomy-demo --reset
python3 main.py --autonomy-demo

# Run safety benchmark and agent comparison
python3 main.py --benchmark
python3 main.py --compare

# Start the local live dashboard
python3 main.py --serve

# Run all tests
python3 -m unittest discover -s tests -v
```

Open `http://127.0.0.1:8787` after `--serve`.

## 6. Optional live GPT-5.6 mode

The project contains a server-side GPT-5.6 generator path. It is optional and
is deliberately not used by the hosted GitHub Pages demo.

```bash
export OPENAI_API_KEY="your-server-side-key"
python3 main.py --forge "Extract invoice IDs and return unique normalized values" \
  --payload '{"text":"Invoices INV-100 and inv-100"}'
```

The generator must return constrained Python source defining `run(payload)`
plus at least two deterministic tests. ForgeAgent then applies policy and
proof checks before persistence. Never put an API key in `demo/index.html`,
GitHub Pages, a client bundle, or a commit.

## 7. Hosted judge demo

Live URL:

```text
https://yashasm18.github.io/ForgeAgent/
```

The static demo requires no account, key, installation, or backend. It
includes:

- preloaded autonomy replay;
- interactive incident run;
- secret-aware redaction;
- clickable ForageGraph with filters and replay;
- Forge Challenge for policy, proof, contract, regression, repair, and
  rollback demonstrations;
- Mission Control with persistent browser memory, curated forge simulation,
  promotion mode, evaluation arena, and downloadable audit receipt.

GitHub Pages serves the `demo/` directory through the repository's `gh-pages`
branch. Changes to `demo/` must be subtree-split and pushed to `gh-pages`.

## 8. Judge walkthrough (two minutes)

1. Open the hosted link; read the capability-memory thesis.
2. Click a node in **ForageGraph** and use the replay slider.
3. Paste a support incident in **Live capability run** and execute it.
4. Include an email, phone number, `secret code 89789`, or `API key:` to show
   the privacy boundary.
5. Open **Forge Challenge** and run `Unsafe filesystem access`.
6. Run `Trusted version regression`, then use rollback.
7. Open **Mission Control**, forge a curated capability, choose a promotion
   policy, and download the audit receipt.
8. Show the repository tests and local `--benchmark` result.

## 9. Submission narrative

**Category:** Developer Tools.

**Problem:** Agent memory generally accumulates code and prompts without
provenance. This makes reuse difficult to trust and failure difficult to audit.

**Solution:** ForgeAgent treats memory as an evidence-backed promotion. Every
skill has source, proof cases, policy decision, version lineage, reuse history,
and an audit record.

**Differentiator:** The capability graph is not a generic codebase graph. It
explains why an agent can safely perform a task now: which tools it uses, how
they were proven, which version is active, and how to roll back.

## 10. Current limitations and honest claims

- The hosted judge demo is deterministic and key-free; its curated forge mode
  is not presented as a live model call.
- GPT-5.6 generation is optional and requires server-side API credentials.
- Browser persistence is for the demo; the local Python registry/audit/graph
  is the persistent implementation.
- Sandbox protections are meaningful prototype controls, not a substitute for
  production container isolation.

## 11. Git and contribution workflow

For future changes, use a feature branch and draft pull request:

```text
feature branch → tests → push → draft PR → review → merge to main
```

Do not commit API keys, generated `data/` state, local audit files, or secrets.

## 12. Verification snapshot

At package creation, the project test suite passes 8 tests, including privacy
safe incident-analysis coverage and secret-redaction regression coverage.
