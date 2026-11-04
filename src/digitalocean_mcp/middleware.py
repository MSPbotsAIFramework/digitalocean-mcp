"""Request-level credential handling.

Per SOP section 3: credentials arrive only via the `X-DigitalOcean-Api-Token`
HTTP header, are scoped per-request through a ContextVar, and are reset in a
`finally` block so one tenant's request can never observe another tenant's
token. There is no environment-variable fallback — a missing header is a 401,
never a silent reuse of some other value.
"""

from __future__ import annotations

from contextvars import ContextVar

from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

CREDENTIAL_HEADER = "X-DigitalOcean-Api-Token"

_api_token: ContextVar[str | None] = ContextVar("digitalocean_api_token", default=None)


def get_api_token() -> str | None:
    """Read the current request's token. None outside a request scope."""
    return _api_token.get()


def _missing_header_response() -> Response:
    body = {
        "error": {
            "code": "not_configured",
            "message": f"Missing required header: {CREDENTIAL_HEADER}",
            "retryable": False,
        }
    }
    return JSONResponse(body, status_code=401)


class CredentialMiddleware:
    """ASGI middleware: reads the credential header before any tool body runs.

    Only applied to the `/mcp` path — `/health` must stay reachable without a
    token (SOP section 1.1: the health probe is purely local).
    """

    def __init__(self, app: ASGIApp, mcp_path: str = "/mcp") -> None:
        self.app = app
        self.mcp_path = mcp_path

    async def __call__(self, scope, receive, send) -> None:  # noqa: ANN001
        if scope["type"] != "http" or not scope["path"].startswith(self.mcp_path):
            await self.app(scope, receive, send)
            return

        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        token = headers.get(CREDENTIAL_HEADER.lower())

        if not token:
            response = _missing_header_response()
            await response(scope, receive, send)
            return

        reset_token = _api_token.set(token)
        try:
            await self.app(scope, receive, send)
        finally:
            _api_token.reset(reset_token)


async def require_token() -> str:
    """Used inside tool bodies as a defense-in-depth check.

    The ASGI middleware above already rejects requests with no header before
    they reach a tool, so this should only ever find a token present; it
    exists so a tool never silently proceeds with `None`.
    """
    token = get_api_token()
    if not token:
        raise RuntimeError(
            "digitalocean_mcp: tool invoked with no credential in context — "
            "the CredentialMiddleware should have rejected this request with 401"
        )
    return token
