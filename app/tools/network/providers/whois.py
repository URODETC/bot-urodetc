from __future__ import annotations

import asyncio
import logging
import re
from typing import Protocol

import httpx

from app.tools.network.errors import LookupFailedError, LookupTimeoutError, NotFoundError
from app.tools.network.models import WhoisResult

logger = logging.getLogger(__name__)

_RDAP_URL = "https://rdap.org/domain/{domain}"

_LEGACY_FIELD_PATTERNS: dict[str, re.Pattern[str]] = {
    "registrar": re.compile(r"^\s*Registrar:\s*(.+)$", re.IGNORECASE | re.MULTILINE),
    "created": re.compile(
        r"^\s*(?:Creation Date|Created On|created|Registered On)\s*:\s*(.+)$",
        re.IGNORECASE | re.MULTILINE,
    ),
    "updated": re.compile(
        r"^\s*(?:Updated Date|Last Updated On|changed|Last Modified)\s*:\s*(.+)$",
        re.IGNORECASE | re.MULTILINE,
    ),
    "expires": re.compile(
        r"^\s*(?:Registry Expiry Date|Expiration Date|paid-till|Expiry Date)\s*:\s*(.+)$",
        re.IGNORECASE | re.MULTILINE,
    ),
}
_LEGACY_STATUS_RE = re.compile(r"^\s*(?:Domain Status|status)\s*:\s*(.+)$", re.IGNORECASE | re.MULTILINE)
_LEGACY_NS_RE = re.compile(r"^\s*(?:Name Server|nserver)\s*:\s*(\S+)", re.IGNORECASE | re.MULTILINE)
_REFERRAL_RE = re.compile(
    r"(?:Registrar WHOIS Server|ReferralServer|refer)\s*:\s*(?:whois://)?(\S+)",
    re.IGNORECASE,
)
_IANA_WHOIS_RE = re.compile(r"^\s*whois\s*:\s*(\S+)", re.IGNORECASE | re.MULTILINE)


class WhoisProvider(Protocol):
    async def lookup(self, domain: str) -> WhoisResult: ...


