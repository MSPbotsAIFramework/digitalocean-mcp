"""Node pool and single-node lifecycle tools."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from digitalocean_mcp.errors import ToolError
from digitalocean_mcp.tools._shared import bounded_dumps, get_kubernetes_client, tool_guard


def _trim_node(node: dict[str, Any]) -> dict[str, Any]:
    return {"id": node.get("id"), "name": node.get("name"), "status": node.get("status")}


def _trim_node_pool(pool: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": pool.get("id"),
        "name": pool.get("name"),
        "size": pool.get("size"),
        "count": pool.get("count"),
        "labels": pool.get("labels"),
        "taints": pool.get("taints"),
        "auto_scale": pool.get("auto_scale"),
        "min_nodes": pool.get("min_nodes"),
        "max_nodes": pool.get("max_nodes"),
        "nodes": [_trim_node(n) for n in pool.get("nodes") or []],
    }


def register(mcp: FastMCP) -> None:
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True), structured_output=False)
    @tool_guard
    async def digitalocean_kubernetes_list_node_pools(cluster_id: str) -> str:
        """List every node pool in a cluster, with node-level detail.

        Args: cluster_id - the cluster whose node pools to list.
        """
        async with await get_kubernetes_client() as client:
            body = await client.request("GET", f"/v2/kubernetes/clusters/{cluster_id}/node_pools")
        return bounded_dumps({"node_pools": [_trim_node_pool(p) for p in body.get("node_pools") or []]})

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True), structured_output=False)
    @tool_guard
    async def digitalocean_kubernetes_get_node_pool(cluster_id: str, node_pool_id: str) -> str:
        """Get one node pool by id.

        Args: cluster_id - the cluster. node_pool_id - the node pool to inspect.
        """
        async with await get_kubernetes_client() as client:
            body = await client.request(
                "GET", f"/v2/kubernetes/clusters/{cluster_id}/node_pools/{node_pool_id}"
            )
        return bounded_dumps(_trim_node_pool(body.get("node_pool") or {}))

    @mcp.tool(annotations=ToolAnnotations(), structured_output=False)
    @tool_guard
    async def digitalocean_kubernetes_create_node_pool(
        cluster_id: str,
        name: str,
        size: str,
        count: int,
        auto_scale: bool | None = None,
        min_nodes: int | None = None,
        max_nodes: int | None = None,
        labels: dict[str, str] | None = None,
        taints: list[dict[str, Any]] | None = None,
    ) -> str:
        """Add a new node pool to a cluster.

        DigitalOcean's own validation errors (e.g. min_nodes/max_nodes
        inconsistent with auto_scale) are surfaced as invalid_argument.
        Args: cluster_id - the cluster. name - pool name. size - DigitalOcean
        droplet size slug. count - initial node count. auto_scale,
        min_nodes, max_nodes - optional autoscaling bounds. labels, taints -
        optional Kubernetes labels/taints applied to every node in the pool.
        """
        body: dict[str, Any] = {"name": name, "size": size, "count": count}
        if auto_scale is not None:
            body["auto_scale"] = auto_scale
        if min_nodes is not None:
            body["min_nodes"] = min_nodes
        if max_nodes is not None:
            body["max_nodes"] = max_nodes
        if labels is not None:
            body["labels"] = labels
        if taints is not None:
            body["taints"] = taints

        async with await get_kubernetes_client() as client:
            result = await client.request(
                "POST", f"/v2/kubernetes/clusters/{cluster_id}/node_pools", json_body=body
            )
        return bounded_dumps(_trim_node_pool(result.get("node_pool") or {}))

    @mcp.tool(annotations=ToolAnnotations(idempotentHint=True), structured_output=False)
    @tool_guard
    async def digitalocean_kubernetes_update_node_pool(
        cluster_id: str,
        node_pool_id: str,
        name: str | None = None,
        count: int | None = None,
        labels: dict[str, str] | None = None,
        taints: list[dict[str, Any]] | None = None,
        auto_scale: bool | None = None,
        min_nodes: int | None = None,
        max_nodes: int | None = None,
    ) -> str:
        """Resize or reconfigure a node pool. Repeating the same call converges to the same state.

        Args: cluster_id - the cluster. node_pool_id - the pool to update.
        name, count, labels, taints, auto_scale, min_nodes, max_nodes -
        optional; only the fields supplied here change.
        """
        body: dict[str, Any] = {}
        if name is not None:
            body["name"] = name
        if count is not None:
            body["count"] = count
        if labels is not None:
            body["labels"] = labels
        if taints is not None:
            body["taints"] = taints
        if auto_scale is not None:
            body["auto_scale"] = auto_scale
        if min_nodes is not None:
            body["min_nodes"] = min_nodes
        if max_nodes is not None:
            body["max_nodes"] = max_nodes

        async with await get_kubernetes_client() as client:
            result = await client.request(
                "PUT", f"/v2/kubernetes/clusters/{cluster_id}/node_pools/{node_pool_id}", json_body=body
            )
        return bounded_dumps(_trim_node_pool(result.get("node_pool") or {}))

    @mcp.tool(annotations=ToolAnnotations(destructiveHint=True), structured_output=False)
    @tool_guard
    async def digitalocean_kubernetes_delete_node_pool(cluster_id: str, node_pool_id: str | None = None) -> str:
        """Delete a node pool. Irreversible; requires the explicit pool id.

        No name lookup, no "all pools" variant.
        Args: cluster_id - the cluster. node_pool_id - the single pool to
        delete (required, no default).
        """
        if not node_pool_id:
            raise ToolError("invalid_argument", "node_pool_id is required -- no name lookup, no bulk delete.")
        async with await get_kubernetes_client() as client:
            await client.request(
                "DELETE", f"/v2/kubernetes/clusters/{cluster_id}/node_pools/{node_pool_id}"
            )
        return bounded_dumps({"deleted": True, "cluster_id": cluster_id, "node_pool_id": node_pool_id})

    @mcp.tool(annotations=ToolAnnotations(destructiveHint=True), structured_output=False)
    @tool_guard
    async def digitalocean_kubernetes_delete_node(
        cluster_id: str | None = None,
        node_pool_id: str | None = None,
        node_id: str | None = None,
        skip_drain: bool = False,
        replace: bool = False,
    ) -> str:
        """Remove one node. No bulk/"all nodes in pool" variant exists.

        replace=false (default) drains (unless skip_drain=true) and removes
        the node with no replacement. replace=true is the modern replacement
        for DigitalOcean's deprecated "recycle" operation.
        Args: cluster_id, node_pool_id, node_id - all required. skip_drain,
        replace - optional booleans.
        """
        if not (cluster_id and node_pool_id and node_id):
            raise ToolError(
                "invalid_argument",
                "cluster_id, node_pool_id, and node_id are all required; there is no bulk/"
                "'all nodes in pool' variant.",
            )
        params = {"skip_drain": 1 if skip_drain else 0, "replace": 1 if replace else 0}
        async with await get_kubernetes_client() as client:
            await client.request(
                "DELETE",
                f"/v2/kubernetes/clusters/{cluster_id}/node_pools/{node_pool_id}/nodes/{node_id}",
                params=params,
            )
        return bounded_dumps(
            {"deleted": True, "node_id": node_id, "node_pool_id": node_pool_id, "replace": replace}
        )
