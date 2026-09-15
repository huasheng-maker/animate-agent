"""Fail-closed URL and browser-request policy for untrusted web inputs."""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import cast
from urllib.parse import urlsplit, urlunsplit

from animate_agent.ingestion.exceptions import BlockedAddress, InvalidURL, UnsupportedScheme

Resolver = Callable[[str, int], Awaitable[Sequence[str]]]

_BLOCKED_HOST_SUFFIXES = (".localhost", ".local", ".internal", ".home", ".lan")
_BLOCKED_HOSTS = {"localhost", "localhost.localdomain", "metadata.google.internal"}
_BLOCKED_IPS = {
    ipaddress.ip_address("169.254.169.254"),
    ipaddress.ip_address("100.100.100.200"),
}


@dataclass(frozen=True)
class ValidatedURL:
    url: str
    hostname: str
    addresses: tuple[str, ...]


async def system_resolver(hostname: str, port: int) -> Sequence[str]:
    def resolve() -> list[str]:
        return list(
            {
                cast(str, item[4][0])
                for item in socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
            }
        )

    return await asyncio.to_thread(resolve)


class URLSecurityPolicy:
    """Validate syntax, DNS results, domains, and every browser network request."""

    def __init__(
        self, *, allowed_domains: frozenset[str] = frozenset(), resolver: Resolver = system_resolver
    ) -> None:
        self._allowed_domains = allowed_domains
        self._resolver = resolver

    async def validate(self, raw_url: str, *, enforce_allowed_domains: bool = True) -> ValidatedURL:
        try:
            parsed = urlsplit(raw_url)
            port = parsed.port
        except ValueError as exc:
            raise InvalidURL("The URL is malformed.", detail=str(exc)) from exc
        scheme = parsed.scheme.lower()
        if scheme not in {"http", "https"}:
            raise UnsupportedScheme("Only http:// and https:// URLs are supported.")
        if not parsed.hostname or parsed.username is not None or parsed.password is not None:
            raise InvalidURL("The URL must contain a valid host and must not include credentials.")
        hostname = parsed.hostname.lower().rstrip(".")
        if hostname in _BLOCKED_HOSTS or hostname.endswith(_BLOCKED_HOST_SUFFIXES):
            raise BlockedAddress("The URL resolves to an internal network name and is blocked.")
        if (
            enforce_allowed_domains
            and self._allowed_domains
            and not any(
                hostname == domain or hostname.endswith(f".{domain}")
                for domain in self._allowed_domains
            )
        ):
            raise BlockedAddress("The URL host is not in the configured allowed domains.")
        effective_port = port or (443 if scheme == "https" else 80)
        try:
            literal = ipaddress.ip_address(hostname.strip("[]"))
            addresses: tuple[str, ...] = (str(literal),)
        except ValueError:
            try:
                addresses = tuple(await self._resolver(hostname, effective_port))
            except OSError as exc:
                raise InvalidURL("The URL host could not be resolved.", detail=str(exc)) from exc
        if not addresses:
            raise InvalidURL("The URL host could not be resolved.")
        for address in addresses:
            try:
                ip = ipaddress.ip_address(address)
            except ValueError as exc:
                raise BlockedAddress(
                    "The URL resolved to an invalid address.", detail=address
                ) from exc
            if ip in _BLOCKED_IPS or not ip.is_global:
                raise BlockedAddress(
                    "The URL resolves to a private or reserved network address and is blocked."
                )
        netloc = hostname
        if ":" in hostname:
            netloc = f"[{hostname}]"
        if port is not None:
            netloc = f"{netloc}:{port}"
        normalized = urlunsplit((scheme, netloc, parsed.path or "/", parsed.query, ""))
        return ValidatedURL(normalized, hostname, addresses)

    async def permits_browser_request(self, url: str, *, is_navigation: bool) -> bool:
        """Allow inert browser-local resources; validate every network request."""

        scheme = urlsplit(url).scheme.lower()
        if scheme in {"about", "blob", "data"}:
            return True
        try:
            await self.validate(url, enforce_allowed_domains=is_navigation)
        except (InvalidURL, UnsupportedScheme, BlockedAddress):
            return False
        return True
