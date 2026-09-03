from __future__ import annotations

from app.infrastructure.redis import create_arq_pool

JOB_DOWNLOAD_VIDEO = "download_video"


async def enqueue_download(
    redis_url: str,
    request_id: str,
) -> str | None:
    pool = await create_arq_pool(redis_url)
    try:
        job = await pool.enqueue_job(JOB_DOWNLOAD_VIDEO, request_id=request_id)
        return job.job_id if job else None
    finally:
        await pool.aclose()