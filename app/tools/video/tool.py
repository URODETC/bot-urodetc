from __future__ import annotations

from app.tools.base import BaseTool, ToolResult, ToolResultKind
from app.tools.video.errors import VideoError
from app.tools.video.manifest import VIDEO_MANIFEST
from app.tools.video.models import VideoPreview
from app.tools.video.service import VideoService


class VideoTool(BaseTool):
    manifest = VIDEO_MANIFEST

    def __init__(self, service: VideoService) -> None:
        self._service = service

    async def execute(
        self,
        *,
        user_id: int,
        url: str,
        cookies: str | None = None,
    ) -> ToolResult:
        try:
            info = await self._service.fetch_info(url, cookies=cookies)
        except VideoError as exc:
            return ToolResult(
                kind=ToolResultKind.FAILED,
                error=str(exc),
            )
        record = await self._service.create_record(user_id=user_id, url=url, info=info)
        return ToolResult(
            kind=ToolResultKind.IMMEDIATE,
            data=VideoPreview(request_id=record.id, info=info),
        )