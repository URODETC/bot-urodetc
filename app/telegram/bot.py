from __future__ import annotations

import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.infrastructure.config import Settings
from app.telegram.callbacks import callbacks_router
from app.telegram.commands import commands_router
from app.telegram.inline import inline_router

logger = logging.getLogger(__name__)


def build_bot(settings: Settings) -> Bot:
    return Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def build_dispatcher() -> Dispatcher:
    dp = Dispatcher()
    dp.include_routers(commands_router, inline_router, callbacks_router)
    return dp


async def run(settings: Settings) -> None:
    bot = build_bot(settings)
    dp = build_dispatcher()
    logger.info("starting bot")
    await dp.start_polling(bot)