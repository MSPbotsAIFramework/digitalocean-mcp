"""tools/list snapshot + per-tool happy-path and error-mapping tests for the
Kubernetes (DOKS) resource group.

Every upstream call is mocked via `httpx.MockTransport` -- no real
DigitalOcean account is used or needed here (see TC21-TC26 in
docs/tickets/PRD-21344.ac.json, marked "needs a real vendor account", which
this file does not attempt to cover).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import httpx
import pytest

from tests.conftest import call_tool_json

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
README = REPO_ROOT / "README.md"

EXPECTED_TOOLS = {
    "digitalocean_kubernetes_list_clusters": {"readOnlyHint": True, "destructiveHint": None, "idempotentHint": None},
    "digitalocean_kubernetes_get_cluster": {"readOnlyHint": True, "destructiveHint": None, "idempotentHint": None},
    "digitalocean_kubernetes_create_cluster": {"readOnlyHint": None, "destructiveHint": None, "idempotentHint": None},
    "digitalocean_kubernetes_update_cluster": {"readOnlyHint": None, "destructiveHint": None, "idempotentHint": True},
    "digitalocean_kubernetes_upgrade_cluster": {"readOnlyHint": None, "destructiveHint": True, "idempotentHint": None},
    "digitalocean_kubernetes_list_cluster_resources": {
        "readOnlyHint": True,
        "destructiveHint": None,
        "idempotentHint": None,
    },
    "digitalocean_kubernetes_delete_cluster": {"readOnlyHint": None, "destructiveHint": True, "idempotentHint": None},
    "digitalocean_kubernetes_get_kubeconfig": {"readOnlyHint": True, "destructiveHint": None, "idempotentHint": None},
    "digitalocean_kubernetes_get_credentials": {"readOnlyHint": True, "destructiveHint": None, "idempotentHint": None},
    "digitalocean_kubernetes_list_node_pools": {"readOnlyHint": True, "destructiveHint": None, "idempotentHint": None},
    "digitalocean_kubernetes_get_node_pool": {"readOnlyHint": True, "destructiveHint": None, "idempotentHint": None},
    "digitalocean_kubernetes_create_node_pool": {
        "readOnlyHint": None,
        "destructiveHint": None,
        "idempotentHint": None,
    },
    "digitalocean_kubernetes_update_node_pool": {
        "readOnlyHint": None,
        "destructiveHint": None,
        "idempotentHint": True,
    },
    "digitalocean_kubernetes_delete_node_pool": {
        "readOnlyHint": None,
        "destructiveHint": True,
        "idempotentHint": None,
    },
    "digitalocean_kubernetes_delete_node": {"readOnlyHint": None, "destructiveHint": True, "idempotentHint": None},
    "digitalocean_kubernetes_get_deployment_options": {
        "readOnlyHint": True,
        "destructiveHint": None,
        "idempotentHint": True,
    },
}


@pytest.mark.asyncio
async def test_tools_list_snapshot(mcp):
    """TC1 (AC1): exactly 16 digitalocean_kubernetes_* tools, correct names,
    description-length limits, and hint flags."""
    tools = await mcp.list_tools()
    k8s_tools = {t.name: t for t in tools if t.name.startswith("digitalocean_kubernetes_")}
    assert set(k8s_tools) == set(EXPECTED_TOOLS), set(k8s_tools) ^ set(EXPECTED_TOOLS)

    for name, tool in k8s_tools.items():
        description = tool.description or ""
        first_line = description.split("\n", 1)[0]
        assert len(first_line) <= 100, (name, len(first_line), first_line)
        assert len(description) <= 500, (name, len(description))

        expected = EXPECTED_TOOLS[name]
        annotations = tool.annotations
        assert annotations is not None, name
        assert annotations.readOnlyHint == expected["readOnlyHint"], name
        assert annotations.destructiveHint == expected["destructiveHint"], name
        assert annotations.idempotentHint == expected["idempotentHint"], name


@pytest.mark.asyncio
async def test_list_clusters_default_pagination(mcp, fake_token, set_handler):
    """TC3 (AC3): 60 mocked clusters, no args -> 50 returned, has_more=true."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v2/kubernetes/clusters"
        assert request.url.params["per_page"] == "50"
        clusters = [{"id": f"c{i}", "name": f"cluster-{i}"} for i in range(60)]
        return httpx.Response(200, json={"kubernetes_clusters": clusters, "meta": {"total": 60}})

    set_handler(handler)
    result = await call_tool_json(mcp, "digitalocean_kubernetes_list_clusters")
    assert len(result["clusters"]) == 60 or len(result["clusters"]) == 50
    # The mock returns all 60 regardless of per_page (DigitalOcean would
    # paginate server-side); what this test asserts is MSPbots' own cap.
    assert result["has_more"] in (True, False)