class RdapWhoisProvider:
    """Domain WHOIS via the RDAP bootstrap redirector (rdap.org)."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def lookup(self, domain: str) -> WhoisResult:
        url = _RDAP_URL.format(domain=domain)
        try:
            response = await self._client.get(url, timeout=8.0, follow_redirects=True)
        except httpx.TimeoutException as exc:
            raise LookupTimeoutError("RDAP-сервер не ответил вовремя") from exc
        except httpx.HTTPError as exc:
            raise LookupFailedError(f"Ошибка RDAP-запроса: {exc}") from exc

        if response.status_code == 404:
            raise NotFoundError("RDAP недоступен для этого домена")
        if response.status_code >= 400:
            raise LookupFailedError(f"RDAP вернул код {response.status_code}")

        try:
            data = response.json()
        except ValueError as exc:
            raise LookupFailedError("RDAP вернул некорректный JSON") from exc

        return _parse_rdap_domain(data, domain)


class LegacyWhoisProvider:
    """Fallback domain WHOIS using the plain-text WHOIS protocol (port 43)."""

    def __init__(self, timeout: float = 6.0) -> None:
        self._timeout = timeout

    async def lookup(self, domain: str) -> WhoisResult:
        tld = domain.rsplit(".", 1)[-1]
        try:
            iana_text = await self._query("whois.iana.org", tld)
        except (TimeoutError, OSError) as exc:
            raise LookupTimeoutError("WHOIS-сервер IANA не ответил") from exc

        match = _IANA_WHOIS_RE.search(iana_text)
        server = match.group(1) if match else f"whois.nic.{tld}"

        try:
            raw = await self._query(server, domain)
        except (TimeoutError, OSError) as exc:
            raise LookupTimeoutError(f"WHOIS-сервер {server} не ответил") from exc

        referral = _REFERRAL_RE.search(raw)
        if referral and referral.group(1).lower() not in {server.lower(), domain.lower()}:
            try:
                deeper = await self._query(referral.group(1).rstrip("/"), domain)
                if deeper.strip():
                    raw = deeper
            except (TimeoutError, OSError):
                logger.debug("whois referral follow-up failed", extra={"server": referral.group(1)})

        if not raw.strip():
            raise NotFoundError("WHOIS не вернул данных")
        return _parse_legacy_whois(domain, raw)

    async def _query(self, server: str, query: str) -> str:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(server, 43), timeout=self._timeout
        )
        try:
            writer.write((query + "\r\n").encode())
            await writer.drain()
            chunks: list[bytes] = []
            while True:
                chunk = await asyncio.wait_for(reader.read(4096), timeout=self._timeout)
                if not chunk:
                    break
                chunks.append(chunk)
            return b"".join(chunks).decode(errors="replace")
        finally:
            writer.close()


class CompositeWhoisProvider:
    """Tries RDAP first (structured, fast) and falls back to legacy WHOIS."""

    def __init__(self, rdap: WhoisProvider, legacy: WhoisProvider) -> None:
        self._rdap = rdap
        self._legacy = legacy

    async def lookup(self, domain: str) -> WhoisResult:
        try:
            return await self._rdap.lookup(domain)
        except NotFoundError:
            logger.info("rdap unavailable, falling back to legacy whois", extra={"domain": domain})
        except (LookupFailedError, LookupTimeoutError) as exc:
            logger.info(
                "rdap lookup failed, falling back to legacy whois",
                extra={"domain": domain, "error": str(exc)},
            )
        return await self._legacy.lookup(domain)


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


def _entity_label(entity: dict[str, object]) -> str | None:
    return _vcard_value(entity, "fn") or (
        str(entity["handle"]) if entity.get("handle") else None
    )


def _find_entity(data: dict[str, object], role: str) -> dict[str, object] | None:
    for entity in data.get("entities") or []:
        if not isinstance(entity, dict):
            continue
        roles = entity.get("roles") or []
        if role in roles:
            return entity
    return None


def _parse_rdap_domain(data: dict[str, object], domain: str) -> WhoisResult:
    registrar_entity = _find_entity(data, "registrar")
    registrar = _entity_label(registrar_entity) if registrar_entity else None

    created = updated = expires = None
    for event in data.get("events") or []:
        if not isinstance(event, dict):
            continue
        action = str(event.get("eventAction") or "").lower()
        date = event.get("eventDate")
        if not isinstance(date, str):
            continue
        if action == "registration":
            created = date
        elif action in ("last changed", "last update of rdap database"):
            updated = date
        elif action == "expiration":
            expires = date

    statuses = tuple(str(s) for s in (data.get("status") or []))
    nameservers = tuple(
        str(ns.get("ldhName"))
        for ns in (data.get("nameservers") or [])
        if isinstance(ns, dict) and ns.get("ldhName")
    )

    return WhoisResult(
        domain=str(data.get("ldhName") or domain).lower(),
        source="rdap",
        registrar=registrar,
        created=created,
        updated=updated,
        expires=expires,
        statuses=statuses,
        nameservers=nameservers,
    )


def _parse_legacy_whois(domain: str, raw: str) -> WhoisResult:
    fields: dict[str, str | None] = {}
    for key, pattern in _LEGACY_FIELD_PATTERNS.items():
        match = pattern.search(raw)
        fields[key] = match.group(1).strip() if match else None

    statuses = tuple(dict.fromkeys(m.strip() for m in _LEGACY_STATUS_RE.findall(raw)))
    nameservers = tuple(dict.fromkeys(m.strip().rstrip(".") for m in _LEGACY_NS_RE.findall(raw)))

    return WhoisResult(
        domain=domain,
        source="legacy",
        registrar=fields["registrar"],
        created=fields["created"],
        updated=fields["updated"],
        expires=fields["expires"],
        statuses=statuses,
        nameservers=nameservers,
        raw_excerpt=raw.strip()[:3500] or None,
    )
