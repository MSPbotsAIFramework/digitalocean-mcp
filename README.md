# digitalocean-mcp

MCP server exposing DigitalOcean App Platform ("Apps") to MSPbots Agent Platform clients (Claude, ChatGPT, Cursor, or any MCP-compatible AI). Covers listing and managing apps, triggering and inspecting deployments, reading logs/instances/events/alerts, and rolling back a bad deployment.

- **Transport**: MCP Streamable HTTP (`POST /mcp`) + `GET /health`.
- **Tech stack**: Python 3.12, [FastMCP](https://github.com/modelcontextprotocol/python-sdk), `httpx`, `pydantic-settings`.
- **License**: Apache-2.0 (see [LICENSE](LICENSE)). Copyright MSPbots.ai.
- **Scope**: this repository is shared by four tickets, one per DigitalOcean resource group — Apps (this one), Inference Model Catalog, Kubernetes (DOKS), and Networking. Only the Apps tools are documented below.

<!-- BEGIN MSPBOTS CONNECTOR SECTION (verbatim copy of vendor-mcp-development's reference/readme-connector-section.md — do not edit by hand, see tests/test_readme.py) -->
<div align="center">

## MSPbots Connector

**The MCP Gateway built for MSPs: visible, controlled, and your data stays where it belongs.**

[**Get started at connect.mspbots.ai →**](https://connect.mspbots.ai)

</div>

---

MSPbots Connector gives your AI clients one MCP URL to reach your entire MSP stack (RMM, PSA, documentation, security, finance), and gives you control over who can call which tool and a record of everything that was called.

**Hosted service: [connect.mspbots.ai](https://connect.mspbots.ai)** · Free to use.

### Why Connector

![MSPbots Connector](https://stgoss.mspbots.ai/files/mcp/mspbots-mcp.png)

| | |
|---|---|
| **Visible** | Every tool call is logged: who, which vendor, when. Usage dashboard, CSV export, SIEM streaming. |
| **Controlled** | Role-based, per-tool allowlist. Deny by default. |
| **Protected** | Credentials encrypted per record. AI clients never see your vendor passwords or tokens. |
| **MSP-native** | Built for the MSP stack only: RMM, PSA, documentation, security, finance. |

### Quick start

1. **Sign up** at [connect.mspbots.ai](https://connect.mspbots.ai).
2. **Connect your vendors.** Pick from 150+ connectors and authorize each one on the vendor's own page, or bring your own API keys. No extra vendor accounts needed.
3. **Set access.** Create roles and decide which tools each role may call. Nothing is allowed until you allow it.
4. **Add your MCP URL to your AI client.** Copy the URL from your Connector dashboard into Claude, ChatGPT, Cursor, VS Code, Gemini, Codex, or any MCP-capable client.
5. **Ask your AI to do real work**, and watch every call appear in the audit log.

### Features

**Unified gateway**
- One MCP URL for all your AI clients
- 150+ connectors across the MSP stack
- Custom MCP servers supported, free
- Authorization happens on each vendor's own page; the AI never sees passwords or tokens
- Bring your own credentials: use the vendor API keys you already have
- Multiple accounts per app; connect once, reuse across AI clients
- Tool search: finds the right action for the task
- One sign-in; vendor credentials are injected behind the scenes and OAuth tokens refresh automatically

**Visibility**
- Audit log for every tool call (who, which vendor, when)
- Usage dashboard: call volume, top vendors, error rate, per-user activity
- Export audit logs to CSV, or stream to Loki, Graylog, or LogScale (SIEM)
- Optional recording of tool arguments and result summaries (off by default, enabled per organization)

**Control**
- Per-role, per-tool allowlist, deny by default
- owner / admin / member roles
- SCIM provisioning with Entra ID, Okta, JumpCloud, and Google Workspace

**Security**
- Credentials encrypted one record at a time (AES-256-GCM, per-record key)
- AI clients authenticate with OAuth 2.1 + PKCE
- Vendor responses are scanned for prompt-injection patterns and returned as structured data. This is one layer of defense, not a guarantee against every attack.
- Static egress IP for customer firewall and API allowlisting

### Pricing

**Free.**

Links: [connect.mspbots.ai](https://connect.mspbots.ai) · [mspbots.ai](https://mspbots.ai)

---
<!-- END MSPBOTS CONNECTOR SECTION -->

## Authentication headers

| Header | Required | Type | Description |
|---|---|---|---|
| `X-DigitalOcean-Api-Token` | yes | password | DigitalOcean Personal Access Token. Create one in the DigitalOcean Control Panel → **API** → **Tokens** → **Generate New Token**. Needs read/write scope for the write tools below; a read-only token still works for the read-only tools and gets DigitalOcean's own 403 on write attempts. |

Missing this header returns HTTP 401 with the header name in the response body — no request ever reaches DigitalOcean's API without it.

## Tools (18)

All tools are prefixed `digitalocean_apps_` (this repository's other DigitalOcean resource groups, delivered on separate tickets, will use their own `digitalocean_<group>_` prefixes).

| Tool | Description |
|---|---|
| `digitalocean_apps_list_apps` | List DigitalOcean App Platform apps in the account. |
| `digitalocean_apps_get_app` | Get one app's current spec and active deployment. |
| `digitalocean_apps_create_app` | Create a new app from an app spec. |
| `digitalocean_apps_update_app` | Replace an app's spec. Uses PUT-replace semantics, not a partial merge. |
| `digitalocean_apps_delete_app` | Delete an app. This is irreversible and removes all its deployments. |
| `digitalocean_apps_restart_app` | Restart an app's components, or the whole app if none are named. |
| `digitalocean_apps_validate_spec` | Validate an app spec without creating or changing any app. |
| `digitalocean_apps_list_deployments` | List an app's deployments, most recent first. |
| `digitalocean_apps_get_deployment` | Get one deployment's phase, cause, and timestamps. |
| `digitalocean_apps_create_deployment` | Trigger a new deployment of an app's current spec. |
| `digitalocean_apps_cancel_deployment` | Cancel a deployment that is in progress. |
| `digitalocean_apps_manage_rollback` | Start, validate, commit, or revert a rollback to a prior deployment. |
| `digitalocean_apps_get_logs` | Get log access URLs for an app, a deployment, or one component. |
| `digitalocean_apps_get_instances` | List the running instances backing an app's components. |
| `digitalocean_apps_list_events` | List an app's build/deploy events, or get one event by id. |
| `digitalocean_apps_list_alerts` | List the alert rules configured on an app. |
| `digitalocean_apps_get_health` | Get an app's aggregate health across its components. |
| `digitalocean_apps_get_deployment_options` | List valid regions and instance sizes for building an app spec. |

Destructive tools (`delete_app`, `restart_app`, `cancel_deployment`, and `manage_rollback`'s `commit`/`revert` actions) always require an explicit resource id — there is no name-based lookup or bulk variant.

## Errors

Every tool returns a compact JSON string. On failure it is `{"error": {"code", "message", "retryable"}}`, with `code` one of: `not_configured`, `unauthorized`, `not_found`, `invalid_argument`, `rate_limited`, `upstream_error`. Tools never raise.

## Local development

```bash
uv sync
uv run pytest

# Run the server locally
uv run python -m digitalocean_mcp

# Exercise it with a placeholder token (real tools/call still needs a real DigitalOcean token)
curl -X POST http://localhost:8080/mcp \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -H 'X-DigitalOcean-Api-Token: do_fake_token_for_local_testing' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

## Container

```bash
docker build --platform linux/amd64 -t digitalocean-mcp:dev .
docker run --rm -p 8080:8080 digitalocean-mcp:dev
```
