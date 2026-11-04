"""tools/list snapshot + per-tool happy-path and error-mapping tests.

Every upstream call is mocked via `httpx.MockTransport` -- no real
DigitalOcean account is used or needed here (see TC12 in
docs/tickets/PRD-21343.ac.json, marked "needs a real vendor account", which
this file does not attempt to cover).
"""

from __future__ import annotations

import httpx
import pytest

from tests.conftest import call_tool_json

EXPECTED_TOOLS = {
    "digitalocean_inference_list_models": {
        "readOnlyHint": True,
        "destructiveHint": None,
        "idempotentHint": None,
    },
    "digitalocean_inference_create_chat_completion": {
        "readOnlyHint": None,
        "destructiveHint": None,
        "idempotentHint": None,
    },
    "digitalocean_inference_create_embedding": {
        "readOnlyHint": None,
        "destructiveHint": None,
        "idempotentHint": None,
    },
    "digitalocean_inference_generate_image": {
        "readOnlyHint": None,
        "destructiveHint": None,
        "idempotentHint": None,
    },
}


@pytest.mark.asyncio
async def test_tools_list_has_all_inference_tools_with_valid_descriptions(mcp):
    """TC1 (AC1)."""
    tools = await mcp.list_tools()
    names = {t.name for t in tools}
    assert names == set(EXPECTED_TOOLS), names

    for tool in tools:
        description = tool.description or ""
        first_line = description.split("\n", 1)[0]
        assert len(first_line) <= 100, (tool.name, len(first_line), first_line)
        assert len(description) <= 500, (tool.name, len(description))

    generate_image = next(t for t in tools if t.name == "digitalocean_inference_generate_image")
    assert "not read-only" in (generate_image.description or ""), (
        "AC6 requires the image tool's description to state it is not read-only"
    )


@pytest.mark.asyncio
async def test_tools_list_hints_match_design(mcp):
    tools = {t.name: t for t in await mcp.list_tools()}
    for name, expected in EXPECTED_TOOLS.items():
        annotations = tools[name].annotations
        assert annotations is not None, name
        assert annotations.readOnlyHint == expected["readOnlyHint"], name
        assert annotations.destructiveHint == expected["destructiveHint"], name
        assert annotations.idempotentHint == expected["idempotentHint"], name


@pytest.mark.asyncio
async def test_list_models_returns_catalog(mcp, fake_token, set_handler):
    """TC3 (AC3)."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/models"
        assert request.headers["authorization"] == "Bearer do_fake_token_test"
        return httpx.Response(
            200,
            json={
                "object": "list",
                "data": [
                    {"id": "llama3.3-70b-instruct", "object": "model", "created": 1730000000, "owned_by": "digitalocean"},
                    {"id": "qwen3-embedding-0.6b", "object": "model", "created": 1730000001, "owned_by": "digitalocean"},
                    {"id": "openai-gpt-image-2", "object": "model", "created": 1730000002, "owned_by": "digitalocean"},
                ],
            },
        )

    set_handler(handler)
    result = await call_tool_json(mcp, "digitalocean_inference_list_models")
    assert len(result["models"]) == 3
    assert result["models"][0] == {"id": "llama3.3-70b-instruct", "created": 1730000000, "owned_by": "digitalocean"}


@pytest.mark.asyncio
async def test_create_chat_completion_happy_path(mcp, fake_token, set_handler):
    """TC4 (AC4)."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-abc123",
                "object": "chat.completion",
                "created": 1730000000,
                "model": "llama3.3-70b-instruct",
                "choices": [
                    {"index": 0, "message": {"role": "assistant", "content": "Hello!"}, "finish_reason": "stop"}
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
            },
        )

    set_handler(handler)
    result = await call_tool_json(
        mcp,
        "digitalocean_inference_create_chat_completion",
        {"model": "llama3.3-70b-instruct", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert result["content"] == "Hello!"
    assert result["finish_reason"] == "stop"
    assert result["usage"] == {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}


@pytest.mark.asyncio
async def test_create_chat_completion_unknown_model_returns_structured_error(mcp, fake_token, set_handler):
    """TC5 (AC4)."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"id": "not_found", "message": "model 'does-not-exist' was not found"})

    set_handler(handler)
    result = await call_tool_json(
        mcp,
        "digitalocean_inference_create_chat_completion",
        {"model": "does-not-exist", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert result["error"]["code"] == "not_found"
    assert "does-not-exist" in result["error"]["message"]
    assert result["error"]["retryable"] is False


@pytest.mark.asyncio
async def test_create_embedding_multi_input(mcp, fake_token, set_handler):
    """TC6 (AC5)."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/embeddings"
        return httpx.Response(
            200,
            json={
                "object": "list",
                "model": "qwen3-embedding-0.6b",
                "data": [
                    {"object": "embedding", "index": 0, "embedding": [0.1, 0.2]},
                    {"object": "embedding", "index": 1, "embedding": [0.3, 0.4]},
                ],
                "usage": {"prompt_tokens": 6, "total_tokens": 6},
            },
        )

    set_handler(handler)
    result = await call_tool_json(
        mcp,
        "digitalocean_inference_create_embedding",
        {"model": "qwen3-embedding-0.6b", "input": ["text one", "text two"]},
    )
    assert result["embeddings"] == [[0.1, 0.2], [0.3, 0.4]]
    assert result["usage"] == {"prompt_tokens": 6, "total_tokens": 6}


@pytest.mark.asyncio
async def test_generate_image_happy_path(mcp, fake_token, set_handler):
    """TC7 (AC6)."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/images/generations"
        return httpx.Response(
            200,
            json={
                "created": 1730000000,
                "data": [{"b64_json": "iVBORw0KG...", "revised_prompt": "A red bicycle, studio lighting"}],
                "size": "1024x1536",
                "quality": "auto",
                "output_format": "png",
            },
        )

    set_handler(handler)
    result = await call_tool_json(
        mcp,
        "digitalocean_inference_generate_image",
        {"model": "openai-gpt-image-2", "prompt": "a red bicycle", "n": 1},
    )
    assert result["images"] == [{"b64_json": "iVBORw0KG...", "revised_prompt": "A red bicycle, studio lighting"}]


@pytest.mark.asyncio
async def test_upstream_401_returns_unauthorized_not_not_configured(mcp, fake_token, set_handler):
    """TC9 (AC8): a valid MSPbots header but an invalid DigitalOcean token."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"id": "unauthorized", "message": "Unable to authenticate you."})

    set_handler(handler)
    result = await call_tool_json(mcp, "digitalocean_inference_list_models")
    assert result["error"]["code"] == "unauthorized"
    assert result["error"]["code"] != "not_configured"
    assert result["error"]["retryable"] is False
