from __future__ import annotations

import asyncio
import socket
import ssl
from datetime import datetime, timezone
from typing import Protocol

from app.tools.network.errors import LookupFailedError, LookupTimeoutError, NotFoundError
from app.tools.network.models import TlsResult

_CERT_DATE_FMT = "%b %d %H:%M:%S %Y %Z"


class TlsProvider(Protocol):
    async def fetch(self, host: str, port: int = 443) -> TlsResult: ...


class SocketTlsProvider:
    """Fetches the leaf TLS certificate of a host via a plain TLS handshake."""

    def __init__(self, timeout: float = 6.0) -> None:
        self._timeout = timeout

    async def fetch(self, host: str, port: int = 443) -> TlsResult:
        try:
            return await asyncio.to_thread(self._fetch_sync, host, port)
        except socket.timeout as exc:
            raise LookupTimeoutError("Сервер не ответил вовремя") from exc
        except (ssl.SSLError, OSError) as exc:
            raise LookupFailedError(f"Не удалось получить сертификат: {exc}") from exc

    def _fetch_sync(self, host: str, port: int) -> TlsResult:
        context = ssl.create_default_context()
        with socket.create_connection((host, port), timeout=self._timeout) as sock:
            with context.wrap_socket(sock, server_hostname=host) as tls_sock:
                cert = tls_sock.getpeercert()
        if not cert:
            raise NotFoundError("Сертификат не получен")

        issuer = _dn(cert.get("issuer"))
        subject = _dn(cert.get("subject"))
        san = tuple(
            value for kind, value in cert.get("subjectAltName", ()) if kind == "DNS"
        )
        valid_from = cert.get("notBefore")
        valid_until = cert.get("notAfter")
        days_left = _days_left(valid_until)

        return TlsResult(
            host=host,
            port=port,
            issuer=issuer,
            subject=subject,
            valid_from=valid_from,
            valid_until=valid_until,
            san=san,
            days_left=days_left,
        )


def _dn(parts: object) -> str | None:
    if not parts:
        return None
    flat: list[str] = []
    for group in parts:  # type: ignore[union-attr]
        for key, value in group:
            flat.append(f"{key}={value}")
    return ", ".join(flat) or None


def _days_left(not_after: str | None) -> int | None:
    if not not_after:
        return None
    try:
        expires = datetime.strptime(not_after, _CERT_DATE_FMT).replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return (expires - datetime.now(timezone.utc)).days
