from __future__ import annotations

import logging
import os
from zoneinfo import ZoneInfo

import httpx
from arq import cron
from arq.connections import RedisSettings

from app.infrastructure.config import DEFAULT_REDIS_URL, Settings
from app.infrastructure.database import Database
from app.telegram.bot import build_bot
from app.telegram.vpn_ui import split_vpn_report
from app.tools.video.downloader import VideoDownloader
from app.tools.video.provider import YtDlpProvider
from app.tools.video.service import VideoService
from app.tools.vpn import RemnawaveHttpProvider, VpnService

logger = logging.getLogger(__name__)


async def startup(ctx: dict) -> None:
    settings = Settings.from_env()
    settings.download_dir.mkdir(parents=True, exist_ok=True)
    db = Database(settings.database_url)
    await db.init()
    provider = YtDlpProvider(settings)
    service = VideoService(provider=provider, db=db, settings=settings)
    bot = build_bot(settings)
    vpn_http_client = httpx.AsyncClient(
        headers={"User-Agent": "bot-urodetc/vpn-tool"},
        timeout=httpx.Timeout(30.0),
    )
    vpn_provider = RemnawaveHttpProvider(
        vpn_http_client,
        base_url=settings.remnawave_url,
        token=settings.remnawave_token,
        api_major=settings.remnawave_api_major,
        caddy_token=settings.remnawave_caddy_token,
    )
    vpn_service = VpnService(
        vpn_provider,
        default_squad_uuids=settings.remnawave_default_squad_uuids,
        default_duration_days=settings.remnawave_default_duration_days,
        default_traffic_gb=settings.remnawave_default_traffic_gb,
        report_timezone=settings.remnawave_report_timezone,
    )
    downloader = VideoDownloader(
        provider=provider,
        service=service,
        settings=settings,
    )
    ctx["db"] = db
    ctx["bot"] = bot
    ctx["downloader"] = downloader
    ctx["vpn_http_client"] = vpn_http_client
    ctx["vpn_service"] = vpn_service
    ctx["settings"] = settings
    logger.info(
        "worker started",
        extra={"potoken_enabled": settings.po_tokens_enabled},
    )


async def shutdown(ctx: dict) -> None:
    vpn_http_client = ctx.get("vpn_http_client")
    if vpn_http_client is not None:
        await vpn_http_client.aclose()
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


async def send_vpn_report(
    ctx: dict,
    *,
    chat_ids: list[int] | None = None,
) -> None:
    settings: Settings = ctx["settings"]
    recipients = tuple(chat_ids or settings.vpn_report_recipients)
    if not settings.remnawave_configured or not recipients:
        logger.info(
            "vpn report skipped",
            extra={
                "configured": settings.remnawave_configured,
                "recipients": len(recipients),
            },
        )
        return
    report = await ctx["vpn_service"].weekly_report()
    for chat_id in recipients:
        for text in split_vpn_report(
            report,
            top_users=settings.remnawave_report_top_users,
        ):
            await ctx["bot"].send_message(chat_id, text)
    logger.info(
        "vpn report sent",
        extra={"recipients": len(recipients), "users": len(report.user_usage)},
    )


class WorkerSettings:
    functions = [download_video, send_vpn_report]
    cron_jobs = [
        cron(
            send_vpn_report,
            weekday=os.environ.get("REMNAWAVE_REPORT_WEEKDAY", "mon").lower(),
            hour=int(os.environ.get("REMNAWAVE_REPORT_HOUR", "9")),
            minute=int(os.environ.get("REMNAWAVE_REPORT_MINUTE", "0")),
            unique=True,
            timeout=300,
            max_tries=3,
        )
    ]
    redis_settings = RedisSettings.from_dsn(
        os.environ.get("REDIS_URL", DEFAULT_REDIS_URL)
    )
    concurrency = 8
    job_timeout = 1800
    max_tries = 1
    keep_result = 3600
    on_startup = startup
    on_shutdown = shutdown
    timezone = ZoneInfo(
        os.environ.get("REMNAWAVE_REPORT_TIMEZONE", "Europe/Moscow")
    )
