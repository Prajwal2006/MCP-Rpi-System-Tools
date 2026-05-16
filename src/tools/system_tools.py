"""System control and uptime MCP tool functions.

Power-action security model
----------------------------
Dangerous actions (restart / shutdown) follow a two-step confirmation flow
to prevent accidental or malicious execution:

1. The agent calls ``request_restart()`` or ``request_shutdown()``.
   The server generates a cryptographically random one-time token and
   stores a pending action, returning the token in the response so the
   human user can read it (e.g. ``CONFIRM_RESTART_A8F291``).
2. Within 30 seconds the user types the token back to the agent.
3. The agent calls ``confirm_action(action="CONFIRM_RESTART_A8F291")``.
   If the token is valid and unexpired the server executes the command.

Because the token is random and unknown before ``request_restart()`` or
``request_shutdown()`` is called, an AI agent cannot pre-compute it and
self-confirm in the same reasoning turn.

Security notes:
    * ONLY ``sudo reboot`` and ``sudo shutdown now`` are ever executed.
    * No arbitrary shell commands are exposed or accepted.
    * Confirmation tokens are generated with :func:`secrets.token_hex` and
      validated with an exact string comparison.
    * A pending action expires automatically after 30 seconds.
    * Power actions are also gated behind the ``ALLOW_POWER_ACTIONS`` setting
      in ``config/settings.py`` (default: ``True``).
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import psutil

from config.settings import ALLOW_POWER_ACTIONS
from tools.confirmation_manager import get_manager
from utils.logging_utils import get_logger

logger = get_logger(__name__)

# Whitelisted commands – the ONLY subprocess calls this module will ever make.
_ALLOWED_POWER_COMMANDS: dict[str, tuple[str, ...]] = {
    "restart": ("sudo", "reboot"),
    "shutdown": ("sudo", "shutdown", "now"),
}


async def _run_power_command(action: str) -> dict[str, Any]:
    """Execute a whitelisted power command with subprocess safety controls.

    Purpose:
        Internal helper that maps a validated action name to its fixed
        command tuple and runs it via ``asyncio.create_subprocess_exec``.
        Shell interpolation is intentionally impossible because the command
        is passed as a sequence, not a string.

    Security notes:
        * Only ``"restart"`` and ``"shutdown"`` are accepted; any other value
          raises ``KeyError`` before a process is ever spawned.
        * ``shell=False`` is the default for ``create_subprocess_exec``.
        * A 10-second timeout guards against hung system calls.

    Args:
        action: Validated action key – must be present in
            :data:`_ALLOWED_POWER_COMMANDS`.

    Returns:
        A JSON-compatible dict describing the outcome.
    """
    command = _ALLOWED_POWER_COMMANDS[action]
    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=10)
        success = process.returncode == 0
        if success:
            logger.info("Power command executed successfully", extra={"action": action})
        else:
            logger.error(
                "Power command returned non-zero exit code",
                extra={
                    "action": action,
                    "returncode": process.returncode,
                    "stderr": stderr.decode().strip(),
                },
            )
        return {
            "ok": success,
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


def _policy_denied_response(action: str) -> dict[str, Any]:
    """Return a standardised policy-denial response."""
    return {
        "status": "error",
        "ok": False,
        "action": action,
        "error": "disabled_by_policy",
        "message": "Power actions are disabled. Set ALLOW_POWER_ACTIONS = True in config/settings.py to enable.",
    }


def request_restart() -> dict[str, Any]:
    """Request a Raspberry Pi restart, requiring explicit user confirmation.

    Purpose:
        Initiates the two-step confirmation flow for a system restart.
        Generates a cryptographically random one-time token (e.g.
        ``CONFIRM_RESTART_A8F291``) that the user must supply to
        :func:`confirm_action` within 30 seconds.

    Security notes:
        * This function never executes any command; it only generates a
          random token and stores pending state.
        * The token is unpredictable, so an AI agent cannot self-confirm
          in the same reasoning turn.
        * Guarded by ``ALLOW_POWER_ACTIONS`` in ``config/settings.py``.

    Usage flow::

        Agent calls request_restart()
        → {"status": "confirmation_required",
           "message": "Reply with CONFIRM_RESTART_A8F291 within 30 seconds to confirm."}

        User reads the token and types it back to the agent.

        Agent calls confirm_action(action="CONFIRM_RESTART_A8F291")
        → {"status": "restarting", ...}

    Returns:
        A JSON-compatible dict with ``status="confirmation_required"`` or a
        policy-denial dict.
    """
    if not ALLOW_POWER_ACTIONS:
        return _policy_denied_response("restart")
    logger.info("Restart requested – awaiting confirmation")
    return get_manager().request("restart")


def request_shutdown() -> dict[str, Any]:
    """Request a Raspberry Pi shutdown, requiring explicit user confirmation.

    Purpose:
        Initiates the two-step confirmation flow for a system shutdown.
        Generates a cryptographically random one-time token (e.g.
        ``CONFIRM_SHUTDOWN_B72C1D``) that the user must supply to
        :func:`confirm_action` within 30 seconds.

    Security notes:
        * This function never executes any command; it only generates a
          random token and stores pending state.
        * The token is unpredictable, so an AI agent cannot self-confirm
          in the same reasoning turn.
        * Guarded by ``ALLOW_POWER_ACTIONS`` in ``config/settings.py``.

    Usage flow::

        Agent calls request_shutdown()
        → {"status": "confirmation_required",
           "message": "Reply with CONFIRM_SHUTDOWN_B72C1D within 30 seconds to confirm."}

        User reads the token and types it back to the agent.

        Agent calls confirm_action(action="CONFIRM_SHUTDOWN_B72C1D")
        → {"status": "shutting_down", ...}

    Returns:
        A JSON-compatible dict with ``status="confirmation_required"`` or a
        policy-denial dict.
    """
    if not ALLOW_POWER_ACTIONS:
        return _policy_denied_response("shutdown")
    logger.info("Shutdown requested – awaiting confirmation")
    return get_manager().request("shutdown")


async def confirm_action(action: str) -> dict[str, Any]:
    """Confirm a previously requested dangerous action and execute it.

    Purpose:
        Validates the one-time random confirmation token supplied by the user
        and, if valid and unexpired, executes the corresponding whitelisted
        system command.

    Security notes:
        * The ``action`` parameter is the *random confirmation token* returned
          by ``request_restart`` or ``request_shutdown`` (e.g.
          ``"CONFIRM_RESTART_A8F291"``), not an arbitrary shell command.
        * Because tokens are cryptographically random and unknown before the
          corresponding ``request_*`` call, an AI agent cannot self-confirm
          within the same reasoning turn.
        * Only the two whitelisted commands (``sudo reboot``,
          ``sudo shutdown now``) can ever be executed.
        * Expired confirmations are rejected and the pending state is cleared.

    Args:
        action: The one-time confirmation token string typed by the human
            user, e.g. ``"CONFIRM_RESTART_A8F291"`` or
            ``"CONFIRM_SHUTDOWN_B72C1D"``.

    Returns:
        A JSON-compatible dict with one of the following ``status`` values:

        * ``"restarting"`` – restart command dispatched.
        * ``"shutting_down"`` – shutdown command dispatched.
        * ``"confirmation_expired"`` – the 30-second window elapsed.
        * ``"invalid_confirmation"`` – token did not match or nothing was pending.
        * ``"error"`` – command execution failed.
    """
    resolved_action, expired = get_manager().confirm(action)

    if expired:
        logger.warning("Confirmation window expired", extra={"token": action})
        return {"status": "confirmation_expired"}

    if resolved_action is None:
        logger.warning("Invalid or unexpected confirmation token", extra={"token": action})
        return {"status": "invalid_confirmation"}

    status_label = "restarting" if resolved_action == "restart" else "shutting_down"
    logger.info("Executing confirmed power action", extra={"action": resolved_action})
    result = await _run_power_command(resolved_action)
    return {"status": status_label, **result}


def cancel_action() -> dict[str, Any]:
    """Cancel any pending dangerous action (restart or shutdown).

    Purpose:
        Discards the pending confirmation state so that neither the current
        token nor any future token submitted against the old request can
        trigger an action.

    Security notes:
        * Safe to call even when no action is pending.
        * After cancellation, ``confirm_action`` will return
          ``"invalid_confirmation"`` for any token.

    Returns:
        A JSON-compatible dict with ``status="cancelled"`` if an action was
        pending, or ``status="no_pending_action"`` otherwise.
    """
    logger.info("cancel_action called")
    return get_manager().cancel()


def get_uptime() -> dict[str, Any]:
    """Return system uptime details in seconds and human-friendly units.

    Purpose:
        Reads the boot timestamp from psutil and computes elapsed time,
        returning values in seconds, minutes, and hours.

    Returns:
        A JSON-compatible dict with uptime values or an error indicator.
    """
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
