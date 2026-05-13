from __future__ import annotations

import ipaddress
import os
import socket
from urllib.parse import urlparse


class ProductionSafetyError(RuntimeError):
    """Raised when a production-only side effect is attempted outside production."""


def is_production() -> bool:
    return os.getenv("STORMLEAD_ENV", "").strip().lower() == "production"


def assert_production_safe(action: str) -> None:
    if not is_production():
        raise ProductionSafetyError(f"{action} requires STORMLEAD_ENV=production")


def is_local_webhook_url(value: str) -> bool:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    hostname = parsed.hostname.lower()
    if hostname in {"localhost", "host.docker.internal"} or hostname.endswith(".localhost"):
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


def hostname_resolves_to_global_addresses(hostname: str) -> bool:
    try:
        return ipaddress.ip_address(hostname).is_global
    except ValueError:
        pass

    try:
        resolved = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except OSError:
        return False

    addresses = {sockaddr[0] for *_, sockaddr in resolved if sockaddr}
    if not addresses:
        return False
    try:
        return all(ipaddress.ip_address(address).is_global for address in addresses)
    except ValueError:
        return False


def is_approved_external_webhook_url(value: str, approved_hosts: set[str]) -> bool:
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.hostname:
        return False
    hostname = parsed.hostname.lower()
    if hostname not in approved_hosts:
        return False
    return hostname_resolves_to_global_addresses(hostname)
