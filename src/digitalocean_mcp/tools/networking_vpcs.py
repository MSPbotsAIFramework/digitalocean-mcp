"""VPC lifecycle and VPC-peering tools: list, inspect, create, update,
delete a VPC, and manage its peerings.
"""

from __future__ import annotations

from typing import Any, Literal

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from digitalocean_mcp.errors import ToolError
from digitalocean_mcp.tools._shared import (
    bounded_dumps,
    clamp_limit,
    get_networking_client,
    tool_guard,
)


def _trim_vpc_summary(vpc: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": vpc.get("id"),
        "name": vpc.get("name"),
        "region": vpc.get("region"),
        "ip_range": vpc.get("ip_range"),
        "default": vpc.get("default"),
    }


def _trim_peering_summary(peering: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": peering.get("id"),
        "name": peering.get("name"),
        "status": peering.get("status"),
        "vpc_ids": peering.get("vpc_ids"),
    }


def register(mcp: FastMCP) -> None:
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True), structured_output=False)
    @tool_guard
    async def digitalocean_networking_list_vpcs(vpc_id: str | None = None, limit: int | None = None) -> str:
        """List VPCs in the account, or get one VPC's detail, member count, and peerings.

        Args: vpc_id - omit to list; pass to get one VPC's full detail merged
        with its member-resource count and current peerings. limit - list
        mode only, max VPCs to return (default 50, hard cap 200).
        """
        async with await get_networking_client() as client:
            if vpc_id:
                vpc_body = await client.request("GET", f"/v2/vpcs/{vpc_id}")
                members_body = await client.request("GET", f"/v2/vpcs/{vpc_id}/members")
                peerings_body = await client.request("GET", f"/v2/vpcs/{vpc_id}/peerings")
                vpc = vpc_body.get("vpc", {})
                members = members_body.get("members") or []
                member_count = members_body.get("meta", {}).get("total", len(members))
                peerings = peerings_body.get("vpc_peerings") or []
                return bounded_dumps(
                    {
                        **_trim_vpc_summary(vpc),
                        "member_count": member_count,
                        "peerings": [_trim_peering_summary(p) for p in peerings],
                    }
                )

            per_page = clamp_limit(limit)
            body = await client.request("GET", "/v2/vpcs", params={"per_page": per_page})
        vpcs = body.get("vpcs") or []
        total = body.get("meta", {}).get("total", len(vpcs))
        return bounded_dumps(
            {
                "vpcs": [_trim_vpc_summary(v) for v in vpcs],
                "has_more": total > len(vpcs),
            }
        )

    @mcp.tool(annotations=ToolAnnotations(), structured_output=False)
    @tool_guard
    async def digitalocean_networking_create_vpc(
        name: str,
        region: str,
        description: str | None = None,
        ip_range: str | None = None,
    ) -> str:
        """Create a new VPC.

        Args: name - the VPC's name. region - the DigitalOcean region slug.
        description - optional free-text description. ip_range - optional
        CIDR range; DigitalOcean assigns one automatically if omitted.
        """
        payload: dict[str, Any] = {"name": name, "region": region}
        if description is not None:
            payload["description"] = description
        if ip_range is not None:
            payload["ip_range"] = ip_range
        async with await get_networking_client() as client:
            body = await client.request("POST", "/v2/vpcs", json_body=payload)
        return bounded_dumps(_trim_vpc_summary(body.get("vpc", {})))

    @mcp.tool(annotations=ToolAnnotations(idempotentHint=True), structured_output=False)
    @tool_guard
    async def digitalocean_networking_update_vpc(
        vpc_id: str,
        name: str | None = None,
        description: str | None = None,
        default: bool | None = None,
    ) -> str:
        """Partially update a VPC. Only the fields supplied here change.

        Uses DigitalOcean's PATCH partial-update semantics, in contrast to
        the whole-object-replace tools below (update_firewall,
        update_load_balancer) -- a field left out is left unchanged, not
        cleared.
        Args: vpc_id - the VPC to update. name, description, default -
        optional; only the ones supplied are sent.
        """
        payload: dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if description is not None:
            payload["description"] = description
        if default is not None:
            payload["default"] = default
        if not payload:
            raise ToolError("invalid_argument", "update_vpc requires at least one of name/description/default")
        async with await get_networking_client() as client:
            body = await client.request("PATCH", f"/v2/vpcs/{vpc_id}", json_body=payload)
        return bounded_dumps(_trim_vpc_summary(body.get("vpc", {})))

    @mcp.tool(annotations=ToolAnnotations(destructiveHint=True), structured_output=False)
    @tool_guard
    async def digitalocean_networking_delete_vpc(vpc_id: str) -> str:
        """Delete a VPC. Irreversible, and fails if the VPC still has member
        resources (Droplets, Load Balancers, etc.) attached -- DigitalOcean's
        own precondition-failure response is surfaced as a structured error.

        Args: vpc_id - the single VPC to delete (no name lookup, no bulk delete).
        """
        async with await get_networking_client() as client:
            await client.request("DELETE", f"/v2/vpcs/{vpc_id}")
        return bounded_dumps({"deleted": True, "vpc_id": vpc_id})

    @mcp.tool(annotations=ToolAnnotations(destructiveHint=True), structured_output=False)
    @tool_guard
    async def digitalocean_networking_manage_vpc_peering(
        action: Literal["list", "get", "create", "update", "delete"],
        vpc_peering_id: str | None = None,
        vpc_ids: list[str] | None = None,
        name: str | None = None,
    ) -> str:
        """List, inspect, create, rename, or delete a VPC peering.

        `create` requires exactly two `vpc_ids` (a peering always connects
        exactly two VPCs). `delete` requires an explicit `vpc_peering_id` --
        no name lookup.
        Args: action - list|get|create|update|delete. vpc_peering_id -
        required for get/update/delete. vpc_ids - required for create,
        exactly two ids. name - the peering's name, for create/update.
        """
        if action == "create" and (vpc_ids is None or len(vpc_ids) != 2):
            raise ToolError(
                "invalid_argument",
                f"action='create' requires exactly two vpc_ids, got {len(vpc_ids) if vpc_ids else 0}",
            )
        if action in ("get", "update", "delete") and not vpc_peering_id:
            raise ToolError("invalid_argument", f"action={action!r} requires vpc_peering_id")

        async with await get_networking_client() as client:
            if action == "list":
                body = await client.request("GET", "/v2/vpc_peerings")
                peerings = body.get("vpc_peerings") or []
                return bounded_dumps({"vpc_peerings": [_trim_peering_summary(p) for p in peerings]})
            if action == "get":
                body = await client.request("GET", f"/v2/vpc_peerings/{vpc_peering_id}")
                return bounded_dumps(_trim_peering_summary(body.get("vpc_peering", {})))
            if action == "create":
                payload: dict[str, Any] = {"vpc_ids": vpc_ids}
                if name is not None:
                    payload["name"] = name
                body = await client.request("POST", "/v2/vpc_peerings", json_body=payload)
                return bounded_dumps(_trim_peering_summary(body.get("vpc_peering", {})))
            if action == "update":
                if name is None:
                    raise ToolError("invalid_argument", "action='update' requires name")
                body = await client.request(
                    "PATCH", f"/v2/vpc_peerings/{vpc_peering_id}", json_body={"name": name}
                )
                return bounded_dumps(_trim_peering_summary(body.get("vpc_peering", {})))
            # delete
            await client.request("DELETE", f"/v2/vpc_peerings/{vpc_peering_id}")
            return bounded_dumps({"deleted": True, "vpc_peering_id": vpc_peering_id})
