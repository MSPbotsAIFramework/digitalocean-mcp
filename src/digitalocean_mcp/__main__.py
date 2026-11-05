"""Entry point: start the HTTP service with uvicorn."""

from __future__ import annotations

import logging

import uvicorn

from digitalocean_mcp.server import build_app
from digitalocean_mcp.settings import get_settings


def main() -> None:
    # `telemetry.log_event` already serializes each record's message as JSON
    # (SOP section 6), so the root formatter is just the bare message -- no
    # extra wrapping to strip downstream.
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    settings = get_settings()
    app = build_app(settings)
    uvicorn.run(app, host=settings.mcp_http_host, port=settings.mcp_http_port)


if __name__ == "__main__":
    main()
