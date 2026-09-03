from __future__ import annotations

from dataclasses import replace

from app.tools.network.errors import NetworkToolError
from app.tools.network.models import DnsResult, GeoResult, IpOwnerResult, RdnsResult, TlsResult, WhoisResult
from app.tools.network.providers.dns import DnsProvider
from app.tools.network.providers.geo import GeoProvider
from app.tools.network.providers.ip_owner import IpOwnerProvider
from app.tools.network.providers.tls import TlsProvider
from app.tools.network.providers.whois import WhoisProvider
from app.tools.network.validators import require_domain, require_host, require_ip


class NetworkService:
    """Domain service orchestrating network-diagnostics providers.

    Framework-agnostic: callers (Telegram menu, inline mode, future REST/CLI)
    all go through the same methods, per the shared-business-logic principle.
    """

    def __init__(
        self,
        *,
        whois: WhoisProvider,
        geo: GeoProvider,
        dns: DnsProvider,
        ip_owner: IpOwnerProvider,
        tls: TlsProvider,
    ) -> None:
        self._whois = whois
        self._geo = geo
        self._dns = dns
        self._ip_owner = ip_owner
        self._tls = tls

    async def whois_domain(self, raw: str) -> WhoisResult:
        domain = require_domain(raw)
        return await self._whois.lookup(domain)

    async def geolocate(self, raw: str) -> GeoResult:
        host = require_host(raw)
        return await self._geo.geolocate(host)

    async def dns_lookup(self, raw: str) -> DnsResult:
        domain = require_domain(raw)
        return await self._dns.lookup(domain)

    async def ip_owner(self, raw: str) -> IpOwnerResult:
        ip = require_ip(raw)
        result = await self._ip_owner.lookup(ip)
        try:
            geo = await self._geo.geolocate(ip)
        except NetworkToolError:
            return result
        return replace(
            result,
            isp=geo.isp,
            asn=geo.asn,
            country=result.country or geo.country,
        )

    async def reverse_dns(self, raw: str) -> RdnsResult:
        ip = require_ip(raw)
        return await self._dns.reverse(ip)

    async def tls_cert(self, raw: str) -> TlsResult:
        domain = require_domain(raw)
        return await self._tls.fetch(domain)
