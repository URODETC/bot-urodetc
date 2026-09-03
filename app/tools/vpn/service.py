from __future__ import annotations

import asyncio
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.tools.vpn.errors import VpnConfigurationError, VpnValidationError
from app.tools.vpn.models import (
    CreateVpnUser,
    VpnUser,
    VpnUserUsage,
    VpnWeeklyReport,
)
from app.tools.vpn.provider import VpnProvider

USERNAME_RE = re.compile(r"^[a-zA-Z0-9_-]{3,36}$")
GIB = 1024**3


class VpnService:
    def __init__(
        self,
        provider: VpnProvider,
        *,
        default_squad_uuids: tuple[str, ...] = (),
        default_duration_days: int = 30,
        default_traffic_gb: int = 0,
        report_timezone: str = "Europe/Moscow",
        report_concurrency: int = 8,
    ) -> None:
        self._provider = provider
        self._default_squad_uuids = default_squad_uuids
        self._default_duration_days = default_duration_days
        self._default_traffic_gb = default_traffic_gb
        self._report_concurrency = max(1, report_concurrency)
        try:
            self._report_tz = ZoneInfo(report_timezone)
        except ZoneInfoNotFoundError as exc:
            raise VpnConfigurationError(
                f"Неизвестный часовой пояс отчётов: {report_timezone}"
            ) from exc

    async def create_user(
        self,
        username: str,
        *,
        days: int | None = None,
        traffic_gb: int | None = None,
        telegram_id: int | None = None,
        description: str | None = None,
        now: datetime | None = None,
    ) -> VpnUser:
        username = username.strip()
        if not USERNAME_RE.fullmatch(username):
            raise VpnValidationError(
                "Имя: 3–36 символов, только латиница, цифры, _ и -"
            )
        duration = self._default_duration_days if days is None else days
        traffic = self._default_traffic_gb if traffic_gb is None else traffic_gb
        _validate_days(duration)
        if traffic < 0 or traffic > 1_000_000:
            raise VpnValidationError("Лимит трафика должен быть от 0 до 1000000 ГБ")
        if telegram_id is not None and telegram_id <= 0:
            raise VpnValidationError("Telegram ID должен быть положительным числом")
        if not self._default_squad_uuids:
            raise VpnConfigurationError(
                "Задайте REMNAWAVE_DEFAULT_SQUAD_UUIDS: без Internal Squad "
                "пользователь не получит VPN-конфигурацию"
            )

        current = now or datetime.now(timezone.utc)
        return await self._provider.create_user(
            CreateVpnUser(
                username=username,
                expire_at=current + timedelta(days=duration),
                traffic_limit_bytes=traffic * GIB,
                telegram_id=telegram_id,
                description=description,
                active_internal_squads=self._default_squad_uuids,
            )
        )

    async def extend_user(self, username: str, days: int) -> VpnUser:
        username = username.strip()
        if not USERNAME_RE.fullmatch(username):
            raise VpnValidationError("Укажите корректное имя пользователя")
        _validate_days(days)
        return await self._provider.extend_user(username, days)

    async def weekly_report(
        self,
        *,
        now: datetime | None = None,
    ) -> VpnWeeklyReport:
        generated_at = now or datetime.now(timezone.utc)
        local_today = generated_at.astimezone(self._report_tz).date()
        period_end = local_today
        period_start = period_end - timedelta(days=7)

        users, nodes, system = await asyncio.gather(
            self._provider.list_users(),
            self._provider.get_nodes(),
            self._provider.get_system_stats(),
        )
        semaphore = asyncio.Semaphore(self._report_concurrency)

        async def usage_for(user: VpnUser) -> VpnUserUsage:
            async with semaphore:
                total = await self._provider.get_user_usage(
                    user,
                    period_start,
                    period_end,
                )
            return VpnUserUsage(username=user.username, total_bytes=total)

        usage = await asyncio.gather(*(usage_for(user) for user in users))
        ordered = tuple(sorted(usage, key=lambda item: item.total_bytes, reverse=True))
        return VpnWeeklyReport(
            period_start=period_start,
            period_end=period_end,
            generated_at=generated_at,
            total_traffic_bytes=sum(item.total_bytes for item in ordered),
            user_usage=ordered,
            nodes=tuple(sorted(nodes, key=lambda item: item.name.casefold())),
            system=system,
        )


def _validate_days(days: int) -> None:
    if days < 1 or days > 3650:
        raise VpnValidationError("Срок должен быть от 1 до 3650 дней")
