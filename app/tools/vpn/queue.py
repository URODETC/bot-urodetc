from __future__ import annotations

import logging

from app.infrastructure.redis import create_arq_pool

JOB_VPN_REPORT = "send_vpn_report"
logger = logging.getLogger(__name__)


async def enqueue_vpn_report(
    redis_url: str,
    chat_id: int,
    *,
    status_message_id: int | None = None,
) -> str | None:
    pool = None
    try:
        pool = await create_arq_pool(redis_url)
        status_messages = (
            {str(chat_id): status_message_id}
            if status_message_id is not None
            else None
        )
        job = await pool.enqueue_job(
            JOB_VPN_REPORT,
            chat_ids=[chat_id],
            status_messages=status_messages,
        )
        return job.job_id if job else None
    except Exception:
        logger.exception("failed to enqueue vpn report", extra={"chat_id": chat_id})
        return None
    finally:
        if pool is not None:
            await pool.aclose()
