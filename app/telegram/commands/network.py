from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.infrastructure.history import HistoryRepository
from app.telegram.flows.network import perform_lookup
from app.telegram.menu import main_menu_keyboard
from app.tools.network.service import NetworkService

router = Router(name="network-commands")

_KIND_BY_COMMAND = {
    "whois": "whois",
    "ip": "dns",
    "ping": "ping",
    "check": "check",
    "mtr": "mtr",
    "geo": "geo",
    "rdns": "rdns",
    "tls": "tls",
}

_USAGE = {
    "whois": "/whois &lt;домен/ссылка/IP&gt;",
    "ip": "/ip &lt;домен/IP&gt;",
    "ping": "/ping &lt;домен/IP&gt;",
    "check": "/check &lt;URL&gt;",
    "mtr": "/mtr &lt;домен/IP&gt;",
    "geo": "/geo &lt;домен/IP&gt;",
    "rdns": "/rdns &lt;IP&gt;",
    "tls": "/tls &lt;домен&gt;",
}


@router.message(Command(*_KIND_BY_COMMAND))
async def network_command(
    message: Message,
    network_service: NetworkService,
    history: HistoryRepository,
) -> None:
    command, argument = _command_and_argument(message)
    if command not in _KIND_BY_COMMAND:
        return
    if not argument:
        await message.answer(
            f"Использование: <code>{_USAGE[command]}</code>",
            reply_markup=main_menu_keyboard(),
        )
        return
    await perform_lookup(
        message,
        service=network_service,
        history=history,
        kind=_KIND_BY_COMMAND[command],
        target=argument,
    )


def _command_and_argument(message: Message) -> tuple[str, str]:
    text = (message.text or message.caption or "").strip()
    head, _, tail = text.partition(" ")
    command = head.removeprefix("/").split("@", 1)[0].lower()
    return command, tail.strip()
