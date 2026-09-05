from __future__ import annotations

from aiogram.types import Message

from app.infrastructure.config import Settings
from app.telegram.menu import main_menu_keyboard, vpn_menu_keyboard
from app.telegram.vpn_ui import (
    format_vpn_user_created,
    format_vpn_user_extended,
    friendly_vpn_error,
)
from app.tools.vpn.errors import VpnToolError, VpnValidationError
from app.tools.vpn.queue import enqueue_vpn_report
from app.tools.vpn.service import VpnService


async def create_vpn_user(
    message: Message,
    service: VpnService,
    raw: str,
) -> None:
    try:
        username, days, traffic_gb, telegram_id = parse_create_request(raw)
        user = await service.create_user(
            username,
            days=days,
            traffic_gb=traffic_gb,
            telegram_id=telegram_id,
        )
    except (VpnToolError, ValueError) as exc:
        await message.answer(friendly_vpn_error(exc), reply_markup=main_menu_keyboard())
        return
    await message.answer(
        format_vpn_user_created(user),
        disable_web_page_preview=True,
        reply_markup=main_menu_keyboard(),
    )


async def extend_vpn_user(
    message: Message,
    service: VpnService,
    raw: str,
) -> None:
    try:
        username, days = parse_extend_request(raw)
        user = await service.extend_user(username, days)
    except (VpnToolError, ValueError) as exc:
        await message.answer(friendly_vpn_error(exc), reply_markup=main_menu_keyboard())
        return
    await message.answer(format_vpn_user_extended(user), reply_markup=main_menu_keyboard())


async def queue_vpn_report(message: Message, settings: Settings) -> None:
    if not settings.remnawave_configured:
        await message.answer(
            "❌ Remnawave не настроен: задайте REMNAWAVE_URL и REMNAWAVE_TOKEN.",
            reply_markup=main_menu_keyboard(),
        )
        return
    status = await message.answer(
        "⏳ Собираю VPN-отчёт…",
        reply_markup=vpn_menu_keyboard(),
    )
    job_id = await enqueue_vpn_report(
        settings.redis_url,
        message.chat.id,
        status_message_id=status.message_id,
    )
    if job_id is None:
        await status.delete()
        await message.answer(
            "❌ Не удалось поставить отчёт в очередь.",
            reply_markup=main_menu_keyboard(),
        )
        return
    await status.edit_text(
        f"⏳ Собираю VPN-отчёт. Задача: <code>{job_id}</code>",
        reply_markup=vpn_menu_keyboard(),
    )


def parse_create_request(raw: str) -> tuple[str, int | None, int | None, int | None]:
    parts = raw.split()
    if not 1 <= len(parts) <= 4:
        raise VpnValidationError(
            "Формат: имя [дней] [лимит_ГБ] [telegram_id]"
        )
    username = parts[0]
    values: list[int | None] = []
    for value in parts[1:]:
        try:
            values.append(None if value == "-" else int(value))
        except ValueError as exc:
            raise VpnValidationError(
                "Дни, лимит трафика и Telegram ID должны быть целыми числами"
            ) from exc
    values.extend([None] * (3 - len(values)))
    return username, values[0], values[1], values[2]


def parse_extend_request(raw: str) -> tuple[str, int]:
    parts = raw.split()
    if len(parts) != 2:
        raise VpnValidationError("Формат: имя количество_дней")
    try:
        days = int(parts[1])
    except ValueError as exc:
        raise VpnValidationError("Количество дней должно быть целым числом") from exc
    return parts[0], days


async def require_vpn_owner(message: Message, settings: Settings) -> bool:
    user_id = message.from_user.id if message.from_user else None
    if settings.is_owner(user_id):
        return True
    await message.answer(
        "⛔ Этот инструмент доступен только владельцу бота.",
        reply_markup=main_menu_keyboard(),
    )
    return False
