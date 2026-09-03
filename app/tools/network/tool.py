from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from app.tools.base import BaseTool, ToolResult, ToolResultKind
from app.tools.network.errors import NetworkToolError
from app.tools.network.manifest import NETWORK_MANIFEST
from app.tools.network.models import LookupKind
from app.tools.network.service import NetworkService


class NetworkTool(BaseTool):
    manifest = NETWORK_MANIFEST

    def __init__(self, service: NetworkService) -> None:
        self._service = service
        self._dispatch: dict[LookupKind, Callable[[str], Awaitable[Any]]] = {
            LookupKind.WHOIS: service.whois_domain,
            LookupKind.GEO: service.geolocate,
            LookupKind.DNS: service.dns_lookup,
            LookupKind.LIR: service.ip_owner,
            LookupKind.RDNS: service.reverse_dns,
            LookupKind.TLS: service.tls_cert,
        }

    async def execute(self, *, kind: str, target: str, **_: Any) -> ToolResult:
        try:
            lookup_kind = LookupKind(kind)
        except ValueError:
            return ToolResult(kind=ToolResultKind.FAILED, error=f"Неизвестный тип запроса: {kind}")

        handler = self._dispatch[lookup_kind]
        try:
            data = await handler(target)
        except NetworkToolError as exc:
            return ToolResult(kind=ToolResultKind.FAILED, error=str(exc))
        return ToolResult(kind=ToolResultKind.IMMEDIATE, data=data)
