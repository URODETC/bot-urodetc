from __future__ import annotations

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.infrastructure.history import HistoryRepository
from app.telegram.flows.network import perform_lookup
from app.telegram.flows.video import start_download_flow
from app.telegram.states import NetworkStates, VideoStates
from app.tools.network.service import NetworkService
from app.tools.video.service import VideoService

router = Router(name="state-inputs")


@router.message(VideoStates.awaiting_url)
async def on_video_url(
    message: Message,
    state: FSMContext,
    video_service: VideoService,
) -> None:
    url = (message.text or "").strip()
    if not url:
        await message.answer("Пришлите ссылку текстом.")
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
        await message.answer("Пришлите значение текстом.")
        return
    data = await state.get_data()
    kind = data.get("kind")
    await state.clear()
    if not kind:
        await message.answer("Сессия устарела, откройте меню заново: /menu")
        return
    await perform_lookup(
        message,
        service=network_service,
        history=history,
        kind=kind,
        target=target,
    )
