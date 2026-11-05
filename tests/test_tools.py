"""tools/list snapshot + error-mapping tests.

These are the design's mapping table turned into assertions (AC1 and AC2's
sibling ACs). Every upstream call is mocked via `httpx.MockTransport` — no
real DigitalOcean account is used or needed here (see tests marked "needs a
real vendor account" in docs/tickets/PRD-21338.ac.json, which this file does
not attempt to cover).
"""

from __future__ import annotations

import json

import httpx
import pytest

from tests.conftest import call_tool_json

EXPECTED_TOOLS = {
    "digitalocean_apps_list_apps": {"readOnlyHint": True, "destructiveHint": None, "idempotentHint": None},
    "digitalocean_apps_get_app": {"readOnlyHint": True, "destructiveHint": None, "idempotentHint": None},
    "digitalocean_apps_create_app": {"readOnlyHint": None, "destructiveHint": None, "idempotentHint": None},
    "digitalocean_apps_update_app": {"readOnlyHint": None, "destructiveHint": None, "idempotentHint": True},
    "digitalocean_apps_delete_app": {"readOnlyHint": None, "destructiveHint": True, "idempotentHint": None},
    "digitalocean_apps_restart_app": {"readOnlyHint": None, "destructiveHint": True, "idempotentHint": None},
    "digitalocean_apps_validate_spec": {"readOnlyHint": True, "destructiveHint": None, "idempotentHint": True},
    "digitalocean_apps_list_deployments": {"readOnlyHint": True, "destructiveHint": None, "idempotentHint": None},
    "digitalocean_apps_get_deployment": {"readOnlyHint": True, "destructiveHint": None, "idempotentHint": None},
    "digitalocean_apps_create_deployment": {"readOnlyHint": None, "destructiveHint": None, "idempotentHint": None},
    "digitalocean_apps_cancel_deployment": {"readOnlyHint": None, "destructiveHint": True, "idempotentHint": None},
    "digitalocean_apps_get_logs": {"readOnlyHint": True, "destructiveHint": None, "idempotentHint": None},
    "digitalocean_apps_get_instances": {"readOnlyHint": True, "destructiveHint": None, "idempotentHint": None},
    "digitalocean_apps_manage_rollback": {"readOnlyHint": None, "destructiveHint": True, "idempotentHint": None},
    "digitalocean_apps_list_events": {"readOnlyHint": True, "destructiveHint": None, "idempotentHint": None},
    "digitalocean_apps_list_alerts": {"readOnlyHint": True, "destructiveHint": None, "idempotentHint": None},
    "digitalocean_apps_get_deployment_options": {"readOnlyHint": True, "destructiveHint": None, "idempotentHint": True},
    "digitalocean_apps_get_health": {"readOnlyHint": True, "destructiveHint": None, "idempotentHint": None},
}


@pytest.mark.asyncio
async def test_tools_list_has_all_apps_tools_with_valid_descriptions(mcp):
    """TC1 (AC1).

    Subset check, not exact-set: `mcp` is the shared service's full
    `tools/list` (PRD-21343's Inference tools are registered alongside Apps'
    in `server.py`), so this only asserts every Apps tool is present and
    well-formed -- it does not assert Apps is the only resource group.
    """
    tools = await mcp.list_tools()
    names = {t.name for t in tools}
    assert set(EXPECTED_TOOLS) <= names, names

    for tool in tools:
        description = tool.description or ""
        first_line = description.split("\n", 1)[0]
        assert len(first_line) <= 100, (tool.name, len(first_line), first_line)
        assert len(description) <= 500, (tool.name, len(description))


@pytest.mark.asyncio
async def test_tools_list_hints_match_design(mcp):
    """TC2 (AC1)."""
    tools = {t.name: t for t in await mcp.list_tools()}
    for name, expected in EXPECTED_TOOLS.items():
        annotations = tools[name].annotations
        assert annotations is not None, name
        assert annotations.readOnlyHint == expected["readOnlyHint"], name
        assert annotations.destructiveHint == expected["destructiveHint"], name
        assert annotations.idempotentHint == expected["idempotentHint"], name