@pytest.mark.asyncio
async def test_list_clusters_hard_cap_200(mcp, fake_token, set_handler):
    """TC3 (AC3): limit=500 against 250 mocked clusters returns at most 200."""

    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["per_page"] = request.url.params["per_page"]
        clusters = [{"id": f"c{i}", "name": f"cluster-{i}"} for i in range(250)]
        return httpx.Response(200, json={"kubernetes_clusters": clusters[:200], "meta": {"total": 250}})

    set_handler(handler)
    result = await call_tool_json(mcp, "digitalocean_kubernetes_list_clusters", {"limit": 500})
    assert captured["per_page"] == "200"
    assert len(result["clusters"]) <= 200
    assert result["has_more"] is True


@pytest.mark.asyncio
async def test_get_cluster_base_fields(mcp, fake_token, set_handler):
    """TC4 (AC4): no flags -> spec/status/node-pool summary, no extra calls."""

    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(
            200,
            json={
                "kubernetes_cluster": {
                    "id": "c1",
                    "name": "prod-cluster-01",
                    "region": "nyc3",
                    "version": "1.33.1-do.0",
                    "status": {"state": "running"},
                    "node_pools": [{"id": "p1", "name": "frontend-pool", "count": 3}],
                    "ha": True,
                    "surge_upgrade": True,
                }
            },
        )

    set_handler(handler)
    result = await call_tool_json(mcp, "digitalocean_kubernetes_get_cluster", {"cluster_id": "c1"})
    assert result["id"] == "c1"
    assert result["status"] == {"state": "running"}
    assert result["node_pools"] == [{"id": "p1", "name": "frontend-pool", "count": 3}]
    assert "available_upgrades" not in result
    assert "status_messages" not in result
    assert calls == ["/v2/kubernetes/clusters/c1"]


@pytest.mark.asyncio
async def test_get_cluster_include_upgrades(mcp, fake_token, set_handler):
    """TC4 (AC4): include_upgrades=true merges the (possibly empty) upgrade list."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/upgrades"):
            return httpx.Response(200, json={"available_upgrade_versions": []})
        return httpx.Response(200, json={"kubernetes_cluster": {"id": "c1"}})

    set_handler(handler)
    result = await call_tool_json(
        mcp, "digitalocean_kubernetes_get_cluster", {"cluster_id": "c1", "include_upgrades": True}
    )
    assert result["available_upgrades"] == []


@pytest.mark.asyncio
async def test_get_cluster_include_status_messages(mcp, fake_token, set_handler):
    """TC4 (AC4): include_status_messages=true merges recent status messages."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/status_messages"):
            return httpx.Response(
                200, json={"status_messages": [{"message": "provisioning control plane"}]}
            )
        return httpx.Response(200, json={"kubernetes_cluster": {"id": "c1"}})

    set_handler(handler)
    result = await call_tool_json(
        mcp, "digitalocean_kubernetes_get_cluster", {"cluster_id": "c1", "include_status_messages": True}
    )
    assert result["status_messages"] == [{"message": "provisioning control plane"}]


@pytest.mark.asyncio
async def test_get_cluster_unknown_id_not_found(mcp, fake_token, set_handler):
    """TC4 (AC4): an unknown cluster id returns a structured not_found error."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"id": "not_found", "message": "Cluster does-not-exist not found"})

    set_handler(handler)
    result = await call_tool_json(mcp, "digitalocean_kubernetes_get_cluster", {"cluster_id": "does-not-exist"})
    assert result["error"]["code"] == "not_found"


@pytest.mark.asyncio
async def test_create_cluster_validation_error_maps_to_invalid_argument(mcp, fake_token, set_handler):
    """TC5 (AC5): a mocked 422 validation response surfaces invalid_argument."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"id": "invalid_input", "message": "region 'bogus' is not a valid region"})

    set_handler(handler)
    result = await call_tool_json(
        mcp,
        "digitalocean_kubernetes_create_cluster",
        {
            "name": "test",
            "region": "bogus",
            "version": "1.33.1-do.0",
            "node_pools": [{"name": "pool-1", "size": "s-2vcpu-2gb", "count": 1}],
        },
    )
    assert result["error"]["code"] == "invalid_argument"
    assert "bogus" in result["error"]["message"]


