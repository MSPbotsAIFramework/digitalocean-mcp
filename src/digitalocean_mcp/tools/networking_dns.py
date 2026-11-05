"""Domain and DNS record tools: list/inspect/create/delete a domain, and
manage its records (create/update/delete a single record).
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


def _trim_domain_summary(domain: dict[str, Any]) -> dict[str, Any]:
    return {"name": domain.get("name"), "ttl": domain.get("ttl")}


def register(mcp: FastMCP) -> None:
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True), structured_output=False)
    @tool_guard
    async def digitalocean_networking_list_domains(domain_name: str | None = None, limit: int | None = None) -> str:
        """List domains in the account, or get one domain's detail (zone file, TTL).

        Args: domain_name - omit to list; pass to get that domain's detail.
        limit - list mode only, max domains to return (default 50, hard cap 200).
        """
        async with await get_networking_client() as client:
            if domain_name:
                body = await client.request("GET", f"/v2/domains/{domain_name}")
                return bounded_dumps(body.get("domain", {}))

            per_page = clamp_limit(limit)
            body = await client.request("GET", "/v2/domains", params={"per_page": per_page})
        domains = body.get("domains") or []
        total = body.get("meta", {}).get("total", len(domains))
        return bounded_dumps(
            {
                "domains": [_trim_domain_summary(d) for d in domains],
                "has_more": total > len(domains),
            }
        )

    @mcp.tool(annotations=ToolAnnotations(), structured_output=False)
    @tool_guard
    async def digitalocean_networking_create_domain(name: str, ip_address: str | None = None) -> str:
        """Register a new domain on the account.

        A domain name that already exists on the account surfaces
        DigitalOcean's own conflict error as a structured error, not a
        generic failure.
        Args: name - the fully-qualified domain name. ip_address - optional,
        creates an initial A record pointing the apex at this IP.
        """
        payload: dict[str, Any] = {"name": name}
        if ip_address is not None:
            payload["ip_address"] = ip_address
        async with await get_networking_client() as client:
            body = await client.request("POST", "/v2/domains", json_body=payload)
        return bounded_dumps(body.get("domain", {}))

    @mcp.tool(annotations=ToolAnnotations(destructiveHint=True), structured_output=False)
    @tool_guard
    async def digitalocean_networking_delete_domain(domain_name: str) -> str:
        """Delete a domain and all of its records. Irreversible.

        Args: domain_name - the single domain to delete (no bulk delete).
        """
        async with await get_networking_client() as client:
            await client.request("DELETE", f"/v2/domains/{domain_name}")
        return bounded_dumps({"deleted": True, "domain_name": domain_name})

    @mcp.tool(annotations=ToolAnnotations(destructiveHint=True), structured_output=False)
    @tool_guard
    async def digitalocean_networking_manage_domain_record(
        domain_name: str,
        action: Literal["list", "get", "create", "update", "delete"],
        domain_record_id: int | None = None,
        type: str | None = None,
        name: str | None = None,
        data: str | None = None,
        priority: int | None = None,
        port: int | None = None,
        ttl: int | None = None,
        weight: int | None = None,
        flags: int | None = None,
        tag: str | None = None,
    ) -> str:
        """List, inspect, create, update, or delete one DNS record on a domain.

        `update` is a PATCH partial update (only supplied fields change).
        `delete` requires an explicit `domain_record_id` -- no "delete all
        records matching type X".
        Args: domain_name - the domain. action - list|get|create|update|delete.
        domain_record_id - required for get/update/delete. type, name, data,
        priority, port, ttl, weight, flags, tag - DigitalOcean record fields.
        """
        if action in ("get", "update", "delete") and domain_record_id is None:
            raise ToolError("invalid_argument", f"action={action!r} requires domain_record_id")
        if action == "create" and (type is None or name is None):
            raise ToolError("invalid_argument", "action='create' requires at least type and name")

        fields = {
            "type": type,
            "name": name,
            "data": data,
            "priority": priority,
            "port": port,
            "ttl": ttl,
            "weight": weight,
            "flags": flags,
            "tag": tag,
        }
        payload = {k: v for k, v in fields.items() if v is not None}

        async with await get_networking_client() as client:
            if action == "list":
                body = await client.request("GET", f"/v2/domains/{domain_name}/records")
                return bounded_dumps({"domain_records": body.get("domain_records") or []})
            if action == "get":
                body = await client.request(
                    "GET", f"/v2/domains/{domain_name}/records/{domain_record_id}"
                )
                return bounded_dumps(body.get("domain_record", {}))
            if action == "create":
                body = await client.request(
                    "POST", f"/v2/domains/{domain_name}/records", json_body=payload
                )
                return bounded_dumps(body.get("domain_record", {}))
            if action == "update":
                if not payload:
                    raise ToolError("invalid_argument", "action='update' requires at least one field to change")
                body = await client.request(
                    "PATCH", f"/v2/domains/{domain_name}/records/{domain_record_id}", json_body=payload
                )
                return bounded_dumps(body.get("domain_record", {}))
            # delete
            await client.request("DELETE", f"/v2/domains/{domain_name}/records/{domain_record_id}")
            return bounded_dumps({"deleted": True, "domain_record_id": domain_record_id})
