"""System control and uptime MCP tool functions."""

from __future__ import annotations

import asyncio
import time
from typing import Any

import psutil

from config.settings import SETTINGS
from utils.logging_utils import get_logger

logger = get_logger(__name__)

_ALLOWED_POWER_COMMANDS: dict[str, tuple[str, ...]] = {
    "reboot": ("sudo", "reboot"),
    "shutdown": ("sudo", "shutdown", "-h", "now"),
}


async def _run_power_command(action: str) -> dict[str, Any]:
    """Execute a whitelisted power command with subprocess safety controls."""

    command = _ALLOWED_POWER_COMMANDS[action]
    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=10)
        return {
            "ok": process.returncode == 0,
            "action": action,
            "returncode": process.returncode,
            "stdout": stdout.decode().strip(),
            "stderr": stderr.decode().strip(),
        }
    except TimeoutError:
        logger.exception("Power command timed out", extra={"action": action})
        return {"ok": False, "action": action, "error": "command_timeout"}
    except Exception:
        logger.exception("Power command execution failed", extra={"action": action})
        return {"ok": False, "action": action, "error": "command_failed"}


async def reboot_pi() -> dict[str, Any]:
    """Reboot the Raspberry Pi using a fixed whitelisted command."""

    if not SETTINGS.allow_power_actions:
        return {
            "ok": False,
            "action": "reboot",
            "error": "disabled_by_policy",
            "message": "Set MCP_ALLOW_POWER_ACTIONS=true to enable reboot/shutdown.",
        }
    return await _run_power_command("reboot")


async def shutdown_pi() -> dict[str, Any]:
    """Shutdown the Raspberry Pi using a fixed whitelisted command."""

    if not SETTINGS.allow_power_actions:
        return {
            "ok": False,
            "action": "shutdown",
            "error": "disabled_by_policy",
            "message": "Set MCP_ALLOW_POWER_ACTIONS=true to enable reboot/shutdown.",
        }
    return await _run_power_command("shutdown")


def get_uptime() -> dict[str, Any]:
    """Return system uptime details in seconds and human-friendly units."""

    try:
        boot_time = max(0.0, float(psutil.boot_time()))
        elapsed = max(0.0, time.time() - boot_time)
        return {
            "ok": True,
            "uptime_seconds": round(elapsed, 2),
            "uptime_minutes": round(elapsed / 60, 2),
            "uptime_hours": round(elapsed / 3600, 2),
        }
    except Exception:
        logger.exception("Failed to fetch uptime")
        return {"ok": False, "error": "uptime_unavailable"}
