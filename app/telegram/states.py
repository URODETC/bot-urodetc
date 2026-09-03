from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class VideoStates(StatesGroup):
    awaiting_url = State()


class NetworkStates(StatesGroup):
    awaiting_target = State()
