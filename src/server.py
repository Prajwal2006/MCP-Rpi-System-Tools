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
from tools.system_tools import get_uptime, reboot_pi, shutdown_pi
from utils.logging_utils import configure_logging, get_logger

configure_logging(SETTINGS.log_level)
logger = get_logger(__name__)

mcp = FastMCP(SETTINGS.server_name)


@mcp.tool(name="reboot_pi")
async def reboot_pi_tool() -> dict:
    """Reboot the Raspberry Pi host (guarded by policy)."""

    return await reboot_pi()


@mcp.tool(name="shutdown_pi")
async def shutdown_pi_tool() -> dict:
    """Shutdown the Raspberry Pi host (guarded by policy)."""

    return await shutdown_pi()


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
