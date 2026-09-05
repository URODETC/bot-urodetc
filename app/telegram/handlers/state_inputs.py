from __future__ import annotations

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.infrastructure.config import Settings
from app.infrastructure.history import HistoryRepository
from app.telegram.flows.network import perform_lookup
from app.telegram.flows.video import start_download_flow
from app.telegram.flows.vpn import create_vpn_user, extend_vpn_user, require_vpn_owner
from app.telegram.menu import MENU_VPN, cancel_keyboard, main_menu_keyboard
from app.telegram.states import NetworkStates, VideoStates, VpnStates
from app.tools.network.service import NetworkService
from app.tools.video.service import VideoService
from app.tools.vpn.service import VpnService

router = Router(name="state-inputs")


@router.message(VideoStates.awaiting_url)
async def on_video_url(
    message: Message,
    state: FSMContext,
    video_service: VideoService,
) -> None:
    url = (message.text or "").strip()
    if not url:
        await message.answer("Пришлите ссылку текстом.", reply_markup=cancel_keyboard())
        return
    await state.clear()
    await start_download_flow(message, video_service, url)


@router.message(NetworkStates.awaiting_target)
async def on_network_target(
    message: Message,
    state: FSMContext,
    network_service: NetworkService,
    history: HistoryRepository,
) -> None:
    target = (message.text or "").strip()
    if not target:
        await message.answer("Пришлите значение текстом.", reply_markup=cancel_keyboard())
        return
    data = await state.get_data()
    kind = data.get("kind")
    await state.clear()
    if not kind:
        await message.answer(
            "Сессия устарела, откройте меню заново: /menu",
            reply_markup=main_menu_keyboard(),
        )
        return
    await perform_lookup(
        message,
        service=network_service,
        history=history,
        kind=kind,
        target=target,
    )


@router.message(VpnStates.awaiting_create)
async def on_vpn_create_input(
    message: Message,
    state: FSMContext,
    settings: Settings,
    vpn_service: VpnService,
) -> None:
    if not await require_vpn_owner(message, settings):
        await state.clear()
        return
    raw = (message.text or "").strip()
    if not raw:
        await message.answer(
            "Пришлите параметры текстом.",
            reply_markup=cancel_keyboard(MENU_VPN),
        )
        return
    await state.clear()
    await create_vpn_user(message, vpn_service, raw)


@router.message(VpnStates.awaiting_extend)
async def on_vpn_extend_input(
    message: Message,
    state: FSMContext,
    settings: Settings,
    vpn_service: VpnService,
) -> None:
    if not await require_vpn_owner(message, settings):
        await state.clear()
        return
    raw = (message.text or "").strip()
    if not raw:
        await message.answer(
            "Пришлите параметры текстом.",
            reply_markup=cancel_keyboard(MENU_VPN),
        )
        return
    await state.clear()
    await extend_vpn_user(message, vpn_service, raw)
