"""Tests for the credential middleware: TC3 (AC2, Apps) / TC2 (AC2, Inference),
TC17 (AC13, Apps) / TC10 (AC9, Inference) -- concurrency isolation is tested
once per resource group's own client class, since each talks to a different
upstream base URL and the point of the test is that neither client lets one
tenant's token leak into another's outbound call.

Also covers the request-id / logging behaviour added in review round 1 of
PRD-21338 (must-fix: structured logging, SOP section 6), which the shared
`CredentialMiddleware` applies to every resource group's requests alike.
"""

from __future__ import annotations

import asyncio
import json
import logging

import httpx
import pytest

from digitalocean_mcp import telemetry
from digitalocean_mcp.client import DigitalOceanClient
from digitalocean_mcp.inference_client import DigitalOceanInferenceClient
from digitalocean_mcp.kubernetes_client import DigitalOceanKubernetesClient
from digitalocean_mcp.middleware import CREDENTIAL_HEADER, CredentialMiddleware, get_api_token
from digitalocean_mcp.settings import Settings


async def call_asgi(app, *, path: str = "/mcp", headers: dict[str, str] | None = None):
    """Drive one HTTP request through an ASGI callable without a real server."""
    raw_headers = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    scope = {"type": "http", "method": "POST", "path": path, "headers": raw_headers}

    sent_once = False

    async def receive():
        nonlocal sent_once
        if sent_once:
            return {"type": "http.disconnect"}
        sent_once = True
        return {"type": "http.request", "body": b"{}", "more_body": False}

    messages: list[dict] = []

    async def send(message):
        messages.append(message)

    await app(scope, receive, send)

    start = next(m for m in messages if m["type"] == "http.response.start")
    body = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
    return start["status"], start["headers"], body


async def _respond_200(send) -> None:
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"ok"})


@pytest.mark.asyncio
async def test_missing_credential_header_returns_401_before_upstream_call():
    calls: list[str] = []

    async def downstream(scope, receive, send):
        calls.append("reached")
        await _respond_200(send)

    middleware = CredentialMiddleware(downstream, mcp_path="/mcp")
    status, _headers, body = await call_asgi(middleware, path="/mcp", headers={})

    assert status == 401
    payload = json.loads(body)
    assert payload["error"]["code"] == "not_configured"
    assert CREDENTIAL_HEADER in payload["error"]["message"]
    assert calls == [], "downstream (and so the upstream DigitalOcean client) must never run"


@pytest.mark.asyncio
async def test_missing_credential_header_logs_a_warning_with_no_token_value(caplog):
    """Review round 1 must-fix: the 401 path is itself observable, and never
    logs the credential header value (there is none to log in this path,
    but the log line must not echo back arbitrary request headers either).
    """
    caplog.set_level(logging.WARNING, logger="digitalocean_mcp")

    async def downstream(scope, receive, send):
        await _respond_200(send)

    middleware = CredentialMiddleware(downstream, mcp_path="/mcp")
    await call_asgi(middleware, path="/mcp", headers={CREDENTIAL_HEADER: ""})

    assert len(caplog.records) == 1
    payload = json.loads(caplog.records[0].message)
    assert payload["event"] == "missing_credential_header"
    assert payload["path"] == "/mcp"
    assert "token" not in json.dumps(payload).lower()


@pytest.mark.asyncio
async def test_request_id_is_bound_during_the_request_and_cleared_after():
    seen: dict[str, str | None] = {}

    async def downstream(scope, receive, send):
        seen["request_id"] = telemetry.get_request_id()
        await _respond_200(send)

    middleware = CredentialMiddleware(downstream, mcp_path="/mcp")
    await call_asgi(middleware, path="/mcp", headers={CREDENTIAL_HEADER: "do_fake_token_123"})

    assert seen["request_id"], "a request-id must be bound while the request is in flight"
    assert telemetry.get_request_id() is None


@pytest.mark.asyncio
async def test_each_request_gets_its_own_request_id():
    seen: list[str | None] = []

    async def downstream(scope, receive, send):
        seen.append(telemetry.get_request_id())
        await _respond_200(send)

    middleware = CredentialMiddleware(downstream, mcp_path="/mcp")
    await call_asgi(middleware, path="/mcp", headers={CREDENTIAL_HEADER: "t"})
    await call_asgi(middleware, path="/mcp", headers={CREDENTIAL_HEADER: "t"})

    assert len(seen) == 2
    assert seen[0] != seen[1]


@pytest.mark.asyncio
async def test_health_path_is_not_gated_by_the_credential_header():
    calls: list[str] = []

    async def downstream(scope, receive, send):
        calls.append("reached")
        await _respond_200(send)

    middleware = CredentialMiddleware(downstream, mcp_path="/mcp")
    status, _headers, _body = await call_asgi(middleware, path="/health", headers={})

    assert status == 200
    assert calls == ["reached"]


