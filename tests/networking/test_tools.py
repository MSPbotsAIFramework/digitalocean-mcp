"""tools/list snapshot + per-tool happy-path and error-mapping tests for the
Networking resource group (VPCs, Firewalls, Domains/DNS, Load Balancers).

Every upstream call is mocked via `httpx.MockTransport` -- no real
DigitalOcean account is used or needed here (see TC20 in
docs/tickets/PRD-21345.ac.json, marked "needs a real vendor account", which
this file does not attempt to cover).
"""

from __future__ import annotations

import httpx
import pytest

from tests.conftest import call_tool_json

EXPECTED_TOOLS = {
    "digitalocean_networking_list_vpcs": {"readOnlyHint": True, "destructiveHint": None, "idempotentHint": None},
    "digitalocean_networking_create_vpc": {"readOnlyHint": None, "destructiveHint": None, "idempotentHint": None},
    "digitalocean_networking_update_vpc": {"readOnlyHint": None, "destructiveHint": None, "idempotentHint": True},
    "digitalocean_networking_delete_vpc": {"readOnlyHint": None, "destructiveHint": True, "idempotentHint": None},
    "digitalocean_networking_manage_vpc_peering": {
        "readOnlyHint": None,
        "destructiveHint": True,
        "idempotentHint": None,
    },
    "digitalocean_networking_list_firewalls": {"readOnlyHint": True, "destructiveHint": None, "idempotentHint": None},
    "digitalocean_networking_create_firewall": {"readOnlyHint": None, "destructiveHint": None, "idempotentHint": None},
    "digitalocean_networking_update_firewall": {
        "readOnlyHint": None,
        "destructiveHint": None,
        "idempotentHint": True,
    },
    "digitalocean_networking_delete_firewall": {"readOnlyHint": None, "destructiveHint": True, "idempotentHint": None},
    "digitalocean_networking_list_domains": {"readOnlyHint": True, "destructiveHint": None, "idempotentHint": None},
    "digitalocean_networking_create_domain": {"readOnlyHint": None, "destructiveHint": None, "idempotentHint": None},
    "digitalocean_networking_delete_domain": {"readOnlyHint": None, "destructiveHint": True, "idempotentHint": None},
    "digitalocean_networking_manage_domain_record": {
        "readOnlyHint": None,
        "destructiveHint": True,
        "idempotentHint": None,
    },
    "digitalocean_networking_list_load_balancers": {
        "readOnlyHint": True,
        "destructiveHint": None,
        "idempotentHint": None,
    },
    "digitalocean_networking_create_load_balancer": {
        "readOnlyHint": None,
        "destructiveHint": None,
        "idempotentHint": None,
    },
    "digitalocean_networking_update_load_balancer": {
        "readOnlyHint": None,
        "destructiveHint": None,
        "idempotentHint": True,
    },
    "digitalocean_networking_delete_load_balancer": {
        "readOnlyHint": None,
        "destructiveHint": True,
        "idempotentHint": None,
    },
}


@pytest.mark.asyncio
async def test_tools_list_has_all_networking_tools_with_valid_descriptions(mcp):
    """TC1 (AC1): exactly 17 digitalocean_networking_* tools, correct names,
    description-length limits, and hint flags."""
    tools = await mcp.list_tools()
    networking_tools = {t.name: t for t in tools if t.name.startswith("digitalocean_networking_")}
    assert set(networking_tools) == set(EXPECTED_TOOLS), set(networking_tools) ^ set(EXPECTED_TOOLS)

    for name, expected_hints in EXPECTED_TOOLS.items():
        tool = networking_tools[name]
        description = tool.description or ""
        first_line = description.split("\n", 1)[0]
        assert len(first_line) <= 100, (name, len(first_line), first_line)
        assert len(description) <= 500, (name, len(description))
        annotations = tool.annotations
        assert getattr(annotations, "readOnlyHint", None) == expected_hints["readOnlyHint"], name
        assert getattr(annotations, "destructiveHint", None) == expected_hints["destructiveHint"], name
        assert getattr(annotations, "idempotentHint", None) == expected_hints["idempotentHint"], name


