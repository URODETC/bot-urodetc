from __future__ import annotations

import html

from app.tools.network.errors import (
    LookupFailedError,
    LookupTimeoutError,
    NetworkToolError,
    NotFoundError,
    ValidationError,
)
from app.tools.network.models import (
    DnsResult,
    GeoResult,
    HttpCheckResult,
    IpOwnerResult,
    MtrResult,
    PingResult,
    RdnsResult,
    TlsResult,
    WhoisResult,
)
from app.tools.video.errors import (
    AuthRequiredError,
    DiskFullError,
    DownloadError,
    ExtractionError,
    FfmpegMissingError,
    FileTooLargeError,
    NoFormatsError,
    RateLimitError,
    TemporaryError,
    UrlValidationError,
    VideoError,
    VideoUnavailableError,
)


def esc(text: str) -> str:
    return html.escape(text, quote=False)


def human_size(size: int | None) -> str:
    if size is None:
        return "размер неизвестен"
    mb = size / 1024 / 1024
    if mb >= 1024:
        return f"{mb / 1024:.2f} ГБ"
    return f"{mb:.1f} МБ"


def human_size_mb(size: int | None) -> str:
    if size is None:
        return "?"
    return f"{size / 1024 / 1024:.0f} МБ"


def format_duration(seconds: int | None) -> str:
    if not seconds:
        return "—"
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def friendly_error(exc: Exception) -> str:
    mapping: dict[type[VideoError], str] = {
        UrlValidationError: "🔗 Ссылка не похожа на YouTube. Пример: /download https://youtu.be/…",
        AuthRequiredError: "🔐 YouTube запросил подтверждение входа. Убедитесь, что сервис potoken запущен (bgutil, порт 4416) и POTOKEN_HTTP_URL задан, либо подключите cookies.txt.",
        VideoUnavailableError: "😕 Видео недоступно (удалено, приватное или недоступно в вашем регионе).",
        NoFormatsError: "🎞️ Не удалось подобрать формат для скачивания.",
        ExtractionError: "🤔 Не удалось получить информацию о видео.",
        DownloadError: "❌ Не удалось скачать файл.",
        TemporaryError: "⏳ Временная ошибка, попробуйте позже.",
        RateLimitError: "🚦 Слишком много запросов к YouTube, попробуйте позже.",
        DiskFullError: "💾 Недостаточно места на диске сервера.",
        FileTooLargeError: "⚠️ ",
        FfmpegMissingError: "🔧 Для аудио требуется FFmpeg на сервере.",
    }
    for error_type, message in mapping.items():
        if isinstance(exc, error_type):
            if isinstance(exc, FileTooLargeError):
                return message + esc(str(exc))[:300]
            return message
    return f"❌ {esc(str(exc))[:500]}"


def friendly_network_error(exc: Exception) -> str:
    mapping: dict[type[NetworkToolError], str] = {
        ValidationError: "🔗 ",
        NotFoundError: "😕 ",
        LookupTimeoutError: "⏳ Сервер не ответил вовремя, попробуйте ещё раз.",
        LookupFailedError: "❌ ",
    }
    for error_type, prefix in mapping.items():
        if isinstance(exc, error_type):
            if error_type is LookupTimeoutError:
                return prefix
            return prefix + esc(str(exc))[:400]
    return f"❌ {esc(str(exc))[:400]}"


def format_whois(result: WhoisResult) -> str:
    lines = [f"🔍 <b>WHOIS: {esc(result.domain)}</b>", ""]
    lines.append(f"🏛 Регистратор: <b>{esc(result.registrar or '—')}</b>")
    lines.append(f"📅 Создан: {esc(result.created or '—')}")
    lines.append(f"🔄 Обновлён: {esc(result.updated or '—')}")
    lines.append(f"⌛ Истекает: {esc(result.expires or '—')}")
    if result.statuses:
        lines.append(f"🚦 Статус: {esc(', '.join(result.statuses[:4]))}")
    if result.nameservers:
        lines.append(f"🧭 NS: {esc(', '.join(result.nameservers[:6]))}")
    lines.append("")
    lines.append(f"<i>Источник: {'RDAP' if result.source == 'rdap' else 'WHOIS'}</i>")
    if result.raw_excerpt and result.source == "legacy":
        lines.append("")
        lines.append(f"<pre>{esc(result.raw_excerpt[:2500])}</pre>")
    return "\n".join(lines)


def format_geo(result: GeoResult) -> str:
    lines = [f"📍 <b>Геолокация: {esc(result.ip)}</b>", ""]
    place = ", ".join(filter(None, [result.city, result.region, result.country]))
    lines.append(f"🌍 Место: <b>{esc(place or '—')}</b>")
    lines.append(f"🗺 Координаты: {_coords(result.lat, result.lon)}")
    lines.append(f"🕒 Часовой пояс: {esc(result.timezone or '—')}")
    lines.append(f"📡 Провайдер: {esc(result.isp or '—')}")
    lines.append(f"🏢 Организация: {esc(result.org or '—')}")
    lines.append(f"🔢 AS: {esc(result.asn or '—')}")
    return "\n".join(lines)


