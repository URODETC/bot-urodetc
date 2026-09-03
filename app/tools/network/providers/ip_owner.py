from __future__ import annotations

from typing import Protocol

import httpx

from app.tools.network.errors import LookupFailedError, LookupTimeoutError, NotFoundError
from app.tools.network.models import IpEntity, IpOwnerResult

_URL = "https://rdap.org/ip/{ip}"

_RIR_HOSTS: tuple[tuple[str, str], ...] = (
    ("rdap.arin.net", "ARIN"),
    ("rdap.db.ripe.net", "RIPE NCC"),
    ("rdap.apnic.net", "APNIC"),
    ("rdap.lacnic.net", "LACNIC"),
    ("rdap.afrinic.net", "AFRINIC"),
)


class IpOwnerProvider(Protocol):
    async def lookup(self, ip: str) -> IpOwnerResult: ...


class RdapIpOwnerProvider:
    """IP allocation / ownership (LIR) lookup via RDAP bootstrap redirector."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def lookup(self, ip: str) -> IpOwnerResult:
        try:
            response = await self._client.get(
                _URL.format(ip=ip), timeout=8.0, follow_redirects=True
            )
        except httpx.TimeoutException as exc:
            raise LookupTimeoutError("RDAP-сервер не ответил вовремя") from exc
        except httpx.HTTPError as exc:
            raise LookupFailedError(f"Ошибка RDAP-запроса: {exc}") from exc

        if response.status_code == 404:
            raise NotFoundError("Данные о владельце этого IP не найдены")
        if response.status_code >= 400:
            raise LookupFailedError(f"RDAP вернул код {response.status_code}")

        try:
            data = response.json()
        except ValueError as exc:
            raise LookupFailedError("RDAP вернул некорректный JSON") from exc

        return _parse_rdap_ip(data, ip, str(response.url))


def _network_range(data: dict[str, object]) -> str | None:
    cidrs = data.get("cidr0_cidrs")
    if isinstance(cidrs, list) and cidrs:
        parts = []
        for cidr in cidrs:
            if isinstance(cidr, dict) and cidr.get("v4prefix"):
                parts.append(f"{cidr['v4prefix']}/{cidr.get('length')}")
            elif isinstance(cidr, dict) and cidr.get("v6prefix"):
                parts.append(f"{cidr['v6prefix']}/{cidr.get('length')}")
        if parts:
            return ", ".join(parts)
    start, end = data.get("startAddress"), data.get("endAddress")
    if start and end:
        return f"{start} - {end}"
    return None


def _guess_rir(response_url: str) -> str | None:
    for host, label in _RIR_HOSTS:
        if host in response_url:
            return label
    return None


def _vcard_value(entity: dict[str, object], key: str) -> str | None:
    vcard = entity.get("vcardArray")
    if not isinstance(vcard, list) or len(vcard) < 2:
        return None
    fields = vcard[1]
    if not isinstance(fields, list):
        return None
    for item in fields:
        if isinstance(item, list) and len(item) >= 4 and item[0] == key:
            value = item[3]
            if isinstance(value, str):
                return value
    return None


def _entity_from(raw: dict[str, object]) -> IpEntity:
    name = _vcard_value(raw, "fn")
    return IpEntity(
        name=name,
        handle=str(raw["handle"]) if raw.get("handle") else None,
        roles=tuple(str(r) for r in (raw.get("roles") or [])),
        country=_vcard_value(raw, "adr"),
    )


def _collect_entities(data: dict[str, object]) -> tuple[IpEntity, ...]:
    entities: list[IpEntity] = []
    for raw in data.get("entities") or []:
        if isinstance(raw, dict):
            entities.append(_entity_from(raw))
            for nested in raw.get("entities") or []:
                if isinstance(nested, dict):
                    entities.append(_entity_from(nested))
    # Prioritise registrant/owner-like roles first, so `.lir` picks them up.
    priority = {"registrant": 0, "owner": 0, "administrative": 1, "technical": 2, "abuse": 3}
    entities.sort(key=lambda e: min((priority.get(r, 4) for r in e.roles), default=4))
    return tuple(entities)


def _parse_rdap_ip(data: dict[str, object], ip: str, response_url: str) -> IpOwnerResult:
    return IpOwnerResult(
        query=ip,
        ip=str(data.get("handle") or ip),
        network_range=_network_range(data),
        rir=_guess_rir(response_url),
        country=data.get("country") if isinstance(data.get("country"), str) else None,
        entities=_collect_entities(data),
    )
