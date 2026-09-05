from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery

from app.infrastructure.config import Settings
from app.telegram.keyboards import quality_keyboard, type_keyboard
from app.telegram.menu import main_menu_keyboard
from app.telegram.ui import esc
from app.tools.video.models import KIND_AUDIO, KIND_VIDEO
from app.tools.video.queue import enqueue_download
from app.tools.video.service import VideoService

logger = logging.getLogger(__name__)

router = Router(name="download-callbacks")


def _parse(payload: str) -> tuple[str, str | None, str | None] | None:
    parts = payload.split(":")
    if len(parts) < 3 or parts[0] != "download":
        return None
    record_id = parts[1]
    action = parts[2]
    param = parts[3] if len(parts) > 3 else None
    return record_id, action, param


@router.callback_query(F.data.startswith("download:"))
async def on_download_callback(
    callback: CallbackQuery,
    video_service: VideoService,
    settings: Settings,
) -> None:
    parsed = _parse(callback.data or "")
    if parsed is None or callback.message is None:
        await callback.answer()
        return

    record_id, action, param = parsed
    user_id = callback.from_user.id

    record = await video_service.get_record(record_id)
    if record is None:
        await callback.message.delete()
        await callback.answer("Запрос не найден", show_alert=True)
        return
    if record.user_id != user_id:
        await callback.answer("Это не ваш запрос", show_alert=True)
        return
    if record.status != "pending":
        await callback.answer("Запрос уже обработан", show_alert=True)
        return

    if action == "mode" and param:
        await _show_quality(callback, video_service, record_id, param, user_id)
    elif action == "q" and param:
        try:
            index = int(param)
        except ValueError:
            await callback.answer("Некорректный запрос", show_alert=True)
            return
        await _start_download(
            callback,
            video_service,
            settings,
            record_id,
            index,
            user_id,
        )
    elif action == "back":
        await callback.message.edit_text(
            "Выберите формат:",
            reply_markup=type_keyboard(record_id),
        )
        await callback.answer()
    elif action == "cancel":
        await video_service.cancel_record(record_id=record_id, user_id=user_id)
        await callback.message.delete()
        await callback.bot.send_message(
            callback.message.chat.id,
            "🚫 Скачивание отменено.",
            reply_markup=main_menu_keyboard(),
        )
        await callback.answer("Запрос отменён", show_alert=True)


async def _show_quality(
    callback: CallbackQuery,
    video_service: VideoService,
    record_id: str,
    kind: str,
    user_id: int,
) -> None:
    record = await video_service.get_record(record_id)
    if record is None or record.user_id != user_id:
        await callback.answer("Запрос не найден", show_alert=True)
        return

    options = video_service.options_by_kind(record, kind)
    if not options:
        await callback.answer("Для этого варианта нет форматов", show_alert=True)
        return

    header = {
        KIND_AUDIO: "🎵 Аудио — выберите качество:",
        KIND_VIDEO: "🎬 Видео — выберите качество:",
    }.get(kind, "Выберите качество:")
    await callback.message.edit_text(
        header,
        reply_markup=quality_keyboard(record_id, options),
    )
    await callback.answer()


async def _start_download(
    callback: CallbackQuery,
    video_service: VideoService,
    settings: Settings,
    record_id: str,
    index: int,
    user_id: int,
) -> None:
    assert callback.message is not None
    selected = await video_service.select_format(
        record_id=record_id,
        user_id=user_id,
        index=index,
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
    )
    if selected is None:
        await callback.answer("Не удалось выбрать формат", show_alert=True)
        return

    try:
        job = await enqueue_download(settings.redis_url, record_id)
    except Exception:
        logger.exception("failed to enqueue download", extra={"request_id": record_id})
        await video_service.set_status(record_id, "failed")
        await callback.message.delete()
        await callback.bot.send_message(
            callback.message.chat.id,
            "⚠️ Очередь недоступна, попробуйте позже.",
            reply_markup=main_menu_keyboard(),
        )
        await callback.answer("Ошибка очереди", show_alert=True)
        return
    if job is None:
        await video_service.set_status(record_id, "failed")
        await callback.message.delete()
        await callback.bot.send_message(
            callback.message.chat.id,
            "⚠️ Очередь недоступна, попробуйте позже.",
            reply_markup=main_menu_keyboard(),
        )
        await callback.answer("Ошибка очереди", show_alert=True)
        return

    await callback.message.edit_text(
        f"⏳ Скачивание начато: <b>{esc(selected.quality)}</b>\n"
        f"Задача: <code>{job.job_id}</code>",
        reply_markup=main_menu_keyboard(),
    )
    await callback.answer("Добавлено в очередь")
