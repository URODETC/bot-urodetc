from __future__ import annotations

from aiogram.types import Message

from app.telegram.keyboards import type_keyboard
from app.telegram.ui import esc, format_duration, friendly_error
from app.tools.video.errors import VideoError
from app.tools.video.service import VideoService


async def start_download_flow(message: Message, video_service: VideoService, url: str) -> None:
    """Shared by /download, the menu-driven flow and (in future) other interfaces."""
    if message.from_user is None:
        return

    try:
        info = await video_service.fetch_info(url)
    except VideoError as exc:
        await message.answer(friendly_error(exc))
        return

    record = await video_service.create_record(
        user_id=message.from_user.id,
        url=url,
        info=info,
    )

    text = (
        f"🎬 <b>{esc(info.title)}</b>\n"
        f"👤 {esc(info.author)}\n"
        f"⏱ {format_duration(info.duration)}\n\n"
        f'<a href="{esc(url)}">🔗 Источник</a>\n\n'
        f"Выберите формат:"
    )
    await message.answer(text, reply_markup=type_keyboard(record.id))
