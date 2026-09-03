from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from app.telegram.menu import NETWORK_PROMPTS, cancel_keyboard
from app.telegram.states import NetworkStates

router = Router(name="network-callbacks")


@router.callback_query(F.data.startswith("net:pick:") | F.data.startswith("net:again:"))
async def on_pick(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None or not callback.data:
        await callback.answer()
        return

    kind = callback.data.rsplit(":", 1)[-1]
    prompt = NETWORK_PROMPTS.get(kind)
    if prompt is None:
        await callback.answer("Неизвестный инструмент", show_alert=True)
        return

    await state.set_state(NetworkStates.awaiting_target)
    await state.update_data(kind=kind)
    await callback.message.edit_text(prompt, reply_markup=cancel_keyboard())
    await callback.answer()
