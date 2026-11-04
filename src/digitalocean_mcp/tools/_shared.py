"""Helpers shared by every tool module.

Keeps each `tools/<resource>.py` file focused on business logic: building a
per-call client from the request's own token, a uniform error boundary
(tools must never raise -- SOP section 4), and the compact-JSON / size-cap
rules from SOP section 2.5.
"""

from __future__ import annotations

import functools
import json
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

import httpx

from digitalocean_mcp.errors import ToolError, build_error
from digitalocean_mcp.inference_client import DigitalOceanInferenceClient
from digitalocean_mcp.middleware import require_token
from digitalocean_mcp.settings import get_settings

MAX_RESPONSE_CHARS = 20_000
DEFAULT_LIST_LIMIT = 50
MAX_LIST_LIMIT = 200

F = TypeVar("F", bound=Callable[..., Awaitable[str]])

# Test-only hook: replaces the real network transport with an
# httpx.MockTransport so unit tests exercise the real request/retry/error
# code path without a network call or a real DigitalOcean account. The
# credential token still comes from the real per-request ContextVar
# (`require_token()`), so concurrency/isolation tests (AC9) stay meaningful.
_transport_override: httpx.BaseTransport | Callable[[], httpx.BaseTransport] | None = None


def set_transport_override(
    transport: httpx.BaseTransport | Callable[[], httpx.BaseTransport] | None,
) -> None:
    global _transport_override
    _transport_override = transport


async def get_client() -> DigitalOceanInferenceClient:
    token = await require_token()
    settings = get_settings()
    if _transport_override is not None:
        transport = _transport_override() if callable(_transport_override) else _transport_override
        return DigitalOceanInferenceClient(token, settings, transport=transport)
    return DigitalOceanInferenceClient(token, settings)


def dumps(payload: Any) -> str:
    """Compact JSON per SOP section 2.5: no indent, non-ASCII left as-is."""
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def clamp_limit(limit: int | None) -> int:
    if limit is None:
        return DEFAULT_LIST_LIMIT
    if limit <= 0:
        return DEFAULT_LIST_LIMIT
    return min(limit, MAX_LIST_LIMIT)


def bounded_dumps(payload: Any, limit: int = MAX_RESPONSE_CHARS) -> str:
    """Serialize and cap the overall response size per SOP section 2.5.

    When the character cap and an upstream row-count cap would disagree, the
    character cap wins (SOP section 2.5). Truncation is wrapped in a small
    JSON envelope so the result stays valid JSON even though the embedded
    `data` string is a truncated fragment of the full payload.
    """
    text = dumps(payload)
    if len(text) <= limit:
        return text
    return dumps(
        {
            "truncated": True,
            "note": f"response truncated at {limit} characters",
            "data": text[:limit],
        }
    )


def tool_guard(fn: F) -> F:
    """Wrap a tool body so it always returns a string, never raises.

    `ToolError` becomes its structured envelope; anything unexpected is
    swallowed into `upstream_error` rather than reaching the MCP transport
    as a protocol-level exception (SOP section 4).
    """

    @functools.wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> str:
        try:
            return await fn(*args, **kwargs)
        except ToolError as exc:
            return exc.to_envelope()
        except Exception as exc:  # noqa: BLE001 - last-resort tool boundary
            return build_error("upstream_error", f"Unexpected error: {exc}")

    return wrapper  # type: ignore[return-value]
