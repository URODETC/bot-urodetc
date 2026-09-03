from __future__ import annotations

from app.infrastructure.redis import create_arq_pool

JOB_VPN_REPORT = "send_vpn_report"


async def enqueue_vpn_report(redis_url: str, chat_id: int) -> str | None:
    pool = await create_arq_pool(redis_url)
    try:
        job = await pool.enqueue_job(JOB_VPN_REPORT, chat_ids=[chat_id])
        return job.job_id if job else None
    finally:
        await pool.aclose()
