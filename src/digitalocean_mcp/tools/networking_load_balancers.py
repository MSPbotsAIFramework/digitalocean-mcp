"""Load balancer lifecycle tools: list, inspect, create, update (whole-object
replace), and delete a DigitalOcean Load Balancer.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from digitalocean_mcp.tools._shared import (
    bounded_dumps,
    clamp_limit,
    get_networking_client,
    tool_guard,
)


def _trim_lb_summary(lb: dict[str, Any]) -> dict[str, Any]:
    """Lean per-load-balancer shape for list_load_balancers -- full detail
    (droplet_ids, forwarding_rules) is only returned when a specific lb_id
    is asked for, same list/get split as `digitalocean_networking_list_firewalls`.
    """
    return {
        "id": lb.get("id"),
        "name": lb.get("name"),
        "region": (lb.get("region") or {}).get("slug") if isinstance(lb.get("region"), dict) else lb.get("region"),
        "status": lb.get("status"),
        "ip": lb.get("ip"),
    }


def register(mcp: FastMCP) -> None:
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True), structured_output=False)
    @tool_guard
    async def digitalocean_networking_list_load_balancers(lb_id: str | None = None, limit: int | None = None) -> str:
        """List load balancers in the account, or get one's full detail.

        Args: lb_id - omit to list; pass to get that load balancer's full
        detail, including droplet_ids and forwarding_rules. limit - list
        mode only, max load balancers to return (default 50, hard cap 200).
        """
        async with await get_networking_client() as client:
            if lb_id:
                body = await client.request("GET", f"/v2/load_balancers/{lb_id}")
                return bounded_dumps(body.get("load_balancer", {}))

            per_page = clamp_limit(limit)
            body = await client.request("GET", "/v2/load_balancers", params={"per_page": per_page})
        lbs = body.get("load_balancers") or []
        total = body.get("meta", {}).get("total", len(lbs))
        return bounded_dumps(
            {
                "load_balancers": [_trim_lb_summary(lb) for lb in lbs],
                "has_more": total > len(lbs),
            }
        )

    @mcp.tool(annotations=ToolAnnotations(), structured_output=False)
    @tool_guard
    async def digitalocean_networking_create_load_balancer(
        name: str,
        region: str,
        forwarding_rules: list[dict[str, Any]],
        droplet_ids: list[int] | None = None,
        tag: str | None = None,
    ) -> str:
        """Create a new load balancer.

        Args: name - the load balancer's name. region - the DigitalOcean
        region slug. forwarding_rules - DigitalOcean forwarding-rule
        objects. droplet_ids - optional Droplets to balance across. tag -
        optional, balance across all Droplets carrying this tag instead of
        an explicit droplet_ids list.
        """
        payload: dict[str, Any] = {
            "name": name,
            "region": region,
            "forwarding_rules": forwarding_rules,
        }
        if droplet_ids is not None:
            payload["droplet_ids"] = droplet_ids
        if tag is not None:
            payload["tag"] = tag
        async with await get_networking_client() as client:
            body = await client.request("POST", "/v2/load_balancers", json_body=payload)
        return bounded_dumps(body.get("load_balancer", {}))

    @mcp.tool(annotations=ToolAnnotations(idempotentHint=True), structured_output=False)
    @tool_guard
    async def digitalocean_networking_update_load_balancer(
        lb_id: str,
        name: str,
        region: str,
        forwarding_rules: list[dict[str, Any]],
        droplet_ids: list[int] | None = None,
        tag: str | None = None,
    ) -> str:
        """Replace a load balancer's droplets and forwarding rules.
        Whole-object replace, not a partial merge: any Droplet or forwarding
        rule not included here is removed, not kept from the previous
        version.

        Args: lb_id - the load balancer to update. name, region,
        forwarding_rules - the full desired state (DigitalOcean requires all
        three on every PUT). droplet_ids, tag - full desired membership;
        omit droplet_ids entirely to clear it.
        """
        payload: dict[str, Any] = {
            "name": name,
            "region": region,
            "forwarding_rules": forwarding_rules,
            "droplet_ids": droplet_ids or [],
        }
        if tag is not None:
            payload["tag"] = tag
        async with await get_networking_client() as client:
            body = await client.request("PUT", f"/v2/load_balancers/{lb_id}", json_body=payload)
        return bounded_dumps(body.get("load_balancer", {}))

    @mcp.tool(annotations=ToolAnnotations(destructiveHint=True), structured_output=False)
    @tool_guard
    async def digitalocean_networking_delete_load_balancer(lb_id: str) -> str:
        """Delete a load balancer. Irreversible, and does not delete the
        Droplets behind it.

        Args: lb_id - the single load balancer to delete (no bulk delete).
        """
        async with await get_networking_client() as client:
            await client.request("DELETE", f"/v2/load_balancers/{lb_id}")
        return bounded_dumps({"deleted": True, "lb_id": lb_id})
