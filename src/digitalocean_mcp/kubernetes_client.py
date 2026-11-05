"""Thin async client for DigitalOcean's Kubernetes Service API (`/v2/kubernetes*`).

One instance is built per tool call from the request's own token (see
`middleware.get_api_token`); nothing here is shared across tenants except the
underlying `httpx.AsyncClient` connection pool, which carries no credentials
of its own -- the `Authorization` header is attached per request.

Named `kubernetes_client.py` (not `client.py`) for the same reason
`inference_client.py` is -- this repository is shared across DigitalOcean
resource-group tickets (PRD-21338 Apps, PRD-21343 Inference, PRD-21344
Kubernetes, PRD-21345 Networking) and each resource group talks to a
different slice of the same `api.digitalocean.com` base URL; see
docs/tickets/PRD-21344.md section "Decisions made by DEV01" for the module
layout note.

`get_kubeconfig` is the one Kubernetes operation that returns a raw YAML
document rather than JSON (PRD-21344.md AC10) -- `request_raw_text` shares
the same retry/error-mapping behaviour as `request()` but returns the
response body unparsed instead of calling `.json()` on it.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from digitalocean_mcp.errors import ToolError
from digitalocean_mcp.settings import Settings

BASE_URL = "https://api.digitalocean.com"

# Status codes DigitalOcean returns that map to a retry, per SOP section 5.
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class DigitalOceanKubernetesClient:
    """Wraps one tenant's DigitalOcean Kubernetes Service calls for the
    lifetime of one tool call."""

    def __init__(
        self,
        token: str,
        settings: Settings,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._settings = settings
        self._client = httpx.AsyncClient(
            base_url=BASE_URL,
            headers={"Authorization": f"Bearer {token}"},
            timeout=httpx.Timeout(
                connect=settings.connect_timeout_seconds,
                read=settings.read_timeout_seconds,
                write=settings.read_timeout_seconds,
                pool=settings.connect_timeout_seconds,
            ),
            # Only ever set in tests: injects a httpx.MockTransport so unit
            # tests exercise the real request/retry/error-mapping code path
            # without a network call or a real DigitalOcean account.
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "DigitalOceanKubernetesClient":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def _send_with_retry(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> httpx.Response:
        """Issue one request with retry-with-backoff on 429/5xx (AC19).

        Raises `ToolError` with a code from the SOP's fixed vocabulary when
        the retry budget is exhausted. Never raises a bare httpx/network
        exception to the caller.
        """
        attempt = 0
        while True:
            attempt += 1
            try:
                response = await self._client.request(method, path, params=params, json=json_body)
            except httpx.TimeoutException as exc:
                if attempt > self._settings.max_retries:
                    raise ToolError(
                        "upstream_error", f"DigitalOcean Kubernetes API request timed out: {exc}"
                    ) from exc
                await asyncio.sleep(self._backoff_seconds(attempt))
                continue
            except httpx.HTTPError as exc:
                if attempt > self._settings.max_retries:
                    raise ToolError(
                        "upstream_error", f"DigitalOcean Kubernetes API request failed: {exc}"
                    ) from exc
                await asyncio.sleep(self._backoff_seconds(attempt))
                continue

            if response.status_code in _RETRYABLE_STATUS and attempt <= self._settings.max_retries:
                await asyncio.sleep(self._wait_seconds(response, attempt))
                continue

            return response

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Issue one request and parse the body as JSON.

        Raises `ToolError` with a code from the SOP's fixed vocabulary.
        """
        response = await self._send_with_retry(method, path, params=params, json_body=json_body)
        return self._to_json_result(response)

    async def request_raw_text(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> str:
        """Issue one request and return the body unparsed (used for kubeconfig YAML, AC10).

        Shares the same status-code -> `ToolError` mapping as `request()`;
        only a 2xx response's body is returned, and it is never truncated
        here (PRD-21344.md "Non-functional": a truncated kubeconfig is
        corrupt, not merely incomplete -- size-bounding, when it applies, is
        the tool's responsibility, not the client's).
        """
        response = await self._send_with_retry(method, path, params=params)
        self._raise_for_error_status(response)
        return response.text

    def _backoff_seconds(self, attempt: int) -> float:
        return min(2.0 ** (attempt - 1), self._settings.max_retry_wait_seconds)

    def _wait_seconds(self, response: httpx.Response, attempt: int) -> float:
        retry_after = response.headers.get("Retry-After")
        if retry_after is not None:
            try:
                return min(float(retry_after), self._settings.max_retry_wait_seconds)
            except ValueError:
                pass
        return self._backoff_seconds(attempt)

    def _raise_for_error_status(self, response: httpx.Response) -> None:
        if response.status_code == 429:
            raise ToolError("rate_limited", "DigitalOcean Kubernetes API rate limit exceeded; retry budget used up")

        if response.status_code in (401, 403):
            raise ToolError("unauthorized", self._upstream_message(response))

        if response.status_code == 404:
            raise ToolError("not_found", self._upstream_message(response, default="Resource not found"))

        if response.status_code in (400, 422):
            raise ToolError("invalid_argument", self._upstream_message(response))

        if response.status_code >= 500:
            raise ToolError(
                "upstream_error", self._upstream_message(response, default="DigitalOcean Kubernetes API server error")
            )

    def _to_json_result(self, response: httpx.Response) -> dict[str, Any]:
        self._raise_for_error_status(response)

        if response.status_code == 204 or not response.content:
            return {}

        try:
            return response.json()
        except ValueError as exc:
            raise ToolError(
                "upstream_error", f"DigitalOcean Kubernetes API returned a non-JSON response: {exc}"
            ) from exc

    @staticmethod
    def _upstream_message(response: httpx.Response, *, default: str = "DigitalOcean Kubernetes API error") -> str:
        """Match DigitalOcean's documented error shape: `{"id": ..., "message": ...}`."""
        try:
            body = response.json()
        except ValueError:
            return default
        if isinstance(body, dict):
            message = body.get("message")
            if isinstance(message, str) and message:
                return message
        return default
