from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.telegram.flows.video import start_download_flow
from app.tools.video.service import VideoService

router = Router(name="download")

_DOWNLOAD_USAGE = "Использование: <code>/download &lt;URL&gt;</code>\nНапример: <code>/download https://youtu.be/dQw4w9WgXcQ</code>"


def _extract_url(message: Message) -> str | None:
    text = (message.text or "").strip()
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        return None
    return parts[1].strip()


@router.message(Command("download"))
async def download(message: Message, video_service: VideoService) -> None:
    url = _extract_url(message)
    if url is None:
        await message.answer(_DOWNLOAD_USAGE)
        return
    await start_download_flow(message, video_service, url)
