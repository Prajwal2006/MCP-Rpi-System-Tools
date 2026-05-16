"""Focused tests for MCP tool responses."""

from __future__ import annotations

import asyncio
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tools.confirmation_manager import ConfirmationManager, TTL_SECONDS, get_manager
from tools.future_tools import get_roadmap_todos
from tools.network_tools import get_ip_addresses, get_network_usage
from tools.process_tools import get_process_count, get_top_processes
from tools.system_tools import confirm_action, get_uptime, request_restart, request_shutdown


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


class ConfirmationManagerTests(unittest.TestCase):
    """Unit tests for ConfirmationManager state machine."""

    def setUp(self) -> None:
        # Use a fresh manager for each test to avoid state leakage.
        self.mgr = ConfirmationManager()

    def test_request_returns_confirmation_required(self) -> None:
        result = self.mgr.request("restart")
        self.assertEqual(result["status"], "confirmation_required")
        self.assertIn("CONFIRM_RESTART", result["message"])

    def test_confirm_valid_token(self) -> None:
        self.mgr.request("restart")
        action, expired = self.mgr.confirm("CONFIRM_RESTART")
        self.assertEqual(action, "restart")
        self.assertFalse(expired)

    def test_confirm_wrong_token_returns_none(self) -> None:
        self.mgr.request("restart")
        action, expired = self.mgr.confirm("CONFIRM_SHUTDOWN")
        self.assertIsNone(action)
        self.assertFalse(expired)

    def test_confirm_with_no_pending_returns_none(self) -> None:
        action, expired = self.mgr.confirm("CONFIRM_RESTART")
        self.assertIsNone(action)
        self.assertFalse(expired)

    def test_confirm_expired_action(self) -> None:
        self.mgr.request("shutdown")
        # Wind the expiry back so the action appears expired.
        self.mgr.expiry = time.monotonic() - 1
        action, expired = self.mgr.confirm("CONFIRM_SHUTDOWN")
        self.assertIsNone(action)
        self.assertTrue(expired)
        # Pending state must be cleared after expiry.
        self.assertIsNone(self.mgr.pending_action)

    def test_second_request_replaces_first(self) -> None:
        self.mgr.request("restart")
        self.mgr.request("shutdown")
        self.assertEqual(self.mgr.pending_action, "shutdown")

    def test_clear_removes_pending(self) -> None:
        self.mgr.request("restart")
        self.mgr.clear()
        self.assertIsNone(self.mgr.pending_action)
        self.assertIsNone(self.mgr.expiry)


class PowerToolPolicyTests(unittest.TestCase):
    """Ensure power tools respect the MCP_ALLOW_POWER_ACTIONS policy flag."""

    def test_request_restart_disabled_by_policy(self) -> None:
        with patch("tools.system_tools.SETTINGS") as mock_settings:
            mock_settings.allow_power_actions = False
            response = request_restart()
        self.assertEqual(response.get("status"), "error")
        self.assertEqual(response.get("error"), "disabled_by_policy")

    def test_request_shutdown_disabled_by_policy(self) -> None:
        with patch("tools.system_tools.SETTINGS") as mock_settings:
            mock_settings.allow_power_actions = False
            response = request_shutdown()
        self.assertEqual(response.get("status"), "error")
        self.assertEqual(response.get("error"), "disabled_by_policy")

    def test_request_restart_requires_confirmation(self) -> None:
        """When power actions are allowed, request_restart enters the flow."""
        with patch("tools.system_tools.SETTINGS") as mock_settings:
            mock_settings.allow_power_actions = True
            # Reset the global manager so prior test state doesn't leak.
            get_manager().clear()
            response = request_restart()
        self.assertEqual(response.get("status"), "confirmation_required")
        self.assertIn("CONFIRM_RESTART", response.get("message", ""))
        get_manager().clear()

    def test_request_shutdown_requires_confirmation(self) -> None:
        """When power actions are allowed, request_shutdown enters the flow."""
        with patch("tools.system_tools.SETTINGS") as mock_settings:
            mock_settings.allow_power_actions = True
            get_manager().clear()
            response = request_shutdown()
        self.assertEqual(response.get("status"), "confirmation_required")
        self.assertIn("CONFIRM_SHUTDOWN", response.get("message", ""))
        get_manager().clear()


class ConfirmActionToolTests(unittest.TestCase):
    """Tests for the confirm_action async tool function."""

    def setUp(self) -> None:
        get_manager().clear()

    def tearDown(self) -> None:
        get_manager().clear()

    def test_confirm_without_pending_returns_invalid(self) -> None:
        response = asyncio.run(confirm_action("CONFIRM_RESTART"))
        self.assertEqual(response.get("status"), "invalid_confirmation")

    def test_confirm_expired_returns_expired_status(self) -> None:
        get_manager().request("restart")
        get_manager().expiry = time.monotonic() - 1  # force expiry
        response = asyncio.run(confirm_action("CONFIRM_RESTART"))
        self.assertEqual(response.get("status"), "confirmation_expired")

    def test_confirm_wrong_token_returns_invalid(self) -> None:
        get_manager().request("restart")
        response = asyncio.run(confirm_action("CONFIRM_SHUTDOWN"))
        self.assertEqual(response.get("status"), "invalid_confirmation")


if __name__ == "__main__":
    unittest.main()
