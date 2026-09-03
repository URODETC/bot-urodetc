from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.infrastructure.history import HistoryRepository
from app.infrastructure.models import DownloadRecord, LookupRecord
from app.telegram.menu import (
    MAIN_MENU_TEXT,
    MENU_HISTORY,
    MENU_MAIN,
    MENU_NETWORK,
    MENU_VIDEO,
    NETWORK_LABELS,
    NETWORK_MENU_TEXT,
    cancel_keyboard,
    main_menu_keyboard,
    network_menu_keyboard,
)
from app.telegram.pagination import PAGE_SIZE, add_pagination_row, clamp_page, page_count
from app.telegram.states import VideoStates
from app.telegram.ui import esc
from app.tools.video.service import VideoService

router = Router(name="menu-callbacks")


@router.callback_query(F.data == "noop")
async def on_noop(callback: CallbackQuery) -> None:
    await callback.answer()


@router.callback_query(F.data == MENU_MAIN)
async def on_main(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if callback.message is not None:
        await callback.message.edit_text(MAIN_MENU_TEXT, reply_markup=main_menu_keyboard())
    await callback.answer()


@router.callback_query(F.data == MENU_NETWORK)
async def on_network(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if callback.message is not None:
        await callback.message.edit_text(NETWORK_MENU_TEXT, reply_markup=network_menu_keyboard())
    await callback.answer()


@router.callback_query(F.data == MENU_VIDEO)
async def on_video(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(VideoStates.awaiting_url)
    if callback.message is not None:
        await callback.message.edit_text(
            "🎬 Пришлите ссылку на видео YouTube.",
            reply_markup=cancel_keyboard(),
        )
    await callback.answer()


@router.callback_query(F.data.startswith(f"{MENU_HISTORY}:"))
async def on_history(
    callback: CallbackQuery,
    state: FSMContext,
    history: HistoryRepository,
    video_service: VideoService,
) -> None:
    await state.clear()
    if callback.message is None or callback.from_user is None:
        await callback.answer()
        return

    # callback data shape: menu:history:<tab>:<page>
    parts = (callback.data or "").split(":")
    tab = parts[2] if len(parts) > 2 else "net"
    try:
        page = int(parts[3]) if len(parts) > 3 else 0
    except ValueError:
        page = 0

    user_id = callback.from_user.id
    if tab == "vid":
        total = await video_service.count_records(user_id)
        pages = page_count(total)
        page = clamp_page(page, pages)
        video_records = await video_service.list_records(user_id, offset=page * PAGE_SIZE, limit=PAGE_SIZE)
        lines = [_format_video_entry(record) for record in video_records]
    else:
        tab = "net"
        total = await history.count_for_user(user_id)
        pages = page_count(total)
        page = clamp_page(page, pages)
        lookup_records = await history.list_for_user(user_id, offset=page * PAGE_SIZE, limit=PAGE_SIZE)
        lines = [_format_lookup_entry(record) for record in lookup_records]

    text = "📜 <b>История</b>\n\n" + ("\n\n".join(lines) if lines else "Пока пусто.")

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="• 🌐 Сеть •" if tab == "net" else "🌐 Сеть",
            callback_data=f"{MENU_HISTORY}:net:0",
        ),
        InlineKeyboardButton(
            text="• 🎬 Видео •" if tab == "vid" else "🎬 Видео",
            callback_data=f"{MENU_HISTORY}:vid:0",
        ),
    )
    add_pagination_row(builder, f"{MENU_HISTORY}:{tab}", page, pages)
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data=MENU_MAIN))

    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()


def _format_lookup_entry(record: LookupRecord) -> str:
    label = NETWORK_LABELS.get(record.kind, record.kind)
    mark = "✅" if record.status == "success" else "❌"
    when = record.created_at.strftime("%d.%m %H:%M")
    return f"{mark} <b>{esc(label)}</b> — {esc(record.target)}\n<i>{when} · {esc(record.summary)}</i>"


def _format_video_entry(record: DownloadRecord) -> str:
    status_icons = {
        "success": "✅",
        "failed": "❌",
        "cancelled": "🚫",
        "pending": "⏳",
        "running": "⏳",
    }
    mark = status_icons.get(record.status, "•")
    title = record.title or record.url
    when = record.created_at.strftime("%d.%m %H:%M")
    return f"{mark} <b>{esc(title[:60])}</b>\n<i>{when} · {esc(record.quality or '—')}</i>"
