from __future__ import annotations

from typing import Protocol

import dns.asyncresolver
import dns.exception
import dns.rdatatype
import dns.resolver
import dns.reversename

from app.tools.network.errors import LookupFailedError, LookupTimeoutError, NotFoundError
from app.tools.network.models import DnsRecordSet, DnsResult, RdnsResult

_RECORD_TYPES = ("A", "AAAA", "MX", "NS", "TXT", "CNAME")

_NS_PROVIDERS: tuple[tuple[str, str], ...] = (
    ("cloudflare.com", "Cloudflare"),
    ("googledomains.com", "Google Domains"),
    ("google.com", "Google"),
    ("ns-cloud", "Google Cloud DNS"),
    ("awsdns", "Amazon Route 53"),
    ("azure-dns", "Microsoft Azure DNS"),
    ("domaincontrol.com", "GoDaddy"),
    ("registrar-servers.com", "Namecheap"),
    ("dnsimple.com", "DNSimple"),
    ("nsone.net", "NS1"),
    ("digitalocean.com", "DigitalOcean"),
    ("vercel-dns.com", "Vercel"),
    ("netlify.com", "Netlify"),
    ("ovh.net", "OVH"),
    ("hetzner.com", "Hetzner"),
    ("hetzner.de", "Hetzner"),
    ("selectel.", "Selectel"),
    ("timeweb.ru", "Timeweb"),
    ("beget.", "Beget"),
    ("reg.ru", "REG.RU"),
    ("yandex.net", "Yandex"),
    ("yandex.ru", "Yandex"),
    ("nic.ru", "RU-CENTER (Nic.ru)"),
    ("cloudns.net", "ClouDNS"),
    ("dns.ripn.net", "RIPN (.RU/.SU registry)"),
)


def classify_ns_provider(nameservers: tuple[str, ...]) -> str | None:
    lowered = [ns.lower() for ns in nameservers]
    for needle, label in _NS_PROVIDERS:
        if any(needle in ns for ns in lowered):
            return label
    return None


class DnsProvider(Protocol):
    async def lookup(self, domain: str) -> DnsResult: ...
    async def reverse(self, ip: str) -> RdnsResult: ...


class DnsPythonProvider:
    """DNS record and reverse-DNS lookups backed by dnspython."""

    def __init__(self, timeout: float = 5.0) -> None:
        self._resolver = dns.asyncresolver.Resolver()
        self._resolver.timeout = timeout
        self._resolver.lifetime = timeout

    async def lookup(self, domain: str) -> DnsResult:
        record_sets: list[DnsRecordSet] = []
        nameservers: tuple[str, ...] = ()

        for record_type in _RECORD_TYPES:
            try:
                answer = await self._resolver.resolve(domain, record_type)
            except (
                dns.resolver.NoAnswer,
                dns.resolver.NXDOMAIN,
                dns.resolver.NoNameservers,
                dns.exception.Timeout,
            ):
                continue
            except dns.exception.DNSException as exc:
                raise LookupFailedError(f"Ошибка DNS-запроса {record_type}: {exc}") from exc

            values = tuple(sorted(_stringify(rdata, record_type) for rdata in answer))
            if not values:
                continue
            record_sets.append(DnsRecordSet(record_type, values))
            if record_type == "NS":
                nameservers = values

        if not record_sets:
            raise NotFoundError("Записи DNS не найдены для этого домена")

        return DnsResult(
            domain=domain,
            records=tuple(record_sets),
            nameserver_provider=classify_ns_provider(nameservers),
            nameservers=nameservers,
        )

    async def reverse(self, ip: str) -> RdnsResult:
        try:
            rev_name = dns.reversename.from_address(ip)
            answer = await self._resolver.resolve(rev_name, "PTR")
        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.resolver.NoNameservers):
            raise NotFoundError("PTR-запись не найдена для этого IP") from None
        except dns.exception.Timeout as exc:
            raise LookupTimeoutError("DNS-сервер не ответил вовремя") from exc
        except dns.exception.DNSException as exc:
            raise LookupFailedError(f"Ошибка обратного DNS-запроса: {exc}") from exc

        hostnames = tuple(str(rdata).rstrip(".") for rdata in answer)
        return RdnsResult(ip=ip, hostnames=hostnames)


def _stringify(rdata: object, record_type: str) -> str:
    if record_type == "TXT":
        strings = getattr(rdata, "strings", None)
        if strings:
            return b"".join(strings).decode(errors="replace")
    text = str(rdata)
    return text.rstrip(".") if record_type in ("NS", "MX", "CNAME") else text
