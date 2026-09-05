from aiogram import Router
from aiogram.filters import Command
from aiogram.filters.command import CommandObject
from aiogram.types import Message

from app.telegram.cinema_ui import format_status, recent_results_keyboard
from app.tools.cinema.models import CinemaError
from app.tools.cinema.service import CinemaService

router = Router(name="cinema_commands")


@router.message(Command("cinema"))
async def cinema(message: Message, command: CommandObject, cinema_service: CinemaService) -> None:
    if message.from_user is None:
        return
    try:
        cinema_service.authorize(message.from_user.id)
        if not command.args:
            await message.answer("🎬 Укажите название, год или сезон:\n<code>/cinema Дюна 2021</code>\n<code>/cinema Во все тяжкие сезон 2</code>\n\nБот покажет варианты с приоритетом 2160p. После выбора qBittorrent скачает файлы на сервер.")
            return
        job = await cinema_service.search(user_id=message.from_user.id, chat_id=message.chat.id, text=command.args)
        await message.answer(f"🔎 Поиск поставлен в очередь. Задача <code>{job.id[:8]}</code>. Результаты появятся здесь.")
    except CinemaError as exc:
        await message.answer(str(exc))


@router.message(Command("cinema_status"))
async def cinema_status(message: Message, cinema_service: CinemaService) -> None:
    if message.from_user is None:
        return
    try:
        jobs = await cinema_service.recent(message.from_user.id)
        await message.answer(format_status(jobs), reply_markup=recent_results_keyboard(jobs))
    except CinemaError as exc:
        await message.answer(str(exc))
