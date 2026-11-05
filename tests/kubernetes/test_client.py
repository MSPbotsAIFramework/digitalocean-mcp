"""Retry/backoff behavior of `DigitalOceanKubernetesClient` on 429/5xx (AC19)."""

from __future__ import annotations

import httpx
import pytest

from digitalocean_mcp.errors import ToolError
from digitalocean_mcp.kubernetes_client import DigitalOceanKubernetesClient
from digitalocean_mcp.settings import Settings


@pytest.mark.asyncio
async def test_429_retries_honoring_retry_after_then_rate_limited(monkeypatch):
    """TC19 (AC19): persistent 429 retries up to the bounded budget, honoring
    Retry-After, then surfaces a structured rate_limited error."""

    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr("digitalocean_mcp.kubernetes_client.asyncio.sleep", fake_sleep)

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
    client = DigitalOceanKubernetesClient("do_fake_token", settings, transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(ToolError) as exc_info:
            await client.request("GET", "/v2/kubernetes/clusters")
    finally:
        await client.aclose()

    assert exc_info.value.code == "rate_limited"
    assert exc_info.value.retryable is True
    assert attempts == settings.max_retries + 1
    assert sleeps == [2.0] * settings.max_retries


@pytest.mark.asyncio
async def test_5xx_retries_then_upstream_error(monkeypatch):
    """TC19 (AC19): a persistent 503 retries, and once the budget is
    exhausted, surfaces a structured upstream_error (not a bare exception)."""

    async def fake_sleep(seconds: float) -> None:
        return None

    monkeypatch.setattr("digitalocean_mcp.kubernetes_client.asyncio.sleep", fake_sleep)

    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(503, json={"id": "server_error", "message": "temporarily unavailable"})

    settings = Settings(max_retries=2, max_retry_wait_seconds=30.0)
    client = DigitalOceanKubernetesClient("do_fake_token", settings, transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(ToolError) as exc_info:
            await client.request("GET", "/v2/kubernetes/clusters")
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

    monkeypatch.setattr("digitalocean_mcp.kubernetes_client.asyncio.sleep", fake_sleep)

    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 2:
            return httpx.Response(503, json={"id": "server_error", "message": "temporarily unavailable"})
        return httpx.Response(200, json={"kubernetes_clusters": []})

    settings = Settings(max_retries=3, max_retry_wait_seconds=30.0)
    client = DigitalOceanKubernetesClient("do_fake_token", settings, transport=httpx.MockTransport(handler))
    try:
        result = await client.request("GET", "/v2/kubernetes/clusters")
    finally:
        await client.aclose()

    assert result == {"kubernetes_clusters": []}
    assert attempts == 2


@pytest.mark.asyncio
async def test_request_raw_text_returns_unparsed_body_and_maps_errors():
    """AC10: get_kubeconfig's underlying call returns the raw body, and still
    maps error status codes the same way request() does."""

    def ok_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="apiVersion: v1\nkind: Config\n")

    client = DigitalOceanKubernetesClient(
        "do_fake_token", Settings(), transport=httpx.MockTransport(ok_handler)
    )
    try:
        text = await client.request_raw_text("GET", "/v2/kubernetes/clusters/abc/kubeconfig")
    finally:
        await client.aclose()
    assert text == "apiVersion: v1\nkind: Config\n"

    def not_found_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"id": "not_found", "message": "Cluster not found"})

    client2 = DigitalOceanKubernetesClient(
        "do_fake_token", Settings(), transport=httpx.MockTransport(not_found_handler)
    )
    try:
        with pytest.raises(ToolError) as exc_info:
            await client2.request_raw_text("GET", "/v2/kubernetes/clusters/missing/kubeconfig")
    finally:
        await client2.aclose()
    assert exc_info.value.code == "not_found"
