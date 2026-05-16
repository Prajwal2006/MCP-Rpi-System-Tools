"""Confirmation manager for dangerous system actions.

Maintains a single in-process pending-action slot with a 30-second TTL.
Only one action can be pending at a time.  Calling ``request`` while a
previous action is already pending replaces it (giving the user a fresh
window to confirm the *new* request).

Security model – random confirmation tokens
-------------------------------------------
Every call to :meth:`ConfirmationManager.request` generates a fresh,
cryptographically random token using :func:`secrets.token_hex`.  Tokens
follow the format ``CONFIRM_RESTART_<6 hex chars>`` or
``CONFIRM_SHUTDOWN_<6 hex chars>`` (e.g. ``CONFIRM_RESTART_A8F291``).

Because the token is unpredictable and disclosed only in the response that
is forwarded to the human user, an AI agent cannot pre-compute or re-use it.
The agent MUST wait for the user to echo the token before calling
:func:`~tools.system_tools.confirm_action`.

Security notes:
    * State lives exclusively in this module's singleton; it is never
      persisted to disk and cannot be manipulated through the MCP
      transport layer other than via the public helper functions.
    * Tokens are validated with a strict equality check so that partial
      or prefixed strings are never accepted.
    * Expired confirmations are cleaned up automatically before any
      validation attempt.
    * The expected token is NEVER logged to prevent accidental exposure
      in log aggregation systems.

Usage flow::

    1. Agent calls ``request_action("restart")`` which stores pending
       state and returns a ``confirmation_required`` response to the user,
       e.g. ``"Reply with CONFIRM_RESTART_A8F291 within 30 seconds."``.
    2. User reads the token and types it back to the agent.
    3. Agent calls ``confirm_action("CONFIRM_RESTART_A8F291")`` which
       validates and clears the pending state, returning the resolved
       action name so the caller can execute the command.
"""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass, field
from typing import Any

from utils.logging_utils import get_logger

logger = get_logger(__name__)

#: Prefix strings used when constructing per-request random tokens.
_TOKEN_PREFIXES: dict[str, str] = {
    "restart": "CONFIRM_RESTART",
    "shutdown": "CONFIRM_SHUTDOWN",
}

#: Seconds before a pending confirmation expires automatically.
TTL_SECONDS: float = 30.0


def _generate_token(action: str) -> str:
    """Return a cryptographically random confirmation token for *action*.

    Args:
        action: One of ``"restart"`` or ``"shutdown"``.

    Returns:
        A token string such as ``"CONFIRM_RESTART_A8F291"``.  The 6-character
        hex suffix is produced by :func:`secrets.token_hex` and is unique to
        each call.
    """
    suffix = secrets.token_hex(3).upper()  # 3 bytes → 6 uppercase hex chars
    return f"{_TOKEN_PREFIXES[action]}_{suffix}"


