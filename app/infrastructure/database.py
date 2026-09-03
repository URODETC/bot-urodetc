from __future__ import annotations

from pathlib import Path

from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class Database:
    def __init__(self, url: str) -> None:
        parsed = make_url(url)
        if parsed.get_backend_name() == "sqlite" and parsed.database:
            database = str(parsed.database)
            if database != ":memory:" and "@" not in database.replace("file:", ""):
                Path(database).expanduser().parent.mkdir(
                    parents=True, exist_ok=True
                )
        self._engine: AsyncEngine = create_async_engine(url)
        self._session_factory = async_sessionmaker(
            self._engine,
            expire_on_commit=False,
        )

    async def init(self) -> None:
        from app.infrastructure import models  # noqa: F401  (register tables)

        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    def session(self) -> AsyncSession:
        return self._session_factory()

    async def close(self) -> None:
        await self._engine.dispose()