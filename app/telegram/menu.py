from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

MENU_MAIN = "menu:main"
MENU_NETWORK = "menu:network"
MENU_VIDEO = "menu:video"
MENU_HISTORY = "menu:history"
MENU_DEVELOPER = "menu:developer"
MENU_VPN = "menu:vpn"
NOOP = "noop"

# (kind, button label, input prompt)
NETWORK_TOOLS: tuple[tuple[str, str, str], ...] = (
    ("whois", "🔍 WHOIS", "Пришлите домен, ссылку или IP, например: <code>example.com</code>"),
    ("geo", "📍 Геолокация IP", "Пришлите IP-адрес или домен, например: <code>8.8.8.8</code>"),
    ("dns", "🧭 DNS / PTR", "Пришлите домен или IP, например: <code>example.com</code>"),
    ("lir", "🏢 Владелец IP (LIR)", "Пришлите IP-адрес, например: <code>8.8.8.8</code>"),
    ("rdns", "↩️ Обратный DNS", "Пришлите IP-адрес, например: <code>1.1.1.1</code>"),
    ("tls", "🔒 SSL-сертификат", "Пришлите домен, например: <code>example.com</code>"),
    ("ping", "📡 Ping", "Пришлите домен или IP, например: <code>example.com</code>"),
    ("check", "🌐 HTTP Check", "Пришлите URL, например: <code>https://example.com</code>"),
    ("mtr", "🛣 MTR", "Пришлите домен или IP, например: <code>example.com</code>"),
)

NETWORK_PROMPTS: dict[str, str] = {kind: prompt for kind, _label, prompt in NETWORK_TOOLS}
NETWORK_LABELS: dict[str, str] = {kind: label for kind, label, _prompt in NETWORK_TOOLS}

MAIN_MENU_TEXT = (
    "🤖 <b>Главное меню</b>\n"
    "Выберите инструмент — всё управление через кнопки, набирать команды не нужно."
)
NETWORK_MENU_TEXT = "🌐 <b>Сетевые инструменты</b>\nВыберите, что нужно проверить:"
VPN_MENU_TEXT = (
    "🔐 <b>Управление VPN</b>\n"
    "Создание и продление пользователей Remnawave, статистика и отчёты."
)


def main_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🎬 Скачать видео", callback_data=MENU_VIDEO))
    builder.row(InlineKeyboardButton(text="🌐 Сетевые инструменты", callback_data=MENU_NETWORK))
    builder.row(InlineKeyboardButton(text="🧰 Инструменты разработчика", callback_data=MENU_DEVELOPER))
    builder.row(InlineKeyboardButton(text="🔐 Управление VPN", callback_data=MENU_VPN))
    builder.row(InlineKeyboardButton(text="📜 История", callback_data=f"{MENU_HISTORY}:net:0"))
    return builder.as_markup()


def network_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for kind, label, _prompt in NETWORK_TOOLS:
        builder.button(text=label, callback_data=f"net:pick:{kind}")
    builder.adjust(2, repeat=True)
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data=MENU_MAIN))
    return builder.as_markup()


def vpn_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="➕ Новый пользователь", callback_data="vpn:create"),
        InlineKeyboardButton(text="📅 Продлить", callback_data="vpn:extend"),
    )
    builder.row(InlineKeyboardButton(text="📊 Отчёт за неделю", callback_data="vpn:report"))
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data=MENU_MAIN))
    return builder.as_markup()


def cancel_keyboard(callback_data: str = MENU_MAIN) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🚫 Отмена", callback_data=callback_data))
    return builder.as_markup()


def result_keyboard(kind: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🔁 Ещё раз", callback_data=f"net:again:{kind}"),
        InlineKeyboardButton(text="🌐 Сеть", callback_data=MENU_NETWORK),
        InlineKeyboardButton(text="🏠 Меню", callback_data=MENU_MAIN),
    )
    return builder.as_markup()


def back_to_main_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🏠 В меню", callback_data=MENU_MAIN))
    return builder.as_markup()
