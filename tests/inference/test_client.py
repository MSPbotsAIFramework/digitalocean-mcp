"""Retry/backoff behavior of `DigitalOceanInferenceClient` on 429."""

from __future__ import annotations

import httpx
import pytest

from digitalocean_mcp.errors import ToolError
from digitalocean_mcp.inference_client import DigitalOceanInferenceClient
from digitalocean_mcp.settings import Settings


@pytest.mark.asyncio
async def test_429_retries_with_backoff_then_rate_limited(monkeypatch):
    """TC8 (AC7): persistent 429 retries up to the bounded budget, honoring
    Retry-After, then surfaces a structured rate_limited error (not a bare
    timeout).
    """

    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr("digitalocean_mcp.inference_client.asyncio.sleep", fake_sleep)

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
    client = DigitalOceanInferenceClient(
        "do_fake_token", settings, transport=httpx.MockTransport(handler)
    )
    try:
        with pytest.raises(ToolError) as exc_info:
            await client.request("GET", "/v1/models")
    finally:
        await client.aclose()

    assert exc_info.value.code == "rate_limited"
    assert exc_info.value.retryable is True
    # initial attempt + max_retries retries, all 429
    assert attempts == settings.max_retries + 1
    # one sleep per retry, honoring Retry-After (2s, below the 30s cap)
    assert sleeps == [2.0] * settings.max_retries


@pytest.mark.asyncio
async def test_5xx_retries_then_succeeds_within_budget(monkeypatch):
    """A transient 503 that clears within the retry budget must not raise."""

    async def fake_sleep(seconds: float) -> None:
        return None

    monkeypatch.setattr("digitalocean_mcp.inference_client.asyncio.sleep", fake_sleep)

    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 2:
            return httpx.Response(503, json={"id": "server_error", "message": "temporarily unavailable"})
        return httpx.Response(200, json={"object": "list", "data": []})

    settings = Settings(max_retries=3, max_retry_wait_seconds=30.0)
    client = DigitalOceanInferenceClient(
        "do_fake_token", settings, transport=httpx.MockTransport(handler)
    )
    try:
        result = await client.request("GET", "/v1/models")
    finally:
        await client.aclose()

    assert result == {"object": "list", "data": []}
    assert attempts == 2
