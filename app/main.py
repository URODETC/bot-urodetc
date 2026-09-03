from __future__ import annotations

import asyncio
import logging

import httpx

from app.infrastructure.config import Settings
from app.infrastructure.database import Database
from app.infrastructure.history import HistoryRepository
from app.infrastructure.logging import setup_logging
from app.registry.tools import ToolRegistry
from app.telegram.bot import build_bot, build_dispatcher
from app.tools.network import (
    CompositeWhoisProvider,
    DnsPythonProvider,
    IpApiGeoProvider,
    LegacyWhoisProvider,
    NetworkService,
    NetworkTool,
    RdapIpOwnerProvider,
    RdapWhoisProvider,
    SocketTlsProvider,
)
from app.tools.video import VideoService, VideoTool, YtDlpProvider

logger = logging.getLogger(__name__)


def build_network_service(http_client: httpx.AsyncClient) -> NetworkService:
    return NetworkService(
        whois=CompositeWhoisProvider(RdapWhoisProvider(http_client), LegacyWhoisProvider()),
        geo=IpApiGeoProvider(http_client),
        dns=DnsPythonProvider(),
        ip_owner=RdapIpOwnerProvider(http_client),
        tls=SocketTlsProvider(),
    )


async def run(settings: Settings) -> None:
    settings.download_dir.mkdir(parents=True, exist_ok=True)
    db = Database(settings.database_url)
    await db.init()

    video_provider = YtDlpProvider(settings)
    video_service = VideoService(provider=video_provider, db=db, settings=settings)
    history = HistoryRepository(db)

    http_client = httpx.AsyncClient(
        headers={"User-Agent": "bot-urodetc/network-tools"},
        timeout=httpx.Timeout(10.0),
    )
    network_service = build_network_service(http_client)

    logger.info(
        "starting tools",
        extra={"potoken_enabled": settings.po_tokens_enabled},
    )

    registry = ToolRegistry()
    registry.register(VideoTool(video_service))
    registry.register(NetworkTool(network_service))

    dp = build_dispatcher()
    dp["settings"] = settings
    dp["video_service"] = video_service
    dp["network_service"] = network_service
    dp["history"] = history
    dp["tools"] = registry

    bot = build_bot(settings)
    try:
        logger.info(
            "starting bot",
            extra={"tools": [m.name for m in registry.manifests()]},
        )
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        await http_client.aclose()
        await db.close()


def main() -> None:
    setup_logging("INFO")
    try:
        settings = Settings.from_env()
    except KeyError as exc:
        logger.error("missing required env var: %s", exc.args[0])
        raise
    setup_logging(settings.log_level)
    asyncio.run(run(settings))


if __name__ == "__main__":
    main()
