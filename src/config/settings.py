"""Centralized configuration for the MCP Raspberry Pi system server.

Purpose
-------
This module is the single source of truth for all configurable values.
Edit this file directly to change server behaviour — no environment variables
are required for feature flags or security-sensitive settings.

How to modify configuration safely
------------------------------------
* To enable or disable power actions, set ``ALLOW_POWER_ACTIONS`` below.
* To change how long a confirmation token is valid, set ``CONFIRMATION_TIMEOUT``.
* Feature flags (``ENABLE_GPIO``, etc.) control future tool availability.
* NEVER gate security-critical logic on environment variables; use the
  named constants defined here instead.

Security-sensitive settings
-----------------------------
``ALLOW_POWER_ACTIONS`` — controls whether restart/shutdown can be requested.
  Even when ``True``, a human must supply a cryptographically random
  confirmation token before any power command is executed.  Setting this to
  ``False`` disables the tools entirely, providing an additional hard guard.

# TODO: Future configuration expansion
#   - Load overrides from a YAML/TOML file (e.g. config.toml)
#   - Database-backed config store for multi-node deployments
#   - Persistent config file with file-watching for live reloads
#   - Role-based permissions per MCP client identity
"""

from __future__ import annotations

import os
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Operational settings (server identity / logging)
# These are safe to configure via environment variables because they do not
# control security-sensitive behaviour.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ServerSettings:
    """Runtime settings for server identity and logging."""

    server_name: str = os.getenv("MCP_SERVER_NAME", "mcp-rpi-system")
    log_level: str = os.getenv("MCP_LOG_LEVEL", "INFO").upper()


SETTINGS = ServerSettings()

# ---------------------------------------------------------------------------
# Power-action policy
# SECURITY-SENSITIVE: controls whether restart/shutdown tools are enabled.
# Even when True, a human must supply a confirmation token before execution.
# Modify this value here — do NOT use an environment variable for this flag.
# ---------------------------------------------------------------------------

#: Set to ``True`` to allow restart/shutdown requests from the MCP client.
#: Set to ``False`` to hard-disable all power actions regardless of client input.
ALLOW_POWER_ACTIONS: bool = True

# ---------------------------------------------------------------------------
# Confirmation flow
# ---------------------------------------------------------------------------

#: Seconds a pending confirmation token remains valid before it expires.
CONFIRMATION_TIMEOUT: int = 30

# ---------------------------------------------------------------------------
# Future feature flags (all disabled by default)
# Enable these when the corresponding tool modules are implemented.
# ---------------------------------------------------------------------------

#: Enable GPIO control tools (requires RPi.GPIO or lgpio).
ENABLE_GPIO: bool = False

#: Enable Docker container monitoring tools (requires docker SDK).
ENABLE_DOCKER_MONITORING: bool = False

#: Enable Raspberry Pi camera tools (requires picamera2).
ENABLE_CAMERA_TOOLS: bool = False

#: Enable audio input/output tools (requires pyaudio or sounddevice).
ENABLE_AUDIO_TOOLS: bool = False
