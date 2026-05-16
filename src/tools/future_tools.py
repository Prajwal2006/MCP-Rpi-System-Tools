"""Future feature placeholders for roadmap planning."""

from __future__ import annotations

from typing import Any


def get_roadmap_todos() -> dict[str, Any]:
    """Return planned future MCP tool integrations."""

    return {
        "ok": True,
        "todo": [
            "GPIO controls",
            "Docker monitoring",
            "Home Assistant integration",
            "Camera integration",
            "Audio controls",
        ],
    }