@pytest.mark.asyncio
async def test_header_present_value_reaches_tool_via_context_var():
    seen: dict[str, str | None] = {}

    async def downstream(scope, receive, send):
        seen["token"] = get_api_token()
        await _respond_200(send)

    middleware = CredentialMiddleware(downstream, mcp_path="/mcp")
    status, _headers, _body = await call_asgi(
        middleware, path="/mcp", headers={CREDENTIAL_HEADER: "do_fake_token_123"}
    )

    assert status == 200
    assert seen["token"] == "do_fake_token_123"
    # Outside any request, the ContextVar must be back to its reset default.
    assert get_api_token() is None


@pytest.mark.asyncio
async def test_concurrent_requests_do_not_cross_contaminate_credentials():
    """AC13 / TC17 (Apps): two tenants' tokens must never leak into each
    other's outbound call through the Apps resource group's client."""

    captured_auth_headers: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_auth_headers.append(request.headers.get("authorization", ""))
        return httpx.Response(200, json={"apps": []})

    transport = httpx.MockTransport(handler)
    results: dict[str, str | None] = {}

    def make_downstream(label: str):
        async def downstream(scope, receive, send):
            token = get_api_token()
            # Force interleaving so a global/module-level bug would actually surface.
            await asyncio.sleep(0.01)
            async with DigitalOceanClient(token, Settings(), transport=transport) as client:
                await client.request("GET", "/v2/apps")
            results[label] = token
            await _respond_200(send)

        return downstream

    middleware_a = CredentialMiddleware(make_downstream("A"), mcp_path="/mcp")
    middleware_b = CredentialMiddleware(make_downstream("B"), mcp_path="/mcp")

    await asyncio.gather(
        call_asgi(middleware_a, path="/mcp", headers={CREDENTIAL_HEADER: "token-A"}),
        call_asgi(middleware_b, path="/mcp", headers={CREDENTIAL_HEADER: "token-B"}),
    )

    assert results["A"] == "token-A"
    assert results["B"] == "token-B"
    assert set(captured_auth_headers) == {"Bearer token-A", "Bearer token-B"}


@pytest.mark.asyncio
async def test_concurrent_requests_do_not_leak_credentials_across_tenants_kubernetes():
    """AC18 / TC18 (Kubernetes): two tenants' tokens must never leak into
    each other's outbound call through the Kubernetes resource group's
    client. A distinct client class and upstream path from the Apps/
    Inference tests above, so each resource group's own client is covered."""

    captured_auth_headers: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_auth_headers.append(request.headers.get("authorization", ""))
        return httpx.Response(200, json={"kubernetes_clusters": []})

    transport = httpx.MockTransport(handler)
    results: dict[str, str | None] = {}

    def make_downstream(label: str):
        async def downstream(scope, receive, send):
            token = get_api_token()
            # Force interleaving so a global/module-level bug would actually surface.
            await asyncio.sleep(0.01)
            async with DigitalOceanKubernetesClient(token, Settings(), transport=transport) as client:
                await client.request("GET", "/v2/kubernetes/clusters")
            results[label] = token
            await _respond_200(send)

        return downstream

    middleware_a = CredentialMiddleware(make_downstream("A"), mcp_path="/mcp")
    middleware_b = CredentialMiddleware(make_downstream("B"), mcp_path="/mcp")

    await asyncio.gather(
        call_asgi(middleware_a, path="/mcp", headers={CREDENTIAL_HEADER: "token-A"}),
        call_asgi(middleware_b, path="/mcp", headers={CREDENTIAL_HEADER: "token-B"}),
    )

    assert results["A"] == "token-A"
    assert results["B"] == "token-B"
    assert set(captured_auth_headers) == {"Bearer token-A", "Bearer token-B"}


@pytest.mark.asyncio
async def test_concurrent_requests_do_not_leak_credentials_across_tenants_inference():
    """AC9 / TC10 (Inference): two tenants' tokens must never leak into each
    other's outbound call through the Serverless Inference resource group's
    client. A distinct client class and upstream path from the Apps test
    above, so both are kept rather than one standing in for the other."""

    captured_auth_headers: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_auth_headers.append(request.headers.get("authorization", ""))
        return httpx.Response(200, json={"object": "list", "data": []})

    transport = httpx.MockTransport(handler)
    results: dict[str, str | None] = {}

    def make_downstream(label: str):
        async def downstream(scope, receive, send):
            token = get_api_token()
            # Force interleaving so a global/module-level bug would actually surface.
            await asyncio.sleep(0.01)
            async with DigitalOceanInferenceClient(token, Settings(), transport=transport) as client:
                await client.request("GET", "/v1/models")
            results[label] = token
            await _respond_200(send)

        return downstream

    middleware_a = CredentialMiddleware(make_downstream("A"), mcp_path="/mcp")
    middleware_b = CredentialMiddleware(make_downstream("B"), mcp_path="/mcp")

    await asyncio.gather(
        call_asgi(middleware_a, path="/mcp", headers={CREDENTIAL_HEADER: "token-A"}),
        call_asgi(middleware_b, path="/mcp", headers={CREDENTIAL_HEADER: "token-B"}),
    )

    assert results["A"] == "token-A"
    assert results["B"] == "token-B"
    assert set(captured_auth_headers) == {"Bearer token-A", "Bearer token-B"}
