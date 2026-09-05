"""Shared durable job runner hosted by the existing ARQ worker."""
from __future__ import annotations

import logging
import time
from html import escape

from app.jobs.persistent import PersistentQueue
from app.telegram.cinema_ui import search_page
from app.tools.cinema.models import CinemaError, TemporaryCinemaError

logger = logging.getLogger(__name__)


async def run_service_jobs(ctx: dict) -> None:
    queue: PersistentQueue = ctx["service_queue"]
    handlers = ctx["service_job_handlers"]
    # Bound each scheduler tick; a lease outlives the ARQ function timeout.
    for _ in range(4):
        job = await queue.claim(tuple(handlers))
        if job is None:
            return
        started = time.monotonic()
        try:
            result, complete = await handlers[job.type](job)
            await queue.finish(job, status="success" if complete else "pending", result=result, delay=30, attempts=0)
        except TemporaryCinemaError as exc:
            attempts = job.attempts + 1
            await queue.finish(job, status="failed" if attempts >= 3 else "pending", error=str(exc), delay=30 * attempts, attempts=attempts)
            if attempts >= 3:
                await notify_failure(ctx, job.chat_id, str(exc))
            continue
        except Exception as exc:
            error = str(exc) if isinstance(exc, CinemaError) else "Не удалось выполнить задачу. Проверьте настройки сервисов."
            # Exception bodies can contain private tracker URLs; log only category.
            logger.error("service job failed", extra={"job_id": job.id, "error_type": type(exc).__name__})
            await queue.finish(job, status="failed", error=error)
            await notify_failure(ctx, job.chat_id, error)
            continue
        logger.info("service job processed", extra={"job_id": job.id, "type": job.type, "duration_ms": int((time.monotonic() - started) * 1000), "complete": complete})
        try:
            if complete:
                job.result = result
                if job.type == "cinema.search":
                    text, markup = search_page(job)
                    await ctx["bot"].send_message(job.chat_id, text, reply_markup=markup)
                else:
                    title = escape(job.payload["release"]["title"][:250])
                    await ctx["bot"].send_message(job.chat_id, f"✅ Скачано в qBittorrent:\n<b>{title}</b>")
            elif not job.result.get("hash") and result.get("hash"):
                await ctx["bot"].send_message(job.chat_id, "📥 Раздача добавлена в qBittorrent. /cinema_status — прогресс.")
        except Exception as exc:
            logger.warning("job notification failed", extra={"job_id": job.id, "error_type": type(exc).__name__})


async def notify_failure(ctx: dict, chat_id: int, error: str) -> None:
    try:
        await ctx["bot"].send_message(chat_id, "❌ " + escape(error))
    except Exception as exc:
        logger.warning("job notification failed", extra={"error_type": type(exc).__name__})
