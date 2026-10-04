"""Blocks outbound URL fetches (SourceService, link preview, etc.) from
reaching private, link-local, or cloud-metadata address ranges.
"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse


class SSRFBlockedError(Exception):
    pass


_BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),  # link-local + cloud metadata (169.254.169.254)
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


def assert_url_is_safe(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise SSRFBlockedError(f"Unsupported URL scheme: {parsed.scheme}")
    if not parsed.hostname:
        raise SSRFBlockedError("URL has no hostname")

    try:
        addr_infos = socket.getaddrinfo(parsed.hostname, None)
    except socket.gaierror as exc:
        raise SSRFBlockedError(f"Could not resolve hostname: {parsed.hostname}") from exc

    for family, _, _, _, sockaddr in addr_infos:
        ip = ipaddress.ip_address(sockaddr[0])
        for network in _BLOCKED_NETWORKS:
            if ip in network:
                raise SSRFBlockedError(f"URL resolves to a blocked address range: {ip}")
