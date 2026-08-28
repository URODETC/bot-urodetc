from __future__ import annotations

from typing import Any

from app.tools.base import BaseTool, ToolManifest, ToolResult


class ToolNotFoundError(LookupError):
    pass


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}
        self._by_command: dict[str, str] = {}

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool
        self._by_command.update(
            {command: tool.name for command in tool.manifest.commands}
        )

    def get(self, name: str) -> BaseTool:
        try:
            return self._tools[name]
        except KeyError:
            raise ToolNotFoundError(name) from None

    def get_by_command(self, command: str) -> BaseTool:
        try:
            return self.get(self._by_command[command])
        except KeyError:
            raise ToolNotFoundError(command) from None

    def manifests(self) -> list[ToolManifest]:
        return [tool.manifest for tool in self._tools.values()]

    async def execute(self, name: str, **kwargs: Any) -> ToolResult:
        return await self.get(name).execute(**kwargs)

    def __iter__(self):
        return iter(self._tools.values())