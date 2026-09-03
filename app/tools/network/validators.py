from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlsplit, urlunsplit

from app.tools.network.errors import ValidationError

_DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)(?!-)[a-zA-Z0-9-]{1,63}(?<!-)"
    r"(\.(?!-)[a-zA-Z0-9-]{1,63}(?<!-))+\.?$"
)

_STRIP_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://")


def clean_target(raw: str) -> str:
    value = raw.strip()
    value = _STRIP_SCHEME_RE.sub("", value)
    value = value.split("/", 1)[0]
    value = value.split("?", 1)[0]
    value = value.split(":", 1)[0] if value.count(":") == 1 and "." in value else value
    return value.strip().rstrip(".")


def is_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False


def is_domain(value: str) -> bool:
    try:
        ascii_value = value.encode("idna").decode("ascii")
    except (UnicodeError, UnicodeDecodeError):
        ascii_value = value
    return bool(_DOMAIN_RE.match(ascii_value)) and "." in ascii_value


def to_ascii_domain(value: str) -> str:
    try:
        return value.encode("idna").decode("ascii")
    except (UnicodeError, UnicodeDecodeError):
        return value


def require_domain(raw: str) -> str:
    target = clean_target(raw)
    if not is_domain(target):
        raise ValidationError(
            "Похоже, это не домен. Пример: example.com"
        )
    return to_ascii_domain(target)


def require_ip(raw: str) -> str:
    target = clean_target(raw)
    if not is_ip(target):
        raise ValidationError(
            "Похоже, это не IP-адрес. Пример: 8.8.8.8"
        )
    return target


def require_host(raw: str) -> str:
    """Accept either an IP address or a domain name (for geolocation)."""
    target = clean_target(raw)
    if is_ip(target) or is_domain(target):
        return target
    raise ValidationError(
        "Укажите IP-адрес или домен. Пример: 8.8.8.8 или example.com"
    )


def require_http_url(raw: str) -> str:
    value = raw.strip()
    if not value:
        raise ValidationError("Укажите URL. Пример: https://example.com")
    if "://" not in value:
        value = f"https://{value}"
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise ValidationError("Некорректный URL") from exc
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValidationError("Поддерживаются только HTTP(S)-ссылки")
    if parsed.username or parsed.password:
        raise ValidationError("URL с логином или паролем не поддерживается")
    hostname = parsed.hostname.encode("idna").decode("ascii")
    host = f"[{hostname}]" if ":" in hostname else hostname
    if port is not None:
        host = f"{host}:{port}"
    path = parsed.path or "/"
    return urlunsplit((parsed.scheme, host, path, parsed.query, ""))
