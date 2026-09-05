from __future__ import annotations

from dataclasses import asdict
import time

from app.jobs.persistent import PersistentJob, PersistentQueue
from app.tools.cinema.models import CinemaError, Release
from app.tools.cinema.providers import DownloadProvider, TrackerProvider
from app.tools.cinema.ranking import parse_query, rank_releases


class CinemaService:
    def __init__(self, queue: PersistentQueue, *, owners: tuple[int, ...], configured: bool, tracker: TrackerProvider | None = None, downloader: DownloadProvider | None = None):
        self.queue, self.owners, self.configured = queue, owners, configured
        self.tracker, self.downloader = tracker, downloader

    def authorize(self, user_id: int) -> None:
        if user_id not in self.owners:
            raise CinemaError("Этот инструмент доступен только владельцу бота.")
        if not self.configured:
            raise CinemaError("Настройте RuTracker и qBittorrent в окружении бота и воркера.")

    async def search(self, *, user_id: int, chat_id: int, text: str) -> PersistentJob:
        self.authorize(user_id)
        parse_query(text)
        return await self.queue.create(type="cinema.search", user_id=user_id, chat_id=chat_id, payload={"query": text})

    async def select(self, *, user_id: int, chat_id: int, search_id: str, topic_id: int) -> PersistentJob:
        self.authorize(user_id)
        search = await self.results(user_id=user_id, search_id=search_id)
        release = next((r for r in search.result["releases"] if r["topic_id"] == topic_id), None)
        if release is None:
            raise CinemaError("Этой раздачи нет в результатах поиска.")
        return await self.queue.create(type="cinema.download", user_id=user_id, chat_id=chat_id, payload={"release": release}, dedupe_key=f"cinema:{user_id}:{search_id}:{topic_id}")

    async def results(self, *, user_id: int, search_id: str) -> PersistentJob:
        self.authorize(user_id)
        job = await self.queue.get(search_id, user_id)
        if job is None or job.type != "cinema.search" or job.status != "success":
            raise CinemaError("Результаты поиска недоступны.")
        if time.time() - job.created_at > 86400:
            raise CinemaError("Результатам больше суток. Запустите поиск заново.")
        return job

    async def recent(self, user_id: int) -> list[PersistentJob]:
        self.authorize(user_id)
        return await self.queue.recent(user_id)

    async def execute_job(self, job: PersistentJob) -> tuple[dict, bool]:
        """Return domain result and whether the job has fully completed."""
        self.authorize(job.user_id)
        if job.type == "cinema.search":
            query = parse_query(job.payload["query"])
            rows = await self.tracker.search(query.title)
            releases = rank_releases(query, rows)[:50]
            return {"releases": [asdict(r) for r in releases]}, True
        release = Release(**job.payload["release"])
        info_hash = job.result.get("hash")
        if not info_hash:
            magnet = await self.tracker.magnet(release.topic_id)
            info_hash = await self.downloader.add(magnet)
            return {"hash": info_hash, "progress": 0, "state": "submitted"}, False
        status = await self.downloader.status(info_hash)
        if not status:
            missing = job.result.get("missing_checks", 0) + 1
            if missing >= 10:
                raise CinemaError("Раздача не найдена в qBittorrent. Проверьте клиент и повторите поиск.")
            return {**job.result, "missing_checks": missing}, False
        if status.get("state") in ("error", "missingFiles"):
            raise CinemaError("qBittorrent сообщил об ошибке раздачи. Проверьте диск и файлы в клиенте.")
        progress = float(status.get("progress", 0))
        return {"hash": info_hash, "progress": progress, "state": status.get("state", "unknown"), "name": str(status.get("name", ""))[:500]}, progress >= 1
