"""Network-related MCP tool functions."""

from __future__ import annotations

import socket
from typing import Any

import psutil

from utils.logging_utils import get_logger

logger = get_logger(__name__)


def get_network_usage() -> dict[str, Any]:
    """Return aggregate network transfer counters for the host."""

    try:
        counters = psutil.net_io_counters()
        return {
            "ok": True,
            "bytes_sent": int(counters.bytes_sent),
            "bytes_recv": int(counters.bytes_recv),
            "packets_sent": int(counters.packets_sent),
            "packets_recv": int(counters.packets_recv),
            "errors_in": int(counters.errin),
            "errors_out": int(counters.errout),
            "drops_in": int(counters.dropin),
            "drops_out": int(counters.dropout),
        }
    except Exception:
        logger.exception("Failed to fetch network usage")
        return {"ok": False, "error": "network_usage_unavailable"}


def get_ip_addresses() -> dict[str, Any]:
    """Return detected IPv4/IPv6 addresses grouped by network interface."""

    try:
        result: dict[str, Any] = {}
        for iface, addrs in psutil.net_if_addrs().items():
            iface_addresses = []
            for addr in addrs:
                if addr.family in (socket.AF_INET, socket.AF_INET6):
                    iface_addresses.append(
                        {
                            "family": "IPv4" if addr.family == socket.AF_INET else "IPv6",
                            "address": addr.address,
                            "netmask": addr.netmask,
                            "broadcast": addr.broadcast,
                        }
                    )
            if iface_addresses:
                result[iface] = iface_addresses

        return {"ok": True, "interfaces": result}
    except Exception:
        logger.exception("Failed to fetch IP addresses")
        return {"ok": False, "error": "ip_addresses_unavailable"}
