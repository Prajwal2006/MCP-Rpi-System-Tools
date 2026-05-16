"""Structured logging helpers."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

LOGGER_NAMESPACE = "mcp_rpi_system"


class JsonFormatter(logging.Formatter):
    """Log formatter that emits JSON log messages."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["error"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str = "INFO") -> None:
    """Configure process-wide structured logging."""

    logger = logging.getLogger(LOGGER_NAMESPACE)
    logger.setLevel(level)
    logger.propagate = False

    if logger.handlers:
        return

    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """Get a named logger instance."""

    return logging.getLogger(f"{LOGGER_NAMESPACE}.{name}")
