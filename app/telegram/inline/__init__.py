from __future__ import annotations

import asyncio
import uuid

from aiogram import Router
from aiogram.types import InlineQuery, InlineQueryResultArticle, InputTextMessageContent

from app.telegram.ui import (
    esc,
    format_dns,
    format_geo,
    format_ip_owner,
    format_rdns,
    format_tls,
    format_whois,
    friendly_network_error,
)
from app.tools.network.errors import NetworkToolError
from app.tools.network.models import LookupKind
from app.tools.network.service import NetworkService

inline_router = Router(name="inline")

_TIMEOUT = 7.0

# Aliases users are likely to type after "@bot ..."
_ALIASES: dict[str, LookupKind] = {
    "whois": LookupKind.WHOIS,
    "geo": LookupKind.GEO,
    "geoip": LookupKind.GEO,
    "dns": LookupKind.DNS,
    "ns": LookupKind.DNS,
    "lir": LookupKind.LIR,
    "ip": LookupKind.LIR,
    "owner": LookupKind.LIR,
    "rdns": LookupKind.RDNS,
    "ptr": LookupKind.RDNS,
    "tls": LookupKind.TLS,
    "ssl": LookupKind.TLS,
}

_TITLES: dict[LookupKind, str] = {
    LookupKind.WHOIS: "🔍 WHOIS домена",
    LookupKind.GEO: "📍 Геолокация IP",
    LookupKind.DNS: "🧭 DNS / NS домена",
    LookupKind.LIR: "🏢 Владелец IP (LIR)",
    LookupKind.RDNS: "↩️ Обратный DNS",
    LookupKind.TLS: "🔒 SSL-сертификат",
}

_FORMATTERS = {
    LookupKind.WHOIS: format_whois,
    LookupKind.GEO: format_geo,
    LookupKind.DNS: format_dns,
    LookupKind.LIR: format_ip_owner,
    LookupKind.RDNS: format_rdns,
    LookupKind.TLS: format_tls,
}

_EXAMPLES: tuple[tuple[str, str], ...] = (
    ("whois example.com", "WHOIS домена"),
    ("geo 8.8.8.8", "Геолокация IP/хоста"),
    ("dns example.com", "DNS-записи и NS-провайдер"),
    ("lir 8.8.8.8", "Владелец IP-блока (RIR/LIR)"),
    ("rdns 1.1.1.1", "Обратный DNS (PTR)"),
    ("tls example.com", "SSL-сертификат сайта"),
)


def _handlers(service: NetworkService):
    return {
        LookupKind.WHOIS: service.whois_domain,
        LookupKind.GEO: service.geolocate,
        LookupKind.DNS: service.dns_lookup,
        LookupKind.LIR: service.ip_owner,
        LookupKind.RDNS: service.reverse_dns,
        LookupKind.TLS: service.tls_cert,
    }


def _help_results() -> list[InlineQueryResultArticle]:
    results = []
    for example, description in _EXAMPLES:
        results.append(
            InlineQueryResultArticle(
                id=uuid.uuid4().hex,
                title=f"Пример: {example}",
                description=description,
                input_message_content=InputTextMessageContent(
                    message_text=(
                        f"ℹ️ Введите в поле ввода после имени бота:\n<code>{esc(example)}</code>"
                    ),
                    parse_mode="HTML",
                ),
            )
        )
    return results


@inline_router.inline_query()
async def on_inline_query(query: InlineQuery, network_service: NetworkService) -> None:
    text = query.query.strip()
    if not text:
        await query.answer(_help_results(), cache_time=300, is_personal=False)
        return

    prefix, _, rest = text.partition(" ")
    kind = _ALIASES.get(prefix.lower())
    target = rest.strip()
    if kind is None or not target:
        await query.answer(_help_results(), cache_time=60, is_personal=False)
        return

    handler = _handlers(network_service)[kind]
    try:
        result = await asyncio.wait_for(handler(target), timeout=_TIMEOUT)
    except NetworkToolError as exc:
        message = friendly_network_error(exc)
        results = [
            InlineQueryResultArticle(
                id=uuid.uuid4().hex,
                title=f"❌ Ошибка: {target}",
                description=str(exc)[:100],
                input_message_content=InputTextMessageContent(message_text=message, parse_mode="HTML"),
            )
        ]
        await query.answer(results, cache_time=5, is_personal=True)
        return
    except TimeoutError:
        results = [
            InlineQueryResultArticle(
                id=uuid.uuid4().hex,
                title="⏳ Слишком долго, попробуйте в чате с ботом",
                description=target,
                input_message_content=InputTextMessageContent(
                    message_text=f"⏳ Запрос занял слишком много времени: <code>{esc(target)}</code>",
                    parse_mode="HTML",
                ),
            )
        ]
        await query.answer(results, cache_time=5, is_personal=True)
        return

    text_result = _FORMATTERS[kind](result)
    results = [
        InlineQueryResultArticle(
            id=uuid.uuid4().hex,
            title=f"{_TITLES[kind]}: {target}",
            description="Отправить результат в чат",
            input_message_content=InputTextMessageContent(message_text=text_result, parse_mode="HTML"),
        )
    ]
    await query.answer(results, cache_time=30, is_personal=True)