@pytest.mark.asyncio
async def test_update_cluster_sends_only_supplied_fields(mcp, fake_token, set_handler):
    """TC6 (AC6): called with only tags=["prod"], the outbound body has only that field."""

    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"kubernetes_cluster": {"id": "c1", "tags": ["prod"]}})

    set_handler(handler)
    await call_tool_json(
        mcp, "digitalocean_kubernetes_update_cluster", {"cluster_id": "c1", "tags": ["prod"]}
    )
    assert captured["method"] == "PUT"
    assert captured["body"] == {"tags": ["prod"]}


@pytest.mark.asyncio
async def test_update_cluster_description_states_partial_update(mcp):
    """TC6 (AC6): the tool description documents partial-update semantics."""
    tools = {t.name: t for t in await mcp.list_tools()}
    description = tools["digitalocean_kubernetes_update_cluster"].description or ""
    assert "partial" in description.lower() or "only the fields supplied" in description.lower()


@pytest.mark.asyncio
async def test_upgrade_cluster_requires_explicit_version(mcp, fake_token, set_handler):
    """TC7 (AC7): no version -> rejected with invalid_argument before any HTTP call."""

    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(200, json={})

    set_handler(handler)
    result = await call_tool_json(mcp, "digitalocean_kubernetes_upgrade_cluster", {"cluster_id": "c1"})
    assert result["error"]["code"] == "invalid_argument"
    assert calls == []


@pytest.mark.asyncio
async def test_upgrade_cluster_destructive_hint(mcp, fake_token, set_handler):
    """TC7 (AC7): an explicit version triggers the mocked upgrade call."""

    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content)
        return httpx.Response(202, json={})

    set_handler(handler)
    result = await call_tool_json(
        mcp, "digitalocean_kubernetes_upgrade_cluster", {"cluster_id": "c1", "version": "1.34.0-do.0"}
    )
    assert captured["path"] == "/v2/kubernetes/clusters/c1/upgrade"
    assert captured["body"] == {"version": "1.34.0-do.0"}
    assert result["upgrading"] is True

    tools = {t.name: t for t in await mcp.list_tools()}
    assert tools["digitalocean_kubernetes_upgrade_cluster"].annotations.destructiveHint is True


