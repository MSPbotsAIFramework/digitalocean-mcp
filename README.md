# digitalocean-mcp

MCP server exposing DigitalOcean to MSPbots Agent Platform clients (Claude, ChatGPT, Cursor, or any MCP-compatible AI). Covers four resource groups so far: App Platform ("Apps") — listing and managing apps, triggering and inspecting deployments, reading logs/instances/events/alerts, and rolling back a bad deployment; Serverless Inference — listing the account's available inference models and running chat completions, embeddings, and image generation against them; Kubernetes (DOKS) — managing clusters and their node pools, including upgrades, kubeconfig/credentials, and node-level operations; and Networking — VPCs (incl. peering), Cloud Firewalls, Domains/DNS, and Load Balancers.

- **Transport**: MCP Streamable HTTP (`POST /mcp`) + `GET /health`.
- **Tech stack**: Python 3.12, [FastMCP](https://github.com/modelcontextprotocol/python-sdk), `httpx`, `pydantic-settings`.
- **License**: Apache-2.0 (see [LICENSE](LICENSE)). Copyright MSPbots.ai.
- **Scope**: this repository is shared by four tickets, one per DigitalOcean resource group — Apps, Inference Model Catalog, Kubernetes (DOKS), and Networking. All four are documented below.

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
| `X-DigitalOcean-Api-Token` | yes | password | DigitalOcean credential, shared by every resource group in this connector. Either a general Personal Access Token (Control Panel → **API** → **Tokens** → **Generate New Token**; needs read/write scope for the write tools below, a read-only token still works for the read-only tools and gets DigitalOcean's own 403 on write attempts) or, for Inference specifically, a narrower-scoped Model Access Key (Control Panel → **Inference** → **Model Access Keys**, see DigitalOcean's "Manage Model Access Keys" docs) — DigitalOcean accepts both for the Inference API. |

Missing this header returns HTTP 401 with the header name in the response body — no request ever reaches DigitalOcean's API without it.

## Tools (55)

Every tool is prefixed `digitalocean_<group>_` so tools from different resource groups never collide by name.

### Apps (18)

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

### Inference (4)

| Tool | Description |
|---|---|
| `digitalocean_inference_list_models` | List models available for inference on the account. |
| `digitalocean_inference_create_chat_completion` | Generate a chat completion from a catalog model. |
| `digitalocean_inference_create_embedding` | Create one embedding vector per input string. |
| `digitalocean_inference_generate_image` | Generate image(s) from a text prompt; not read-only, consumes quota. |

### Kubernetes (16)

| Tool | Description |
|---|---|
| `digitalocean_kubernetes_list_clusters` | List DigitalOcean Kubernetes (DOKS) clusters in the account. |
| `digitalocean_kubernetes_get_cluster` | Get one cluster's spec, status, and node-pool summary. |
| `digitalocean_kubernetes_create_cluster` | Create a new DOKS cluster with at least one node pool. |
| `digitalocean_kubernetes_update_cluster` | Partially update a cluster: only the fields supplied here change. |
| `digitalocean_kubernetes_upgrade_cluster` | Trigger a control-plane upgrade. Disruptive maintenance operation. |
| `digitalocean_kubernetes_list_cluster_resources` | List load balancers, volumes, and volume snapshots associated with a cluster. |
| `digitalocean_kubernetes_delete_cluster` | Delete a cluster. No default mode -- the caller must choose one. |
| `digitalocean_kubernetes_get_kubeconfig` | Get a cluster's raw kubeconfig YAML. Never logged, never truncated. |
| `digitalocean_kubernetes_get_credentials` | Get a cluster's structured credential bundle (server/token/expires_at). |
| `digitalocean_kubernetes_list_node_pools` | List every node pool in a cluster, with node-level detail. |
| `digitalocean_kubernetes_get_node_pool` | Get one node pool by id. |
| `digitalocean_kubernetes_create_node_pool` | Add a new node pool to a cluster. |
| `digitalocean_kubernetes_update_node_pool` | Resize or reconfigure a node pool. Repeating the same call converges to the same state. |
| `digitalocean_kubernetes_delete_node_pool` | Delete a node pool. Irreversible; requires the explicit pool id. |
| `digitalocean_kubernetes_delete_node` | Remove one node. No bulk/"all nodes in pool" variant exists. |
| `digitalocean_kubernetes_get_deployment_options` | List valid regions, Kubernetes versions, and node sizes for DOKS. |

Destructive tools (`delete_cluster`, `upgrade_cluster`, `delete_node_pool`, `delete_node`) always require an explicit resource id (and, for `delete_cluster`, an explicit `mode` -- there is no default). `get_kubeconfig` and `get_credentials` return maximally privileged cluster-admin artifacts and are never logged.

### Networking (17)

| Tool | Description |
|---|---|
| `digitalocean_networking_list_vpcs` | List VPCs in the account, or get one VPC's detail, member count, and peerings. |
| `digitalocean_networking_create_vpc` | Create a new VPC. |
| `digitalocean_networking_update_vpc` | Partially update a VPC. Only the fields supplied here change. |
| `digitalocean_networking_delete_vpc` | Delete a VPC. Irreversible, and fails if the VPC still has member resources attached. |
| `digitalocean_networking_manage_vpc_peering` | List, inspect, create, rename, or delete a VPC peering. |
| `digitalocean_networking_list_firewalls` | List firewalls in the account, or get one firewall's full detail. |
| `digitalocean_networking_create_firewall` | Create a new firewall. |
| `digitalocean_networking_update_firewall` | Replace a firewall's rules and membership. Whole-object replace, not a partial merge. |
| `digitalocean_networking_delete_firewall` | Delete a firewall. This is irreversible. |
| `digitalocean_networking_list_domains` | List domains in the account, or get one domain's detail (zone file, TTL). |
| `digitalocean_networking_create_domain` | Register a new domain on the account. |
| `digitalocean_networking_delete_domain` | Delete a domain and all of its records. Irreversible. |
| `digitalocean_networking_manage_domain_record` | List, inspect, create, update, or delete one DNS record on a domain. |
| `digitalocean_networking_list_load_balancers` | List load balancers in the account, or get one's full detail. |
| `digitalocean_networking_create_load_balancer` | Create a new load balancer. |
| `digitalocean_networking_update_load_balancer` | Replace a load balancer's droplets and forwarding rules. Whole-object replace, not a partial merge. |
| `digitalocean_networking_delete_load_balancer` | Delete a load balancer. Irreversible, and does not delete the Droplets behind it. |

Destructive tools (`delete_vpc`, `delete_firewall`, `delete_domain`, `delete_load_balancer`, and `manage_vpc_peering`/`manage_domain_record`'s `delete` action) always require an explicit resource id -- there is no name-based lookup or bulk variant. `update_firewall` and `update_load_balancer` are whole-object `PUT` replaces (unspecified arrays are not preserved); `update_vpc` and `manage_domain_record`'s `update` action are `PATCH` partial updates (only the given fields change) -- read the current full state first (`list_vpcs`/`list_firewalls`/`list_load_balancers` with the resource id) before calling either update-by-replace tool.

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
