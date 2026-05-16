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
from tools.system_tools import cancel_action, confirm_action, get_uptime, request_restart, request_shutdown


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
        # Token is random but must carry the correct action prefix.
        self.assertIn("CONFIRM_RESTART_", result["message"])

    def test_request_generates_unique_tokens(self) -> None:
        """Each request must produce a different token."""
        import re
        r1 = self.mgr.request("restart")
        r2 = self.mgr.request("restart")
        # Extract tokens from messages using a pattern-based search so the
        # test is not coupled to the exact whitespace layout of the message.
        token1 = re.search(r"CONFIRM_\w+_[A-F0-9]{6}", r1["message"]).group(0)
        token2 = re.search(r"CONFIRM_\w+_[A-F0-9]{6}", r2["message"]).group(0)
        self.assertNotEqual(token1, token2)

    def test_token_stored_on_request(self) -> None:
        self.mgr.request("shutdown")
        self.assertIsNotNone(self.mgr._token)
        self.assertTrue(self.mgr._token.startswith("CONFIRM_SHUTDOWN_"))

    def test_confirm_valid_token(self) -> None:
        self.mgr.request("restart")
        token = self.mgr._token
        action, expired = self.mgr.confirm(token)
        self.assertEqual(action, "restart")
        self.assertFalse(expired)

    def test_confirm_wrong_token_returns_none(self) -> None:
        self.mgr.request("restart")
        action, expired = self.mgr.confirm("CONFIRM_RESTART_WRONG1")
        self.assertIsNone(action)
        self.assertFalse(expired)

    def test_confirm_with_no_pending_returns_none(self) -> None:
        action, expired = self.mgr.confirm("CONFIRM_RESTART_NOPEND")
        self.assertIsNone(action)
        self.assertFalse(expired)

    def test_confirm_expired_action(self) -> None:
        self.mgr.request("shutdown")
        token = self.mgr._token
        # Wind the expiry back so the action appears expired.
        self.mgr.expiry = time.monotonic() - 1
        action, expired = self.mgr.confirm(token)
        self.assertIsNone(action)
        self.assertTrue(expired)
        # Pending state must be cleared after expiry.
        self.assertIsNone(self.mgr.pending_action)
        self.assertIsNone(self.mgr._token)

    def test_second_request_replaces_first(self) -> None:
        self.mgr.request("restart")
        result = self.mgr.request("shutdown")
        self.assertEqual(self.mgr.pending_action, "shutdown")
        self.assertIn("warning", result)

    def test_clear_removes_pending(self) -> None:
        self.mgr.request("restart")
        self.mgr.clear()
        self.assertIsNone(self.mgr.pending_action)
        self.assertIsNone(self.mgr.expiry)
        self.assertIsNone(self.mgr._token)

    def test_cancel_with_pending_action(self) -> None:
        self.mgr.request("restart")
        result = self.mgr.cancel()
        self.assertEqual(result["status"], "cancelled")
        self.assertTrue(result["ok"])
        self.assertIsNone(self.mgr.pending_action)
        self.assertIsNone(self.mgr._token)

    def test_cancel_with_no_pending_action(self) -> None:
        result = self.mgr.cancel()
        self.assertEqual(result["status"], "no_pending_action")
        self.assertTrue(result["ok"])


class PowerToolPolicyTests(unittest.TestCase):
    """Ensure power tools respect the ALLOW_POWER_ACTIONS policy flag."""

    def test_request_restart_disabled_by_policy(self) -> None:
        with patch("tools.system_tools.ALLOW_POWER_ACTIONS", False):
            response = request_restart()
        self.assertEqual(response.get("status"), "error")
        self.assertEqual(response.get("error"), "disabled_by_policy")

    def test_request_shutdown_disabled_by_policy(self) -> None:
        with patch("tools.system_tools.ALLOW_POWER_ACTIONS", False):
            response = request_shutdown()
        self.assertEqual(response.get("status"), "error")
        self.assertEqual(response.get("error"), "disabled_by_policy")

    def test_request_restart_requires_confirmation(self) -> None:
        """When power actions are allowed, request_restart enters the flow."""
        with patch("tools.system_tools.ALLOW_POWER_ACTIONS", True):
            # Reset the global manager so prior test state doesn't leak.
            get_manager().clear()
            response = request_restart()
        self.assertEqual(response.get("status"), "confirmation_required")
        # Token is random; verify the correct prefix is present.
        self.assertIn("CONFIRM_RESTART_", response.get("message", ""))
        get_manager().clear()

    def test_request_shutdown_requires_confirmation(self) -> None:
        """When power actions are allowed, request_shutdown enters the flow."""
        with patch("tools.system_tools.ALLOW_POWER_ACTIONS", True):
            get_manager().clear()
            response = request_shutdown()
        self.assertEqual(response.get("status"), "confirmation_required")
        self.assertIn("CONFIRM_SHUTDOWN_", response.get("message", ""))
        get_manager().clear()


class ConfirmActionToolTests(unittest.TestCase):
    """Tests for the confirm_action async tool function."""

    def setUp(self) -> None:
        get_manager().clear()

    def tearDown(self) -> None:
        get_manager().clear()

    def test_confirm_without_pending_returns_invalid(self) -> None:
        response = asyncio.run(confirm_action("CONFIRM_RESTART_NOPEND"))
        self.assertEqual(response.get("status"), "invalid_confirmation")

    def test_confirm_expired_returns_expired_status(self) -> None:
        get_manager().request("restart")
        token = get_manager()._token
        get_manager().expiry = time.monotonic() - 1  # force expiry
        response = asyncio.run(confirm_action(token))
        self.assertEqual(response.get("status"), "confirmation_expired")

    def test_confirm_wrong_token_returns_invalid(self) -> None:
        get_manager().request("restart")
        response = asyncio.run(confirm_action("CONFIRM_RESTART_WRONG1"))
        self.assertEqual(response.get("status"), "invalid_confirmation")


class CancelActionTests(unittest.TestCase):
    """Tests for the cancel_action tool function."""

    def setUp(self) -> None:
        get_manager().clear()

    def tearDown(self) -> None:
        get_manager().clear()

    def test_cancel_with_pending_action(self) -> None:
        with patch("tools.system_tools.ALLOW_POWER_ACTIONS", True):
            request_restart()
        response = cancel_action()
        self.assertEqual(response.get("status"), "cancelled")
        self.assertTrue(response.get("ok"))
        self.assertIsNone(get_manager().pending_action)

    def test_cancel_with_no_pending_action(self) -> None:
        response = cancel_action()
        self.assertEqual(response.get("status"), "no_pending_action")
        self.assertTrue(response.get("ok"))

    def test_confirm_after_cancel_returns_invalid(self) -> None:
        """After cancellation, any token must be rejected."""
        with patch("tools.system_tools.ALLOW_POWER_ACTIONS", True):
            request_restart()
        # Extract the token that was issued.
        token = get_manager()._token
        cancel_action()
        response = asyncio.run(confirm_action(token))
        self.assertEqual(response.get("status"), "invalid_confirmation")


if __name__ == "__main__":
    unittest.main()