@pytest.mark.asyncio
async def test_list_vpcs_no_id_returns_paginated_list(mcp, fake_token, set_handler):
    """TC3 (AC3)."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v2/vpcs"
        return httpx.Response(
            200,
            json={
                "vpcs": [
                    {"id": "v1", "name": "vpc-1", "region": "nyc3", "ip_range": "10.10.0.0/24", "default": False},
                    {"id": "v2", "name": "vpc-2", "region": "nyc3", "ip_range": "10.10.1.0/24", "default": False},
                    {"id": "v3", "name": "default-nyc3", "region": "nyc3", "ip_range": "10.10.2.0/24", "default": True},
                ],
                "meta": {"total": 5},
            },
        )

    set_handler(handler)
    result = await call_tool_json(mcp, "digitalocean_networking_list_vpcs", {})
    assert len(result["vpcs"]) == 3
    assert result["has_more"] is True


@pytest.mark.asyncio
async def test_list_vpcs_with_id_merges_detail_members_and_peerings(mcp, fake_token, set_handler):
    """TC4 (AC3)."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v2/vpcs/v1":
            return httpx.Response(
                200,
                json={"vpc": {"id": "v1", "name": "prod-vpc", "region": "nyc3", "ip_range": "10.10.0.0/24", "default": False}},
            )
        if request.url.path == "/v2/vpcs/v1/members":
            return httpx.Response(200, json={"members": [{"urn": "a"}, {"urn": "b"}], "meta": {"total": 2}})
        if request.url.path == "/v2/vpcs/v1/peerings":
            return httpx.Response(
                200,
                json={"vpc_peerings": [{"id": "p1", "name": "prod-to-staging", "status": "ACTIVE", "vpc_ids": ["v1", "v2"]}]},
            )
        raise AssertionError(f"unexpected path {request.url.path}")

    set_handler(handler)
    result = await call_tool_json(mcp, "digitalocean_networking_list_vpcs", {"vpc_id": "v1"})
    assert result["id"] == "v1"
    assert result["member_count"] == 2
    assert len(result["peerings"]) == 1
    assert result["peerings"][0]["id"] == "p1"


@pytest.mark.asyncio
async def test_create_vpc_missing_name_returns_invalid_argument(mcp, fake_token, set_handler):
    """TC5 (AC4): a mocked 400 validation response surfaces invalid_argument,
    carrying DigitalOcean's own message."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"id": "invalid_input", "message": "name is required"})

    set_handler(handler)
    result = await call_tool_json(
        mcp, "digitalocean_networking_create_vpc", {"name": "", "region": "nyc3"}
    )
    assert result["error"]["code"] == "invalid_argument"
    assert "name is required" in result["error"]["message"]


@pytest.mark.asyncio
async def test_update_vpc_sends_partial_patch_body(mcp, fake_token, set_handler):
    """TC6 (AC5): called with only description, the outbound PATCH body has
    only that field -- not name or default."""

    import json as _json

    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["body"] = _json.loads(request.content)
        return httpx.Response(200, json={"vpc": {"id": "v1", "name": "prod-vpc", "region": "nyc3", "ip_range": "10.10.0.0/24", "default": False}})

    set_handler(handler)
    await call_tool_json(mcp, "digitalocean_networking_update_vpc", {"vpc_id": "v1", "description": "new desc"})
    assert captured["method"] == "PATCH"
    assert captured["body"] == {"description": "new desc"}


@pytest.mark.asyncio
async def test_delete_vpc_with_members_returns_structured_error(mcp, fake_token, set_handler):
    """TC7 (AC6)."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"id": "precondition_failed", "message": "Can not delete VPC with members"})

    set_handler(handler)
    result = await call_tool_json(mcp, "digitalocean_networking_delete_vpc", {"vpc_id": "v1"})
    assert result["error"]["code"] == "invalid_argument"
    assert "members" in result["error"]["message"]


@pytest.mark.asyncio
async def test_manage_vpc_peering_create_requires_exactly_two_vpc_ids(mcp, fake_token, set_handler):
    """TC8 (AC7)."""

    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(
            200, json={"vpc_peering": {"id": "p1", "name": "link", "status": "PROVISIONING", "vpc_ids": ["v1", "v2"]}}
        )

    set_handler(handler)

    result_one = await call_tool_json(
        mcp, "digitalocean_networking_manage_vpc_peering", {"action": "create", "vpc_ids": ["v1"]}
    )
    assert result_one["error"]["code"] == "invalid_argument"

    result_three = await call_tool_json(
        mcp, "digitalocean_networking_manage_vpc_peering", {"action": "create", "vpc_ids": ["v1", "v2", "v3"]}
    )
    assert result_three["error"]["code"] == "invalid_argument"
    assert calls == [], "DigitalOcean must never be called for an invalid vpc_ids count"

    result_ok = await call_tool_json(
        mcp,
        "digitalocean_networking_manage_vpc_peering",
        {"action": "create", "vpc_ids": ["v1", "v2"], "name": "link"},
    )
    assert result_ok["id"] == "p1"
    assert calls == ["/v2/vpc_peerings"]


