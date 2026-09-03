from __future__ import annotations

from typing import Any

from app.tools.base import BaseTool, ToolResult, ToolResultKind
from app.tools.developer.manifest import DEVELOPER_MANIFEST
from app.tools.developer.service import DeveloperInputError, DeveloperService


class DeveloperTool(BaseTool):
    manifest = DEVELOPER_MANIFEST

    def __init__(self, service: DeveloperService) -> None:
        self._service = service

    async def execute(self, *, operation: str, value: str = "", **kwargs: Any) -> ToolResult:
        methods = {
            "urlencode": self._service.urlencode,
            "urldecode": self._service.urldecode,
            "length": self._service.text_length,
            "getcolor": self._service.color,
            "unix": self._service.unix_time,
            "base64encode": self._service.base64encode,
            "base64decode": self._service.base64decode,
        }
        try:
            if operation in {"md2", "md5", "sha1", "sha256", "sha384", "sha512"}:
                data = self._service.digest(operation, value)
            elif operation == "uuid":
                data = self._service.uuid()
            elif operation == "password":
                data = self._service.password(int(value) if value.strip() else 20)
            elif operation == "qr":
                data = self._service.qr_generate(value)
            elif operation in methods:
                data = methods[operation](value)
            else:
                return ToolResult(kind=ToolResultKind.FAILED, error=f"Неизвестная операция: {operation}")
        except (DeveloperInputError, ValueError) as exc:
            return ToolResult(kind=ToolResultKind.FAILED, error=str(exc))
        return ToolResult(kind=ToolResultKind.IMMEDIATE, data=data)
