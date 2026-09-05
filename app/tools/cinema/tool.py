from app.tools.base import BaseTool, ToolManifest, ToolResult, ToolResultKind
from app.tools.cinema.models import CinemaError
from app.tools.cinema.service import CinemaService

CINEMA_MANIFEST = ToolManifest(name="cinema", description="Фильмы и сериалы: RuTracker → qBittorrent", commands=["cinema", "cinema_status"], async_mode=True, required_permission="owner")


class CinemaTool(BaseTool):
    manifest = CINEMA_MANIFEST

    def __init__(self, service: CinemaService):
        self.service = service

    async def execute(self, *, user_id: int, chat_id: int, text: str = "", action: str = "search", search_id: str = "", topic_id: int = 0) -> ToolResult:
        try:
            if action == "search":
                job = await self.service.search(user_id=user_id, chat_id=chat_id, text=text)
            elif action == "select":
                job = await self.service.select(user_id=user_id, chat_id=chat_id, search_id=search_id, topic_id=topic_id)
            elif action == "status":
                return ToolResult(kind=ToolResultKind.IMMEDIATE, data=await self.service.recent(user_id))
            else:
                raise CinemaError("Неизвестное действие.")
            return ToolResult(kind=ToolResultKind.QUEUED, job_id=job.id)
        except CinemaError as exc:
            return ToolResult(kind=ToolResultKind.FAILED, error=str(exc))
