"""Account-level reference data needed to build an app spec."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from digitalocean_mcp.tools._shared import bounded_dumps, get_client, tool_guard


def register(mcp: FastMCP) -> None:
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True), structured_output=False)
    @tool_guard
    async def digitalocean_apps_get_deployment_options(instance_size_slug: str | None = None) -> str:
        """List valid regions and instance sizes for building an app spec.

        Account-level and stateless: needs no app id. Pass instance_size_slug
        to get that one size's details instead of the full size list.
        Args: instance_size_slug - optional, look up one instance size by slug.
        """
        async with await get_client() as client:
            regions = await client.request("GET", "/v2/apps/regions")
            if instance_size_slug:
                sizes = await client.request(
                    "GET", f"/v2/apps/tiers/instance_sizes/{instance_size_slug}"
                )
            else:
                sizes = await client.request("GET", "/v2/apps/tiers/instance_sizes")
        return bounded_dumps({"regions": regions.get("regions", []), "instance_sizes": sizes})
