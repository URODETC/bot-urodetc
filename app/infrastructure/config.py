from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_DATABASE_URL = "sqlite+aiosqlite:///./data/bot.db"
DEFAULT_REDIS_URL = "redis://localhost:6379/0"
DEFAULT_DOWNLOAD_DIR = "./data/downloads"
DEFAULT_REMNAWAVE_REPORT_TIMEZONE = "Europe/Moscow"

MIN_BOT_API_FILE_SIZE = 50 * 1024 * 1024
MAX_LOCAL_BOT_API_FILE_SIZE = 2 * 1024 * 1024 * 1024


def _env_or(name: str, default: str) -> str:
    value = os.environ.get(name)
    return default if value in (None, "") else value


def _csv_ints(name: str) -> tuple[int, ...]:
    raw = os.environ.get(name, "")
    if not raw.strip():
        return ()
    return tuple(int(item.strip()) for item in raw.split(",") if item.strip())


def _csv_strings(name: str) -> tuple[str, ...]:
    raw = os.environ.get(name, "")
    return tuple(item.strip() for item in raw.split(",") if item.strip())


@dataclass(frozen=True)
class Settings:
    bot_token: str
    log_level: str = "INFO"
    database_url: str = DEFAULT_DATABASE_URL
    redis_url: str = DEFAULT_REDIS_URL
    download_dir: Path = Path(DEFAULT_DOWNLOAD_DIR)
    cookies_file: Path | None = None
    po_token_http_url: str | None = None
    local_api_base: str | None = None
    max_file_size_mb: int | None = None
    owner_telegram_ids: tuple[int, ...] = ()
    remnawave_url: str | None = None
    remnawave_token: str | None = None
    remnawave_caddy_token: str | None = None
    remnawave_api_major: int = 3
    remnawave_default_squad_uuids: tuple[str, ...] = ()
    remnawave_default_duration_days: int = 30
    remnawave_default_traffic_gb: int = 0
    remnawave_report_chat_ids: tuple[int, ...] = ()
    remnawave_report_weekday: str = "mon"
    remnawave_report_hour: int = 9
    remnawave_report_minute: int = 0
    remnawave_report_timezone: str = DEFAULT_REMNAWAVE_REPORT_TIMEZONE
    remnawave_report_top_users: int = 20

    @property
    def po_tokens_enabled(self) -> bool:
        return bool(self.po_token_http_url)

    @property
    def max_file_size(self) -> int:
        if self.max_file_size_mb is not None:
            return self.max_file_size_mb * 1024 * 1024
        if self.local_api_base:
            return MAX_LOCAL_BOT_API_FILE_SIZE
        return MIN_BOT_API_FILE_SIZE

    @property
    def remnawave_configured(self) -> bool:
        return bool(self.remnawave_url and self.remnawave_token)

    @property
    def vpn_report_recipients(self) -> tuple[int, ...]:
        return self.remnawave_report_chat_ids or self.owner_telegram_ids

    def is_owner(self, telegram_id: int | None) -> bool:
        return telegram_id is not None and telegram_id in self.owner_telegram_ids

    @classmethod
    def from_env(cls) -> "Settings":
        raw_max = os.environ.get("MAX_FILE_SIZE_MB")
        api_major = int(_env_or("REMNAWAVE_API_MAJOR", "3"))
        if api_major not in (2, 3):
            raise ValueError("REMNAWAVE_API_MAJOR must be 2 or 3")
        return cls(
            bot_token=os.environ["BOT_TOKEN"],
            log_level=_env_or("LOG_LEVEL", "INFO"),
            database_url=_env_or("DATABASE_URL", DEFAULT_DATABASE_URL),
            redis_url=_env_or("REDIS_URL", DEFAULT_REDIS_URL),
            download_dir=Path(os.environ.get("DOWNLOAD_DIR", DEFAULT_DOWNLOAD_DIR)),
            cookies_file=Path(os.environ["COOKIES_FILE"])
            if os.environ.get("COOKIES_FILE")
            else None,
            po_token_http_url=os.environ.get("POTOKEN_HTTP_URL") or None,
            local_api_base=_env_or("LOCAL_API_BASE", "") or None,
            max_file_size_mb=int(raw_max) if raw_max else None,
            owner_telegram_ids=_csv_ints("OWNER_TELEGRAM_IDS"),
            remnawave_url=_env_or("REMNAWAVE_URL", "").rstrip("/") or None,
            remnawave_token=_env_or("REMNAWAVE_TOKEN", "") or None,
            remnawave_caddy_token=_env_or("REMNAWAVE_CADDY_TOKEN", "") or None,
            remnawave_api_major=api_major,
            remnawave_default_squad_uuids=_csv_strings(
                "REMNAWAVE_DEFAULT_SQUAD_UUIDS"
            ),
            remnawave_default_duration_days=int(
                _env_or("REMNAWAVE_DEFAULT_DURATION_DAYS", "30")
            ),
            remnawave_default_traffic_gb=int(
                _env_or("REMNAWAVE_DEFAULT_TRAFFIC_GB", "0")
            ),
            remnawave_report_chat_ids=_csv_ints("REMNAWAVE_REPORT_CHAT_IDS"),
            remnawave_report_weekday=_env_or(
                "REMNAWAVE_REPORT_WEEKDAY", "mon"
            ).lower(),
            remnawave_report_hour=int(_env_or("REMNAWAVE_REPORT_HOUR", "9")),
            remnawave_report_minute=int(
                _env_or("REMNAWAVE_REPORT_MINUTE", "0")
            ),
            remnawave_report_timezone=_env_or(
                "REMNAWAVE_REPORT_TIMEZONE", DEFAULT_REMNAWAVE_REPORT_TIMEZONE
            ),
            remnawave_report_top_users=int(
                _env_or("REMNAWAVE_REPORT_TOP_USERS", "20")
            ),
        )
