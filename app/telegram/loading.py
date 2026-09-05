from __future__ import annotations

import asyncio
import contextlib

from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from aiogram.types import Message

from app.telegram.menu import main_menu_keyboard

_FRAMES = ("◐", "◓", "◑", "◒")


class LoadingIndicator:
    """Small Telegram-native spinner that edits one temporary message."""

    def __init__(self, message: Message, label: str = "Выполняю запрос") -> None:
        self._request = message
        self._label = label
        self._status: Message | None = None
        self._task: asyncio.Task[None] | None = None

    async def __aenter__(self) -> LoadingIndicator:
        self._status = await self._request.answer(
            f"{_FRAMES[0]} <i>{self._label}…</i>",
            reply_markup=main_menu_keyboard(),
        )
        self._task = asyncio.create_task(self._animate())
        return self

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        if self._status is not None:
            with contextlib.suppress(TelegramBadRequest):
                await self._status.delete()

    async def _animate(self) -> None:
        index = 1
        while True:
            await asyncio.sleep(1.2)
            if self._status is None:
                return
            try:
                await self._status.edit_text(
                    f"{_FRAMES[index % len(_FRAMES)]} <i>{self._label}…</i>",
                    reply_markup=main_menu_keyboard(),
                )
            except TelegramRetryAfter as exc:
                await asyncio.sleep(exc.retry_after)
            except TelegramBadRequest:
                return
            index += 1
