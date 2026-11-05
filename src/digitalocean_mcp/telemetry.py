"""Structured, request-correlated logging (SOP section 6).

Every tool call and every outbound DigitalOcean API call emits one JSON log
line through the stdlib `logging` module, tagged with the current request's
id so a single `/mcp` request's log lines can be grepped together.

Callers must pass already-redacted fields -- this module never filters
anything itself. It must never be given the credential header value, the
`Authorization` header, or a raw request/response body that could carry a
tenant secret (SOP sections 6 and 11).
"""

from __future__ import annotations

import json
import logging
import time
from contextvars import ContextVar
from typing import Any

logger = logging.getLogger("digitalocean_mcp")

_request_id: ContextVar[str | None] = ContextVar("digitalocean_mcp_request_id", default=None)


def set_request_id(value: str) -> object:
    """Bind a request-id to the current async context. Returns a reset token."""
    return _request_id.set(value)


def reset_request_id(token: object) -> None:
    _request_id.reset(token)  # type: ignore[arg-type]


def get_request_id() -> str | None:
    """None outside a request scope (e.g. a unit test that calls a tool directly)."""
    return _request_id.get()


def log_event(event: str, *, level: int = logging.INFO, **fields: Any) -> None:
    """Emit one structured (JSON) log line for `event`.

    Always includes the current request-id. `fields` must already be
    redacted by the caller.
    """
    payload = {"event": event, "request_id": get_request_id(), **fields}
    logger.log(level, json.dumps(payload, ensure_ascii=False, separators=(",", ":")))


def elapsed_ms(started: float) -> float:
    """Milliseconds since `started` (a `time.perf_counter()` reading)."""
    return round((time.perf_counter() - started) * 1000, 1)
