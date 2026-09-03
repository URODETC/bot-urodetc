from __future__ import annotations

import logging
import os

from arq.connections import RedisSettings

from app.infrastructure.config import DEFAULT_REDIS_URL, Settings
from app.infrastructure.database import Database
from app.telegram.bot import build_bot
from app.tools.video.downloader import VideoDownloader
from app.tools.video.provider import YtDlpProvider
from app.tools.video.service import VideoService

logger = logging.getLogger(__name__)


async def startup(ctx: dict) -> None:
    settings = Settings.from_env()
    settings.download_dir.mkdir(parents=True, exist_ok=True)
    db = Database(settings.database_url)
    await db.init()
    provider = YtDlpProvider(settings)
    service = VideoService(provider=provider, db=db, settings=settings)
    bot = build_bot(settings)
    downloader = VideoDownloader(
        provider=provider,
        service=service,
        settings=settings,
    )
    ctx["db"] = db
    ctx["bot"] = bot
    ctx["downloader"] = downloader
    logger.info(
        "worker started",
        extra={"potoken_enabled": settings.po_tokens_enabled},
    )


async def shutdown(ctx: dict) -> None:
    bot = ctx.get("bot")
    if bot is not None:
        await bot.session.close()
    db = ctx.get("db")
    if db is not None:
        await db.close()
    logger.info("worker stopped")


async def download_video(ctx: dict, *, request_id: str) -> None:
    downloader = ctx["downloader"]
    bot = ctx["bot"]
    await downloader.process(request_id, bot)


class WorkerSettings:
    functions = [download_video]
    redis_settings = RedisSettings.from_dsn(
        os.environ.get("REDIS_URL", DEFAULT_REDIS_URL)
    )
    concurrency = 8
    job_timeout = 1800
    max_tries = 1
    keep_result = 3600
    on_startup = startup
    on_shutdown = shutdown