@pytest.mark.asyncio
async def test_manage_vpc_peering_delete_requires_explicit_id(mcp, fake_token, set_handler):
    """TC9 (AC7)."""

    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(204)

    set_handler(handler)

    result_missing = await call_tool_json(mcp, "digitalocean_networking_manage_vpc_peering", {"action": "delete"})
    assert result_missing["error"]["code"] == "invalid_argument"
    assert calls == []

    result_ok = await call_tool_json(
        mcp, "digitalocean_networking_manage_vpc_peering", {"action": "delete", "vpc_peering_id": "p1"}
    )
    assert result_ok["deleted"] is True
    assert calls == ["/v2/vpc_peerings/p1"]


@pytest.mark.asyncio
async def test_list_firewalls_get_by_id_happy_path_and_not_found(mcp, fake_token, set_handler):
    """TC10 (AC8)."""

    def ok_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "firewall": {
                    "id": "f1",
                    "name": "web",
                    "status": "succeeded",
                    "inbound_rules": [{"protocol": "tcp", "ports": "80"}],
                    "outbound_rules": [],
                    "droplet_ids": [1, 2],
                    "tags": ["web"],
                }
            },
        )

    set_handler(ok_handler)
    result = await call_tool_json(mcp, "digitalocean_networking_list_firewalls", {"firewall_id": "f1"})
    assert result["inbound_rules"] == [{"protocol": "tcp", "ports": "80"}]
    assert result["droplet_ids"] == [1, 2]

    def not_found_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"id": "not_found", "message": "firewall not found"})

    set_handler(not_found_handler)
    result2 = await call_tool_json(mcp, "digitalocean_networking_list_firewalls", {"firewall_id": "missing"})
    assert result2["error"]["code"] == "not_found"


@pytest.mark.asyncio
async def test_update_firewall_sends_whole_object_replace_body(mcp, fake_token, set_handler):
    """TC11 (AC9): the outbound PUT body is exactly the supplied payload --
    no merge with any prior server-side state."""

    import json as _json

    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["body"] = _json.loads(request.content)
        return httpx.Response(200, json={"firewall": {"id": "f1", "name": "web"}})

    set_handler(handler)
    payload = {
        "firewall_id": "f1",
        "name": "web",
        "inbound_rules": [{"protocol": "tcp", "ports": "443"}],
        "outbound_rules": [{"protocol": "tcp", "ports": "all"}],
        "droplet_ids": [1],
        "tags": ["web"],
    }
    await call_tool_json(mcp, "digitalocean_networking_update_firewall", payload)
    assert captured["method"] == "PUT"
    assert captured["body"] == {
        "name": "web",
        "inbound_rules": [{"protocol": "tcp", "ports": "443"}],
        "outbound_rules": [{"protocol": "tcp", "ports": "all"}],
        "droplet_ids": [1],
        "tags": ["web"],
    }


@pytest.mark.asyncio
async def test_delete_firewall_requires_explicit_id(mcp, fake_token, set_handler):
    """TC12 (AC10)."""

    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(204)

    set_handler(handler)
    result = await call_tool_json(mcp, "digitalocean_networking_delete_firewall", {"firewall_id": "f1"})
    assert result["deleted"] is True
    assert calls == ["/v2/firewalls/f1"]


@pytest.mark.asyncio
async def test_list_domains_get_by_name_and_create_domain_duplicate_conflict(mcp, fake_token, set_handler):
    """TC13 (AC11)."""

    def ok_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"domain": {"name": "example.com", "ttl": 1800, "zone_file": "..."}})

    set_handler(ok_handler)
    result = await call_tool_json(mcp, "digitalocean_networking_list_domains", {"domain_name": "example.com"})
    assert result["name"] == "example.com"

    def conflict_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(409, json={"id": "conflict", "message": "domain already exists"})

    set_handler(conflict_handler)
    result2 = await call_tool_json(mcp, "digitalocean_networking_create_domain", {"name": "example.com"})
    assert result2["error"]["code"] == "upstream_error"
    assert result2["error"]["retryable"] is False


