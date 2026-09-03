from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_DATABASE_URL = "sqlite+aiosqlite:///./data/bot.db"
DEFAULT_REDIS_URL = "redis://localhost:6379/0"
DEFAULT_DOWNLOAD_DIR = "./data/downloads"

MIN_BOT_API_FILE_SIZE = 50 * 1024 * 1024
MAX_LOCAL_BOT_API_FILE_SIZE = 2 * 1024 * 1024 * 1024


def _env_or(name: str, default: str) -> str:
    value = os.environ.get(name)
    return default if value in (None, "") else value


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

    @classmethod
    def from_env(cls) -> "Settings":
        raw_max = os.environ.get("MAX_FILE_SIZE_MB")
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
        )