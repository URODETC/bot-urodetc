from __future__ import annotations

import asyncio

from app.jobs.models import Job


class JobQueue:
    def __init__(self) -> None:
        self._queue: asyncio.Queue[Job] = asyncio.Queue()

    async def enqueue(self, job: Job) -> None:
        await self._queue.put(job)

    async def get(self) -> Job:
        return await self._queue.get()