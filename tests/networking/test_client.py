"""Retry/backoff behavior of `DigitalOceanNetworkingClient` on 429/5xx (AC16),
and its 409-conflict mapping (AC11)."""

from __future__ import annotations

import httpx
import pytest

from digitalocean_mcp.errors import ToolError
from digitalocean_mcp.networking_client import DigitalOceanNetworkingClient
from digitalocean_mcp.settings import Settings


@pytest.mark.asyncio
async def test_429_retries_with_backoff_then_rate_limited(monkeypatch):
    """TC18 (AC16): persistent 429 retries up to the bounded budget, honoring
    Retry-After, then surfaces a structured rate_limited error."""

    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr("digitalocean_mcp.networking_client.asyncio.sleep", fake_sleep)

    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(
            429,
            headers={"Retry-After": "2"},
            json={"id": "too_many_requests", "message": "API rate limit exceeded."},
        )

    settings = Settings(max_retries=3, max_retry_wait_seconds=30.0)
    client = DigitalOceanNetworkingClient("do_fake_token", settings, transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(ToolError) as exc_info:
            await client.request("GET", "/v2/vpcs")
    finally:
        await client.aclose()

    assert exc_info.value.code == "rate_limited"
    assert exc_info.value.retryable is True
    assert attempts == settings.max_retries + 1
    assert sleeps == [2.0] * settings.max_retries


@pytest.mark.asyncio
async def test_5xx_retries_then_upstream_error(monkeypatch):
    """TC18 (AC16): a persistent 503 retries, and once the budget is
    exhausted, surfaces a structured upstream_error (not a bare exception)."""

    async def fake_sleep(seconds: float) -> None:
        return None

    monkeypatch.setattr("digitalocean_mcp.networking_client.asyncio.sleep", fake_sleep)

    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(503, json={"id": "server_error", "message": "temporarily unavailable"})

    settings = Settings(max_retries=2, max_retry_wait_seconds=30.0)
    client = DigitalOceanNetworkingClient("do_fake_token", settings, transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(ToolError) as exc_info:
            await client.request("GET", "/v2/vpcs")
    finally:
        await client.aclose()

    assert exc_info.value.code == "upstream_error"
    assert exc_info.value.retryable is True
    assert attempts == settings.max_retries + 1


@pytest.mark.asyncio
async def test_5xx_retries_then_succeeds_within_budget(monkeypatch):
    """A transient 503 that clears within the retry budget must not raise."""

    async def fake_sleep(seconds: float) -> None:
        return None

    monkeypatch.setattr("digitalocean_mcp.networking_client.asyncio.sleep", fake_sleep)

    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 2:
            return httpx.Response(503, json={"id": "server_error", "message": "temporarily unavailable"})
        return httpx.Response(200, json={"vpcs": []})

    settings = Settings(max_retries=3, max_retry_wait_seconds=30.0)
    client = DigitalOceanNetworkingClient("do_fake_token", settings, transport=httpx.MockTransport(handler))
    try:
        result = await client.request("GET", "/v2/vpcs")
    finally:
        await client.aclose()

    assert result == {"vpcs": []}
    assert attempts == 2


@pytest.mark.asyncio
async def test_409_conflict_maps_to_non_retryable_upstream_error():
    """AC11: a duplicate domain name (409) is a real state collision, not a
    blip -- surfaced as upstream_error with retryable=False, never retried."""

    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(409, json={"id": "conflict", "message": "domain already exists"})

    client = DigitalOceanNetworkingClient("do_fake_token", Settings(), transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(ToolError) as exc_info:
            await client.request("POST", "/v2/domains", json_body={"name": "example.com"})
    finally:
        await client.aclose()

    assert exc_info.value.code == "upstream_error"
    assert exc_info.value.retryable is False
    assert attempts == 1
