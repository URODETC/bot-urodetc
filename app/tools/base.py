from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ToolResultKind(StrEnum):
    IMMEDIATE = "immediate"
    CACHED = "cached"
    QUEUED = "queued"
    FAILED = "failed"


@dataclass(frozen=True)
class ToolManifest:
    name: str
    description: str
    commands: list[str] = field(default_factory=list)
    inline: bool = False
    async_mode: bool = False


@dataclass
class ToolResult:
    kind: ToolResultKind
    data: Any = None
    job_id: str | None = None
    error: str | None = None


class BaseTool(ABC):
    manifest: ToolManifest

    @property
    def name(self) -> str:
        return self.manifest.name

    @abstractmethod
    async def execute(self, **kwargs: Any) -> ToolResult:
        ...