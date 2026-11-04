"""Serverless Inference tools: list the model catalog, then run chat
completions, embeddings, and image generation against a catalog model id.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from digitalocean_mcp.tools._shared import bounded_dumps, get_client, tool_guard


def register(mcp: FastMCP) -> None:
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True), structured_output=False)
    @tool_guard
    async def digitalocean_inference_list_models() -> str:
        """List models available for inference on the account.

        No arguments. Returns each model's id, creation timestamp, and owner.
        """
        async with await get_client() as client:
            body = await client.request("GET", "/v1/models")
        models = body.get("data") or []
        return bounded_dumps(
            {
                "models": [
                    {"id": m.get("id"), "created": m.get("created"), "owned_by": m.get("owned_by")}
                    for m in models
                ]
            }
        )

    @mcp.tool(annotations=ToolAnnotations(), structured_output=False)
    @tool_guard
    async def digitalocean_inference_create_chat_completion(
        model: str,
        messages: list[dict[str, str]],
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str:
        """Generate a chat completion from a catalog model.

        Args: model - catalog model id (see list_models). messages - chat
        history as a list of {role, content} objects, oldest first.
        max_tokens - optional response length cap. temperature - optional
        sampling temperature.
        """
        body: dict[str, Any] = {"model": model, "messages": messages}
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        if temperature is not None:
            body["temperature"] = temperature
        async with await get_client() as client:
            result = await client.request("POST", "/v1/chat/completions", json_body=body)
        choice = (result.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        return bounded_dumps(
            {
                "content": message.get("content"),
                "finish_reason": choice.get("finish_reason"),
                "usage": result.get("usage"),
            }
        )

    @mcp.tool(annotations=ToolAnnotations(), structured_output=False)
    @tool_guard
    async def digitalocean_inference_create_embedding(model: str, input: str | list[str]) -> str:
        """Create one embedding vector per input string.

        Args: model - catalog embedding model id. input - a single string or
        a list of strings to embed.
        """
        async with await get_client() as client:
            result = await client.request(
                "POST", "/v1/embeddings", json_body={"model": model, "input": input}
            )
        data = sorted(result.get("data") or [], key=lambda d: d.get("index", 0))
        return bounded_dumps(
            {
                "embeddings": [d.get("embedding") for d in data],
                "usage": result.get("usage"),
            }
        )

    @mcp.tool(annotations=ToolAnnotations(), structured_output=False)
    @tool_guard
    async def digitalocean_inference_generate_image(
        model: str,
        prompt: str,
        n: int | None = None,
        size: str | None = None,
        output_format: str | None = None,
    ) -> str:
        """Generate image(s) from a text prompt; not read-only, consumes quota.

        Args: model - catalog image model id. prompt - text description of
        the desired image. n - optional image count (DigitalOcean caps at
        10). size - optional dimensions, e.g. "1024x1024". output_format -
        optional, e.g. "png".
        """
        body: dict[str, Any] = {"model": model, "prompt": prompt}
        if n is not None:
            body["n"] = n
        if size is not None:
            body["size"] = size
        if output_format is not None:
            body["output_format"] = output_format
        async with await get_client() as client:
            result = await client.request("POST", "/v1/images/generations", json_body=body)
        images = result.get("data") or []
        return bounded_dumps(
            {
                "images": [
                    {"b64_json": img.get("b64_json"), "revised_prompt": img.get("revised_prompt")}
                    for img in images
                ]
            }
        )
