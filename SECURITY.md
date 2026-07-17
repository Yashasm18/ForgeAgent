# Security policy

## Supported versions

ForgeAgent is a hackathon submission with no versioned releases yet. The
actively supported security target is the current `main` branch. Please report
security issues against that branch rather than assuming historical commits or
unreleased versions receive fixes.

## Reporting a vulnerability

Please report undisclosed security issues privately through GitHub's
[**Report a vulnerability**](https://github.com/Yashasm18/ForgeAgent/security/advisories/new)
flow. Do not open a public issue for an unpatched security bug.

Include a minimal reproduction, affected files or commands, impact, and any
suggested mitigation. The maintainer aims to acknowledge a report within seven
days and will use the private advisory to coordinate validation, a fix, and
disclosure. If the repository owner later publishes an alternative private
contact method, reporters may use that method instead.

## What this project actually protects against

- **Static policy before execution.**
  [`policy_violations()`](sandbox.py#L78-L97) parses candidate source with the
  Python AST before it reaches execution. It rejects imports outside the
  allowlist; forbidden name references including `__import__` (the import
  primitive), `eval`, `exec`, `compile`, `open`, `globals`, `locals`, `vars`,
  `getattr`, `setattr`, and `delattr`; and dunder attribute access. A candidate
  must also define `run(payload)`.
- **Runtime import enforcement as an independent layer.** The generated-tool
  runner replaces the normal import function with
  [`safe_import`](sandbox.py#L41-L44), which permits only the same explicit
  module allowlist. If static checking were bypassed, a sandboxed import still
  cannot load a disallowed top-level module. This is defense in depth, not a
  claim that the static check alone is a security boundary.
- **Constrained execution.** [`execute()`](sandbox.py#L100-L139) runs a
  candidate in a fresh subprocess with a timeout, temporary working directory,
  minimal environment, and restricted builtins. The optional container profile
  adds a non-root user, read-only filesystem, no network egress, dropped Linux
  capabilities, no-new-privileges, and process/CPU/memory limits; see
  [`Dockerfile.sandbox`](Dockerfile.sandbox) and
  [`compose.production.yml`](compose.production.yml).
- **Governed promotion.** [`governance.py`](governance.py) rejects policy or
  proof failures and holds sensitive, review-policy, and production-policy
  capabilities for a named human approval. Approval requires a substantive
  reason; production policy never silently promotes a candidate.
- **Auditable decisions.** [`audit.py`](audit.py) appends Foundry events to
  `data/audit_log.jsonl`. The SQLite platform store records capability state,
  approvals, rejections, and related events; its project receipts include an
  integrity SHA-256 digest without raw incident payloads. The local control
  plane also records capability requests and authorization events in SQLite.
- **Optional live adversarial proof.** When a live GPT-5.6 generator is
  configured and adversarial proof is requested, ForgeAgent obtains
  adversarial inputs and runs them through the same proof sandbox before
  promotion. Requesting that mode without a usable live generator or without
  returned cases raises an error; it does not silently skip the proof.

## A real vulnerability we found and fixed

ForgeAgent previously needed stronger protection around the `__import__`
primitive. Generated code could assign it to a local variable and then use
that alias to reach a disallowed module, evading a policy rule that only
matched direct-name calls.

The fix is deliberately two-layered:

1. The static AST policy now rejects the `__import__` name reference itself,
   regardless of whether it is called directly or first assigned to an alias.
2. The runner still injects the allowlisted `safe_import` implementation at
   runtime, so importing a module outside the allowlist fails independently of
   static analysis.

[`tests/test_sandbox_security.py`](tests/test_sandbox_security.py) proves the
alias bypass is rejected before execution, while also covering dunder-attribute
and dynamic-`getattr` escape attempts and confirming that an allowed `re`
import still works.

## Known limitations — what this does not claim

ForgeAgent is defense in depth for a hackathon project, not hardened
containment against a fully hostile, motivated attacker. It has not undergone
external penetration testing. The production container profile reduces risk,
but it does not eliminate container-escape risk. A real deployment also needs
a hardened host, current and patched images, runtime monitoring, and a real
organizational incident-response and approval policy beyond what this
repository implements.