def format_dns(result: DnsResult) -> str:
    lines = [f"🧭 <b>DNS: {esc(result.domain)}</b>", ""]
    if result.nameserver_provider:
        lines.append(f"🏷 DNS-провайдер: <b>{esc(result.nameserver_provider)}</b>")
    for record in result.records:
        values = ", ".join(record.values[:8])
        lines.append(f"<b>{esc(record.record_type)}</b>: {esc(values)}")
    return "\n".join(lines)


def format_ip_owner(result: IpOwnerResult) -> str:
    lines = [f"🏢 <b>Владелец IP: {esc(result.query)}</b>", ""]
    lines.append(f"👤 Организация / LIR: <b>{esc(result.lir or '—')}</b>")
    lines.append(f"📦 Диапазон сети: {esc(result.network_range or '—')}")
    lines.append(f"🏛 Регистратура (RIR): {esc(result.rir or '—')}")
    lines.append(f"🌍 Страна: {esc(result.country or '—')}")
    if result.isp:
        lines.append(f"📡 ISP: {esc(result.isp)}")
    if result.asn:
        lines.append(f"🔢 AS: {esc(result.asn)}")
    if result.entities:
        lines.append("")
        lines.append("<b>Контакты:</b>")
        for entity in result.entities[:6]:
            label = entity.name or entity.handle or "—"
            roles = ", ".join(entity.roles) or "—"
            lines.append(f"• {esc(label)} <i>({esc(roles)})</i>")
    return "\n".join(lines)


def format_rdns(result: RdnsResult) -> str:
    lines = [f"↩️ <b>Обратный DNS: {esc(result.ip)}</b>", ""]
    if result.hostnames:
        for hostname in result.hostnames:
            lines.append(f"• {esc(hostname)}")
    else:
        lines.append("Записи PTR не найдены.")
    return "\n".join(lines)


def format_tls(result: TlsResult) -> str:
    lines = [f"🔒 <b>TLS-сертификат: {esc(result.host)}</b>", ""]
    lines.append(f"🏛 Издатель: {esc(result.issuer or '—')}")
    lines.append(f"👤 Владелец: {esc(result.subject or '—')}")
    lines.append(f"📅 Действителен с: {esc(result.valid_from or '—')}")
    lines.append(f"⌛ Действителен до: {esc(result.valid_until or '—')}")
    if result.days_left is not None:
        warn = "⚠️ " if result.days_left < 14 else ""
        lines.append(f"{warn}Осталось дней: <b>{result.days_left}</b>")
    if result.san:
        lines.append(f"🌐 SAN: {esc(', '.join(result.san[:8]))}")
    return "\n".join(lines)


def format_ping(result: PingResult) -> str:
    state = "✅ Доступен" if result.received else "❌ Нет ответа"
    lines = [f"📡 <b>Ping: {esc(result.host)}</b>", "", state, f"🌐 IP: <code>{esc(result.ip)}</code>"]
    lines.append(f"📦 Пакеты: {result.received}/{result.transmitted}, потери {result.packet_loss:g}%")
    if result.avg_ms is not None:
        lines.append(f"⏱ min/avg/max: {result.min_ms:.1f}/{result.avg_ms:.1f}/{result.max_ms:.1f} ms")
    lines.append("\n<i>Проверено с текущего сервера бота.</i>")
    return "\n".join(lines)


def format_http_check(result: HttpCheckResult) -> str:
    state = "✅ Сервер отвечает" if result.reachable else "⚠️ Сервер вернул ошибку"
    lines = [f"🌐 <b>HTTP-проверка</b>", "", state]
    lines.append(f"Код: <b>{result.status_code} {esc(result.reason)}</b>")
    lines.append(f"⏱ Ответ: <b>{result.elapsed_ms:.0f} ms</b>")
    lines.append(f"↪️ Переадресаций: {result.redirects}")
    lines.append(f"🔗 Итоговый URL: {esc(result.final_url)}")
    if result.server:
        lines.append(f"🖥 Сервер: {esc(result.server)}")
    if result.content_type:
        lines.append(f"📄 Content-Type: {esc(result.content_type)}")
    lines.append("\n<i>Проверено с текущего сервера бота.</i>")
    return "\n".join(lines)


def format_mtr(result: MtrResult) -> str:
    lines = [f"🛣 <b>MTR: {esc(result.host)}</b>", f"Цель: <code>{esc(result.ip)}</code>", "", "<pre>Hop  Узел                 Avg      Loss"]
    for hop in result.hops[:20]:
        host = hop.host if len(hop.host) <= 20 else hop.host[:19] + "…"
        avg = f"{hop.avg_ms:.1f}ms" if hop.avg_ms is not None else "—"
        loss = f"{hop.loss_percent:g}%" if hop.loss_percent is not None else "—"
        lines.append(f"{hop.number:>3}  {esc(host):<20} {avg:>8} {loss:>8}")
    lines.append("</pre>\n<i>Маршрут измерен с текущего сервера бота.</i>")
    return "\n".join(lines)


def _coords(lat: float | None, lon: float | None) -> str:
    if lat is None or lon is None:
        return "—"
    return f"{lat:.4f}, {lon:.4f}"
