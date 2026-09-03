from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class LookupKind(StrEnum):
    WHOIS = "whois"
    GEO = "geo"
    DNS = "dns"
    LIR = "lir"
    RDNS = "rdns"
    TLS = "tls"


@dataclass(frozen=True)
class WhoisResult:
    domain: str
    source: str  # "rdap" or "legacy"
    registrar: str | None = None
    created: str | None = None
    updated: str | None = None
    expires: str | None = None
    statuses: tuple[str, ...] = ()
    nameservers: tuple[str, ...] = ()
    raw_excerpt: str | None = None


@dataclass(frozen=True)
class GeoResult:
    query: str
    ip: str
    country: str | None
    country_code: str | None
    region: str | None
    city: str | None
    zip_code: str | None
    lat: float | None
    lon: float | None
    timezone: str | None
    isp: str | None
    org: str | None
    asn: str | None


@dataclass(frozen=True)
class DnsRecordSet:
    record_type: str
    values: tuple[str, ...]


@dataclass(frozen=True)
class DnsResult:
    domain: str
    records: tuple[DnsRecordSet, ...]
    nameserver_provider: str | None
    nameservers: tuple[str, ...]


@dataclass(frozen=True)
class IpEntity:
    name: str | None
    handle: str | None
    roles: tuple[str, ...]
    country: str | None


@dataclass(frozen=True)
class IpOwnerResult:
    query: str
    ip: str
    network_range: str | None
    rir: str | None
    country: str | None
    entities: tuple[IpEntity, ...] = ()
    isp: str | None = None
    asn: str | None = None

    @property
    def lir(self) -> str | None:
        for entity in self.entities:
            if entity.name:
                return entity.name
        return None


@dataclass(frozen=True)
class RdnsResult:
    ip: str
    hostnames: tuple[str, ...]


@dataclass(frozen=True)
class TlsResult:
    host: str
    port: int
    issuer: str | None
    subject: str | None
    valid_from: str | None
    valid_until: str | None
    san: tuple[str, ...] = ()
    days_left: int | None = None
