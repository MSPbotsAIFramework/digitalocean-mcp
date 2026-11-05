"""Helpers shared by every tool module.

Keeps each `tools/<resource>.py` file focused on business logic: building a
per-call client from the request's own token, a uniform error boundary
(tools must never raise — SOP section 4), and the compact-JSON / size-cap
rules from SOP section 2.5.

`tool_guard` is also where every tool call is logged (SOP section 6): one
`tool_call` structured log line per invocation, with the tool name, a
redacted argument summary, the outcome, duration, and error code when there
is one. Argument redaction keeps short scalars (ids, flags, limits) as-is
and collapses anything else (dicts, lists — e.g. an app `spec`, which can
carry `SECRET`-type environment variables) to just its type name, so a
tenant secret embedded in a tool argument can never reach the logs.
"""

from __future__ import annotations

import functools
import json
import time
from collections.abc import Awaitable, Callable, Mapping
from typing import Any, TypeVar

import httpx

from digitalocean_mcp.client import DigitalOceanClient
from digitalocean_mcp.errors import ToolError, build_error
from digitalocean_mcp.middleware import require_token
from digitalocean_mcp.settings import get_settings
from digitalocean_mcp.telemetry import elapsed_ms, log_event

MAX_RESPONSE_CHARS = 20_000
DEFAULT_LIST_LIMIT = 50
MAX_LIST_LIMIT = 200

# Argument values of these types are safe to log as-is (ids, names, limits,
# flags); everything else is reduced to its type name — see module docstring.
_SAFE_SCALAR_TYPES = (str, int, float, bool)
_MAX_SCALAR_LOG_LEN = 200

F = TypeVar("F", bound=Callable[..., Awaitable[str]])

# Test-only hook: replaces the real network transport with an
# httpx.MockTransport so unit tests exercise the real request/retry/error
# code path without a network call or a real DigitalOcean account. The
# credential token still comes from the real per-request ContextVar
# (`require_token()`), so concurrency/isolation tests (AC13) stay meaningful.
_transport_override: httpx.BaseTransport | Callable[[], httpx.BaseTransport] | None = None


def set_transport_override(
    transport: httpx.BaseTransport | Callable[[], httpx.BaseTransport] | None,
) -> None:
    global _transport_override
    _transport_override = transport


async def get_client() -> DigitalOceanClient:
    token = await require_token()
    settings = get_settings()
    if _transport_override is not None:
        transport = _transport_override() if callable(_transport_override) else _transport_override
        return DigitalOceanClient(token, settings, transport=transport)
    return DigitalOceanClient(token, settings)


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


def truncate_text(text: str, limit: int = MAX_RESPONSE_CHARS) -> tuple[str, bool]:
    """Cap a free-form text payload (e.g. logs) at `limit` characters.

    Character cap takes priority over any upstream row-count cap per SOP
    section 2.5 ("two limits conflict, character cap wins").
    """
    if len(text) <= limit:
        return text, False
    return text[:limit], True


def _redact_args(kwargs: Mapping[str, Any]) -> dict[str, Any]:
    """Keep short scalars as-is; collapse anything else to its type name."""
    redacted: dict[str, Any] = {}
    for key, value in kwargs.items():
        if value is None or isinstance(value, _SAFE_SCALAR_TYPES):
            text = str(value)
            redacted[key] = text if len(text) <= _MAX_SCALAR_LOG_LEN else text[:_MAX_SCALAR_LOG_LEN] + "...(truncated)"
        else:
            redacted[key] = f"<{type(value).__name__}>"
    return redacted


def tool_guard(fn: F) -> F:
    """Wrap a tool body so it always returns a string, never raises.

    `ToolError` becomes its structured envelope; anything unexpected is
    swallowed into `upstream_error` rather than reaching the MCP transport
    as a protocol-level exception (SOP section 4).

    Also logs one `tool_call` structured event per invocation (SOP section
    6) — see the module docstring for the argument-redaction rule.
    """

    @functools.wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> str:
        tool_name = fn.__name__
        started = time.perf_counter()
        try:
            result = await fn(*args, **kwargs)
        except ToolError as exc:
            log_event(
                "tool_call",
                tool=tool_name,
                args=_redact_args(kwargs),
                outcome="error",
                error_code=exc.code,
                duration_ms=elapsed_ms(started),
            )
            return exc.to_envelope()
        except Exception as exc:  # noqa: BLE001 - last-resort tool boundary
            log_event(
                "tool_call",
                tool=tool_name,
                args=_redact_args(kwargs),
                outcome="error",
                error_code="upstream_error",
                duration_ms=elapsed_ms(started),
            )
            return build_error("upstream_error", f"Unexpected error: {exc}")
        else:
            log_event(
                "tool_call",
                tool=tool_name,
                args=_redact_args(kwargs),
                outcome="ok",
                error_code=None,
                duration_ms=elapsed_ms(started),
            )
            return result

    return wrapper  # type: ignore[return-value]
