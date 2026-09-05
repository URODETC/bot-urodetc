from __future__ import annotations

import unittest
from dataclasses import asdict
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import parse_qs

import httpx
from sqlalchemy import update

from app.infrastructure.database import Database
from app.jobs.persistent import PersistentJob, PersistentQueue
from app.jobs.service_worker import run_service_jobs
from app.telegram.cinema_ui import search_page
from app.tools.cinema.models import AuthenticationError, CinemaError, Release
from app.tools.cinema.providers.qbittorrent import QBittorrentProvider, magnet_hash
from app.tools.cinema.providers.rutracker import RutrackerProvider, parse_results, parse_size
from app.tools.cinema.ranking import parse_query, rank_releases
from app.tools.cinema.service import CinemaService

HASH = "a" * 40
MAGNET = "magnet:?xt=urn:btih:" + HASH
HTML = '''<div id="logged-in-username">owner</div><table id="tor-tbl"><tbody><tr>
<td></td><td></td><td></td><td class="t-title-col"><a class="tLink" href="viewtopic.php?t=42">Дюна / Dune [2021, фантастика, WEB-DL 2160p] Dub HDR10</a></td><td></td>
<td class="tor-size" data-ts_text="21474836480"><a class="tr-dl" href="dl.php?t=42">20 GB</a></td><td><b class="seedmed">18</b></td>
</tr></tbody></table>'''


class RankingTests(unittest.TestCase):
    def test_numeric_movie_titles_and_tracker_sizes(self):
        self.assertEqual(parse_query("1917").title, "1917")
        self.assertEqual(parse_query("1917 2019").year, 2019)
        self.assertEqual(parse_size("20 GB"), 20 * 1024**3)
        self.assertEqual(parse_size("1,5 GiB"), int(1.5 * 1024**3))

    def test_year_season_and_live_uhd_priority(self):
        query = parse_query("Хочу посмотреть сериал Тест сезон 2 2024")
        rows = [
            Release(1, "Тест / Сезон: 2 [2024, WEB-DL 1080p] Dub", 20, 100),
            Release(2, "Тест / Сезон: 2 [2024, WEB-DL 2160p] Dub", 40, 2),
            Release(3, "Тест / Сезон: 2 [2024, WEB-DL 2160p] Dub", 40, 0),
            Release(4, "Тест / Сезон: 3 [2024, WEB-DL 2160p] Dub", 40, 10),
            Release(5, "Тест / Сезон: 2 [2023, WEB-DL 2160p] Dub", 40, 10),
            Release(6, "Другое / Сезон: 2 [2024, WEB-DL 2160p] Тест", 40, 10),
        ]
        self.assertEqual([r.topic_id for r in rank_releases(query, rows)], [2, 1, 3])

    def test_cyrillic_season_range_and_deduplication(self):
        query = parse_query("Ёлки 2 сезон")
        row = Release(1, "Елки / Сезоны: 1-3 [2024, UHD BluRay] MVO Dolby Vision", 5, 1)
        results = rank_releases(query, [row, row])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].resolution, 2160)
        self.assertEqual(results[0].dynamic_range, "Dolby Vision")

    def test_search_html_and_unknown_page(self):
        row = parse_results(HTML)[0]
        self.assertEqual((row.topic_id, row.size, row.seeders), (42, 20 * 1024**3, 18))
        self.assertEqual(parse_results("Ничего не найдено"), [])
        with self.assertRaises(CinemaError):
            parse_results("<html>Just a moment...</html>")

    def test_ui_escapes_titles_and_bounds_pages(self):
        releases = [asdict(Release(i, "<b>&" * 80, 10, 0)) for i in range(10)]
        job = SimpleNamespace(id="a" * 32, payload={"query": "<test>"}, result={"releases": releases})
        text, keyboard = search_page(job, 100)
        self.assertIn("&lt;test&gt;", text)
        self.assertLess(len(text), 4096)
        self.assertTrue(all(len(b.callback_data.encode()) <= 64 for row in keyboard.inline_keyboard for b in row if b.callback_data))


class ProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_rutracker_login_cp1251_and_magnet(self):
        logged_in = False
        async def handle(request):
            nonlocal logged_in
            if request.url.path.endswith("login.php"):
                self.assertIn(b"login_username=", request.content)
                logged_in = True
                return httpx.Response(200, headers={"set-cookie": "bb_session=test; Path=/"})
            if not logged_in:
                return httpx.Response(200, text="login required")
            self.assertIn("bb_session=test", request.headers.get("cookie", ""))
            if request.url.path.endswith("tracker.php"):
                self.assertIn(b"%C4%FE%ED%E0", request.url.query)
                return httpx.Response(200, content=HTML.encode("cp1251"))
            return httpx.Response(200, text=f'<div id="logged-in-username"></div><a class="magnet-link" href="{MAGNET}">Magnet</a>')
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            tracker = RutrackerProvider(client, base_url="https://tracker.example", username="user", password="secret")
            self.assertEqual(len(await tracker.search("Дюна")), 1)
            self.assertEqual(await tracker.magnet(42), MAGNET)

    async def test_expired_session_does_not_return_empty_results(self):
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, text="captcha"))) as client:
            tracker = RutrackerProvider(client, base_url="https://tracker.example", session="expired")
            with self.assertRaises(AuthenticationError):
                await tracker.search("Дюна")

    async def test_qbit_auth_add_status_and_duplicate(self):
        authenticated = False
        added = False
        posts = 0
        async def handle(request):
            nonlocal authenticated, added, posts
            self.assertEqual(request.headers["referer"], "http://qbit.example/")
            if request.url.path.endswith("auth/login"):
                authenticated = True
                return httpx.Response(200, text="Ok.", headers={"set-cookie": "SID=test; Path=/"})
            if not authenticated:
                return httpx.Response(403)
            if request.url.path.endswith("torrents/info"):
                return httpx.Response(200, json=[{"hash": HASH, "progress": 0.5}] if added else [])
            data = parse_qs(request.content.decode())
            self.assertEqual(data["urls"], [MAGNET])
            self.assertEqual(data["savepath"], ["/media"])
            added = True
            posts += 1
            return httpx.Response(200, text="Ok.")
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            provider = QBittorrentProvider(client, base_url="http://qbit.example", username="user", password="pass", save_path="/media")
            self.assertEqual(await provider.add(MAGNET), HASH)
            self.assertEqual(await provider.add(MAGNET), HASH)
            self.assertEqual(posts, 1)
        with self.assertRaises(CinemaError):
            magnet_hash("https://example.com/file")


class JobFlowTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = Database("sqlite+aiosqlite:///:memory:")
        await self.db.init()
        self.queue = PersistentQueue(self.db)
        self.tracker = SimpleNamespace(search=AsyncMock(return_value=parse_results(HTML)), magnet=AsyncMock(return_value=MAGNET))
        self.downloader = SimpleNamespace(add=AsyncMock(return_value=HASH), status=AsyncMock(return_value={"progress": 1, "state": "uploading"}))
        self.service = CinemaService(self.queue, owners=(123,), configured=True, tracker=self.tracker, downloader=self.downloader)
        self.bot = SimpleNamespace(send_message=AsyncMock())
        self.ctx = {"service_queue": self.queue, "service_job_handlers": {"cinema.search": self.service.execute_job, "cinema.download": self.service.execute_job}, "bot": self.bot}

    async def asyncTearDown(self):
        await self.db.close()

    async def test_search_selection_download_and_completion(self):
        search = await self.service.search(user_id=123, chat_id=123, text="Дюна 2021")
        await run_service_jobs(self.ctx)
        self.assertEqual((await self.service.results(user_id=123, search_id=search.id)).result["releases"][0]["resolution"], 2160)
        job = await self.service.select(user_id=123, chat_id=123, search_id=search.id, topic_id=42)
        again = await self.service.select(user_id=123, chat_id=123, search_id=search.id, topic_id=42)
        self.assertEqual(job.id, again.id)
        await run_service_jobs(self.ctx)
        submitted = await self.queue.get(job.id, 123)
        self.assertEqual(submitted.result["hash"], HASH)
        self.assertEqual(submitted.status, "pending")
        async with self.db.session() as session:
            await session.execute(update(PersistentJob).where(PersistentJob.id == job.id).values(available_at=0))
            await session.commit()
        await run_service_jobs(self.ctx)
        self.assertEqual((await self.queue.get(job.id, 123)).status, "success")
        self.downloader.add.assert_awaited_once()
        self.assertIn("Скачано", self.bot.send_message.call_args.args[1])

    async def test_permissions_and_unlisted_release(self):
        with self.assertRaises(CinemaError):
            await self.service.search(user_id=999, chat_id=999, text="Дюна")
        search = await self.service.search(user_id=123, chat_id=123, text="Дюна")
        await run_service_jobs(self.ctx)
        with self.assertRaises(CinemaError):
            await self.service.select(user_id=999, chat_id=999, search_id=search.id, topic_id=42)
        with self.assertRaises(CinemaError):
            await self.service.select(user_id=123, chat_id=123, search_id=search.id, topic_id=999)

    async def test_expired_lease_recovery_and_stale_worker_cannot_commit(self):
        created = await self.service.search(user_id=123, chat_id=123, text="Дюна")
        old_claim = await self.queue.claim(("cinema.search",))
        self.assertIsNone(await self.queue.claim(("cinema.search",)))
        async with self.db.session() as session:
            await session.execute(update(PersistentJob).where(PersistentJob.id == created.id).values(available_at=0))
            await session.commit()
        new_claim = await self.queue.claim(("cinema.search",))
        await self.queue.finish(old_claim, status="failed")
        self.assertEqual((await self.queue.get(created.id, 123)).status, "running")
        await self.queue.finish(new_claim, status="success")
        self.assertEqual((await self.queue.get(created.id, 123)).status, "success")

    async def test_retry_temporary_errors_and_no_private_exception_leak(self):
        from app.tools.cinema.models import TemporaryCinemaError
        self.tracker.search.side_effect = TemporaryCinemaError("Недоступен")
        created = await self.service.search(user_id=123, chat_id=123, text="Дюна")
        await run_service_jobs(self.ctx)
        job = await self.queue.get(created.id, 123)
        self.assertEqual((job.status, job.attempts), ("pending", 1))
        self.tracker.search.side_effect = RuntimeError("private magnet tracker passkey")
        async with self.db.session() as session:
            await session.execute(update(PersistentJob).where(PersistentJob.id == created.id).values(available_at=0))
            await session.commit()
        await run_service_jobs(self.ctx)
        self.assertNotIn("passkey", (await self.queue.get(created.id, 123)).error)
