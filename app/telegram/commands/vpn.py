from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.infrastructure.config import Settings
from app.telegram.flows.vpn import (
    create_vpn_user,
    extend_vpn_user,
    queue_vpn_report,
    require_vpn_owner,
)
from app.telegram.menu import VPN_MENU_TEXT, main_menu_keyboard, vpn_menu_keyboard
from app.tools.vpn.service import VpnService

router = Router(name="vpn-commands")


@router.message(Command("vpn"))
async def vpn_menu(message: Message, settings: Settings) -> None:
    if not await require_vpn_owner(message, settings):
        return
    await message.answer(VPN_MENU_TEXT, reply_markup=vpn_menu_keyboard())


@router.message(Command("vpn_add"))
async def vpn_add(
    message: Message,
    settings: Settings,
    vpn_service: VpnService,
) -> None:
    if not await require_vpn_owner(message, settings):
        return
    argument = _argument(message)
    if not argument:
        await message.answer(
            "Использование: <code>/vpn_add имя [дней] [лимит_ГБ] [telegram_id]</code>\n"
            "0 ГБ означает безлимит, <code>-</code> — значение по умолчанию.",
            reply_markup=main_menu_keyboard(),
        )
        return
    await create_vpn_user(message, vpn_service, argument)


@router.message(Command("vpn_extend"))
async def vpn_extend(
    message: Message,
    settings: Settings,
    vpn_service: VpnService,
) -> None:
    if not await require_vpn_owner(message, settings):
        return
    argument = _argument(message)
    if not argument:
        await message.answer(
            "Использование: <code>/vpn_extend имя количество_дней</code>",
            reply_markup=main_menu_keyboard(),
        )
        return
    await extend_vpn_user(message, vpn_service, argument)


@router.message(Command("vpn_report"))
async def vpn_report(message: Message, settings: Settings) -> None:
    if not await require_vpn_owner(message, settings):
        return
    await queue_vpn_report(message, settings)


def _argument(message: Message) -> str:
    text = (message.text or "").strip()
    _command, _separator, argument = text.partition(" ")
    return argument.strip()
