"""Cluster access tools: kubeconfig (raw YAML) and the structured credentials
bundle. Both return maximally privileged cluster-admin artifacts -- never
logged, never persisted, see `kubernetes_client.request_raw_text` and
PRD-21344.md "Non-functional" / "Risks & dependencies".
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from digitalocean_mcp.tools._shared import bounded_dumps, get_kubernetes_client, tool_guard


def register(mcp: FastMCP) -> None:
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True), structured_output=False)
    @tool_guard
    async def digitalocean_kubernetes_get_kubeconfig(cluster_id: str) -> str:
        """Get a cluster's raw kubeconfig YAML. Never logged, never truncated.

        Distinct from get_credentials, which returns a structured JSON
        bundle instead of a YAML document.
        Args: cluster_id - the cluster whose kubeconfig to fetch.
        """
        async with await get_kubernetes_client() as client:
            kubeconfig = await client.request_raw_text(
                "GET", f"/v2/kubernetes/clusters/{cluster_id}/kubeconfig"
            )
        return kubeconfig

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True), structured_output=False)
    @tool_guard
    async def digitalocean_kubernetes_get_credentials(
        cluster_id: str, expiry_seconds: int | None = None
    ) -> str:
        """Get a cluster's structured credential bundle (server/token/expires_at).

        Distinct from get_kubeconfig, which returns raw YAML instead of this
        JSON shape. Never logged.
        Args: cluster_id - the cluster whose credentials to fetch.
        expiry_seconds - optional token lifetime in seconds; omit to use
        DigitalOcean's own default.
        """
        params = {"expiry_seconds": expiry_seconds} if expiry_seconds is not None else None
        async with await get_kubernetes_client() as client:
            body = await client.request(
                "GET", f"/v2/kubernetes/clusters/{cluster_id}/credentials", params=params
            )
        return bounded_dumps(body)
