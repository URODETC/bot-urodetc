from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Protocol
from urllib.parse import quote

import httpx

from app.tools.vpn.errors import (
    VpnAuthenticationError,
    VpnConfigurationError,
    VpnExternalServiceError,
    VpnNotFoundError,
    VpnRateLimitError,
    VpnTemporaryError,
)
from app.tools.vpn.models import (
    CreateVpnUser,
    VpnNodeLoad,
    VpnSystemStats,
    VpnUser,
)


class VpnProvider(Protocol):
    async def create_user(self, request: CreateVpnUser) -> VpnUser: ...

    async def extend_user(self, username: str, days: int) -> VpnUser: ...

    async def list_users(self) -> list[VpnUser]: ...

    async def get_user_usage(
        self,
        user: VpnUser,
        start: date,
        end: date,
    ) -> int: ...

    async def get_nodes(self) -> list[VpnNodeLoad]: ...

    async def get_system_stats(self) -> VpnSystemStats: ...


class RemnawaveHttpProvider:
    """HTTP provider for the official Remnawave 2.x and 3.x REST contracts."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        base_url: str | None,
        token: str | None,
        api_major: int = 3,
        caddy_token: str | None = None,
    ) -> None:
        self._client = client
        self._base_url = (base_url or "").rstrip("/")
        self._token = token or ""
        self._api_major = api_major
        self._caddy_token = caddy_token

    async def create_user(self, request: CreateVpnUser) -> VpnUser:
        payload: dict[str, Any] = {
            "username": request.username,
            "expireAt": _iso(request.expire_at),
            "trafficLimitBytes": request.traffic_limit_bytes,
            "trafficLimitStrategy": "NO_RESET",
            "activeInternalSquads": list(request.active_internal_squads),
        }
        if request.telegram_id is not None:
            payload["telegramId"] = request.telegram_id
        if request.description:
            payload["description"] = request.description
        data = await self._request("POST", "/api/users", json=payload)
        return _parse_user(_unwrap(data))

    async def extend_user(self, username: str, days: int) -> VpnUser:
        user_data = _unwrap(
            await self._request(
                "GET",
                f"/api/users/by-username/{quote(username, safe='')}",
            )
        )
        user = _parse_user(user_data)
        if self._api_major >= 3:
            updated = await self._request(
                "POST",
                f"/api/users/{user.id}/actions/extend",
                json={"days": days},
            )
            return _parse_user(_unwrap(updated))

        base = max(user.expire_at, datetime.now(timezone.utc))
        payload: dict[str, Any] = {
            "uuid": user.uuid,
            "expireAt": _iso(base + timedelta(days=days)),
        }
        if user.status.upper() == "EXPIRED":
            payload["status"] = "ACTIVE"
        updated = await self._request("PATCH", "/api/users", json=payload)
        return _parse_user(_unwrap(updated))

    async def list_users(self) -> list[VpnUser]:
        if self._api_major >= 3:
            return await self._list_users_v3()
        return await self._list_users_v2()

    async def _list_users_v3(self) -> list[VpnUser]:
        users: list[VpnUser] = []
        cursor: int | None = None
        while True:
            params: dict[str, Any] = {"size": 1000}
            if cursor is not None:
                params["cursor"] = cursor
            page = _unwrap(await self._request("GET", "/api/users/stream", params=params))
            users.extend(_parse_user(item) for item in _list(page, "users"))
            if not page.get("hasMore"):
                return users
            raw_cursor = page.get("nextCursor")
            if raw_cursor is None:
                raise VpnExternalServiceError("Remnawave не вернул курсор следующей страницы")
            cursor = int(raw_cursor)

    async def _list_users_v2(self) -> list[VpnUser]:
        users: list[VpnUser] = []
        start = 0
        size = 500
        while True:
            page = _unwrap(
                await self._request(
                    "GET",
                    "/api/users",
                    params={"start": start, "size": size},
                )
            )
            batch = _list(page, "users")
            users.extend(_parse_user(item) for item in batch)
            total = _integer(page.get("total"), len(users))
            if len(users) >= total or not batch:
                return users
            start += len(batch)

    async def get_user_usage(
        self,
        user: VpnUser,
        start: date,
        end: date,
    ) -> int:
        identifier: int | str
        if self._api_major >= 3:
            identifier = user.id
        elif user.uuid:
            identifier = user.uuid
        else:
            raise VpnExternalServiceError(
                f"У пользователя {user.username} нет UUID для Remnawave 2.x"
            )
        payload = _unwrap(
            await self._request(
                "GET",
                f"/api/bandwidth-stats/users/{identifier}",
                params={
                    "start": start.isoformat(),
                    "end": end.isoformat(),
                    "topNodesLimit": 20,
                },
            )
        )
        return sum(_integer(value) for value in payload.get("sparklineData", []))

    async def get_nodes(self) -> list[VpnNodeLoad]:
        data = _unwrap(await self._request("GET", "/api/nodes"))
        if not isinstance(data, list):
            raise VpnExternalServiceError("Некорректный список узлов Remnawave")
        return [_parse_node(item) for item in data if isinstance(item, dict)]

    async def get_system_stats(self) -> VpnSystemStats:
        data = _unwrap(await self._request("GET", "/api/system/stats"))
        users = _mapping(data.get("users"))
        online = _mapping(data.get("onlineStats"))
        nodes = _mapping(data.get("nodes"))
        memory = _mapping(data.get("memory"))
        return VpnSystemStats(
            total_users=_integer(users.get("totalUsers")),
            users_online=_integer(online.get("onlineNow")),
            nodes_online=_integer(nodes.get("totalOnline")),
            lifetime_traffic_bytes=_integer(nodes.get("totalBytesLifetime")),
            panel_memory_used_bytes=_integer(memory.get("used")),
            panel_memory_total_bytes=_integer(memory.get("total")),
        )

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        if not self._base_url or not self._token:
            raise VpnConfigurationError(
                "Задайте REMNAWAVE_URL и REMNAWAVE_TOKEN в окружении бота"
            )
        headers = dict(kwargs.pop("headers", {}))
        headers["Authorization"] = (
            self._token if self._token.startswith("Bearer ") else f"Bearer {self._token}"
        )
        if self._caddy_token:
            headers["X-Api-Key"] = self._caddy_token
        try:
            response = await self._client.request(
                method,
                f"{self._base_url}{path}",
                headers=headers,
                **kwargs,
            )
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise VpnTemporaryError("Панель Remnawave временно недоступна") from exc

        if response.status_code in (401, 403):
            raise VpnAuthenticationError(
                "Remnawave отклонил API-токен или ему не хватает прав"
            )
        if response.status_code == 404:
            raise VpnNotFoundError("Пользователь или endpoint Remnawave не найден")
        if response.status_code == 429:
            raise VpnRateLimitError("Remnawave ограничил частоту запросов")
        if response.status_code >= 500:
            raise VpnTemporaryError("Remnawave вернул временную серверную ошибку")
        if response.is_error:
            detail = _error_detail(response)
            raise VpnExternalServiceError(f"Remnawave отклонил запрос: {detail}")
        if response.status_code == 204 or not response.content:
            return None
        try:
            return response.json()
        except ValueError as exc:
            raise VpnExternalServiceError("Remnawave вернул некорректный JSON") from exc


def _parse_user(data: Any) -> VpnUser:
    item = _mapping(data)
    traffic = _mapping(item.get("userTraffic"))
    try:
        expire_at = _datetime(item["expireAt"])
        return VpnUser(
            id=_integer(item["id"]),
            uuid=str(item["uuid"]) if item.get("uuid") else None,
            username=str(item["username"]),
            status=str(item["status"]),
            expire_at=expire_at,
            traffic_limit_bytes=_integer(item.get("trafficLimitBytes")),
            used_traffic_bytes=_integer(traffic.get("usedTrafficBytes")),
            lifetime_used_traffic_bytes=_integer(
                traffic.get("lifetimeUsedTrafficBytes")
            ),
            subscription_url=str(item.get("subscriptionUrl") or ""),
            telegram_id=(
                _integer(item["telegramId"]) if item.get("telegramId") is not None else None
            ),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise VpnExternalServiceError("Некорректные данные пользователя Remnawave") from exc


def _parse_node(data: dict[str, Any]) -> VpnNodeLoad:
    system = _mapping(data.get("system"))
    info = _mapping(system.get("info"))
    stats = _mapping(system.get("stats"))
    interface = _mapping(stats.get("interface"))
    loads = stats.get("loadAvg")
    load_1m = float(loads[0]) if isinstance(loads, list) and loads else None
    return VpnNodeLoad(
        name=str(data.get("name") or "Без имени"),
        connected=bool(data.get("isConnected")),
        users_online=_integer(data.get("usersOnline")),
        cpu_count=_optional_integer(info.get("cpus")),
        load_average_1m=load_1m,
        memory_used_bytes=_optional_integer(stats.get("memoryUsed")),
        memory_total_bytes=_optional_integer(info.get("memoryTotal")),
        rx_bytes_per_second=_optional_integer(interface.get("rxBytesPerSec")),
        tx_bytes_per_second=_optional_integer(interface.get("txBytesPerSec")),
    )


def _unwrap(data: Any) -> Any:
    if isinstance(data, dict) and "response" in data:
        return data["response"]
    return data


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any, key: str) -> list[dict[str, Any]]:
    items = _mapping(value).get(key, [])
    if not isinstance(items, list):
        raise VpnExternalServiceError(f"Remnawave вернул некорректное поле {key}")
    return [item for item in items if isinstance(item, dict)]


def _integer(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    return int(float(value))


def _optional_integer(value: Any) -> int | None:
    return None if value is None else _integer(value)


def _datetime(value: Any) -> datetime:
    result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)
    return result


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _error_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.reason_phrase or f"HTTP {response.status_code}"
    if isinstance(payload, dict):
        detail = payload.get("message") or payload.get("error") or payload.get("detail")
        if isinstance(detail, list):
            return "; ".join(str(item) for item in detail)[:300]
        if detail:
            return str(detail)[:300]
    return response.reason_phrase or f"HTTP {response.status_code}"
