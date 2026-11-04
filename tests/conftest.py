from __future__ import annotations

import json
from typing import Any, Callable

import httpx
import pytest

from digitalocean_mcp import middleware
from digitalocean_mcp.server import build_fastmcp
from digitalocean_mcp.tools import _shared


@pytest.fixture
def mcp():
    return build_fastmcp()


@pytest.fixture
def fake_token():
    token_obj = middleware._api_token.set("do_fake_token_test")
    yield "do_fake_token_test"
    middleware._api_token.reset(token_obj)


@pytest.fixture
def set_handler():
    """Install a httpx.MockTransport handler for the duration of one test."""

    def _set(handler: Callable[[httpx.Request], httpx.Response]) -> None:
        _shared.set_transport_override(httpx.MockTransport(handler))

    yield _set
    _shared.set_transport_override(None)


async def call_tool_json(mcp, name: str, arguments: dict[str, Any] | None = None) -> Any:
    """Call a tool and parse its single text content block as JSON."""
    blocks = await mcp.call_tool(name, arguments or {})
    assert len(blocks) == 1, blocks
    return json.loads(blocks[0].text)
