from __future__ import annotations

from typing import Any

from app.tools.base import BaseTool, ToolResult, ToolResultKind
from app.tools.vpn.errors import VpnToolError
from app.tools.vpn.manifest import VPN_MANIFEST
from app.tools.vpn.service import VpnService


class VpnTool(BaseTool):
    manifest = VPN_MANIFEST

    def __init__(self, service: VpnService) -> None:
        self._service = service

    async def execute(self, *, action: str, **kwargs: Any) -> ToolResult:
        try:
            if action == "create_user":
                data = await self._service.create_user(**kwargs)
            elif action == "extend_user":
                data = await self._service.extend_user(**kwargs)
            elif action == "weekly_report":
                data = await self._service.weekly_report(**kwargs)
            else:
                return ToolResult(
                    kind=ToolResultKind.FAILED,
                    error=f"Неизвестное VPN-действие: {action}",
                )
        except VpnToolError as exc:
            return ToolResult(kind=ToolResultKind.FAILED, error=str(exc))
        return ToolResult(kind=ToolResultKind.IMMEDIATE, data=data)
