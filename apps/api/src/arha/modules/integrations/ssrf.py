"""SSRF protection for outgoing webhooks (S-11): resolve, then refuse private, loopback, link local,
multicast, reserved and metadata addresses. Redirects are never followed."""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit

from arha.core.errors import AppError

METADATA_HOSTS = {"metadata.google.internal", "metadata", "instance-data"}


def _forbidden(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved
            or ip.is_unspecified or str(ip) in ("169.254.169.254", "100.100.100.200")
            or ip in ipaddress.ip_network("100.64.0.0/10"))


def check_url_shape(url: str) -> tuple[str, int]:
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
        raise AppError("webhook_url_forbidden", 422)
    host = parts.hostname.lower()
    if host in METADATA_HOSTS or host.endswith((".local", ".internal", ".localhost")) or host == "localhost":
        raise AppError("webhook_url_forbidden", 422)
    return host, parts.port or 443


async def resolve_public(url: str) -> list[str]:
    host, port = check_url_shape(url)
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise AppError("webhook_url_forbidden", 422) from exc
    ips = sorted({str(i[4][0]) for i in infos})
    if not ips or any(_forbidden(ipaddress.ip_address(ip)) for ip in ips):
        raise AppError("webhook_url_forbidden", 422)
    return ips
