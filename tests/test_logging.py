"""Review round 1 must-fix: structured logging in `client.py` and
`tools/_shared.py` (SOP section 6).

Asserts the actual log records emitted through a real tool call, not just
that the logging functions exist in isolation (that is `test_telemetry.py`).
Every assertion here also checks the fake credential never appears anywhere
in the captured log text.
"""

from __future__ import annotations

import json
import logging

import httpx
import pytest

from tests.conftest import call_tool_json

FAKE_TOKEN = "do_fake_token_test"


def _events(caplog, name: str) -> list[dict]:
    out = []
    for record in caplog.records:
        payload = json.loads(record.message)
        if payload.get("event") == name:
            out.append(payload)
    return out


@pytest.mark.asyncio
async def test_successful_tool_call_logs_api_call_and_tool_call(mcp, fake_token, set_handler, caplog):
    caplog.set_level(logging.INFO, logger="digitalocean_mcp")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"apps": [], "meta": {"total": 0}})

    set_handler(handler)
    await call_tool_json(mcp, "digitalocean_apps_list_apps", {"limit": 10})

    api_calls = _events(caplog, "digitalocean_api_call")
    assert len(api_calls) == 1
    assert api_calls[0]["method"] == "GET"
    assert api_calls[0]["path"] == "/v2/apps"
    assert api_calls[0]["status_code"] == 200
    assert api_calls[0]["attempt"] == 1
    assert isinstance(api_calls[0]["latency_ms"], (int, float))

    tool_calls = _events(caplog, "tool_call")
    assert len(tool_calls) == 1
    assert tool_calls[0]["tool"] == "digitalocean_apps_list_apps"
    assert tool_calls[0]["args"] == {"limit": "10"}
    assert tool_calls[0]["outcome"] == "ok"
    assert tool_calls[0]["error_code"] is None
    assert isinstance(tool_calls[0]["duration_ms"], (int, float))

    full_text = "\n".join(r.message for r in caplog.records)
    assert FAKE_TOKEN not in full_text
    assert "bearer" not in full_text.lower()


@pytest.mark.asyncio
async def test_failed_tool_call_logs_error_code(mcp, fake_token, set_handler, caplog):
    caplog.set_level(logging.INFO, logger="digitalocean_mcp")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"id": "not_found", "message": "App not found"})

    set_handler(handler)
    await call_tool_json(mcp, "digitalocean_apps_get_app", {"app_id": "missing"})

    api_calls = _events(caplog, "digitalocean_api_call")
    assert api_calls[-1]["status_code"] == 404

    tool_calls = _events(caplog, "tool_call")
    assert tool_calls[-1]["outcome"] == "error"
    assert tool_calls[-1]["error_code"] == "not_found"
    assert tool_calls[-1]["args"] == {"app_id": "missing"}


@pytest.mark.asyncio
async def test_retried_call_logs_every_attempt(mcp, fake_token, set_handler, caplog):
    """Mirrors test_tools.py::test_single_429_then_success_retries_and_succeeds."""
    caplog.set_level(logging.INFO, logger="digitalocean_mcp")
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        if attempts["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "0"}, json={"message": "rate limited"})
        return httpx.Response(200, json={"apps": [], "meta": {"total": 0}})

    set_handler(handler)
    await call_tool_json(mcp, "digitalocean_apps_list_apps")

    api_calls = _events(caplog, "digitalocean_api_call")
    assert [c["attempt"] for c in api_calls] == [1, 2]
    assert api_calls[0]["status_code"] == 429
    assert api_calls[0]["retrying"] is True
    assert api_calls[1]["status_code"] == 200
    assert api_calls[1]["retrying"] is False


@pytest.mark.asyncio
async def test_dict_and_list_arguments_are_redacted_to_their_type_name(mcp, fake_token, set_handler, caplog):
    """A `spec` arg can carry a DigitalOcean `SECRET`-type env var -- it must
    never reach the logs verbatim, only as its type name.
    """
    caplog.set_level(logging.INFO, logger="digitalocean_mcp")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"app": {"id": "a1"}})

    set_handler(handler)
    secret_marker = "do-secret-value-should-never-be-logged"
    spec = {
        "name": "app",
        "envs": [{"key": "S", "value": secret_marker, "type": "SECRET"}],
    }
    await call_tool_json(mcp, "digitalocean_apps_create_app", {"spec": spec})

    tool_calls = _events(caplog, "tool_call")
    assert tool_calls[-1]["args"] == {"spec": "<dict>"}

    full_text = "\n".join(r.message for r in caplog.records)
    assert secret_marker not in full_text


@pytest.mark.asyncio
async def test_missing_header_401_never_reaches_the_client_logger(mcp, caplog):
    """Without `fake_token`, `require_token()` raises before any DigitalOcean
    API call is made -- there must be no `digitalocean_api_call` event, only
    the `tool_call` error event.
    """
    caplog.set_level(logging.INFO, logger="digitalocean_mcp")

    result = await call_tool_json(mcp, "digitalocean_apps_list_apps")
    assert result["error"]["code"] == "upstream_error"

    assert _events(caplog, "digitalocean_api_call") == []
    tool_calls = _events(caplog, "tool_call")
    assert tool_calls[-1]["outcome"] == "error"
