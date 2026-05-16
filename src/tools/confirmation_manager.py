"""Confirmation manager for dangerous system actions.

Maintains a single in-process pending-action slot with a 30-second TTL.
Only one action can be pending at a time.  Calling ``request`` while a
previous action is already pending replaces it (giving the user a fresh
window to confirm the *new* request).

Confirmation tokens:
    ``CONFIRM_RESTART``  – authorises a system restart
    ``CONFIRM_SHUTDOWN`` – authorises a system shutdown

Security notes:
    * State lives exclusively in this module's singleton; it is never
      persisted to disk and cannot be manipulated through the MCP
      transport layer other than via the public helper functions.
    * Tokens are validated with a strict equality check so that partial
      or prefixed strings are never accepted.
    * Expired confirmations are cleaned up automatically before any
      validation attempt.

Usage flow::

    1. Agent calls ``request_action("restart")`` which stores pending
       state and returns a ``confirmation_required`` response to the user.
    2. User replies with ``CONFIRM_RESTART`` within 30 seconds.
    3. Agent calls ``confirm_action("CONFIRM_RESTART")`` which validates
       and clears the pending state, returning the resolved action name
       so the caller can execute the command.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from utils.logging_utils import get_logger

logger = get_logger(__name__)

#: Mapping from action name to the exact confirmation token the user must supply.
CONFIRMATION_TOKENS: dict[str, str] = {
    "restart": "CONFIRM_RESTART",
    "shutdown": "CONFIRM_SHUTDOWN",
}

#: Seconds before a pending confirmation expires automatically.
TTL_SECONDS: float = 30.0


@dataclass
class ConfirmationManager:
    """Single-slot store for a pending dangerous-action confirmation.

    Only one action may be pending at a time.  Requesting a new action while
    one is already pending replaces the old one.
    """

    pending_action: str | None = field(default=None, init=False)
    expiry: float | None = field(default=None, init=False)

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def request(self, action: str) -> dict[str, Any]:
        """Record ``action`` as pending and return a confirmation_required response.

        Purpose:
            Stores the requested action and a monotonic expiry timestamp so
            that :meth:`confirm` can validate it later.

        Security notes:
            Only action names present in :data:`CONFIRMATION_TOKENS` are
            accepted; callers must validate before calling this method.

        Args:
            action: One of ``"restart"`` or ``"shutdown"``.

        Returns:
            A JSON-compatible dict with ``status="confirmation_required"``
            and a human-readable message containing the expected token.
        """
        token = CONFIRMATION_TOKENS[action]
        self.pending_action = action
        self.expiry = time.monotonic() + TTL_SECONDS
        logger.info(
            "Dangerous action requested",
            extra={"action": action, "ttl_seconds": TTL_SECONDS},
        )
        return {
            "status": "confirmation_required",
            "message": f"Reply with {token} within 30 seconds to confirm.",
        }

    def confirm(self, token: str) -> tuple[str | None, bool]:
        """Attempt to validate *token* against the current pending action.

        Purpose:
            Checks whether *token* exactly matches the expected confirmation
            string for the pending action, honouring the TTL.

        Security notes:
            * Comparison is exact (``==``); no fuzzy or prefix matching.
            * Expired state is cleared before any further validation so that
              stale tokens can never succeed.

        Args:
            token: The confirmation string supplied by the user, e.g.
                ``"CONFIRM_RESTART"``.

        Returns:
            ``(action, expired)`` where:

            * ``action`` is the resolved action name (``"restart"`` /
              ``"shutdown"``) when confirmation succeeds, otherwise ``None``.
            * ``expired`` is ``True`` when there *was* a pending action but it
              expired before the token arrived.
        """
        if self.pending_action is None:
            logger.warning("Confirmation attempt with no pending action", extra={"token": token})
            return None, False

        if time.monotonic() > (self.expiry or 0.0):
            logger.warning(
                "Confirmation expired",
                extra={"action": self.pending_action, "token": token},
            )
            self._clear()
            return None, True

        expected = CONFIRMATION_TOKENS[self.pending_action]
        if token != expected:
            logger.warning(
                "Invalid confirmation token",
                extra={"expected": expected, "received": token},
            )
            return None, False

        action = self.pending_action
        logger.info("Confirmation accepted", extra={"action": action})
        self._clear()
        return action, False

    def clear(self) -> None:
        """Discard any pending action unconditionally.

        Useful for explicit cleanup; safe to call even when nothing is pending.
        """
        self._clear()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _clear(self) -> None:
        self.pending_action = None
        self.expiry = None


# Module-level singleton shared across all tool invocations in the process.
_manager = ConfirmationManager()


def get_manager() -> ConfirmationManager:
    """Return the process-wide :class:`ConfirmationManager` singleton."""
    return _manager
