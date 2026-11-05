"""Core app lifecycle tools: list, inspect, create, update, delete, restart,
and validate a spec before applying it.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from digitalocean_mcp.tools._shared import (
    bounded_dumps,
    clamp_limit,
    get_client,
    tool_guard,
)

def _trim_app(app: dict[str, Any]) -> dict[str, Any]:
    active_deployment = app.get("active_deployment") or {}
    return {
        "id": app.get("id"),
        "spec": app.get("spec"),
        "active_deployment": {
            "id": active_deployment.get("id"),
            "phase": active_deployment.get("phase"),
        }
        if active_deployment
        else None,
        "default_ingress": app.get("default_ingress"),
        "updated_at": app.get("updated_at"),
    }


def register(mcp: FastMCP) -> None:
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True), structured_output=False)
    @tool_guard
    async def digitalocean_apps_list_apps(limit: int | None = None) -> str:
        """List DigitalOcean App Platform apps in the account.

        Args: limit - max apps to return (default 50, hard cap 200).
        """
        per_page = clamp_limit(limit)
        async with await get_client() as client:
            body = await client.request("GET", "/v2/apps", params={"per_page": per_page})
        apps_list = body.get("apps", [])
        total = body.get("meta", {}).get("total", len(apps_list))
        return bounded_dumps(
            {
                "apps": [_trim_app(a) for a in apps_list],
                "has_more": total > len(apps_list),
            }
        )

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True), structured_output=False)
    @tool_guard
    async def digitalocean_apps_get_app(app_id: str) -> str:
        """Get one app's current spec and active deployment.

        Args: app_id - the app's DigitalOcean id.
        """
        async with await get_client() as client:
            body = await client.request("GET", f"/v2/apps/{app_id}")
        return bounded_dumps(_trim_app(body.get("app", {})))

    @mcp.tool(annotations=ToolAnnotations(), structured_output=False)
    @tool_guard
    async def digitalocean_apps_create_app(spec: dict[str, Any]) -> str:
        """Create a new app from an app spec.

        Args: spec - the DigitalOcean app spec (services, static sites, jobs, etc).
        """
        async with await get_client() as client:
            body = await client.request("POST", "/v2/apps", json_body={"spec": spec})
        return bounded_dumps(_trim_app(body.get("app", {})))

    @mcp.tool(annotations=ToolAnnotations(idempotentHint=True), structured_output=False)
    @tool_guard
    async def digitalocean_apps_update_app(app_id: str, spec: dict[str, Any]) -> str:
        """Replace an app's spec. Uses PUT-replace semantics, not a partial merge.

        DigitalOcean replaces the entire spec: any field left out of `spec` is
        removed, not kept from the previous version.
        Args: app_id - app to update. spec - full replacement app spec.
        """
        async with await get_client() as client:
            body = await client.request("PUT", f"/v2/apps/{app_id}", json_body={"spec": spec})
        return bounded_dumps(_trim_app(body.get("app", {})))

    @mcp.tool(annotations=ToolAnnotations(destructiveHint=True), structured_output=False)
    @tool_guard
    async def digitalocean_apps_delete_app(app_id: str) -> str:
        """Delete an app. This is irreversible and removes all its deployments.

        Args: app_id - the single app to delete (no name lookup, no bulk delete).
        """
        async with await get_client() as client:
            await client.request("DELETE", f"/v2/apps/{app_id}")
        return bounded_dumps({"deleted": True, "app_id": app_id})

    @mcp.tool(annotations=ToolAnnotations(destructiveHint=True), structured_output=False)
    @tool_guard
    async def digitalocean_apps_restart_app(
        app_id: str, component_names: list[str] | None = None
    ) -> str:
        """Restart an app's components, or the whole app if none are named.

        Args: app_id - the app to restart. component_names - optional list of
        component names to restart; omit to restart every component.
        """
        body: dict[str, Any] = {}
        if component_names:
            body["components"] = [{"name": name} for name in component_names]
        async with await get_client() as client:
            result = await client.request("POST", f"/v2/apps/{app_id}/restart", json_body=body)
        return bounded_dumps(result)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True), structured_output=False)
    @tool_guard
    async def digitalocean_apps_validate_spec(spec: dict[str, Any]) -> str:
        """Validate an app spec without creating or changing any app.

        Args: spec - the app spec to validate against DigitalOcean's rules.
        """
        async with await get_client() as client:
            result = await client.request("POST", "/v2/apps/propose", json_body={"spec": spec})
        return bounded_dumps(result)
