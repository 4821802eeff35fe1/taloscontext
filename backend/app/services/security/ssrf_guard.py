"""Blocks outbound URL fetches (SourceService, link preview, etc.) from
reaching private, link-local, or cloud-metadata address ranges.
"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse


class SSRFBlockedError(Exception):
    pass


def resolve_public_addresses(url: str) -> list[str]:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise SSRFBlockedError(f"Unsupported URL scheme: {parsed.scheme}")
    if parsed.username or parsed.password:
        raise SSRFBlockedError("Credentials in source URLs are not allowed")
    if not parsed.hostname:
        raise SSRFBlockedError("URL has no hostname")

    try:
        addr_infos = socket.getaddrinfo(parsed.hostname, None)
    except socket.gaierror as exc:
        raise SSRFBlockedError(f"Could not resolve hostname: {parsed.hostname}") from exc

    addresses = []
    for _, _, _, _, sockaddr in addr_infos:
        ip = ipaddress.ip_address(sockaddr[0])
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
            ip = ip.ipv4_mapped
        if not ip.is_global or ip.is_multicast:
            raise SSRFBlockedError(f"URL resolves to a non-public address: {ip}")
        addresses.append(str(ip))
    if not addresses:
        raise SSRFBlockedError("Hostname has no public addresses")
    return list(dict.fromkeys(addresses))


def assert_url_is_safe(url: str) -> None:
    resolve_public_addresses(url)
