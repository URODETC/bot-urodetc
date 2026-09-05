import httpx

from app.infrastructure.config import Settings
from app.jobs.persistent import PersistentQueue
from app.tools.cinema.providers.qbittorrent import QBittorrentProvider
from app.tools.cinema.providers.rutracker import RutrackerProvider
from app.tools.cinema.service import CinemaService


def build_cinema_worker(settings: Settings, queue: PersistentQueue) -> tuple[CinemaService, list[httpx.AsyncClient]]:
    # Separate cookie jars: tracker credentials must never reach the downloader.
    tracker_client = httpx.AsyncClient(proxy=settings.rutracker_proxy_url, trust_env=False, timeout=20, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0 bot-urodetc"})
    qbit_client = httpx.AsyncClient(timeout=20, trust_env=False)
    tracker = RutrackerProvider(tracker_client, base_url=settings.rutracker_url, username=settings.rutracker_username, password=settings.rutracker_password, session=settings.rutracker_session)
    downloader = QBittorrentProvider(qbit_client, base_url=settings.qbittorrent_url, username=settings.qbittorrent_username, password=settings.qbittorrent_password, save_path=settings.qbittorrent_save_path, category=settings.qbittorrent_category)
    return CinemaService(queue, owners=settings.owner_telegram_ids, configured=settings.cinema_configured, tracker=tracker, downloader=downloader), [tracker_client, qbit_client]
