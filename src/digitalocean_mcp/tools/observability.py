"""Read-only observability tools: logs, instances, events, alerts, health."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from digitalocean_mcp.errors import ToolError
from digitalocean_mcp.tools._shared import bounded_dumps, get_client, tool_guard

# DigitalOcean App Platform's log_type enum.
_VALID_LOG_TYPES = {"BUILD", "DEPLOY", "RUN", "RUN_RESTARTED"}


def register(mcp: FastMCP) -> None:
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True), structured_output=False)
    @tool_guard
    async def digitalocean_apps_get_logs(
        app_id: str,
        deployment_id: str | None = None,
        component_name: str | None = None,
        log_type: str | None = None,
    ) -> str:
        """Get log access URLs for an app, a deployment, or one component.

        Defaults to the active deployment's aggregate logs when deployment_id
        and component_name are omitted; the most specific endpoint is used
        the more of those two are given.
        Args: app_id - the app. deployment_id - defaults to active deployment.
        component_name - defaults to the aggregate across components.
        log_type - one of BUILD, DEPLOY, RUN, RUN_RESTARTED.
        """
        if log_type is not None and log_type not in _VALID_LOG_TYPES:
            raise ToolError(
                "invalid_argument",
                f"Unsupported log_type {log_type!r}; expected one of {sorted(_VALID_LOG_TYPES)}",
            )

        if deployment_id and component_name:
            path = f"/v2/apps/{app_id}/deployments/{deployment_id}/components/{component_name}/logs"
        elif deployment_id:
            path = f"/v2/apps/{app_id}/deployments/{deployment_id}/logs"
        elif component_name:
            path = f"/v2/apps/{app_id}/components/{component_name}/logs"
        else:
            path = f"/v2/apps/{app_id}/logs"

        params: dict[str, Any] = {}
        if log_type is not None:
            params["type"] = log_type

        async with await get_client() as client:
            body = await client.request("GET", path, params=params)
        return bounded_dumps(body)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True), structured_output=False)
    @tool_guard
    async def digitalocean_apps_get_instances(app_id: str, deployment_id: str | None = None) -> str:
        """List the running instances backing an app's components.

        Args: app_id - the app. deployment_id - defaults to the active deployment.
        """
        params = {"deployment_id": deployment_id} if deployment_id else {}
        async with await get_client() as client:
            body = await client.request("GET", f"/v2/apps/{app_id}/instances", params=params)
        return bounded_dumps(body)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True), structured_output=False)
    @tool_guard
    async def digitalocean_apps_list_events(app_id: str, event_id: str | None = None) -> str:
        """List an app's build/deploy events, or get one event by id.

        Args: app_id - the app. event_id - fetch this single event instead of listing.
        """
        path = f"/v2/apps/{app_id}/events" if not event_id else f"/v2/apps/{app_id}/events/{event_id}"
        async with await get_client() as client:
            body = await client.request("GET", path)
        return bounded_dumps(body)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True), structured_output=False)
    @tool_guard
    async def digitalocean_apps_list_alerts(app_id: str) -> str:
        """List the alert rules configured on an app.

        Args: app_id - the app whose alerts to list.
        """
        async with await get_client() as client:
            body = await client.request("GET", f"/v2/apps/{app_id}/alerts")
        return bounded_dumps(body)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True), structured_output=False)
    @tool_guard
    async def digitalocean_apps_get_health(app_id: str) -> str:
        """Get an app's aggregate health across its components.

        Args: app_id - the app to check.
        """
        async with await get_client() as client:
            body = await client.request("GET", f"/v2/apps/{app_id}/health")
        return bounded_dumps(body)