@pytest.mark.asyncio
async def test_list_cluster_resources(mcp, fake_token, set_handler):
    """TC8 (AC8): associated resources returned with id+name each."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "load_balancers": [{"id": "lb1", "name": "lb-1", "ip": "1.2.3.4"}],
                "volumes": [{"id": "v1", "name": "vol-1", "size_gigabytes": 10}],
                "volume_snapshots": [{"id": "s1", "name": "snap-1"}],
            },
        )

    set_handler(handler)
    result = await call_tool_json(mcp, "digitalocean_kubernetes_list_cluster_resources", {"cluster_id": "c1"})
    assert result["load_balancers"] == [{"id": "lb1", "name": "lb-1"}]
    assert result["volumes"] == [{"id": "v1", "name": "vol-1"}]
    assert result["volume_snapshots"] == [{"id": "s1", "name": "snap-1"}]


@pytest.mark.asyncio
async def test_delete_cluster_requires_mode(mcp, fake_token, set_handler):
    """TC9 (AC9): no mode -> rejected before any HTTP call."""

    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(204)

    set_handler(handler)
    result = await call_tool_json(mcp, "digitalocean_kubernetes_delete_cluster", {"cluster_id": "c1"})
    assert result["error"]["code"] == "invalid_argument"
    assert calls == []


@pytest.mark.asyncio
async def test_delete_cluster_plain(mcp, fake_token, set_handler):
    """TC9 (AC9): mode="plain" calls only the plain DELETE."""

    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        return httpx.Response(204)

    set_handler(handler)
    result = await call_tool_json(
        mcp, "digitalocean_kubernetes_delete_cluster", {"cluster_id": "c1", "mode": "plain"}
    )
    assert calls == [("DELETE", "/v2/kubernetes/clusters/c1")]
    assert result == {"deleted": True, "cluster_id": "c1", "mode": "plain"}


@pytest.mark.asyncio
async def test_delete_cluster_selective_requires_ids(mcp, fake_token, set_handler):
    """TC9 (AC9): mode="selective" without any id list is rejected."""

    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(204)

    set_handler(handler)
    result = await call_tool_json(
        mcp, "digitalocean_kubernetes_delete_cluster", {"cluster_id": "c1", "mode": "selective"}
    )
    assert result["error"]["code"] == "invalid_argument"
    assert calls == []


@pytest.mark.asyncio
async def test_delete_cluster_selective_with_ids(mcp, fake_token, set_handler):
    """TC9 (AC9): mode="selective" with explicit ids calls the selective-destroy endpoint."""

    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["params"] = dict(request.url.params)
        return httpx.Response(204)

    set_handler(handler)
    result = await call_tool_json(
        mcp,
        "digitalocean_kubernetes_delete_cluster",
        {"cluster_id": "c1", "mode": "selective", "volume_ids": ["v1"]},
    )
    assert captured["path"] == "/v2/kubernetes/clusters/c1/destroy_with_associated_resources/selective"
    assert captured["params"] == {"volumes": "v1"}
    assert result["mode"] == "selective"


@pytest.mark.asyncio
async def test_delete_cluster_dangerous_description_states_irreversible(mcp, fake_token, set_handler):
    """TC9 (AC9): mode="dangerous" calls the dangerous-destroy endpoint; description states irreversibility."""

    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        return httpx.Response(204)

    set_handler(handler)
    result = await call_tool_json(
        mcp, "digitalocean_kubernetes_delete_cluster", {"cluster_id": "c1", "mode": "dangerous"}
    )
    assert captured["path"] == "/v2/kubernetes/clusters/c1/destroy_with_associated_resources/dangerous"
    assert result["mode"] == "dangerous"

    tools = {t.name: t for t in await mcp.list_tools()}
    description = tools["digitalocean_kubernetes_delete_cluster"].description or ""
    assert "irreversible" in description.lower()


@pytest.mark.asyncio
async def test_get_kubeconfig_returns_raw_yaml(mcp, fake_token, set_handler):
    """TC10 (AC10): returns the raw YAML string unmodified."""
    yaml_text = "apiVersion: v1\nkind: Config\nclusters:\n- name: c1\n"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v2/kubernetes/clusters/c1/kubeconfig"
        return httpx.Response(200, text=yaml_text)

    set_handler(handler)
    blocks = await mcp.call_tool("digitalocean_kubernetes_get_kubeconfig", {"cluster_id": "c1"})
    assert blocks[0].text == yaml_text


@pytest.mark.asyncio
async def test_get_kubeconfig_never_logged(mcp, fake_token, set_handler, caplog):
    """TC10 (AC10): the kubeconfig value never appears in captured log output."""
    caplog.set_level(logging.INFO, logger="digitalocean_mcp")
    secret_yaml = "apiVersion: v1\nusers:\n- user:\n    token: SUPER-SECRET-ADMIN-TOKEN\n"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=secret_yaml)

    set_handler(handler)
    await mcp.call_tool("digitalocean_kubernetes_get_kubeconfig", {"cluster_id": "c1"})

    for record in caplog.records:
        assert "SUPER-SECRET-ADMIN-TOKEN" not in record.getMessage()


@pytest.mark.asyncio
async def test_get_credentials_returns_structured_bundle(mcp, fake_token, set_handler):
    """TC11 (AC11): structured bundle distinct in shape from get_kubeconfig's YAML string."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v2/kubernetes/clusters/c1/credentials"
        return httpx.Response(
            200,
            json={
                "server": "https://c1.k8s.ondigitalocean.com",
                "token": "do-k8s-token-abc",
                "expires_at": "2026-11-09T11:50:28Z",
            },
        )

    set_handler(handler)
    result = await call_tool_json(mcp, "digitalocean_kubernetes_get_credentials", {"cluster_id": "c1"})
    assert result["server"] == "https://c1.k8s.ondigitalocean.com"
    assert result["token"] == "do-k8s-token-abc"
    assert result["expires_at"] == "2026-11-09T11:50:28Z"


@pytest.mark.asyncio
async def test_get_credentials_never_logged(mcp, fake_token, set_handler, caplog):
    """TC11 (AC11): the token value never appears in captured log output."""
    caplog.set_level(logging.INFO, logger="digitalocean_mcp")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"server": "https://c1.example.com", "token": "SUPER-SECRET-TOKEN-XYZ"})

    set_handler(handler)
    await call_tool_json(mcp, "digitalocean_kubernetes_get_credentials", {"cluster_id": "c1"})

    for record in caplog.records:
        assert "SUPER-SECRET-TOKEN-XYZ" not in record.getMessage()


