"""System monitoring MCP tool functions."""

from __future__ import annotations

import asyncio
import os
import re
from typing import Any

import psutil

from utils.logging_utils import get_logger

logger = get_logger(__name__)


async def _get_cpu_temperature() -> dict[str, Any]:
    """Read Raspberry Pi CPU temperature from vcgencmd when available."""

    command = ("vcgencmd", "measure_temp")
    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=5)
        if process.returncode != 0:
            return {
                "available": False,
                "error": stderr.decode().strip() or "vcgencmd_failed",
            }

        output = stdout.decode().strip()
        match = re.search(r"temp=([0-9]+(?:\.[0-9]+)?)", output)
        if not match:
            return {"available": False, "error": "parse_error", "raw": output}

        return {"available": True, "celsius": float(match.group(1)), "raw": output}
    except FileNotFoundError:
        return {"available": False, "error": "vcgencmd_not_installed"}
    except TimeoutError:
        return {"available": False, "error": "vcgencmd_timeout"}
    except Exception:
        logger.exception("Failed to fetch CPU temperature")
        return {"available": False, "error": "temperature_unavailable"}


def _get_load_average() -> dict[str, Any]:
    """Read system load average in a cross-platform safe way."""

    try:
        load1, load5, load15 = os.getloadavg()
        return {
            "available": True,
            "1m": round(load1, 2),
            "5m": round(load5, 2),
            "15m": round(load15, 2),
        }
    except (OSError, AttributeError):
        return {"available": False}


async def get_system_stats() -> dict[str, Any]:
    """Return CPU, RAM, disk, temperature, and load-average metrics."""

    try:
        cpu_usage = psutil.cpu_percent(interval=0.5)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        temperature = await _get_cpu_temperature()
        load_average = _get_load_average()

        return {
            "ok": True,
            "cpu_usage_percent": round(cpu_usage, 2),
            "ram": {
                "usage_percent": round(memory.percent, 2),
                "total_bytes": int(memory.total),
                "used_bytes": int(memory.used),
                "available_bytes": int(memory.available),
            },
            "disk": {
                "usage_percent": round(disk.percent, 2),
                "total_bytes": int(disk.total),
                "used_bytes": int(disk.used),
                "free_bytes": int(disk.free),
            },
            "cpu_temperature": temperature,
            "load_average": load_average,
        }
    except Exception:
        logger.exception("Failed to fetch system stats")
        return {"ok": False, "error": "system_stats_unavailable"}
