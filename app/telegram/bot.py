from __future__ import annotations

import logging

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.default import DefaultBotProperties
from aiogram.client.telegram import TelegramAPIServer
from aiogram.enums import ParseMode

from app.infrastructure.config import Settings
from app.telegram.callbacks import callbacks_router
from app.telegram.commands import commands_router
from app.telegram.handlers import handlers_router
from app.telegram.inline import inline_router

logger = logging.getLogger(__name__)


def build_bot(settings: Settings) -> Bot:
    server = (
        TelegramAPIServer.from_base(base=settings.local_api_base, is_local=True)
        if settings.local_api_base
        else None
    )
    session_options = {"api": server} if server else {}
    session = AiohttpSession(
        proxy=None if server else settings.telegram_proxy_url, **session_options
    )
    return Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        session=session,
    )


def build_dispatcher() -> Dispatcher:
    dp = Dispatcher()
    dp.include_routers(commands_router, handlers_router, inline_router, callbacks_router)
    return dp