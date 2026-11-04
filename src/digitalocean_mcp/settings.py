"""Non-secret service configuration.

Per SOP section 1.2 and section 3.1: credentials never live here. This only
holds transport-level knobs, and must tolerate unknown environment variables
injected by the runtime (`extra="ignore"`), otherwise the container crashes
on startup whenever the platform injects a variable this project never
declared.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    mcp_http_host: str = "0.0.0.0"
    mcp_http_port: int = 8080

    # Outbound HTTP timeouts against api.digitalocean.com (SOP section 5).
    connect_timeout_seconds: float = 5.0
    read_timeout_seconds: float = 30.0

    # Retry budget for 429 / 5xx responses (SOP section 5).
    max_retries: int = 4
    max_retry_wait_seconds: float = 30.0


def get_settings() -> Settings:
    return Settings()
