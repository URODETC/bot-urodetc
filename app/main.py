from __future__ import annotations

import asyncio
import logging

import httpx
from aiogram.types import BotCommand

from app.infrastructure.config import Settings
from app.infrastructure.database import Database
from app.infrastructure.history import HistoryRepository
from app.infrastructure.logging import setup_logging
from app.registry.tools import ToolRegistry
from app.telegram.bot import build_bot, build_dispatcher
from app.tools.developer import DeveloperService, DeveloperTool
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
    SystemDiagnosticsProvider,
)
from app.tools.video import VideoService, VideoTool, YtDlpProvider
from app.tools.vpn import RemnawaveHttpProvider, VpnService, VpnTool

logger = logging.getLogger(__name__)


def build_network_service(http_client: httpx.AsyncClient) -> NetworkService:
    return NetworkService(
        whois=CompositeWhoisProvider(RdapWhoisProvider(http_client), LegacyWhoisProvider()),
        geo=IpApiGeoProvider(http_client),
        dns=DnsPythonProvider(),
        ip_owner=RdapIpOwnerProvider(http_client),
        tls=SocketTlsProvider(),
        diagnostics=SystemDiagnosticsProvider(http_client),
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
    developer_service = DeveloperService()
    vpn_provider = RemnawaveHttpProvider(
        http_client,
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

    logger.info(
        "starting tools",
        extra={"potoken_enabled": settings.po_tokens_enabled},
    )

    registry = ToolRegistry()
    registry.register(VideoTool(video_service))
    registry.register(NetworkTool(network_service))
    registry.register(DeveloperTool(developer_service))
    registry.register(VpnTool(vpn_service))

    dp = build_dispatcher()
    dp["settings"] = settings
    dp["video_service"] = video_service
    dp["network_service"] = network_service
    dp["developer_service"] = developer_service
    dp["vpn_service"] = vpn_service
    dp["history"] = history
    dp["tools"] = registry

    bot = build_bot(settings)
    try:
        await bot.set_my_commands(_bot_commands())
        logger.info(
            "starting bot",
            extra={"tools": [m.name for m in registry.manifests()]},
        )
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        await http_client.aclose()
        await db.close()


def _bot_commands() -> list[BotCommand]:
    return [
        BotCommand(command="menu", description="Главное меню"),
        BotCommand(command="help", description="Все инструменты"),
        BotCommand(command="download", description="Скачать видео"),
        BotCommand(command="whois", description="WHOIS домена или IP"),
        BotCommand(command="ip", description="DNS или PTR-записи"),
        BotCommand(command="ping", description="Проверить доступность"),
        BotCommand(command="check", description="Проверить HTTP(S) URL"),
        BotCommand(command="mtr", description="Диагностика маршрута"),
        BotCommand(command="qr", description="Создать или прочитать QR"),
        BotCommand(command="getcolor", description="Карточка цвета"),
        BotCommand(command="unix", description="Unix-время"),
        BotCommand(command="sha256", description="SHA-256 текста"),
        BotCommand(command="length", description="Длина и вес текста"),
        BotCommand(command="uuid", description="Создать UUID v4"),
        BotCommand(command="password", description="Надёжный пароль"),
        BotCommand(command="vpn", description="Управление VPN"),
        BotCommand(command="vpn_add", description="Добавить VPN-пользователя"),
        BotCommand(command="vpn_extend", description="Продлить VPN-подписку"),
        BotCommand(command="vpn_report", description="VPN-отчёт за неделю"),
    ]


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
