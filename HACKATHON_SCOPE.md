# OpenAI Build Week scope

## Pre-existing prototype

The original ForgeAgent prototype demonstrated two fixed capability blueprints,
a JSON registry, and a subprocess sandbox.

## Build Week extension

During OpenAI Build Week, ForgeAgent is being extended into a judge-testable
Developer Tool with:

- GPT-5.6 Responses API generation for capability code and edge-case tests.
- A multi-test trust gate with explicit rejection evidence.
- Provenance, test evidence, and reuse counts in persistent skill memory.
- The browser-based **Forge Ledger** for explaining the lifecycle visually.
- Automated regression tests and a submission-ready demo workflow.

Codex was used for the architecture, safety-policy implementation, dashboard,
tests, and documentation. GPT-5.6 is the live capability proposer at runtime.
