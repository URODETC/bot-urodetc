from __future__ import annotations

import math

from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.telegram.menu import NOOP

PAGE_SIZE = 5


def page_count(total_items: int, page_size: int = PAGE_SIZE) -> int:
    return max(1, math.ceil(total_items / page_size))


def clamp_page(page: int, total_pages: int) -> int:
    return max(0, min(page, total_pages - 1))


def add_pagination_row(builder: InlineKeyboardBuilder, prefix: str, page: int, total_pages: int) -> None:
    """Appends a ◀️ page/total ▶️ navigation row to an existing keyboard builder."""
    if total_pages <= 1:
        return
    prev_data = f"{prefix}:{page - 1}" if page > 0 else NOOP
    next_data = f"{prefix}:{page + 1}" if page < total_pages - 1 else NOOP
    builder.row(
        InlineKeyboardButton(text="◀️" if page > 0 else "·", callback_data=prev_data),
        InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data=NOOP),
        InlineKeyboardButton(text="▶️" if page < total_pages - 1 else "·", callback_data=next_data),
    )
