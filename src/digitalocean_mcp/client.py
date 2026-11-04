"""Thin async client for DigitalOcean's App Platform API (`/v2/apps*`).

One instance is built per tool call from the request's own token (see
`middleware.get_api_token`); nothing here is shared across tenants except the
underlying `httpx.AsyncClient` connection pool, which carries no credentials
of its own — the `Authorization` header is attached per request.
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


class DigitalOceanClient:
    """Wraps one tenant's DigitalOcean API calls for the lifetime of one tool call."""

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

    async def __aenter__(self) -> "DigitalOceanClient":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Issue one request with retry-with-backoff on 429/5xx.

        Raises `ToolError` with a code from the SOP's fixed vocabulary.
        Never raises a bare httpx/network exception to the caller.
        """
        attempt = 0
        while True:
            attempt += 1
            try:
                response = await self._client.request(method, path, params=params, json=json_body)
            except httpx.TimeoutException as exc:
                if attempt > self._settings.max_retries:
                    raise ToolError(
                        "upstream_error", f"DigitalOcean API request timed out: {exc}"
                    ) from exc
                await asyncio.sleep(self._backoff_seconds(attempt))
                continue
            except httpx.HTTPError as exc:
                if attempt > self._settings.max_retries:
                    raise ToolError(
                        "upstream_error", f"DigitalOcean API request failed: {exc}"
                    ) from exc
                await asyncio.sleep(self._backoff_seconds(attempt))
                continue

            if response.status_code in _RETRYABLE_STATUS and attempt <= self._settings.max_retries:
                await asyncio.sleep(self._wait_seconds(response, attempt))
                continue

            return self._to_result(response)

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

    def _to_result(self, response: httpx.Response) -> dict[str, Any]:
        if response.status_code == 429:
            raise ToolError("rate_limited", "DigitalOcean API rate limit exceeded; retry budget used up")

        if response.status_code in (401, 403):
            raise ToolError("unauthorized", self._upstream_message(response))

        if response.status_code == 404:
            raise ToolError("not_found", self._upstream_message(response, default="Resource not found"))

        if response.status_code in (400, 422):
            raise ToolError("invalid_argument", self._upstream_message(response))

        if response.status_code == 409:
            # A conflict (e.g. a deployment already in progress) is a real,
            # non-transient state collision — surface it as upstream_error and
            # never retry it as if it were a blip (AC9).
            raise ToolError(
                "upstream_error",
                self._upstream_message(response, default="DigitalOcean API reported a conflict"),
                retryable=False,
            )

        if response.status_code >= 500:
            raise ToolError("upstream_error", self._upstream_message(response, default="DigitalOcean API server error"))

        if response.status_code == 204 or not response.content:
            return {}

        try:
            return response.json()
        except ValueError as exc:
            raise ToolError("upstream_error", f"DigitalOcean API returned a non-JSON response: {exc}") from exc

    @staticmethod
    def _upstream_message(response: httpx.Response, *, default: str = "DigitalOcean API error") -> str:
        try:
            body = response.json()
        except ValueError:
            return default
        if isinstance(body, dict):
            message = body.get("message")
            if isinstance(message, str) and message:
                return message
        return default
