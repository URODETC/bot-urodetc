from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    bot_token: str
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            bot_token=os.environ["BOT_TOKEN"],
            log_level=os.environ.get("LOG_LEVEL", "INFO"),
        )