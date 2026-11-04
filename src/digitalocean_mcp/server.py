"""FastMCP app factory and the Starlette app that wraps it.

Per SOP section 1.3 this service is truly stateless (`stateless_http=True`);
per section 7, DNS-rebinding protection is disabled because the service sits
behind MSPbots' internal gateway/proxy, and the MCP app's lifespan is
explicitly wired into the outer Starlette app (mounting alone does not run a
sub-app's lifespan, which otherwise breaks `/mcp` with "Task group is not
initialized" while `/health` keeps returning 200).

This repository is shared across DigitalOcean resource-group tickets
(PRD-21338 Apps, PRD-21343 Inference, PRD-21344 Kubernetes, PRD-21345
Networking); this ticket (PRD-21343) only registers the Inference tools.
Whichever sibling ticket's branch merges first/second needs to reconcile this
file's imports and `register()` calls into one list covering every landed
resource group -- see docs/tickets/PRD-21343.md section "Risks &
dependencies".
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
from digitalocean_mcp.tools import inference

SERVICE_INSTRUCTIONS = (
    "DigitalOcean Serverless Inference connector. Covers one DigitalOcean "
    "resource group: Inference -- the model catalog and core generative "
    "operations (chat completions, embeddings, image generation) served "
    "against your account's available models. Typical flow: "
    "list_models to see what is available on the account -> "
    "create_chat_completion / create_embedding / generate_image naming one "
    "of the catalog's model ids. list_models is read-only; the other three "
    "tools create new content and consume the tenant's DigitalOcean quota."
)


def build_fastmcp() -> FastMCP:
    mcp = FastMCP(
        "digitalocean-mcp",
        instructions=SERVICE_INSTRUCTIONS,
        stateless_http=True,
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
    inference.register(mcp)
    return mcp


async def health(_: Request) -> JSONResponse:
    """Pure local probe -- never calls DigitalOcean (SOP section 1.1)."""
    return JSONResponse({"status": "ok"})


def build_app(settings: Settings | None = None) -> Starlette:
    settings = settings or get_settings()
    mcp = build_fastmcp()
    # FastMCP's streamable_http_app() already registers the "/mcp" route
    # itself, so it is mounted at "/" here -- mounting it under "/mcp" again
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