@dataclass
class ConfirmationManager:
    """Single-slot store for a pending dangerous-action confirmation.

    Only one action may be pending at a time.  Requesting a new action while
    one is already pending replaces the old one and issues a warning in the
    response.

    Attributes:
        pending_action: The name of the pending action (``"restart"`` or
            ``"shutdown"``), or ``None`` when no action is pending.
        expiry: Monotonic timestamp after which the pending action is
            considered expired, or ``None`` when no action is pending.
        _token: The random confirmation token that must be supplied by the
            user to authorise execution.  Never logged.
    """

    pending_action: str | None = field(default=None, init=False)
    expiry: float | None = field(default=None, init=False)
    _token: str | None = field(default=None, init=False)

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def request(self, action: str) -> dict[str, Any]:
        """Record ``action`` as pending and return a confirmation_required response.

        Purpose:
            Generates a fresh random confirmation token, stores the requested
            action with a monotonic expiry timestamp, and returns the token in
            the response message so the user can echo it back.

        Security notes:
            * The token is generated with :func:`secrets.token_hex` and is
              therefore unpredictable.  An AI agent cannot determine it
              without seeing the response that is shown to the human user.
            * If another action was already pending it is replaced and the
              response includes a ``"warning"`` key.

        Args:
            action: One of ``"restart"`` or ``"shutdown"``.

        Returns:
            A JSON-compatible dict with ``status="confirmation_required"``
            and a human-readable message containing the one-time token.
            If a previous action was replaced, the dict also contains
            ``"warning": "A previous pending action was cancelled by this
            request."``.
        """
        replaced = self.pending_action is not None
        token = _generate_token(action)
        self._token = token
        self.pending_action = action
        self.expiry = time.monotonic() + TTL_SECONDS
        logger.info(
            "Dangerous action requested",
            extra={"action": action, "ttl_seconds": TTL_SECONDS, "replaced": replaced},
        )
        result: dict[str, Any] = {
            "status": "confirmation_required",
            "message": (
                f"Reply with {token} within {int(TTL_SECONDS)} seconds to confirm."
            ),
        }
        if replaced:
            result["warning"] = "A previous pending action was cancelled by this request."
        return result

    def confirm(self, token: str) -> tuple[str | None, bool]:
        """Attempt to validate *token* against the current pending action.

        Purpose:
            Checks whether *token* exactly matches the one-time confirmation
            string stored for the pending action, honouring the TTL.

        Security notes:
            * Comparison is exact (``==``); no fuzzy or prefix matching.
            * Expired state is cleared before any further validation so that
              stale tokens can never succeed.
            * The expected token is intentionally not included in log output
              to avoid exposure in log aggregation systems.

        Args:
            token: The confirmation string supplied by the user, e.g.
                ``"CONFIRM_RESTART_A8F291"``.

        Returns:
            ``(action, expired)`` where:

            * ``action`` is the resolved action name (``"restart"`` /
              ``"shutdown"``) when confirmation succeeds, otherwise ``None``.
            * ``expired`` is ``True`` when there *was* a pending action but it
              expired before the token arrived.
        """
        if self.pending_action is None:
            logger.warning("Confirmation attempt with no pending action")
            return None, False

        if time.monotonic() > (self.expiry or 0.0):
            logger.warning(
                "Confirmation expired",
                extra={"action": self.pending_action},
            )
            self._clear()
            return None, True

        if token != self._token:
            logger.warning(
                "Invalid confirmation token received",
                extra={"action": self.pending_action},
            )
            return None, False

        action = self.pending_action
        logger.info("Confirmation accepted", extra={"action": action})
        self._clear()
        return action, False

    def cancel(self) -> dict[str, Any]:
        """Discard any pending action and return a cancellation response.

        Purpose:
            Allows the user to explicitly abort a pending dangerous action
            before the TTL elapses.  Safe to call even when nothing is pending.

        Returns:
            A JSON-compatible dict with ``status="cancelled"`` when an action
            was pending, or ``status="no_pending_action"`` otherwise.
        """
        action = self.pending_action
        self._clear()
        if action is not None:
            logger.info("Pending action cancelled", extra={"action": action})
            return {
                "status": "cancelled",
                "ok": True,
                "message": f"Pending {action} cancelled.",
            }
        logger.info("Cancel called with no pending action")
        return {
            "status": "no_pending_action",
            "ok": True,
            "message": "No pending action to cancel.",
        }

    def clear(self) -> None:
        """Discard any pending action unconditionally.

        Useful for explicit cleanup; safe to call even when nothing is pending.
        Unlike :meth:`cancel`, this method does not return a structured response
        and is intended for internal teardown (e.g. in tests).
        """
        self._clear()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _clear(self) -> None:
        """Reset all pending-action state to ``None``."""
        self.pending_action = None
        self.expiry = None
        self._token = None


# Module-level singleton shared across all tool invocations in the process.
_manager = ConfirmationManager()


def get_manager() -> ConfirmationManager:
    """Return the process-wide :class:`ConfirmationManager` singleton."""
    return _manager