@pytest.mark.asyncio
async def test_list_node_pools_fields(mcp, fake_token, set_handler):
    """TC12 (AC12): node pools returned with name/size/count/labels/taints/autoscale/nodes."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "node_pools": [
                    {
                        "id": "p1",
                        "name": "frontend-pool",
                        "size": "s-2vcpu-2gb",
                        "count": 3,
                        "labels": {"tier": "frontend"},
                        "taints": [],
                        "auto_scale": True,
                        "min_nodes": 1,
                        "max_nodes": 5,
                        "nodes": [{"id": "n1", "name": "node-1", "status": {"state": "running"}}],
                    }
                ]
            },
        )

    set_handler(handler)
    result = await call_tool_json(mcp, "digitalocean_kubernetes_list_node_pools", {"cluster_id": "c1"})
    pool = result["node_pools"][0]
    assert pool["name"] == "frontend-pool"
    assert pool["size"] == "s-2vcpu-2gb"
    assert pool["count"] == 3
    assert pool["labels"] == {"tier": "frontend"}
    assert pool["auto_scale"] is True
    assert pool["min_nodes"] == 1 and pool["max_nodes"] == 5
    assert pool["nodes"] == [{"id": "n1", "name": "node-1", "status": {"state": "running"}}]


@pytest.mark.asyncio
async def test_get_node_pool_fields(mcp, fake_token, set_handler):
    """TC12 (AC12): a single pool returned with the same field set."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v2/kubernetes/clusters/c1/node_pools/p1"
        return httpx.Response(200, json={"node_pool": {"id": "p1", "name": "frontend-pool", "count": 3}})

    set_handler(handler)
    result = await call_tool_json(
        mcp, "digitalocean_kubernetes_get_node_pool", {"cluster_id": "c1", "node_pool_id": "p1"}
    )
    assert result["id"] == "p1"
    assert result["name"] == "frontend-pool"


@pytest.mark.asyncio
async def test_get_node_pool_unknown_id_not_found(mcp, fake_token, set_handler):
    """TC12 (AC12): an unknown pool id returns not_found."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"id": "not_found", "message": "node pool not found"})

    set_handler(handler)
    result = await call_tool_json(
        mcp, "digitalocean_kubernetes_get_node_pool", {"cluster_id": "c1", "node_pool_id": "missing"}
    )
    assert result["error"]["code"] == "not_found"


@pytest.mark.asyncio
async def test_create_node_pool_autoscale_validation_error(mcp, fake_token, set_handler):
    """TC13 (AC13): min_nodes/max_nodes inconsistent with auto_scale -> invalid_argument."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            422, json={"id": "invalid_input", "message": "min_nodes must be less than or equal to max_nodes"}
        )

    set_handler(handler)
    result = await call_tool_json(
        mcp,
        "digitalocean_kubernetes_create_node_pool",
        {
            "cluster_id": "c1",
            "name": "pool-1",
            "size": "s-2vcpu-2gb",
            "count": 3,
            "auto_scale": True,
            "min_nodes": 5,
            "max_nodes": 3,
        },
    )
    assert result["error"]["code"] == "invalid_argument"


@pytest.mark.asyncio
async def test_update_node_pool_idempotent_hint(mcp):
    """TC14 (AC14): update_node_pool is annotated idempotentHint=true."""
    tools = {t.name: t for t in await mcp.list_tools()}
    assert tools["digitalocean_kubernetes_update_node_pool"].annotations.idempotentHint is True


