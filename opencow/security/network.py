"""Network security — SSRF protection for web_fetch."""

import asyncio
import ipaddress
import socket
from contextlib import suppress
from urllib.parse import urlparse

_BLOCKED_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


async def validate_url_target(url: str) -> tuple[bool, str]:
    """Validate a URL is safe to fetch (blocks internal/private IPs)."""
    try:
        p = urlparse(url)
    except Exception as e:
        return False, str(e)

    if p.scheme not in ("http", "https"):
        return False, f"Only http/https allowed, got '{p.scheme or 'none'}'"
    if not p.hostname:
        return False, "Missing hostname"

    # Resolve DNS asynchronously to avoid blocking the event loop
    try:
        addrs = await asyncio.to_thread(
            socket.getaddrinfo, p.hostname, None, 0, socket.SOCK_STREAM
        )
    except socket.gaierror as e:
        return False, f"DNS resolution failed: {e}"

    for addr in addrs:
        ip_str = addr[4][0]
        with suppress(ValueError):
            ip = ipaddress.ip_address(ip_str)
            if any(ip in net for net in _BLOCKED_NETWORKS):
                return False, f"Blocked internal IP: {ip_str}"
    return True, ""
