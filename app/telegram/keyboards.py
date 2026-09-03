from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.telegram.ui import human_size
from app.tools.video.models import KIND_AUDIO, KIND_VIDEO, MediaOption

CB_DOWNLOAD = "download"


def _cb(record_id: str, action: str, param: str | None = None) -> str:
    if param is None:
        return f"{CB_DOWNLOAD}:{record_id}:{action}"
    return f"{CB_DOWNLOAD}:{record_id}:{action}:{param}"


def type_keyboard(record_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="🎵 Только аудио",
            callback_data=_cb(record_id, "mode", KIND_AUDIO),
        ),
        InlineKeyboardButton(
            text="🎬 Видео со звуком",
            callback_data=_cb(record_id, "mode", KIND_VIDEO),
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="🚫 Отмена",
            callback_data=_cb(record_id, "cancel"),
        )
    )
    return builder.as_markup()


def quality_keyboard(
    record_id: str,
    options: list[tuple[int, MediaOption]],
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for index, option in options:
        size_note = f" · ≈ {human_size(option.size)}" if option.size else ""
        builder.button(
            text=f"{option.label} ({option.ext}){size_note}",
            callback_data=_cb(record_id, "q", str(index)),
        )
    builder.adjust(2, repeat=True)
    builder.row(
        InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data=_cb(record_id, "back"),
        ),
        InlineKeyboardButton(
            text="🚫 Отмена",
            callback_data=_cb(record_id, "cancel"),
        ),
    )
    return builder.as_markup()