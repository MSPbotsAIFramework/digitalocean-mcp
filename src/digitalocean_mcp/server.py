"""FastMCP app factory and the Starlette app that wraps it.

Per SOP section 1.3 this service is truly stateless (`stateless_http=True`);
per section 7, DNS-rebinding protection is disabled because the service sits
behind MSPbots' internal gateway/proxy, and the MCP app's lifespan is
explicitly wired into the outer Starlette app (mounting alone does not run a
sub-app's lifespan, which otherwise breaks `/mcp` with "Task group is not
initialized" while `/health` keeps returning 200).

This repository is shared across DigitalOcean resource-group tickets
(PRD-21338 Apps, PRD-21343 Inference, PRD-21344 Kubernetes, PRD-21345
Networking). This module registers every resource group's tools that have
landed on `main` so far; a new resource group adds its own `import` and
`register()` call here plus a paragraph to `SERVICE_INSTRUCTIONS`, without
touching the other groups' registrations.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator

from mcp.server.fastmcp import FastMCP
from mcp.server.streamable_http_manager import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from digitalocean_mcp.middleware import CredentialMiddleware
from digitalocean_mcp.settings import Settings, get_settings
from digitalocean_mcp.tools import (
    apps,
    deployments,
    inference,
    kubernetes,
    kubernetes_access,
    kubernetes_node_pools,
    kubernetes_reference,
    observability,
    reference,
)

SERVICE_INSTRUCTIONS = (
    "DigitalOcean connector. Covers two DigitalOcean resource groups so far:\n"
    "\n"
    "Apps (App Platform) — the PaaS that builds and runs apps from a Git repo "
    "or container image. Core concepts: an app has a spec (services, static "
    "sites, jobs) and a sequence of deployments; each deployment has a phase "
    "and, once active, serves traffic at the app's ingress URL. Typical "
    "flows: list/inspect apps -> get_app for one app's spec and active "
    "deployment -> get_logs/get_instances/get_health to observe it -> "
    "create_deployment to ship a new version, or manage_rollback to recover "
    "a bad one. validate_spec and get_deployment_options are account-level "
    "reference lookups that do not require an app id. All destructive "
    "actions (delete_app, restart_app, cancel_deployment, rollback "
    "commit/revert) require an explicit resource id — there is no "
    "name-based or bulk variant.\n"
    "\n"
    "Inference — the Serverless Inference model catalog and core generative "
    "operations (chat completions, embeddings, image generation) served "
    "against your account's available models. Typical flow: "
    "list_models to see what is available on the account -> "
    "create_chat_completion / create_embedding / generate_image naming one "
    "of the catalog's model ids. list_models is read-only; the other three "
    "tools create new content and consume the tenant's DigitalOcean quota.\n"
    "\n"
    "Kubernetes — DOKS cluster and node-pool management. Core concepts: a "
    "cluster has a spec (region, version, HA) and one or more node pools; "
    "each node pool has a size, a node count, and optional autoscale "
    "bounds. Typical flow: list/get_cluster -> get_deployment_options for "
    "valid regions/versions/sizes -> create_cluster with at least one node "
    "pool -> list/get/create/update_node_pool to manage capacity -> "
    "get_kubeconfig or get_credentials to connect kubectl. "
    "list_cluster_resources shows what delete_cluster(mode=\"dangerous\") "
    "would also destroy. All destructive actions (delete_cluster, "
    "delete_node_pool, delete_node, upgrade_cluster) require an explicit "
    "resource id and, for delete_cluster, an explicit mode -- there is no "
    "default mode and no bulk/name-based variant.\n"
    "\n"
    "Every tool is prefixed `digitalocean_<group>_` so tools from different "
    "resource groups never collide by name."
)


def build_fastmcp() -> FastMCP:
    mcp = FastMCP(
        "digitalocean-mcp",
        instructions=SERVICE_INSTRUCTIONS,
        stateless_http=True,
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
    apps.register(mcp)
    deployments.register(mcp)
    observability.register(mcp)
    reference.register(mcp)
    inference.register(mcp)
    kubernetes.register(mcp)
    kubernetes_access.register(mcp)
    kubernetes_node_pools.register(mcp)
    kubernetes_reference.register(mcp)
    return mcp


async def health(_: Request) -> JSONResponse:
    """Pure local probe — never calls DigitalOcean (SOP section 1.1)."""
    return JSONResponse({"status": "ok"})


def build_app(settings: Settings | None = None) -> Starlette:
    settings = settings or get_settings()
    mcp = build_fastmcp()
    # FastMCP's streamable_http_app() already registers the "/mcp" route
    # itself, so it is mounted at "/" here — mounting it under "/mcp" again
    # would make the real endpoint "/mcp/mcp".
    mcp_app = mcp.streamable_http_app()

    @contextlib.asynccontextmanager
    async def lifespan(_: Starlette) -> AsyncIterator[None]:
        # Run the MCP app's own lifespan explicitly: Mount() does not do this
        # for you, and skipping it breaks every /mcp request (SOP section 7).
        async with mcp_app.router.lifespan_context(mcp_app):
            yield

    app = Starlette(
        routes=[
            Route("/health", health, methods=["GET"]),
            Mount("/", app=mcp_app),
        ],
        lifespan=lifespan,
    )
    app.add_middleware(CredentialMiddleware, mcp_path="/mcp")
    return app