@pytest.mark.asyncio
async def test_manage_domain_record_create_update_delete_lifecycle(mcp, fake_token, set_handler):
    """TC14 (AC12): create/update/delete each map to the corresponding
    DigitalOcean record endpoint."""

    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        if request.method == "POST":
            return httpx.Response(201, json={"domain_record": {"id": 1, "type": "A", "name": "www", "data": "1.2.3.4"}})
        if request.method == "PATCH":
            return httpx.Response(200, json={"domain_record": {"id": 1, "type": "A", "name": "www", "data": "5.6.7.8"}})
        return httpx.Response(204)

    set_handler(handler)

    created = await call_tool_json(
        mcp,
        "digitalocean_networking_manage_domain_record",
        {"domain_name": "example.com", "action": "create", "type": "A", "name": "www", "data": "1.2.3.4"},
    )
    assert created["id"] == 1

    updated = await call_tool_json(
        mcp,
        "digitalocean_networking_manage_domain_record",
        {"domain_name": "example.com", "action": "update", "domain_record_id": 1, "data": "5.6.7.8"},
    )
    assert updated["data"] == "5.6.7.8"

    deleted = await call_tool_json(
        mcp,
        "digitalocean_networking_manage_domain_record",
        {"domain_name": "example.com", "action": "delete", "domain_record_id": 1},
    )
    assert deleted["deleted"] is True

    assert calls == [
        ("POST", "/v2/domains/example.com/records"),
        ("PATCH", "/v2/domains/example.com/records/1"),
        ("DELETE", "/v2/domains/example.com/records/1"),
    ]


@pytest.mark.asyncio
async def test_manage_domain_record_delete_requires_explicit_record_id(mcp, fake_token, set_handler):
    """TC14 (AC12)."""

    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(204)

    set_handler(handler)
    result = await call_tool_json(
        mcp, "digitalocean_networking_manage_domain_record", {"domain_name": "example.com", "action": "delete"}
    )
    assert result["error"]["code"] == "invalid_argument"
    assert calls == []


@pytest.mark.asyncio
async def test_list_load_balancers_get_by_id_and_update_sends_whole_object_replace(mcp, fake_token, set_handler):
    """TC15 (AC13)."""

    def ok_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "load_balancer": {
                    "id": "lb1",
                    "name": "web-lb",
                    "droplet_ids": [1, 2],
                    "forwarding_rules": [{"entry_protocol": "https", "entry_port": 443}],
                }
            },
        )

    set_handler(ok_handler)
    result = await call_tool_json(mcp, "digitalocean_networking_list_load_balancers", {"lb_id": "lb1"})
    assert result["droplet_ids"] == [1, 2]
    assert result["forwarding_rules"] == [{"entry_protocol": "https", "entry_port": 443}]

    import json as _json

    captured = {}

    def update_handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["body"] = _json.loads(request.content)
        return httpx.Response(200, json={"load_balancer": {"id": "lb1", "name": "web-lb"}})

    set_handler(update_handler)
    await call_tool_json(
        mcp,
        "digitalocean_networking_update_load_balancer",
        {
            "lb_id": "lb1",
            "name": "web-lb",
            "region": "nyc3",
            "forwarding_rules": [{"entry_protocol": "https", "entry_port": 443}],
            "droplet_ids": [3],
        },
    )
    assert captured["method"] == "PUT"
    assert captured["body"] == {
        "name": "web-lb",
        "region": "nyc3",
        "forwarding_rules": [{"entry_protocol": "https", "entry_port": 443}],
        "droplet_ids": [3],
    }


@pytest.mark.asyncio
async def test_delete_load_balancer_requires_explicit_id(mcp, fake_token, set_handler):
    """TC16 (AC14)."""

    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(204)

    set_handler(handler)
    result = await call_tool_json(mcp, "digitalocean_networking_delete_load_balancer", {"lb_id": "lb1"})
    assert result["deleted"] is True
    assert calls == ["/v2/load_balancers/lb1"]
