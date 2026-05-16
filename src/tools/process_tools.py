"""Process monitoring MCP tool functions."""

from __future__ import annotations

from typing import Any

import psutil

from utils.logging_utils import get_logger

logger = get_logger(__name__)


def get_top_processes(limit: int = 5) -> dict[str, Any]:
    """Return top processes ranked by CPU and memory usage."""

    if not isinstance(limit, int) or limit < 1 or limit > 50:
        return {
            "ok": False,
            "error": "invalid_limit",
            "message": "limit must be an integer between 1 and 50",
        }

    try:
        processes: list[dict[str, Any]] = []
        for proc in psutil.process_iter(
            attrs=["pid", "name", "username", "cpu_percent", "memory_percent"],
        ):
            info = proc.info
            processes.append(
                {
                    "pid": info.get("pid"),
                    "name": info.get("name") or "unknown",
                    "username": info.get("username") or "unknown",
                    "cpu_percent": round(float(info.get("cpu_percent") or 0.0), 2),
                    "memory_percent": round(float(info.get("memory_percent") or 0.0), 2),
                }
            )

        processes.sort(
            key=lambda item: (item["cpu_percent"], item["memory_percent"]),
            reverse=True,
        )
        return {"ok": True, "count": len(processes), "top_processes": processes[:limit]}
    except Exception:
        logger.exception("Failed to fetch top processes")
        return {"ok": False, "error": "top_processes_unavailable"}


def get_process_count() -> dict[str, Any]:
    """Return the number of running processes visible to the current user."""

    try:
        return {"ok": True, "process_count": len(psutil.pids())}
    except Exception:
        logger.exception("Failed to fetch process count")
        return {"ok": False, "error": "process_count_unavailable"}
