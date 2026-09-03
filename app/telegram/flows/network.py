from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram.types import BufferedInputFile, Message

from app.infrastructure.history import HistoryRepository
from app.telegram.menu import result_keyboard
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
from app.tools.network.infographics import render_geo_card, render_ip_owner_card
from app.tools.network.models import DnsResult, GeoResult, IpOwnerResult, LookupKind, RdnsResult, TlsResult, WhoisResult
from app.tools.network.service import NetworkService

_CAPTION_LIMIT = 1024

_FORMATTERS: dict[LookupKind, Callable[[Any], str]] = {
    LookupKind.WHOIS: format_whois,
    LookupKind.GEO: format_geo,
    LookupKind.DNS: format_dns,
    LookupKind.LIR: format_ip_owner,
    LookupKind.RDNS: format_rdns,
    LookupKind.TLS: format_tls,
}


def _handlers(service: NetworkService) -> dict[LookupKind, Callable[[str], Awaitable[Any]]]:
    return {
        LookupKind.WHOIS: service.whois_domain,
        LookupKind.GEO: service.geolocate,
        LookupKind.DNS: service.dns_lookup,
        LookupKind.LIR: service.ip_owner,
        LookupKind.RDNS: service.reverse_dns,
        LookupKind.TLS: service.tls_cert,
    }


def _summarize(kind: LookupKind, result: Any) -> str:
    if isinstance(result, WhoisResult):
        return f"{result.registrar or '—'}"
    if isinstance(result, GeoResult):
        return ", ".join(filter(None, [result.city, result.country])) or "—"
    if isinstance(result, DnsResult):
        return result.nameserver_provider or (result.records[0].record_type if result.records else "—")
    if isinstance(result, IpOwnerResult):
        return result.lir or "—"
    if isinstance(result, RdnsResult):
        return ", ".join(result.hostnames[:1]) or "—"
    if isinstance(result, TlsResult):
        return result.issuer or "—"
    return "—"


def _render_image(kind: LookupKind, result: Any) -> bytes | None:
    if kind is LookupKind.GEO and isinstance(result, GeoResult):
        return render_geo_card(result)
    if kind is LookupKind.LIR and isinstance(result, IpOwnerResult):
        return render_ip_owner_card(result)
    return None


async def perform_lookup(
    message: Message,
    *,
    service: NetworkService,
    history: HistoryRepository,
    kind: str,
    target: str,
) -> None:
    """Shared by the network menu, inline mode and (in future) other interfaces."""
    if message.from_user is None:
        return

    try:
        lookup_kind = LookupKind(kind)
    except ValueError:
        await message.answer(f"❌ Неизвестный инструмент: {esc(kind)}")
        return

    handler = _handlers(service)[lookup_kind]
    try:
        result = await handler(target)
    except NetworkToolError as exc:
        await history.add(
            user_id=message.from_user.id,
            kind=kind,
            target=target,
            summary=str(exc)[:200],
            status="failed",
            error=str(exc),
        )
        await message.answer(friendly_network_error(exc), reply_markup=result_keyboard(kind))
        return

    text = _FORMATTERS[lookup_kind](result)
    await history.add(
        user_id=message.from_user.id,
        kind=kind,
        target=target,
        summary=_summarize(lookup_kind, result),
    )

    image = _render_image(lookup_kind, result)
    if image is None:
        await message.answer(text, reply_markup=result_keyboard(kind))
        return

    caption = text if len(text) <= _CAPTION_LIMIT else None
    await message.answer_photo(
        BufferedInputFile(image, filename=f"{kind}.png"),
        caption=caption,
        reply_markup=result_keyboard(kind) if caption else None,
    )
    if caption is None:
        await message.answer(text, reply_markup=result_keyboard(kind))
