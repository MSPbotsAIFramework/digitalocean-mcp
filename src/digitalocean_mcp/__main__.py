"""Entry point: start the HTTP service with uvicorn."""

from __future__ import annotations

import uvicorn

from digitalocean_mcp.server import build_app
from digitalocean_mcp.settings import get_settings


def main() -> None:
    settings = get_settings()
    app = build_app(settings)
    uvicorn.run(app, host=settings.mcp_http_host, port=settings.mcp_http_port)


if __name__ == "__main__":
    main()