@pytest.mark.asyncio
async def test_list_apps_default_limit_and_has_more(mcp, fake_token, set_handler):
    """TC4 (AC3)."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["per_page"] == "50"
        apps = [{"id": f"app-{i}", "spec": {"name": f"app-{i}"}} for i in range(50)]
        return httpx.Response(200, json={"apps": apps, "meta": {"total": 73}})

    set_handler(handler)
    result = await call_tool_json(mcp, "digitalocean_apps_list_apps")
    assert len(result["apps"]) == 50
    assert result["has_more"] is True


@pytest.mark.asyncio
async def test_list_apps_hard_cap_at_200(mcp, fake_token, set_handler):
    """TC5 (AC3)."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["per_page"] == "200"
        apps = [{"id": f"app-{i}"} for i in range(200)]
        return httpx.Response(200, json={"apps": apps, "meta": {"total": 500}})

    set_handler(handler)
    result = await call_tool_json(mcp, "digitalocean_apps_list_apps", {"limit": 500})
    assert len(result["apps"]) == 200
    assert result["has_more"] is True


@pytest.mark.asyncio
async def test_get_app_unknown_id_returns_not_found_error(mcp, fake_token, set_handler):
    """TC7 (AC4)."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"id": "not_found", "message": "App not found"})

    set_handler(handler)
    result = await call_tool_json(mcp, "digitalocean_apps_get_app", {"app_id": "missing"})
    assert result == {"error": {"code": "not_found", "message": "App not found", "retryable": False}}


@pytest.mark.asyncio
async def test_update_app_description_documents_replace_semantics(mcp):
    """TC9 (AC6)."""
    tools = {t.name: t for t in await mcp.list_tools()}
    description = (tools["digitalocean_apps_update_app"].description or "").lower()
    assert "put" in description
    assert "replace" in description


@pytest.mark.asyncio
async def test_delete_app_requires_explicit_id_and_is_marked_destructive(mcp):
    """TC10 (AC7)."""
    tools = {t.name: t for t in await mcp.list_tools()}
    tool = tools["digitalocean_apps_delete_app"]
    required = set(tool.inputSchema.get("required", []))
    assert required == {"app_id"}
    assert "name" not in tool.inputSchema.get("properties", {})
    assert tool.annotations.destructiveHint is True
    assert "irreversible" in (tool.description or "").lower()


@pytest.mark.asyncio
async def test_restart_app_default_restarts_all_components(mcp, fake_token, set_handler):
    """TC11 (AC8), no-filter branch."""
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content or b"{}")
        return httpx.Response(200, json={"deployment": {"id": "d1"}})

    set_handler(handler)
    await call_tool_json(mcp, "digitalocean_apps_restart_app", {"app_id": "a1"})
    assert "components" not in captured["body"]


@pytest.mark.asyncio
async def test_restart_app_with_component_filter(mcp, fake_token, set_handler):
    """TC11 (AC8), filtered branch."""
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content or b"{}")
        return httpx.Response(200, json={"deployment": {"id": "d1"}})

    set_handler(handler)
    await call_tool_json(mcp, "digitalocean_apps_restart_app", {"app_id": "a1", "component_names": ["web"]})
    assert captured["body"]["components"] == [{"name": "web"}]


@pytest.mark.asyncio
async def test_create_deployment_conflict_is_not_retried(mcp, fake_token, set_handler):
    """TC12 (AC9)."""
    call_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        return httpx.Response(409, json={"message": "a deployment is already in progress"})

    set_handler(handler)
    result = await call_tool_json(mcp, "digitalocean_apps_create_deployment", {"app_id": "a1"})
    assert call_count["n"] == 1, "a 409 conflict must not be retried as if transient"
    assert result["error"]["code"] == "upstream_error"
    assert result["error"]["retryable"] is False


@pytest.mark.asyncio
async def test_get_logs_defaults_to_active_deployment_aggregate(mcp, fake_token, set_handler):
    """TC13 (AC10), no deployment_id / no component_name."""
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        return httpx.Response(200, json={"live_url": "https://example.test/logs"})

    set_handler(handler)
    await call_tool_json(mcp, "digitalocean_apps_get_logs", {"app_id": "a1"})
    assert captured["path"] == "/v2/apps/a1/logs"


@pytest.mark.asyncio
async def test_get_logs_with_deployment_and_component_calls_specific_endpoint(mcp, fake_token, set_handler):
    """TC13 (AC10), both deployment_id and component_name given."""
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        return httpx.Response(200, json={"live_url": "https://example.test/logs"})

    set_handler(handler)
    await call_tool_json(
        mcp,
        "digitalocean_apps_get_logs",
        {"app_id": "a1", "deployment_id": "d1", "component_name": "web"},
    )
    assert captured["path"] == "/v2/apps/a1/deployments/d1/components/web/logs"


@pytest.mark.asyncio
async def test_get_logs_unsupported_log_type_is_invalid_argument(mcp, fake_token, set_handler):
    """TC14 (AC10)."""
    called = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        called["n"] += 1
        return httpx.Response(200, json={})

    set_handler(handler)
    result = await call_tool_json(
        mcp, "digitalocean_apps_get_logs", {"app_id": "a1", "log_type": "not-a-real-type"}
    )
    assert called["n"] == 0, "invalid log_type must be rejected before calling the upstream API"
    assert result["error"]["code"] == "invalid_argument"


@pytest.mark.asyncio
async def test_manage_rollback_commit_without_prior_start_is_invalid_argument(mcp, fake_token, set_handler):
    """Extra dev-authored safety-net test for the non-real-account half of TC15 (AC11)."""
    called = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        called["n"] += 1
        return httpx.Response(200, json={})

    set_handler(handler)
    result = await call_tool_json(
        mcp, "digitalocean_apps_manage_rollback", {"app_id": "a1", "action": "commit"}
    )
    assert called["n"] == 0
    assert result["error"]["code"] == "invalid_argument"


@pytest.mark.asyncio
async def test_deployment_options_and_validate_spec_need_no_app_id(mcp, fake_token, set_handler):
    """TC16 (AC12)."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v2/apps/regions":
            return httpx.Response(200, json={"regions": [{"slug": "nyc"}]})
        if request.url.path == "/v2/apps/tiers/instance_sizes":
            return httpx.Response(200, json={"instance_sizes": [{"slug": "basic-xs"}]})
        if request.url.path == "/v2/apps/propose":
            return httpx.Response(200, json={"app": {"spec": {"name": "x"}}})
        raise AssertionError(f"unexpected path {request.url.path}")

    set_handler(handler)

    options = await call_tool_json(mcp, "digitalocean_apps_get_deployment_options")
    assert options["regions"] == [{"slug": "nyc"}]

    validated = await call_tool_json(
        mcp, "digitalocean_apps_validate_spec", {"spec": {"name": "x", "region": "nyc"}}
    )
    assert "error" not in validated

    tools = {t.name: t for t in await mcp.list_tools()}
    assert "app_id" not in tools["digitalocean_apps_get_deployment_options"].inputSchema.get("properties", {})
    assert "app_id" not in tools["digitalocean_apps_validate_spec"].inputSchema.get("properties", {})
    assert tools["digitalocean_apps_get_deployment_options"].annotations.readOnlyHint is True
    assert tools["digitalocean_apps_validate_spec"].annotations.readOnlyHint is True


@pytest.mark.asyncio
async def test_single_429_then_success_retries_and_succeeds(mcp, fake_token, set_handler):
    """TC18 (AC14), first half."""
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        if attempts["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "0"}, json={"message": "rate limited"})
        return httpx.Response(200, json={"apps": [], "meta": {"total": 0}})

    set_handler(handler)
    result = await call_tool_json(mcp, "digitalocean_apps_list_apps")
    assert attempts["n"] == 2
    assert "error" not in result


@pytest.mark.asyncio
async def test_sustained_429_returns_rate_limited_not_a_hang(mcp, fake_token, set_handler):
    """TC18 (AC14), second half."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": "0"}, json={"message": "rate limited"})

    set_handler(handler)
    result = await call_tool_json(mcp, "digitalocean_apps_list_apps")
    assert result["error"]["code"] == "rate_limited"
    assert result["error"]["retryable"] is True
