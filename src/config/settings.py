"""Application configuration values for the MCP Raspberry Pi system server."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ServerSettings:
    """Runtime settings loaded from environment variables."""

    server_name: str = os.getenv("MCP_SERVER_NAME", "mcp-rpi-system")
    log_level: str = os.getenv("MCP_LOG_LEVEL", "INFO").upper()
    allow_power_actions: bool = os.getenv("MCP_ALLOW_POWER_ACTIONS", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


SETTINGS = ServerSettings()
