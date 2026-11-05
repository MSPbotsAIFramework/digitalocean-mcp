"""Firewall lifecycle tools: list, inspect, create, update (whole-object
replace), and delete a DigitalOcean Cloud Firewall.
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


def _trim_firewall_summary(firewall: dict[str, Any]) -> dict[str, Any]:
    """Lean per-firewall shape for list_firewalls -- full rule/droplet/tag
    detail is only returned when a specific firewall_id is asked for, same
    list/get split as `digitalocean_kubernetes_list_clusters`.
    """
    return {
        "id": firewall.get("id"),
        "name": firewall.get("name"),
        "status": firewall.get("status"),
        "droplet_ids": firewall.get("droplet_ids"),
    }


def register(mcp: FastMCP) -> None:
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True), structured_output=False)
    @tool_guard
    async def digitalocean_networking_list_firewalls(firewall_id: str | None = None, limit: int | None = None) -> str:
        """List firewalls in the account, or get one firewall's full detail.

        Args: firewall_id - omit to list; pass to get that firewall's full
        rule/droplet/tag detail. A nonexistent id returns a structured
        not_found error, not an HTTP 500. limit - list mode only, max
        firewalls to return (default 50, hard cap 200).
        """
        async with await get_networking_client() as client:
            if firewall_id:
                body = await client.request("GET", f"/v2/firewalls/{firewall_id}")
                return bounded_dumps(body.get("firewall", {}))

            per_page = clamp_limit(limit)
            body = await client.request("GET", "/v2/firewalls", params={"per_page": per_page})
        firewalls = body.get("firewalls") or []
        total = body.get("meta", {}).get("total", len(firewalls))
        return bounded_dumps(
            {
                "firewalls": [_trim_firewall_summary(f) for f in firewalls],
                "has_more": total > len(firewalls),
            }
        )

    @mcp.tool(annotations=ToolAnnotations(), structured_output=False)
    @tool_guard
    async def digitalocean_networking_create_firewall(
        name: str,
        inbound_rules: list[dict[str, Any]],
        outbound_rules: list[dict[str, Any]],
        droplet_ids: list[int] | None = None,
        tags: list[str] | None = None,
    ) -> str:
        """Create a new firewall.

        Args: name - the firewall's name. inbound_rules, outbound_rules -
        DigitalOcean rule objects. droplet_ids - optional Droplets to apply
        the firewall to. tags - optional tags to apply the firewall to.
        """
        payload: dict[str, Any] = {
            "name": name,
            "inbound_rules": inbound_rules,
            "outbound_rules": outbound_rules,
        }
        if droplet_ids is not None:
            payload["droplet_ids"] = droplet_ids
        if tags is not None:
            payload["tags"] = tags
        async with await get_networking_client() as client:
            body = await client.request("POST", "/v2/firewalls", json_body=payload)
        return bounded_dumps(body.get("firewall", {}))

    @mcp.tool(annotations=ToolAnnotations(idempotentHint=True), structured_output=False)
    @tool_guard
    async def digitalocean_networking_update_firewall(
        firewall_id: str,
        name: str,
        inbound_rules: list[dict[str, Any]],
        outbound_rules: list[dict[str, Any]],
        droplet_ids: list[int] | None = None,
        tags: list[str] | None = None,
    ) -> str:
        """Replace a firewall's rules and membership. Whole-object replace,
        not a partial merge: any rule, Droplet, or tag not included here is
        removed, not kept from the previous version.

        Args: firewall_id - the firewall to update. name, inbound_rules,
        outbound_rules - the full desired state (DigitalOcean requires all
        three on every PUT). droplet_ids, tags - full desired membership;
        omit entirely to clear that membership.
        """
        payload: dict[str, Any] = {
            "name": name,
            "inbound_rules": inbound_rules,
            "outbound_rules": outbound_rules,
            "droplet_ids": droplet_ids or [],
            "tags": tags or [],
        }
        async with await get_networking_client() as client:
            body = await client.request("PUT", f"/v2/firewalls/{firewall_id}", json_body=payload)
        return bounded_dumps(body.get("firewall", {}))

    @mcp.tool(annotations=ToolAnnotations(destructiveHint=True), structured_output=False)
    @tool_guard
    async def digitalocean_networking_delete_firewall(firewall_id: str) -> str:
        """Delete a firewall. This is irreversible.

        Args: firewall_id - the single firewall to delete (no name lookup, no bulk delete).
        """
        async with await get_networking_client() as client:
            await client.request("DELETE", f"/v2/firewalls/{firewall_id}")
        return bounded_dumps({"deleted": True, "firewall_id": firewall_id})
