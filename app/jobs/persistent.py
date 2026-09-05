"""Durable generic job queue, polled by the shared ARQ worker.

Database claims have leases so a terminated worker cannot strand a job.
Handlers must be idempotent because delivery is at least once.
"""
from __future__ import annotations

import time
import uuid
from typing import Any

from sqlalchemy import BigInteger, JSON, Float, Integer, String, select, update
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database import Base, Database


class PersistentJob(Base):
    __tablename__ = "service_jobs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    type: Mapped[str] = mapped_column(String(80), index=True)
    user_id: Mapped[int] = mapped_column(BigInteger)
    chat_id: Mapped[int] = mapped_column(BigInteger)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    available_at: Mapped[float] = mapped_column(Float, default=time.time, index=True)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)
    dedupe_key: Mapped[str | None] = mapped_column(String(160), unique=True, nullable=True)
    lease: Mapped[str | None] = mapped_column(String(32), nullable=True)


class PersistentQueue:
    def __init__(self, db: Database):
        self.db = db

    async def create(self, *, type: str, user_id: int, chat_id: int, payload: dict, dedupe_key: str | None = None) -> PersistentJob:
        from sqlalchemy.exc import IntegrityError
        async with self.db.session() as session:
            job = PersistentJob(id=uuid.uuid4().hex, type=type, user_id=user_id, chat_id=chat_id, payload=payload, dedupe_key=dedupe_key)
            session.add(job)
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                if dedupe_key is None:
                    raise
                job = (await session.execute(select(PersistentJob).where(PersistentJob.dedupe_key == dedupe_key))).scalar_one()
            return job

    async def get(self, job_id: str, user_id: int) -> PersistentJob | None:
        async with self.db.session() as session:
            return (await session.execute(select(PersistentJob).where(PersistentJob.id == job_id, PersistentJob.user_id == user_id))).scalar_one_or_none()

    async def recent(self, user_id: int, *, limit: int = 5) -> list[PersistentJob]:
        async with self.db.session() as session:
            return list((await session.scalars(select(PersistentJob).where(PersistentJob.user_id == user_id, PersistentJob.type.like("cinema.%")).order_by(PersistentJob.created_at.desc()).limit(limit))).all())

    async def claim(self, types: tuple[str, ...]) -> PersistentJob | None:
        now = time.time()
        async with self.db.session() as session:
            job = (await session.scalars(select(PersistentJob).where(PersistentJob.type.in_(types), PersistentJob.status.in_(("pending", "running")), PersistentJob.available_at <= now).order_by(PersistentJob.available_at).limit(1))).first()
            if job is None:
                return None
            lease = uuid.uuid4().hex
            claimed = await session.execute(update(PersistentJob).where(PersistentJob.id == job.id, PersistentJob.available_at <= now, PersistentJob.status.in_(("pending", "running"))).values(status="running", available_at=now + 300, lease=lease))
            await session.commit()
            if claimed.rowcount != 1:
                return None
            await session.refresh(job)
            return job

    async def finish(self, job: PersistentJob, *, status: str, result: dict | None = None, error: str | None = None, delay: int = 0, attempts: int | None = None) -> None:
        async with self.db.session() as session:
            await session.execute(update(PersistentJob).where(PersistentJob.id == job.id, PersistentJob.lease == job.lease).values(status=status, result=result if result is not None else job.result, error=error, available_at=time.time() + delay, attempts=job.attempts if attempts is None else attempts, lease=None))
            await session.commit()
