from __future__ import annotations

import asyncio
import html
import logging
import re
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

from aiogram import Bot
from aiogram.types import FSInputFile

from app.infrastructure.config import Settings
from app.infrastructure.models import DownloadRecord
from app.telegram.menu import main_menu_keyboard
from app.tools.video.errors import FileTooLargeError, VideoError
from app.tools.video.models import KIND_AUDIO, MediaOption
from app.tools.video.provider import MediaProvider
from app.tools.video.service import VideoService

logger = logging.getLogger(__name__)

SAFE_NAME_RE = re.compile(r"[^\w\-. ]+")
_PROGRESS_EDIT_INTERVAL = 2.0


class VideoDownloader:
    def __init__(
        self,
        *,
        provider: MediaProvider,
        service: VideoService,
        settings: Settings,
    ) -> None:
        self._provider = provider
        self._service = service
        self._settings = settings
        self._download_root = settings.download_dir

    async def process(self, request_id: str, bot: Bot) -> None:
        record = await self._service.get_record(request_id)
        if record is None:
            logger.warning("record not found", extra={"request_id": request_id})
            return
        if not await self._service.claim(request_id):
            logger.info("record already claimed", extra={"request_id": request_id})
            return

        option = self._service.selected_option(record)
        if option is None:
            await self._service.fail(request_id, "Формат не выбран")
            await self._delete_status(bot, record)
            await self._notify_error(bot, record, "Формат не выбран")
            return

        self._download_root.mkdir(parents=True, exist_ok=True)
        tmpdir = Path(
            tempfile.mkdtemp(prefix=f"{request_id[:8]}_", dir=self._download_root)
        )
        try:
            path = await self._download_with_progress(
                record,
                option,
                tmpdir,
                bot,
                cookies=self._service.cookies_text(),
            )
            await self._enforce_size(record, path)
            await self._send_file(bot, record, path)
            await self._service.complete(request_id, path.stat().st_size)
            await self._delete_status(bot, record)
        except FileTooLargeError as exc:
            await self._handle_failure(bot, record, exc)
        except VideoError as exc:
            await self._handle_failure(bot, record, exc)
        except Exception:
            logger.exception("unexpected download failure", extra={"request_id": request_id})
            await self._handle_failure(bot, record, "Неизвестная ошибка")
        finally:
            self._cleanup(tmpdir)

    async def _download_with_progress(
        self,
        record: DownloadRecord,
        option: MediaOption,
        tmpdir: Path,
        bot: Bot,
        cookies: str | None,
    ) -> Path:
        loop = asyncio.get_running_loop()
        last_update = 0.0

        def on_progress(data: dict[str, Any]) -> None:
            nonlocal last_update
            if data.get("status") != "downloading":
                return
            total = data.get("total_bytes") or data.get("total_bytes_estimate")
            downloaded = data.get("downloaded_bytes") or 0
            if not total:
                return
            pct = int(downloaded / total * 100)
            now = time.monotonic()
            if now - last_update < _PROGRESS_EDIT_INTERVAL:
                return
            last_update = now
            asyncio.run_coroutine_threadsafe(
                self._update_progress(record, pct, bot),
                loop,
            )

        logger.info(
            "downloading media",
            extra={
                "request_id": record.id,
                "format": option.format_id,
                "authenticated": bool(cookies or self._settings.cookies_file),
            },
        )
        return await self._provider.download(
            record.url,
            option,
            tmpdir,
            cookies=cookies,
            progress=on_progress,
        )

    async def _update_progress(self, record: DownloadRecord, pct: int, bot: Bot) -> None:
        await self._service.set_progress(record.id, pct)
        await self._edit_message(
            bot,
            record,
            f"⏳ Скачивание… {pct}% "
            f"({'#' * (pct // 10)}{'-' * (10 - pct // 10)})",
        )

    async def _enforce_size(self, record: DownloadRecord, path: Path) -> None:
        size = path.stat().st_size
        limit = self._settings.max_file_size
        if size > limit:
            limit_mb = limit // 1024 // 1024
            raise FileTooLargeError(
                f"Файл {size // 1024 // 1024} МБ превышает лимит Telegram ({limit_mb} МБ)"
            )

    async def _send_file(self, bot: Bot, record: DownloadRecord, path: Path) -> None:
        if not record.chat_id:
            raise VideoError("Чат неизвестен, файл не отправлен")
        await self._edit_message(bot, record, "📤 Отправляю файл…")

        filename = self._safe_filename(record, path)
        input_file = FSInputFile(path, filename=filename)
        if record.media_type == KIND_AUDIO:
            await bot.send_audio(
                record.chat_id,
                input_file,
                title=self._escaped((record.title or "")[:64]),
                performer=self._escaped((record.author or "")[:64]),
                duration=record.duration,
                caption=self._caption(record),
                reply_markup=main_menu_keyboard(),
            )
        else:
            await bot.send_video(
                record.chat_id,
                input_file,
                width=None,
                height=None,
                duration=record.duration,
                supports_streaming=True,
                caption=self._caption(record),
                reply_markup=main_menu_keyboard(),
            )
        logger.info(
            "file sent",
            extra={"request_id": record.id, "size": path.stat().st_size},
        )

    async def _handle_failure(self, bot: Bot, record: DownloadRecord, error: Exception | str) -> None:
        message = str(error) or "Ошибка"
        await self._service.fail(record.id, message)
        await self._delete_status(bot, record)
        await self._notify_error(bot, record, message)

    async def _notify_error(self, bot: Bot, record: DownloadRecord, message: str) -> None:
        if not record.chat_id:
            return
        try:
            await bot.send_message(
                record.chat_id,
                f"❌ {message}",
                parse_mode=None,
                reply_markup=main_menu_keyboard(),
            )
        except Exception:
            logger.exception("failed to notify user", extra={"request_id": record.id})

    async def _edit_message(
        self,
        bot: Bot,
        record: DownloadRecord,
        text: str,
    ) -> None:
        if not (record.chat_id and record.message_id):
            return
        try:
            await bot.edit_message_text(
                chat_id=record.chat_id,
                message_id=record.message_id,
                text=text,
                reply_markup=main_menu_keyboard(),
            )
        except Exception:
            logger.debug(
                "preview message edit failed", extra={"request_id": record.id}
            )

    async def _delete_status(self, bot: Bot, record: DownloadRecord) -> None:
        if not (record.chat_id and record.message_id):
            return
        try:
            await bot.delete_message(record.chat_id, record.message_id)
        except Exception:
            logger.debug(
                "status message delete failed", extra={"request_id": record.id}
            )

    @staticmethod
    def _caption(record: DownloadRecord) -> str:
        title = (record.title or "")[:100]
        if record.quality:
            return f"{VideoDownloader._escaped(title)} ({record.quality})"
        return VideoDownloader._escaped(title)

    @staticmethod
    def _escaped(text: str) -> str:
        return html.escape(text, quote=False)

    @staticmethod
    def _safe_filename(record: DownloadRecord, path: Path) -> str:
        base = SAFE_NAME_RE.sub("_", record.title or "video")
        return f"{base[:60]}{path.suffix.lower()}"

    @staticmethod
    def _cleanup(tmpdir: Path) -> None:
        try:
            shutil.rmtree(tmpdir, ignore_errors=True)
        except Exception:
            logger.exception("failed to clean up tmpdir", extra={"tmpdir": str(tmpdir)})
