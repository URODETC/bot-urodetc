from __future__ import annotations

import asyncio
import logging

from app.infrastructure.config import Settings
from app.infrastructure.logging import setup_logging
from app.telegram.bot import run as run_bot

logger = logging.getLogger(__name__)


def main() -> None:
    setup_logging("INFO")
    try:
        settings = Settings.from_env()
    except KeyError as exc:
        logger.error("missing required env var: %s", exc.args[0])
        raise
    setup_logging(settings.log_level)
    asyncio.run(run_bot(settings))


if __name__ == "__main__":
    main()