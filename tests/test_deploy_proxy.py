import unittest
from unittest.mock import patch

from app.infrastructure.config import Settings
from app.telegram.bot import build_bot
from app.tools.cinema.runtime import build_cinema_worker


class ProxyRoutingTests(unittest.IsolatedAsyncioTestCase):
    async def test_telegram_proxy_and_local_api_routing(self):
        settings = Settings(bot_token='123456:ABC', telegram_proxy_url='http://hysteria:8080')
        bot = build_bot(settings)
        try:
            self.assertEqual(bot.session.proxy, settings.telegram_proxy_url)
        finally:
            await bot.session.close()
        local = build_bot(Settings(bot_token='123456:ABC', telegram_proxy_url='http://hysteria:8080', local_api_base='http://local-api:8081'))
        try:
            self.assertIsNone(local.session.proxy)
            self.assertEqual(local.session.api.base, 'http://local-api:8081/bot{token}/{method}')
        finally:
            await local.session.close()

    async def test_tracker_proxy_does_not_reach_qbittorrent(self):
        settings = Settings(bot_token='123456:ABC', rutracker_proxy_url='http://hysteria:8080')
        with patch('app.tools.cinema.runtime.httpx.AsyncClient') as client:
            build_cinema_worker(settings, queue=object())
        tracker, qbit = client.call_args_list
        self.assertEqual(tracker.kwargs['proxy'], settings.rutracker_proxy_url)
        self.assertFalse(tracker.kwargs['trust_env'])
        self.assertNotIn('proxy', qbit.kwargs)
        self.assertFalse(qbit.kwargs['trust_env'])

    async def test_env_settings(self):
        with patch.dict('os.environ', {'BOT_TOKEN': '123456:ABC', 'TELEGRAM_PROXY_URL': 'http://hysteria:8080', 'RUTRACKER_PROXY_URL': ''}):
            settings = Settings.from_env()
        self.assertEqual(settings.telegram_proxy_url, 'http://hysteria:8080')
        self.assertIsNone(settings.rutracker_proxy_url)
