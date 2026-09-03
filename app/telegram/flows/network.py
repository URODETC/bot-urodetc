from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram.types import BufferedInputFile, Message

from app.infrastructure.history import HistoryRepository
from app.telegram.loading import LoadingIndicator
from app.telegram.menu import result_keyboard
from app.telegram.ui import (
    esc,
    format_dns,
    format_geo,
    format_http_check,
    format_ip_owner,
    format_mtr,
    format_ping,
    format_rdns,
    format_tls,
    format_whois,
    friendly_network_error,
)
from app.tools.network.errors import NetworkToolError
from app.tools.network.infographics import (
    render_geo_card,
    render_http_card,
    render_ip_owner_card,
    render_mtr_card,
    render_ping_card,
)
from app.tools.network.models import (
    DnsResult,
    GeoResult,
    HttpCheckResult,
    IpOwnerResult,
    LookupKind,
    MtrResult,
    PingResult,
    RdnsResult,
    TlsResult,
    WhoisResult,
)
from app.tools.network.service import NetworkService

_CAPTION_LIMIT = 1024

_FORMATTERS: dict[type[Any], Callable[[Any], str]] = {
    WhoisResult: format_whois,
    GeoResult: format_geo,
    DnsResult: format_dns,
    IpOwnerResult: format_ip_owner,
    RdnsResult: format_rdns,
    TlsResult: format_tls,
    PingResult: format_ping,
    HttpCheckResult: format_http_check,
    MtrResult: format_mtr,
}


def _handlers(service: NetworkService) -> dict[LookupKind, Callable[[str], Awaitable[Any]]]:
    return {
        LookupKind.WHOIS: service.whois,
        LookupKind.GEO: service.geolocate,
        LookupKind.DNS: service.ip_lookup,
        LookupKind.LIR: service.ip_owner,
        LookupKind.RDNS: service.reverse_dns,
        LookupKind.TLS: service.tls_cert,
        LookupKind.PING: service.ping,
        LookupKind.CHECK: service.check_http,
        LookupKind.MTR: service.mtr,
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
    if isinstance(result, PingResult):
        return f"loss {result.packet_loss:g}%, avg {result.avg_ms or 0:.1f} ms"
    if isinstance(result, HttpCheckResult):
        return f"HTTP {result.status_code}, {result.elapsed_ms:.0f} ms"
    if isinstance(result, MtrResult):
        return f"{len(result.hops)} hops"
    return "—"


def _render_image(kind: LookupKind, result: Any) -> bytes | None:
    if kind is LookupKind.GEO and isinstance(result, GeoResult):
        return render_geo_card(result)
    if kind is LookupKind.LIR and isinstance(result, IpOwnerResult):
        return render_ip_owner_card(result)
    if isinstance(result, IpOwnerResult):
        return render_ip_owner_card(result)
    if isinstance(result, PingResult):
        return render_ping_card(result)
    if isinstance(result, HttpCheckResult):
        return render_http_card(result)
    if isinstance(result, MtrResult):
        return render_mtr_card(result)
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
        async with LoadingIndicator(message, "Проверяю"):
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

    text = _FORMATTERS[type(result)](result)
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
