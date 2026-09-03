from __future__ import annotations

import uuid
from typing import Sequence

from sqlalchemy import func, select

from app.infrastructure.database import Database
from app.infrastructure.models import LookupRecord

FAILED_STATUS = "failed"
SUCCESS_STATUS = "success"


class HistoryRepository:
    """Persists and lists network-lookup history for the "История" menu."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def add(
        self,
        *,
        user_id: int,
        kind: str,
        target: str,
        summary: str,
        status: str = SUCCESS_STATUS,
        error: str | None = None,
    ) -> LookupRecord:
        record = LookupRecord(
            id=uuid.uuid4().hex,
            user_id=user_id,
            kind=kind,
            target=target[:255],
            summary=summary[:255],
            status=status,
            error=(error[:255] if error else None),
        )
        async with self._db.session() as session:
            session.add(record)
            await session.commit()
            await session.refresh(record)
        return record

    async def list_for_user(
        self,
        user_id: int,
        *,
        offset: int = 0,
        limit: int = 5,
    ) -> Sequence[LookupRecord]:
        async with self._db.session() as session:
            result = await session.execute(
                select(LookupRecord)
                .where(LookupRecord.user_id == user_id)
                .order_by(LookupRecord.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
            return result.scalars().all()

    async def count_for_user(self, user_id: int) -> int:
        async with self._db.session() as session:
            result = await session.execute(
                select(func.count()).select_from(LookupRecord).where(LookupRecord.user_id == user_id)
            )
            return int(result.scalar_one())
