# ForgeAgent developer integrations

ForgeAgent is an MCP **control plane** for coding agents. It is intentionally
not a replacement for Codex, Claude Code, or Cursor: those agents keep their
own planning and editing ability, while ForgeAgent supplies governed capability
memory, repository inspection, proof evidence, approval state, and audit
receipts.

## What an agent can ask ForgeAgent

| MCP tool | Developer outcome |
| --- | --- |
| `forge_inspect_repository` | Discover code/docs context and impact hints before duplicating a capability. |
| `forge_list_capabilities` | Find trusted, pending, rejected, or rolled-back capability versions. |
| `forge_request_capability` | Start the governed proposal → policy → proof → approval lifecycle. |
| `forge_run_trusted_capability` | Reuse a trusted local capability for a supported task. |
| `forge_get_approval_status` | Retrieve state plus an integrity-hashed audit receipt. |
| `forge_decide_capability` | Record a human approval or rejection with a named reason. |
| `forge_get_metrics` | Inspect capability state and control-plane activity without raw payloads. |

`forge_request_capability` defaults to production policy. It therefore keeps a
candidate **pending** rather than silently promoting or reusing it. This is by
design: use the approval workflow to make it trusted.

Without `OPENAI_API_KEY`, the server still supports curated capabilities and
explicitly reviewed local templates. For example, an invoice-ID extraction
request is generated and proved from the deterministic `invoice_id_extractor`
template, then remains pending until a reviewer approves it. Arbitrary new
capabilities remain a live-model feature and are refused offline rather than
being guessed.

## Local stdio setup

Use the included [`mcp.config.example.json`](../mcp.config.example.json) as the
shared configuration shape. Replace the absolute path with the clone location.

### Fast path: safe setup helper

From the repository root, first run the default dry-run plan. It detects
Codex, Cursor, and Claude Code without changing any config. Only the explicit
second command writes a config; it backs up existing files and never replaces
unrelated MCP entries.

```bash
python3 scripts/setup_mcp.py
python3 scripts/setup_mcp.py --apply
```

The helper adds `forgeagent-foundry` with the absolute path to this clone's
`forgeagent/mcp_server.py`. It uses Codex's `$CODEX_HOME/config.toml` (normally
`~/.codex/config.toml`), Cursor's `~/.cursor/mcp.json`, and Claude Code's
documented project-scope `.mcp.json` through `claude mcp add-json --scope project`.
The manual instructions below remain useful when you want to select a different
scope or inspect the exact configuration yourself.

```json
{
  "mcpServers": {
    "forgeagent-foundry": {
      "command": "python3",
      "args": ["/absolute/path/to/ForgeAgent/forgeagent/mcp_server.py"]
    }
  }
}
```

### Codex

Add the server to your Codex MCP configuration, then trust the repository and
ask Codex to use `forge_inspect_repository` before proposing a reusable tool.
Keep project conventions and verification commands in `AGENTS.md`; use MCP for
live capability and approval operations. See the [Codex configuration
guide](https://learn.chatgpt.com/docs/config-file/config-basic).

### Cursor

Place the configuration in `.cursor/mcp.json` for one repository, or
`~/.cursor/mcp.json` for a personal global setup. Cursor supports local stdio
servers as well as remote SSE and Streamable HTTP servers, so this local config
is the first step before a team deploys the remote gateway. See [Cursor MCP
documentation](https://docs.cursor.com/context/model-context-protocol).

### Claude Code

Use the Claude Code MCP command with the same stdio executable, for example:

```bash
claude mcp add-json forgeagent-foundry \
  '{"type":"stdio","command":"python3","args":["/absolute/path/to/ForgeAgent/forgeagent/mcp_server.py"]}' \
  --scope project
```

Verify the registration with `claude mcp list`. Claude Code documents MCP
configuration and project/user scopes in its [MCP guide](https://docs.anthropic.com/en/docs/mcp).

## Team control-plane API

The dependency-free local API is the contract for a future remote deployment.
It binds only to `127.0.0.1` by default:

```bash
python3 main.py --api
```

Bootstrap a project and save the returned token in a password manager or
secret manager—never in source control:

```bash
curl -X POST http://127.0.0.1:8090/v1/projects \
  -H 'Content-Type: application/json' \
  -d '{"project_id":"team/invoices","owner":"alice"}'
```

Use the returned `bootstrap_token` as a bearer token:

```bash
curl http://127.0.0.1:8090/v1/projects/team/invoices/snapshot \
  -H 'Authorization: Bearer fga_replace_me'

curl -X POST http://127.0.0.1:8090/v1/projects/team/invoices/capability-requests \
  -H 'Authorization: Bearer fga_replace_me' \
  -H 'Content-Type: application/json' \
  -d '{"task":"Normalize inconsistent date formats in this import log","payload":{"text":"batch=A 03/07/2026"},"production":true}'
```

Roles are `viewer`, `developer`, `reviewer`, `admin`, and `owner`. Capability
requests require `developer`; approvals require `reviewer`; role assignment
requires `admin`. API tokens are stored only as SHA-256 hashes and receive an
expiry by default.

## Remote deployment boundary

`Dockerfile.control-plane` and `compose.production.yml` provide a rootless
local/container deployment. Before exposing it to a team, add a TLS reverse
proxy, OAuth/OIDC identity provider, managed Postgres, encrypted secret store,
rate limiting, backups, and an external approval notification channel. The
current local API is intentionally not advertised as a public multi-tenant
service.
