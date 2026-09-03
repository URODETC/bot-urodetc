from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Sequence

from sqlalchemy import func, select, update

from app.infrastructure.config import Settings
from app.infrastructure.database import Database
from app.infrastructure.models import (
    CANCELLED,
    FAILED,
    PENDING,
    RUNNING,
    SUCCESS,
    DownloadRecord,
)
from app.tools.video.errors import (
    FileTooLargeError,
    UrlValidationError,
)
from app.tools.video.models import KIND_VIDEO, MediaOption, VideoInfo
from app.tools.video.provider import YOUTUBE_URL_RE, MediaProvider

logger = logging.getLogger(__name__)


def is_supported_url(url: str) -> bool:
    return bool(YOUTUBE_URL_RE.match(url.strip()))


class VideoService:
    def __init__(
        self,
        provider: MediaProvider,
        db: Database,
        settings: Settings,
    ) -> None:
        self._provider = provider
        self._db = db
        self._settings = settings

    def cookies_text(self) -> str | None:
        path = self._settings.cookies_file
        if path is None or not path.is_file():
            return None
        try:
            return path.read_text(encoding="utf-8")
        except OSError:
            logger.warning("failed to read cookies file", extra={"path": str(path)})
            return None

    async def fetch_info(
        self,
        url: str,
        cookies: str | None = None,
    ) -> VideoInfo:
        if not is_supported_url(url):
            raise UrlValidationError("Ссылка не похожа на YouTube")
        if cookies is None:
            cookies = self.cookies_text()
        info = await self._provider.fetch_info(url, cookies=cookies)

        allowed = [
            opt
            for opt in info.options
            if opt.size is None or opt.size <= self._settings.max_file_size
        ]
        if not allowed:
            limit_mb = self._settings.max_file_size // 1024 // 1024
            raise FileTooLargeError(
                f"Все доступные варианты превышают лимит Telegram ({limit_mb} МБ)"
            )
        return VideoInfo(
            video_id=info.video_id,
            url=info.url,
            title=info.title,
            author=info.author,
            duration=info.duration,
            thumbnail=info.thumbnail,
            options=tuple(allowed),
        )

    async def create_record(
        self,
        *,
        user_id: int,
        url: str,
        info: VideoInfo,
    ) -> DownloadRecord:
        record = DownloadRecord(
            id=uuid.uuid4().hex,
            user_id=user_id,
            url=info.url,
            title=info.title[:500],
            author=info.author[:250],
            duration=info.duration,
            formats=[opt.to_dict() for opt in info.options],
        )
        async with self._db.session() as session:
            session.add(record)
            await session.commit()
            await session.refresh(record)
        return record

    async def get_record(self, record_id: str) -> DownloadRecord | None:
        async with self._db.session() as session:
            return await session.get(DownloadRecord, record_id)

    async def list_records(
        self,
        user_id: int,
        *,
        offset: int = 0,
        limit: int = 5,
    ) -> Sequence[DownloadRecord]:
        async with self._db.session() as session:
            result = await session.execute(
                select(DownloadRecord)
                .where(DownloadRecord.user_id == user_id)
                .order_by(DownloadRecord.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
            return result.scalars().all()

    async def count_records(self, user_id: int) -> int:
        async with self._db.session() as session:
            result = await session.execute(
                select(func.count()).select_from(DownloadRecord).where(DownloadRecord.user_id == user_id)
            )
            return int(result.scalar_one())

    async def select_format(
        self,
        *,
        record_id: str,
        user_id: int,
        index: int,
        chat_id: int,
        message_id: int,
    ) -> DownloadRecord | None:
        async with self._db.session() as session:
            record = await session.get(DownloadRecord, record_id)
            if record is None or record.user_id != user_id:
                return None
            options = self._record_options(record)
            if index < 0 or index >= len(options):
                return None
            option = options[index]
            record.media_type = option.kind
            record.quality = option.label
            record.selected_index = index
            record.chat_id = chat_id
            record.message_id = message_id
            await session.commit()
            await session.refresh(record)
            return record

    async def cancel_record(
        self,
        *,
        record_id: str,
        user_id: int,
    ) -> DownloadRecord | None:
        async with self._db.session() as session:
            record = await session.get(DownloadRecord, record_id)
            if record is None or record.user_id != user_id:
                return None
            if record.status in (PENDING, RUNNING):
                record.status = CANCELLED
                record.finished_at = datetime.now(timezone.utc)
                await session.commit()
                await session.refresh(record)
            return record

    async def set_status(self, record_id: str, status: str) -> None:
        async with self._db.session() as session:
            record = await session.get(DownloadRecord, record_id)
            if record is None:
                return
            record.status = status
            if status == RUNNING:
                record.started_at = datetime.now(timezone.utc)
            await session.commit()

    async def claim(self, record_id: str) -> bool:
        async with self._db.session() as session:
            result = await session.execute(
                update(DownloadRecord)
                .where(
                    DownloadRecord.id == record_id,
                    DownloadRecord.status == PENDING,
                )
                .values(
                    status=RUNNING,
                    started_at=datetime.now(timezone.utc),
                )
            )
            await session.commit()
            return result.rowcount == 1

    async def set_progress(self, record_id: str, progress: int) -> None:
        async with self._db.session() as session:
            record = await session.get(DownloadRecord, record_id)
            if record is None:
                return
            record.progress = progress
            await session.commit()

    async def complete(self, record_id: str, file_size: int) -> None:
        async with self._db.session() as session:
            record = await session.get(DownloadRecord, record_id)
            if record is None:
                return
            record.status = SUCCESS
            record.progress = 100
            record.file_size = file_size
            record.finished_at = datetime.now(timezone.utc)
            await session.commit()

    async def fail(self, record_id: str, error: str) -> None:
        async with self._db.session() as session:
            record = await session.get(DownloadRecord, record_id)
            if record is None:
                return
            record.status = FAILED
            record.error = error[:500]
            record.finished_at = datetime.now(timezone.utc)
            await session.commit()

    @staticmethod
    def _record_options(record: DownloadRecord) -> list[MediaOption]:
        raw = record.formats or []
        return [MediaOption.from_dict(item) for item in raw]

    def options_by_kind(
        self,
        record: DownloadRecord,
        kind: str,
    ) -> list[tuple[int, MediaOption]]:
        return [
            (index, option)
            for index, option in enumerate(self._record_options(record))
            if option.kind == kind
        ]

    def selected_option(self, record: DownloadRecord) -> MediaOption | None:
        if record.selected_index is None:
            return None
        options = self._record_options(record)
        if record.selected_index < 0 or record.selected_index >= len(options):
            return None
        return options[record.selected_index]

    def is_video(self, record: DownloadRecord) -> bool:
        return record.media_type == KIND_VIDEO