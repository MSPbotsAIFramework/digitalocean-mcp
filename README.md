# digitalocean-mcp

MCP server exposing DigitalOcean's Serverless Inference model catalog to MSPbots Agent Platform clients (Claude, ChatGPT, Cursor, or any MCP-compatible AI). Covers listing the account's available inference models and running chat completions, embeddings, and image generation against them.

- **Transport**: MCP Streamable HTTP (`POST /mcp`) + `GET /health`.
- **Tech stack**: Python 3.12, [FastMCP](https://github.com/modelcontextprotocol/python-sdk), `httpx`, `pydantic-settings`.
- **License**: Apache-2.0 (see [LICENSE](LICENSE)). Copyright MSPbots.ai.
- **Scope**: this repository is shared by four tickets, one per DigitalOcean resource group — Apps, Inference Model Catalog (this one), Kubernetes (DOKS), and Networking. Only the Inference tools are documented below.

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
| `X-DigitalOcean-Api-Token` | yes | password | DigitalOcean credential for Serverless Inference. Either a general Personal Access Token (Control Panel → **API** → **Tokens** → **Generate New Token**) or a narrower-scoped Model Access Key (Control Panel → **Inference** → **Model Access Keys**, see DigitalOcean's "Manage Model Access Keys" docs) — DigitalOcean accepts both for this API. |

Missing this header returns HTTP 401 with the header name in the response body — no request ever reaches DigitalOcean's API without it.

## Tools (4)

All tools are prefixed `digitalocean_inference_` (this repository's other DigitalOcean resource groups, delivered on separate tickets, use their own `digitalocean_<group>_` prefixes).

| Tool | Description |
|---|---|
| `digitalocean_inference_list_models` | List models available for inference on the account. |
| `digitalocean_inference_create_chat_completion` | Generate a chat completion from a catalog model. |
| `digitalocean_inference_create_embedding` | Create one embedding vector per input string. |
| `digitalocean_inference_generate_image` | Generate image(s) from a text prompt; not read-only, consumes quota. |

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
