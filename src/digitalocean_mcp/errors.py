"""Structured error envelope shared by every tool.

Per the vendor-mcp-development SOP section 4: tools never raise, they return
a JSON string. Errors use a fixed, finite code vocabulary so an Agent can
branch on `error.code` and decide whether to retry (`retryable`).
"""

from __future__ import annotations

import json
from typing import Literal

ErrorCode = Literal[
    "not_configured",
    "unauthorized",
    "not_found",
    "invalid_argument",
    "rate_limited",
    "upstream_error",
]

# code -> default retryable flag, used when the caller does not override it.
_DEFAULT_RETRYABLE: dict[ErrorCode, bool] = {
    "not_configured": False,
    "unauthorized": False,
    "not_found": False,
    "invalid_argument": False,
    "rate_limited": True,
    "upstream_error": True,
}


def build_error(code: ErrorCode, message: str, retryable: bool | None = None) -> str:
    """Serialize a tool error into the SOP's compact JSON envelope.

    `message` must never contain the credential header value or a raw
    upstream response body that could carry tenant secrets.
    """
    payload = {
        "error": {
            "code": code,
            "message": message,
            "retryable": _DEFAULT_RETRYABLE[code] if retryable is None else retryable,
        }
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


class ToolError(Exception):
    """Raised inside tool implementations, caught at the tool boundary and
    turned into `build_error(...)`. Never escapes to the MCP transport.
    """

    def __init__(self, code: ErrorCode, message: str, retryable: bool | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = _DEFAULT_RETRYABLE[code] if retryable is None else retryable

    def to_envelope(self) -> str:
        return build_error(self.code, self.message, self.retryable)
