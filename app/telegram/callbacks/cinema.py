from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from app.telegram.cinema_ui import search_page
from app.tools.cinema.models import CinemaError
from app.tools.cinema.service import CinemaService

router = Router(name="cinema_callbacks")


@router.callback_query(F.data.startswith("cin:"))
async def cinema_callback(callback: CallbackQuery, cinema_service: CinemaService) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Сообщение недоступно.")
        return
    try:
        _, action, search_id, raw_value = (callback.data or "").split(":")
        value = int(raw_value)
        if action == "page":
            job = await cinema_service.results(user_id=callback.from_user.id, search_id=search_id)
            text, markup = search_page(job, value)
            await callback.answer()
            await callback.message.edit_text(text, reply_markup=markup)
        elif action == "add":
            job = await cinema_service.select(user_id=callback.from_user.id, chat_id=callback.message.chat.id, search_id=search_id, topic_id=value)
            await callback.answer("Задача загрузки сохранена")
            await callback.message.answer(f"📥 Задача <code>{job.id[:8]}</code> · /cinema_status — состояние. Повторное нажатие не создаст копию задачи.")
        else:
            await callback.answer("Неизвестное действие.")
    except (ValueError, CinemaError) as exc:
        await callback.answer(str(exc) if isinstance(exc, CinemaError) else "Некорректная кнопка.", show_alert=True)
