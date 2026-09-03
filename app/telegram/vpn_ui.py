from __future__ import annotations

from datetime import timedelta

from app.telegram.ui import esc
from app.tools.vpn.models import VpnNodeLoad, VpnUser, VpnWeeklyReport


def format_vpn_user_created(user: VpnUser) -> str:
    lines = [
        "✅ <b>VPN-пользователь создан</b>",
        "",
        f"Имя: <code>{esc(user.username)}</code>",
        f"Действует до: <b>{user.expire_at:%d.%m.%Y %H:%M}</b>",
        f"Лимит: <b>{_bytes(user.traffic_limit_bytes)}</b>",
    ]
    if user.subscription_url:
        lines.extend(("", f"🔗 {esc(user.subscription_url)}"))
    return "\n".join(lines)


def format_vpn_user_extended(user: VpnUser) -> str:
    return (
        "✅ <b>Подписка продлена</b>\n\n"
        f"Пользователь: <code>{esc(user.username)}</code>\n"
        f"Новая дата: <b>{user.expire_at:%d.%m.%Y %H:%M}</b>\n"
        f"Статус: {esc(user.status)}"
    )


def format_vpn_report(report: VpnWeeklyReport, *, top_users: int = 20) -> str:
    last_day = report.period_end - timedelta(days=1)
    system = report.system
    lines = [
        "📊 <b>Еженедельный VPN-отчёт</b>",
        f"{report.period_start:%d.%m.%Y} — {last_day:%d.%m.%Y}",
        "",
        f"Трафик за неделю: <b>{_bytes(report.total_traffic_bytes)}</b>",
        f"Трафик за всё время: {_bytes(system.lifetime_traffic_bytes)}",
        f"Пользователи: {system.total_users}, сейчас онлайн: <b>{system.users_online}</b>",
        f"Узлы онлайн: <b>{system.nodes_online}/{len(report.nodes)}</b>",
        f"RAM панели: {_ratio(system.panel_memory_used_bytes, system.panel_memory_total_bytes)}",
        "",
        f"👥 <b>Расход по пользователям (топ {top_users})</b>",
    ]
    visible = report.user_usage[:top_users]
    if visible:
        lines.extend(
            f"{index}. <code>{esc(item.username)}</code> — {_bytes(item.total_bytes)}"
            for index, item in enumerate(visible, 1)
        )
    else:
        lines.append("Нет пользователей.")
    remaining = len(report.user_usage) - len(visible)
    if remaining > 0:
        lines.append(f"…ещё пользователей: {remaining}")

    lines.extend(("", "🖥 <b>Нагрузка узлов</b>"))
    if not report.nodes:
        lines.append("Узлы не найдены.")
    else:
        lines.extend(_format_node(node) for node in report.nodes)
    return "\n".join(lines)


def split_vpn_report(
    report: VpnWeeklyReport,
    *,
    top_users: int = 20,
    limit: int = 4000,
) -> tuple[str, ...]:
    text = format_vpn_report(report, top_users=top_users)
    if len(text) <= limit:
        return (text,)
    chunks: list[str] = []
    current: list[str] = []
    current_length = 0
    for line in text.splitlines():
        added = len(line) + (1 if current else 0)
        if current and current_length + added > limit:
            chunks.append("\n".join(current))
            current = []
            current_length = 0
        current.append(line)
        current_length += len(line) + (1 if current_length else 0)
    if current:
        chunks.append("\n".join(current))
    return tuple(chunks)


def friendly_vpn_error(exc: Exception) -> str:
    return f"❌ {esc(str(exc))[:500]}"


def _format_node(node: VpnNodeLoad) -> str:
    state = "🟢" if node.connected else "🔴"
    load = "—"
    if node.load_average_1m is not None:
        if node.cpu_count:
            load = f"{node.load_average_1m:.2f}/{node.cpu_count} CPU"
        else:
            load = f"{node.load_average_1m:.2f}"
    speed = "—"
    if node.rx_bytes_per_second is not None or node.tx_bytes_per_second is not None:
        speed = (
            f"↓{_bytes(node.rx_bytes_per_second or 0)}/с "
            f"↑{_bytes(node.tx_bytes_per_second or 0)}/с"
        )
    return (
        f"{state} <b>{esc(node.name)}</b> · online {node.users_online}\n"
        f"   load {load} · RAM {_ratio(node.memory_used_bytes, node.memory_total_bytes)} · {speed}"
    )


def _bytes(value: int) -> str:
    if value <= 0:
        return "0 Б"
    units = ("Б", "КБ", "МБ", "ГБ", "ТБ", "ПБ")
    amount = float(value)
    unit = units[0]
    for unit in units:
        if amount < 1024 or unit == units[-1]:
            break
        amount /= 1024
    return f"{amount:.2f} {unit}"


def _ratio(used: int | None, total: int | None) -> str:
    if used is None or not total:
        return "—"
    percent = used / total * 100
    return f"{_bytes(used)} / {_bytes(total)} ({percent:.0f}%)"
