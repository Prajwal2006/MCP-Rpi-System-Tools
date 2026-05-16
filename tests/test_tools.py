"""Focused tests for MCP tool responses."""

from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tools.future_tools import get_roadmap_todos
from tools.network_tools import get_ip_addresses, get_network_usage
from tools.process_tools import get_process_count, get_top_processes
from tools.system_tools import get_uptime, reboot_pi, shutdown_pi


class ToolResponseTests(unittest.TestCase):
    """Ensure key tool functions return JSON-compatible dictionaries."""

    def test_sync_tools_return_dict(self) -> None:
        for fn in (
            get_uptime,
            get_process_count,
            get_network_usage,
            get_ip_addresses,
            get_roadmap_todos,
        ):
            response = fn()
            self.assertIsInstance(response, dict)
            self.assertIn("ok", response)

    def test_top_processes_limit_validation(self) -> None:
        response = get_top_processes(limit=0)
        self.assertFalse(response.get("ok", True))
        self.assertEqual(response.get("error"), "invalid_limit")

    def test_power_tools_are_policy_guarded_by_default(self) -> None:
        reboot_response = asyncio.run(reboot_pi())
        shutdown_response = asyncio.run(shutdown_pi())

        self.assertFalse(reboot_response.get("ok", True))
        self.assertEqual(reboot_response.get("error"), "disabled_by_policy")
        self.assertFalse(shutdown_response.get("ok", True))
        self.assertEqual(shutdown_response.get("error"), "disabled_by_policy")


if __name__ == "__main__":
    unittest.main()
