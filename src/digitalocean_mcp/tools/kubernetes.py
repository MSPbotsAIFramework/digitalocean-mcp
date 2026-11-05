"""Cluster lifecycle tools: list, inspect, create, update, upgrade, list
associated resources, and delete a DigitalOcean Kubernetes (DOKS) cluster.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from digitalocean_mcp.errors import ToolError
from digitalocean_mcp.tools._shared import (
    bounded_dumps,
    clamp_limit,
    get_kubernetes_client,
    tool_guard,
)

_DELETE_CLUSTER_MODES = {"plain", "selective", "dangerous"}


def _trim_node_pool_summary(pool: dict[str, Any]) -> dict[str, Any]:
    return {"id": pool.get("id"), "name": pool.get("name"), "count": pool.get("count")}


def _trim_cluster_summary(cluster: dict[str, Any]) -> dict[str, Any]:
    """Lean per-cluster shape for list_clusters -- the hard-capped 200-item
    case must stay well under the response size cap (SOP section 2.5), so
    this intentionally carries less than `_trim_cluster`'s single-cluster
    detail.
    """
    return {
        "id": cluster.get("id"),
        "name": cluster.get("name"),
        "region": cluster.get("region"),
        "version": cluster.get("version"),
        "status": cluster.get("status"),
        "node_pool_count": len(cluster.get("node_pools") or []),
    }


def _trim_cluster(cluster: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": cluster.get("id"),
        "name": cluster.get("name"),
        "region": cluster.get("region"),
        "version": cluster.get("version"),
        "status": cluster.get("status"),
        "node_pools": [_trim_node_pool_summary(p) for p in cluster.get("node_pools") or []],
        "ha": cluster.get("ha"),
        "surge_upgrade": cluster.get("surge_upgrade"),
        "vpc_uuid": cluster.get("vpc_uuid"),
        "tags": cluster.get("tags"),
        "created_at": cluster.get("created_at"),
        "updated_at": cluster.get("updated_at"),
    }


def register(mcp: FastMCP) -> None:
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True), structured_output=False)
    @tool_guard
    async def digitalocean_kubernetes_list_clusters(limit: int | None = None) -> str:
        """List DigitalOcean Kubernetes (DOKS) clusters in the account.

        Args: limit - max clusters to return (default 50, hard cap 200).
        """
        per_page = clamp_limit(limit)
        async with await get_kubernetes_client() as client:
            body = await client.request("GET", "/v2/kubernetes/clusters", params={"per_page": per_page})
        clusters = body.get("kubernetes_clusters") or []
        total = body.get("meta", {}).get("total", len(clusters))
        return bounded_dumps(
            {
                "clusters": [_trim_cluster_summary(c) for c in clusters],
                "has_more": total > len(clusters),
            }
        )

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True), structured_output=False)
    @tool_guard
    async def digitalocean_kubernetes_get_cluster(
        cluster_id: str,
        include_upgrades: bool = False,
        include_status_messages: bool = False,
    ) -> str:
        """Get one cluster's spec, status, and node-pool summary.

        Args: cluster_id - the cluster's DigitalOcean id. include_upgrades -
        also fetch available control-plane upgrade target versions (empty
        list if already current). include_status_messages - also fetch
        recent lifecycle status messages.
        """
        async with await get_kubernetes_client() as client:
            body = await client.request("GET", f"/v2/kubernetes/clusters/{cluster_id}")
            result = _trim_cluster(body.get("kubernetes_cluster") or {})
            if include_upgrades:
                upgrades = await client.request("GET", f"/v2/kubernetes/clusters/{cluster_id}/upgrades")
                result["available_upgrades"] = upgrades.get("available_upgrade_versions") or []
            if include_status_messages:
                messages = await client.request(
                    "GET", f"/v2/kubernetes/clusters/{cluster_id}/status_messages"
                )
                result["status_messages"] = messages.get("status_messages") or []
        return bounded_dumps(result)

    @mcp.tool(annotations=ToolAnnotations(), structured_output=False)
    @tool_guard
    async def digitalocean_kubernetes_create_cluster(
        name: str,
        region: str,
        version: str,
        node_pools: list[dict[str, Any]],
        ha: bool | None = None,
        surge_upgrade: bool | None = None,
        auto_upgrade: bool | None = None,
        tags: list[str] | None = None,
        vpc_uuid: str | None = None,
    ) -> str:
        """Create a new DOKS cluster with at least one node pool.

        DigitalOcean's own validation errors (bad region/size/version slug,
        malformed node pool spec) are surfaced as invalid_argument.
        Args: name, region, version (see get_deployment_options). node_pools
        - list of {name, size, count, ...} specs, at least one required.
        ha, surge_upgrade, auto_upgrade - optional booleans. tags, vpc_uuid -
        optional.
        """
        body: dict[str, Any] = {
            "name": name,
            "region": region,
            "version": version,
            "node_pools": node_pools,
        }
        if ha is not None:
            body["ha"] = ha
        if surge_upgrade is not None:
            body["surge_upgrade"] = surge_upgrade
        if auto_upgrade is not None:
            body["auto_upgrade"] = auto_upgrade
        if tags is not None:
            body["tags"] = tags
        if vpc_uuid is not None:
            body["vpc_uuid"] = vpc_uuid

        async with await get_kubernetes_client() as client:
            result = await client.request("POST", "/v2/kubernetes/clusters", json_body=body)
        return bounded_dumps(_trim_cluster(result.get("kubernetes_cluster") or {}))

    @mcp.tool(annotations=ToolAnnotations(idempotentHint=True), structured_output=False)
    @tool_guard
    async def digitalocean_kubernetes_update_cluster(
        cluster_id: str,
        name: str | None = None,
        tags: list[str] | None = None,
        auto_upgrade: bool | None = None,
        surge_upgrade: bool | None = None,
        ha: bool | None = None,
        maintenance_policy: dict[str, Any] | None = None,
    ) -> str:
        """Partially update a cluster: only the fields supplied here change.

        Unlike DigitalOcean's App Platform update (a full-spec PUT replace),
        this keeps every omitted field at its current server-side value.
        Args: cluster_id - the cluster. name, tags, auto_upgrade,
        surge_upgrade, ha, maintenance_policy - all optional.
        """
        body: dict[str, Any] = {}
        if name is not None:
            body["name"] = name
        if tags is not None:
            body["tags"] = tags
        if auto_upgrade is not None:
            body["auto_upgrade"] = auto_upgrade
        if surge_upgrade is not None:
            body["surge_upgrade"] = surge_upgrade
        if ha is not None:
            body["ha"] = ha
        if maintenance_policy is not None:
            body["maintenance_policy"] = maintenance_policy

        async with await get_kubernetes_client() as client:
            result = await client.request("PUT", f"/v2/kubernetes/clusters/{cluster_id}", json_body=body)
        return bounded_dumps(_trim_cluster(result.get("kubernetes_cluster") or {}))

    @mcp.tool(annotations=ToolAnnotations(destructiveHint=True), structured_output=False)
    @tool_guard
    async def digitalocean_kubernetes_upgrade_cluster(cluster_id: str, version: str | None = None) -> str:
        """Trigger a control-plane upgrade. Disruptive maintenance operation.

        There is no "upgrade to latest" default -- `version` must be an
        explicit target slug obtained from a prior get_cluster(cluster_id,
        include_upgrades=true) call.
        Args: cluster_id - the cluster to upgrade. version - explicit target
        Kubernetes version slug (required, no default).
        """
        if not version:
            raise ToolError(
                "invalid_argument",
                "version is required -- call get_cluster(include_upgrades=true) to obtain a "
                "real target version; there is no implicit 'upgrade to latest' default.",
            )
        async with await get_kubernetes_client() as client:
            await client.request(
                "POST", f"/v2/kubernetes/clusters/{cluster_id}/upgrade", json_body={"version": version}
            )
        return bounded_dumps({"upgrading": True, "cluster_id": cluster_id, "version": version})

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True), structured_output=False)
    @tool_guard
    async def digitalocean_kubernetes_list_cluster_resources(cluster_id: str) -> str:
        """List load balancers, volumes, and volume snapshots associated with a cluster.

        Intended to be called before a destructive delete, to see what
        `delete_cluster(mode="dangerous")` would also destroy.
        Args: cluster_id - the cluster to inspect.
        """
        async with await get_kubernetes_client() as client:
            body = await client.request(
                "GET", f"/v2/kubernetes/clusters/{cluster_id}/destroy_with_associated_resources"
            )
        return bounded_dumps(
            {
                "load_balancers": [{"id": r.get("id"), "name": r.get("name")} for r in body.get("load_balancers") or []],
                "volumes": [{"id": r.get("id"), "name": r.get("name")} for r in body.get("volumes") or []],
                "volume_snapshots": [
                    {"id": r.get("id"), "name": r.get("name")} for r in body.get("volume_snapshots") or []
                ],
            }
        )

    @mcp.tool(annotations=ToolAnnotations(destructiveHint=True), structured_output=False)
    @tool_guard
    async def digitalocean_kubernetes_delete_cluster(
        cluster_id: str,
        mode: str | None = None,
        load_balancer_ids: list[str] | None = None,
        volume_ids: list[str] | None = None,
        volume_snapshot_ids: list[str] | None = None,
    ) -> str:
        """Delete a cluster. No default mode -- the caller must choose one.

        "plain" deletes only the cluster. "selective" also destroys exactly
        the listed ids. "dangerous" is irreversible: cluster + every
        associated resource -- call list_cluster_resources first.
        Args: mode - plain|selective|dangerous, required. load_balancer_ids/
        volume_ids/volume_snapshot_ids - for "selective", one required.
        """
        if mode not in _DELETE_CLUSTER_MODES:
            raise ToolError(
                "invalid_argument",
                f"mode is required and must be one of {sorted(_DELETE_CLUSTER_MODES)}; got {mode!r}. "
                "There is no default -- choose explicitly.",
            )

        async with await get_kubernetes_client() as client:
            if mode == "plain":
                await client.request("DELETE", f"/v2/kubernetes/clusters/{cluster_id}")
            elif mode == "selective":
                if not (load_balancer_ids or volume_ids or volume_snapshot_ids):
                    raise ToolError(
                        "invalid_argument",
                        "mode='selective' requires at least one id in load_balancer_ids, "
                        "volume_ids, or volume_snapshot_ids.",
                    )
                params: dict[str, Any] = {}
                if load_balancer_ids:
                    params["load_balancers"] = ",".join(load_balancer_ids)
                if volume_ids:
                    params["volumes"] = ",".join(volume_ids)
                if volume_snapshot_ids:
                    params["volume_snapshots"] = ",".join(volume_snapshot_ids)
                await client.request(
                    "DELETE",
                    f"/v2/kubernetes/clusters/{cluster_id}/destroy_with_associated_resources/selective",
                    params=params,
                )
            else:  # dangerous
                await client.request(
                    "DELETE", f"/v2/kubernetes/clusters/{cluster_id}/destroy_with_associated_resources/dangerous"
                )
        return bounded_dumps({"deleted": True, "cluster_id": cluster_id, "mode": mode})
