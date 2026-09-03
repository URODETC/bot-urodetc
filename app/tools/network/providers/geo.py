from __future__ import annotations

from typing import Protocol

import httpx

from app.tools.network.errors import LookupFailedError, LookupTimeoutError, NotFoundError
from app.tools.network.models import GeoResult

_URL = "http://ip-api.com/json/{target}"
_FIELDS = (
    "status,message,country,countryCode,region,regionName,city,zip,"
    "lat,lon,timezone,isp,org,as,query"
)


class GeoProvider(Protocol):
    async def geolocate(self, target: str) -> GeoResult: ...


class IpApiGeoProvider:
    """IP/host geolocation via the free ip-api.com JSON API."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def geolocate(self, target: str) -> GeoResult:
        try:
            response = await self._client.get(
                _URL.format(target=target),
                params={"fields": _FIELDS},
                timeout=8.0,
            )
        except httpx.TimeoutException as exc:
            raise LookupTimeoutError("Сервис геолокации не ответил вовремя") from exc
        except httpx.HTTPError as exc:
            raise LookupFailedError(f"Ошибка запроса геолокации: {exc}") from exc

        try:
            data = response.json()
        except ValueError as exc:
            raise LookupFailedError("Сервис геолокации вернул некорректный ответ") from exc

        if data.get("status") != "success":
            raise NotFoundError(str(data.get("message") or "Не удалось определить геопозицию"))

        return GeoResult(
            query=target,
            ip=str(data.get("query") or target),
            country=data.get("country"),
            country_code=data.get("countryCode"),
            region=data.get("regionName"),
            city=data.get("city"),
            zip_code=data.get("zip"),
            lat=data.get("lat"),
            lon=data.get("lon"),
            timezone=data.get("timezone"),
            isp=data.get("isp"),
            org=data.get("org"),
            asn=data.get("as"),
        )