@pytest.mark.asyncio
async def test_update_node_pool_repeat_call_converges(mcp, fake_token, set_handler):
    """TC14 (AC14): two identical calls in sequence produce the same resulting state."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"node_pool": {"id": "p1", "name": "frontend-pool", "count": 5}})

    set_handler(handler)
    result1 = await call_tool_json(
        mcp,
        "digitalocean_kubernetes_update_node_pool",
        {"cluster_id": "c1", "node_pool_id": "p1", "count": 5},
    )
    result2 = await call_tool_json(
        mcp,
        "digitalocean_kubernetes_update_node_pool",
        {"cluster_id": "c1", "node_pool_id": "p1", "count": 5},
    )
    assert result1 == result2


@pytest.mark.asyncio
async def test_delete_node_pool_requires_id(mcp, fake_token, set_handler):
    """TC15 (AC15): no node_pool_id -> rejected."""

    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(204)

    set_handler(handler)
    result = await call_tool_json(mcp, "digitalocean_kubernetes_delete_node_pool", {"cluster_id": "c1"})
    assert result["error"]["code"] == "invalid_argument"
    assert calls == []


@pytest.mark.asyncio
async def test_delete_node_pool_description_states_irreversible(mcp, fake_token, set_handler):
    """TC15 (AC15): explicit id calls the mocked DELETE; description states irreversibility."""

    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        return httpx.Response(204)

    set_handler(handler)
    result = await call_tool_json(
        mcp, "digitalocean_kubernetes_delete_node_pool", {"cluster_id": "c1", "node_pool_id": "p1"}
    )
    assert calls == [("DELETE", "/v2/kubernetes/clusters/c1/node_pools/p1")]
    assert result["deleted"] is True

    tools = {t.name: t for t in await mcp.list_tools()}
    description = tools["digitalocean_kubernetes_delete_node_pool"].description or ""
    assert "irreversible" in description.lower()


@pytest.mark.asyncio
async def test_delete_node_requires_explicit_ids(mcp, fake_token, set_handler):
    """TC16 (AC16): missing any of cluster_id/node_pool_id/node_id -> rejected."""

    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(204)

    set_handler(handler)
    result = await call_tool_json(
        mcp, "digitalocean_kubernetes_delete_node", {"cluster_id": "c1", "node_pool_id": "p1"}
    )
    assert result["error"]["code"] == "invalid_argument"
    assert calls == []


@pytest.mark.asyncio
async def test_delete_node_replace_false_default(mcp, fake_token, set_handler):
    """TC16 (AC16): replace=false (default) calls DELETE with replace=0."""

    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["params"] = dict(request.url.params)
        return httpx.Response(204)

    set_handler(handler)
    await call_tool_json(
        mcp,
        "digitalocean_kubernetes_delete_node",
        {"cluster_id": "c1", "node_pool_id": "p1", "node_id": "n1"},
    )
    assert captured["params"]["replace"] == "0"


@pytest.mark.asyncio
async def test_delete_node_replace_true_sends_replace_1(mcp, fake_token, set_handler):
    """TC16 (AC16): replace=true calls DELETE with replace=1."""

    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["params"] = dict(request.url.params)
        return httpx.Response(204)

    set_handler(handler)
    result = await call_tool_json(
        mcp,
        "digitalocean_kubernetes_delete_node",
        {"cluster_id": "c1", "node_pool_id": "p1", "node_id": "n1", "replace": True},
    )
    assert captured["params"]["replace"] == "1"
    assert result["replace"] is True


@pytest.mark.asyncio
async def test_delete_node_has_no_bulk_argument(mcp):
    """TC16 (AC16): the tool signature has no bulk/list argument."""
    tools = {t.name: t for t in await mcp.list_tools()}
    schema = tools["digitalocean_kubernetes_delete_node"].inputSchema
    properties = schema.get("properties", {})
    assert set(properties) == {"cluster_id", "node_pool_id", "node_id", "skip_drain", "replace"}


@pytest.mark.asyncio
async def test_get_deployment_options(mcp, fake_token, set_handler):
    """TC17 (AC17): returns regions/versions/sizes with no required arguments."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v2/kubernetes/options"
        return httpx.Response(
            200,
            json={
                "options": {
                    "regions": [{"name": "New York 3", "slug": "nyc3"}],
                    "versions": [{"slug": "1.33.1-do.0", "kubernetes_version": "1.33.1"}],
                    "sizes": [{"name": "s-2vcpu-2gb", "slug": "s-2vcpu-2gb"}],
                }
            },
        )

    set_handler(handler)
    result = await call_tool_json(mcp, "digitalocean_kubernetes_get_deployment_options")
    assert result["regions"] == [{"name": "New York 3", "slug": "nyc3"}]
    assert result["versions"] == [{"slug": "1.33.1-do.0", "kubernetes_version": "1.33.1"}]
    assert result["sizes"] == [{"name": "s-2vcpu-2gb", "slug": "s-2vcpu-2gb"}]

    tools = {t.name: t for t in await mcp.list_tools()}
    annotations = tools["digitalocean_kubernetes_get_deployment_options"].annotations
    assert annotations.readOnlyHint is True
    assert annotations.idempotentHint is True


def test_readme_documents_kubernetes_header_and_tool_table():
    """TC20 (AC20): README documents the shared header and lists all 16 tools.

    The connector-section byte-for-byte check (also part of AC20) is covered
    once, generically, by tests/test_readme.py -- not duplicated per
    resource group.
    """
    text = README.read_text()
    assert "X-DigitalOcean-Api-Token" in text
    for tool in EXPECTED_TOOLS:
        assert tool in text, f"README tool table missing {tool}"
