# ForgeAgent — verified skill memory for AI agents

> GPT-5.6 may propose a new agent capability. ForgeAgent decides whether it has
> earned trust.

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
python3 main.py --showcase --reset
```

Open `http://127.0.0.1:8787` to see the **Forge Ledger**. The first demo run
creates two curated offline skills; the second proves that verified memory is
reused. The curated mode is intentionally labelled as a recording fallback—it
does not claim to be a live model call.

The dashboard now also shows the **Evidence Trail**: every capability request,
policy rejection, verification result, trusted reuse, and execution is stored
in `data/audit_log.jsonl`.

`--benchmark` evaluates the trust gate against five representative cases:
safe code, filesystem access, network access, dynamic execution, and a broken
tool contract. `--showcase` is the recording-ready workflow: redact sensitive
support data, explain customer risk, and reuse those proven capabilities on the
next pass.

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

## OpenAI Build Week evidence

ForgeAgent is entered in **Developer Tools**. See [HACKATHON_SCOPE.md](HACKATHON_SCOPE.md)
for the boundary between the earlier prototype and Build Week work.

Codex accelerated the architecture, safety lifecycle, dashboard, tests, and
submission materials. GPT-5.6 is used at runtime to propose constrained tool
code and its deterministic test cases. The demo video will show both the
successful forge path and a deliberate policy/test rejection.

## Judge testing path

- Supported platform: macOS, Linux, or Windows with Python 3.10+.
- Dependencies: none beyond the Python standard library.
- Offline proof: `python3 main.py --demo --reset`.
- Live GPT-5.6 proof: set `OPENAI_API_KEY` and use `--forge` as above.
- Visual inspection: `python3 main.py --serve`.
