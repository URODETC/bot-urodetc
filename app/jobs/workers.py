from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone

from app.jobs.models import Job, JobStatus
from app.jobs.queue import JobQueue

logger = logging.getLogger(__name__)

JobHandler = Callable[[Job], Awaitable[None]]


class Worker:
    def __init__(self, queue: JobQueue, handler: JobHandler) -> None:
        self._queue = queue
        self._handler = handler

    async def run(self) -> None:
        while True:
            job = await self._queue.get()
            await self._process(job)

    async def _process(self, job: Job) -> None:
        job.status = JobStatus.RUNNING
        job.started_at = datetime.now(timezone.utc)
        logger.info("job started", extra={"job_id": job.id, "type": job.type})
        try:
            await self._handler(job)
            job.status = JobStatus.SUCCESS
        except Exception as exc:
            job.status = JobStatus.FAILED
            job.error = str(exc)
            logger.exception(
                "job failed",
                extra={"job_id": job.id, "type": job.type},
            )
        finally:
            job.finished_at = datetime.now(timezone.utc)
            logger.info(
                "job finished",
                extra={"job_id": job.id, "status": job.status.value},
            )