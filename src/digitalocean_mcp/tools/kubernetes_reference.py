"""Account-level reference data needed to build a cluster/node-pool spec."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from digitalocean_mcp.tools._shared import bounded_dumps, get_kubernetes_client, tool_guard


def register(mcp: FastMCP) -> None:
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True), structured_output=False)
    @tool_guard
    async def digitalocean_kubernetes_get_deployment_options() -> str:
        """List valid regions, Kubernetes versions, and node sizes for DOKS.

        Account-level and stateless: no arguments. Use this to validate
        inputs before calling create_cluster or create_node_pool.
        """
        async with await get_kubernetes_client() as client:
            body = await client.request("GET", "/v2/kubernetes/options")
        options = body.get("options") or {}
        return bounded_dumps(
            {
                "regions": options.get("regions") or [],
                "versions": options.get("versions") or [],
                "sizes": options.get("sizes") or [],
            }
        )
