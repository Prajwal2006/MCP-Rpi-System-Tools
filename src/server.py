"""Entrypoint for the mcp-rpi-system FastMCP server."""

from __future__ import annotations

import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from config.settings import SETTINGS
from tools.monitoring_tools import get_system_stats
from tools.network_tools import get_ip_addresses, get_network_usage
from tools.process_tools import get_process_count, get_top_processes
from tools.system_tools import cancel_action, confirm_action, get_uptime, request_restart, request_shutdown
from utils.logging_utils import configure_logging, get_logger

configure_logging(SETTINGS.log_level)
logger = get_logger(__name__)

mcp = FastMCP(SETTINGS.server_name)


@mcp.tool(name="request_restart")
def request_restart_tool() -> dict:
    """Request a Raspberry Pi restart.

    Initiates the two-step confirmation flow.  A cryptographically random
    one-time token (e.g. ``CONFIRM_RESTART_A8F291``) is generated and
    included in the response message.  The user must type that exact token
    back; the agent must then pass it to ``confirm_action``.

    Requires ``MCP_ALLOW_POWER_ACTIONS=true``.
    """
    return request_restart()


@mcp.tool(name="request_shutdown")
def request_shutdown_tool() -> dict:
    """Request a Raspberry Pi shutdown.

    Initiates the two-step confirmation flow.  A cryptographically random
    one-time token (e.g. ``CONFIRM_SHUTDOWN_B72C1D``) is generated and
    included in the response message.  The user must type that exact token
    back; the agent must then pass it to ``confirm_action``.

    Requires ``MCP_ALLOW_POWER_ACTIONS=true``.
    """
    return request_shutdown()


@mcp.tool(name="confirm_action")
async def confirm_action_tool(action: str) -> dict:
    """Confirm a previously requested dangerous action.

    IMPORTANT: Never call this tool automatically. Only call this tool after
    receiving the exact confirmation token typed by the human user in their
    message. Do not extract the token from a prior tool response and pass it
    here within the same reasoning turn — doing so bypasses the human-in-the-
    loop safety gate.

    Pass the random one-time token returned by ``request_restart`` or
    ``request_shutdown`` (e.g. ``CONFIRM_RESTART_A8F291``).  The action must
    be confirmed within 30 seconds or the request expires.

    Args:
        action: The confirmation token string typed by the human user, e.g.
            ``"CONFIRM_RESTART_A8F291"``.
    """
    return await confirm_action(action)


@mcp.tool(name="cancel_action")
def cancel_action_tool() -> dict:
    """Cancel any pending dangerous action (restart or shutdown).

    Discards the current pending confirmation token and action.  Safe to call
    even when no action is pending.
    """
    return cancel_action()


@mcp.tool(name="get_uptime")
def get_uptime_tool() -> dict:
    """Get Raspberry Pi uptime metrics."""

    return get_uptime()


@mcp.tool(name="get_system_stats")
async def get_system_stats_tool() -> dict:
    """Get CPU/RAM/disk/temperature/load stats."""

    return await get_system_stats()


@mcp.tool(name="get_top_processes")
def get_top_processes_tool(limit: int = 5) -> dict:
    """Get top processes by CPU and memory usage."""

    return get_top_processes(limit=limit)


@mcp.tool(name="get_process_count")
def get_process_count_tool() -> dict:
    """Get count of running processes."""

    return get_process_count()


@mcp.tool(name="get_network_usage")
def get_network_usage_tool() -> dict:
    """Get aggregate network transfer statistics."""

    return get_network_usage()


@mcp.tool(name="get_ip_addresses")
def get_ip_addresses_tool() -> dict:
    """Get host IPv4/IPv6 addresses by interface."""

    return get_ip_addresses()


def main() -> None:
    """Run the FastMCP server over stdio."""

    logger.info("Starting MCP Raspberry Pi system server")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
