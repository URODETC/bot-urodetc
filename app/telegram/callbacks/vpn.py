from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from app.infrastructure.config import Settings
from app.telegram.menu import MENU_VPN, VPN_MENU_TEXT, cancel_keyboard, vpn_menu_keyboard
from app.telegram.states import VpnStates
from app.tools.vpn.queue import enqueue_vpn_report

router = Router(name="vpn-callbacks")


def _is_owner(callback: CallbackQuery, settings: Settings) -> bool:
    return settings.is_owner(callback.from_user.id if callback.from_user else None)


@router.callback_query(F.data == MENU_VPN)
async def on_vpn_menu(
    callback: CallbackQuery,
    state: FSMContext,
    settings: Settings,
) -> None:
    if not _is_owner(callback, settings):
        await callback.answer("Доступно только владельцу", show_alert=True)
        return
    await state.clear()
    if callback.message is not None:
        await callback.message.edit_text(VPN_MENU_TEXT, reply_markup=vpn_menu_keyboard())
    await callback.answer()


@router.callback_query(F.data == "vpn:create")
async def on_vpn_create(
    callback: CallbackQuery,
    state: FSMContext,
    settings: Settings,
) -> None:
    if not _is_owner(callback, settings):
        await callback.answer("Доступно только владельцу", show_alert=True)
        return
    await state.set_state(VpnStates.awaiting_create)
    if callback.message is not None:
        await callback.message.edit_text(
            "➕ Пришлите: <code>имя [дней] [лимит_ГБ] [telegram_id]</code>\n"
            "Например: <code>ivan 30 100 123456789</code>\n"
            "Для настроек по умолчанию достаточно имени.",
            reply_markup=cancel_keyboard(MENU_VPN),
        )
    await callback.answer()


@router.callback_query(F.data == "vpn:extend")
async def on_vpn_extend(
    callback: CallbackQuery,
    state: FSMContext,
    settings: Settings,
) -> None:
    if not _is_owner(callback, settings):
        await callback.answer("Доступно только владельцу", show_alert=True)
        return
    await state.set_state(VpnStates.awaiting_extend)
    if callback.message is not None:
        await callback.message.edit_text(
            "📅 Пришлите имя и срок продления в днях.\n"
            "Например: <code>ivan 30</code>",
            reply_markup=cancel_keyboard(MENU_VPN),
        )
    await callback.answer()


@router.callback_query(F.data == "vpn:report")
async def on_vpn_report(callback: CallbackQuery, settings: Settings) -> None:
    if not _is_owner(callback, settings):
        await callback.answer("Доступно только владельцу", show_alert=True)
        return
    if callback.message is None:
        await callback.answer()
        return
    if not settings.remnawave_configured:
        await callback.answer("Remnawave не настроен", show_alert=True)
        return
    job_id = await enqueue_vpn_report(settings.redis_url, callback.message.chat.id)
    if job_id is None:
        await callback.answer("Не удалось поставить отчёт в очередь", show_alert=True)
        return
    await callback.message.answer(
        f"⏳ Собираю VPN-отчёт. Задача: <code>{job_id}</code>"
    )
    await callback.answer("Отчёт поставлен в очередь")
