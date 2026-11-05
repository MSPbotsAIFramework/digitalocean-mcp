"""Deployment lifecycle tools: list, inspect, create, cancel, and roll back."""

from __future__ import annotations

from typing import Any, Literal

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from digitalocean_mcp.errors import ToolError
from digitalocean_mcp.tools._shared import bounded_dumps, clamp_limit, get_client, tool_guard


def _trim_deployment(deployment: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": deployment.get("id"),
        "phase": deployment.get("phase"),
        "cause": deployment.get("cause"),
        "created_at": deployment.get("created_at"),
        "updated_at": deployment.get("updated_at"),
    }


def register(mcp: FastMCP) -> None:
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True), structured_output=False)
    @tool_guard
    async def digitalocean_apps_list_deployments(app_id: str, limit: int | None = None) -> str:
        """List an app's deployments, most recent first.

        Args: app_id - the app. limit - max deployments to return (default 50, hard cap 200).
        """
        per_page = clamp_limit(limit)
        async with await get_client() as client:
            body = await client.request(
                "GET", f"/v2/apps/{app_id}/deployments", params={"per_page": per_page}
            )
        deployments = body.get("deployments", [])
        total = body.get("meta", {}).get("total", len(deployments))
        return bounded_dumps(
            {
                "deployments": [_trim_deployment(d) for d in deployments],
                "has_more": total > len(deployments),
            }
        )

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True), structured_output=False)
    @tool_guard
    async def digitalocean_apps_get_deployment(app_id: str, deployment_id: str) -> str:
        """Get one deployment's phase, cause, and timestamps.

        Args: app_id - the app. deployment_id - the deployment to inspect.
        """
        async with await get_client() as client:
            body = await client.request("GET", f"/v2/apps/{app_id}/deployments/{deployment_id}")
        return bounded_dumps(_trim_deployment(body.get("deployment", {})))

    @mcp.tool(annotations=ToolAnnotations(), structured_output=False)
    @tool_guard
    async def digitalocean_apps_create_deployment(app_id: str, force_build: bool = False) -> str:
        """Trigger a new deployment of an app's current spec.

        A deployment already in progress is reported as a conflict, not retried.
        Args: app_id - the app. force_build - rebuild even if nothing changed.
        """
        async with await get_client() as client:
            body = await client.request(
                "POST",
                f"/v2/apps/{app_id}/deployments",
                json_body={"force_build": force_build},
            )
        return bounded_dumps(_trim_deployment(body.get("deployment", {})))

    @mcp.tool(annotations=ToolAnnotations(destructiveHint=True), structured_output=False)
    @tool_guard
    async def digitalocean_apps_cancel_deployment(app_id: str, deployment_id: str) -> str:
        """Cancel a deployment that is in progress.

        Args: app_id - the app. deployment_id - the in-progress deployment to cancel.
        """
        async with await get_client() as client:
            body = await client.request(
                "POST", f"/v2/apps/{app_id}/deployments/{deployment_id}/cancel"
            )
        return bounded_dumps(body)

    @mcp.tool(annotations=ToolAnnotations(destructiveHint=True), structured_output=False)
    @tool_guard
    async def digitalocean_apps_manage_rollback(
        app_id: str,
        action: Literal["start", "validate", "commit", "revert"],
        deployment_id: str | None = None,
    ) -> str:
        """Start, validate, commit, or revert a rollback to a prior deployment.

        `commit`/`revert` require the `deployment_id` returned by a prior
        `start` call — they never guess which deployment to roll back to.
        Args: app_id - the app. action - start|validate|commit|revert.
        deployment_id - target deployment for start/validate, or the rollback
        deployment id from `start` for commit/revert.
        """
        if action in ("commit", "revert") and not deployment_id:
            raise ToolError(
                "invalid_argument",
                f"action={action!r} requires deployment_id from a prior action='start' call; "
                "it does not guess which deployment to roll back to.",
            )

        async with await get_client() as client:
            if action == "start":
                body = await client.request(
                    "POST", f"/v2/apps/{app_id}/rollback", json_body={"deployment_id": deployment_id}
                )
            elif action == "validate":
                body = await client.request(
                    "POST",
                    f"/v2/apps/{app_id}/rollback/validate",
                    json_body={"deployment_id": deployment_id},
                )
            elif action == "commit":
                body = await client.request(
                    "POST", f"/v2/apps/{app_id}/deployments/{deployment_id}/rollback/commit"
                )
            else:  # revert
                body = await client.request(
                    "POST", f"/v2/apps/{app_id}/deployments/{deployment_id}/rollback/revert"
                )
        return bounded_dumps(body)
