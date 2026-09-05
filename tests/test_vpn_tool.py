from __future__ import annotations

import json
import unittest
from datetime import date, datetime, timezone
from types import SimpleNamespace

import httpx

from app.telegram.flows.vpn import parse_create_request, parse_extend_request
from app.telegram.vpn_ui import format_vpn_report
from app.tools.vpn.models import (
    CreateVpnUser,
    VpnNodeLoad,
    VpnSystemStats,
    VpnUser,
)
from app.tools.vpn.provider import RemnawaveHttpProvider
from app.tools.vpn.service import GIB, VpnService
from app.tools.video.worker import send_vpn_report


def _raw_user(*, api_major: int = 3, username: str = "alice", user_id: int = 7) -> dict:
    data = {
        "id": user_id,
        "username": username,
        "status": "ACTIVE",
        "expireAt": "2026-10-01T12:00:00Z",
        "trafficLimitBytes": 100 * GIB,
        "telegramId": 123,
        "subscriptionUrl": f"https://sub.example/{username}",
        "userTraffic": {
            "usedTrafficBytes": 2 * GIB,
            "lifetimeUsedTrafficBytes": 9 * GIB,
        },
    }
    if api_major == 2:
        data["uuid"] = "00000000-0000-0000-0000-000000000007"
    return data


class RemnawaveProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_create_user_uses_bearer_and_official_payload(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.method, "POST")
            self.assertEqual(request.url.path, "/api/users")
            self.assertEqual(request.headers["authorization"], "Bearer secret")
            body = json.loads(request.content)
            self.assertEqual(body["username"], "alice")
            self.assertEqual(body["activeInternalSquads"], ["squad-uuid"])
            self.assertEqual(body["trafficLimitStrategy"], "NO_RESET")
            return httpx.Response(201, json={"response": _raw_user()}, request=request)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = RemnawaveHttpProvider(
                client,
                base_url="https://panel.example",
                token="secret",
                api_major=3,
            )
            user = await provider.create_user(
                CreateVpnUser(
                    username="alice",
                    expire_at=datetime(2026, 10, 1, 12, tzinfo=timezone.utc),
                    traffic_limit_bytes=100 * GIB,
                    active_internal_squads=("squad-uuid",),
                )
            )

        self.assertEqual(user.username, "alice")
        self.assertEqual(user.id, 7)
        self.assertIsNone(user.uuid)

    async def test_v3_extension_uses_numeric_user_id(self) -> None:
        requests: list[httpx.Request] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if request.method == "GET":
                return httpx.Response(200, json={"response": _raw_user()}, request=request)
            updated = _raw_user()
            updated["expireAt"] = "2026-10-31T12:00:00Z"
            return httpx.Response(200, json={"response": updated}, request=request)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = RemnawaveHttpProvider(
                client,
                base_url="https://panel.example",
                token="secret",
                api_major=3,
            )
            user = await provider.extend_user("alice", 30)

        self.assertEqual(requests[1].url.path, "/api/users/7/actions/extend")
        self.assertEqual(json.loads(requests[1].content), {"days": 30})
        self.assertEqual(user.expire_at.day, 31)

    async def test_v2_extension_patches_uuid_and_expiration(self) -> None:
        requests: list[httpx.Request] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            raw = _raw_user(api_major=2)
            if request.method == "PATCH":
                raw["expireAt"] = json.loads(request.content)["expireAt"]
            return httpx.Response(200, json={"response": raw}, request=request)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = RemnawaveHttpProvider(
                client,
                base_url="https://panel.example",
                token="secret",
                api_major=2,
            )
            await provider.extend_user("alice", 5)

        self.assertEqual(requests[1].method, "PATCH")
        self.assertEqual(requests[1].url.path, "/api/users")
        self.assertEqual(
            json.loads(requests[1].content)["uuid"],
            "00000000-0000-0000-0000-000000000007",
        )

    async def test_v3_cursor_pagination(self) -> None:
        pages = 0

        async def handler(request: httpx.Request) -> httpx.Response:
            nonlocal pages
            pages += 1
            if pages == 1:
                response = {
                    "users": [_raw_user(username="alice", user_id=1)],
                    "hasMore": True,
                    "nextCursor": "1",
                }
            else:
                response = {
                    "users": [_raw_user(username="bob", user_id=2)],
                    "hasMore": False,
                    "nextCursor": None,
                }
                self.assertEqual(request.url.params["cursor"], "1")
            return httpx.Response(200, json={"response": response}, request=request)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = RemnawaveHttpProvider(
                client,
                base_url="https://panel.example",
                token="secret",
                api_major=3,
            )
            users = await provider.list_users()

        self.assertEqual([user.username for user in users], ["alice", "bob"])


class _FakeProvider:
    def __init__(self) -> None:
        self.users = [
            _user("alice", 1),
            _user("bob", 2),
        ]

    async def create_user(self, request: CreateVpnUser) -> VpnUser:
        return _user(request.username, 3)

    async def extend_user(self, username: str, days: int) -> VpnUser:
        return _user(username, 1)

    async def list_users(self) -> list[VpnUser]:
        return self.users

    async def get_user_usage(self, user: VpnUser, start: date, end: date) -> int:
        return {"alice": 3 * GIB, "bob": 5 * GIB}[user.username]

    async def get_nodes(self) -> list[VpnNodeLoad]:
        return [
            VpnNodeLoad(
                name="node-1",
                connected=True,
                users_online=2,
                cpu_count=2,
                load_average_1m=0.5,
                memory_used_bytes=GIB,
                memory_total_bytes=2 * GIB,
                rx_bytes_per_second=1024,
                tx_bytes_per_second=2048,
            )
        ]

    async def get_system_stats(self) -> VpnSystemStats:
        return VpnSystemStats(
            total_users=2,
            users_online=2,
            nodes_online=1,
            lifetime_traffic_bytes=100 * GIB,
            panel_memory_used_bytes=GIB,
            panel_memory_total_bytes=2 * GIB,
        )


class VpnServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_create_uses_configured_defaults(self) -> None:
        provider = _FakeProvider()
        service = VpnService(
            provider,
            default_duration_days=45,
            default_traffic_gb=100,
            default_squad_uuids=("squad",),
        )
        user = await service.create_user(
            "charlie",
            now=datetime(2026, 9, 3, tzinfo=timezone.utc),
        )
        self.assertEqual(user.username, "charlie")

    async def test_weekly_report_orders_users_and_totals_traffic(self) -> None:
        service = VpnService(_FakeProvider(), report_timezone="Europe/Moscow")
        report = await service.weekly_report(
            now=datetime(2026, 9, 3, 12, tzinfo=timezone.utc)
        )

        self.assertEqual(report.period_start, date(2026, 8, 27))
        self.assertEqual(report.period_end, date(2026, 9, 3))
        self.assertEqual(report.total_traffic_bytes, 8 * GIB)
        self.assertEqual([item.username for item in report.user_usage], ["bob", "alice"])
        rendered = format_vpn_report(report, top_users=1)
        self.assertIn("8.00 ГБ", rendered)
        self.assertIn("node-1", rendered)


class VpnTelegramParsingTests(unittest.TestCase):
    def test_create_and_extend_parsing(self) -> None:
        self.assertEqual(parse_create_request("alice"), ("alice", None, None, None))
        self.assertEqual(
            parse_create_request("alice 30 - 123"),
            ("alice", 30, None, 123),
        )
        self.assertEqual(parse_extend_request("alice 15"), ("alice", 15))


class _FakeBot:
    def __init__(self) -> None:
        self.messages: list[tuple[int, str, object | None]] = []
        self.deleted: list[tuple[int, int]] = []

    async def send_message(self, chat_id: int, text: str, *, reply_markup=None) -> None:
        self.messages.append((chat_id, text, reply_markup))

    async def delete_message(self, chat_id: int, message_id: int) -> None:
        self.deleted.append((chat_id, message_id))


class VpnReportWorkerTests(unittest.IsolatedAsyncioTestCase):
    async def test_manual_report_deletes_status_and_puts_menu_last(self) -> None:
        bot = _FakeBot()
        service = VpnService(_FakeProvider(), report_timezone="Europe/Moscow")
        settings = SimpleNamespace(
            remnawave_configured=True,
            vpn_report_recipients=(),
            remnawave_report_top_users=20,
        )

        await send_vpn_report(
            {"bot": bot, "vpn_service": service, "settings": settings},
            chat_ids=[123],
            status_messages={"123": 456},
        )

        self.assertEqual(bot.deleted, [(123, 456)])
        self.assertTrue(bot.messages)
        self.assertIsNotNone(bot.messages[-1][2])

    async def test_failed_report_also_deletes_status_and_restores_menu(self) -> None:
        class BrokenService:
            async def weekly_report(self):
                raise RuntimeError("provider failed")

        bot = _FakeBot()
        settings = SimpleNamespace(
            remnawave_configured=True,
            vpn_report_recipients=(),
            remnawave_report_top_users=20,
        )

        with self.assertRaises(RuntimeError):
            await send_vpn_report(
                {"bot": bot, "vpn_service": BrokenService(), "settings": settings},
                chat_ids=[123],
                status_messages={"123": 456},
            )

        self.assertEqual(bot.deleted, [(123, 456)])
        self.assertEqual(bot.messages[-1][0], 123)
        self.assertIsNotNone(bot.messages[-1][2])


def _user(username: str, user_id: int) -> VpnUser:
    return VpnUser(
        id=user_id,
        username=username,
        status="ACTIVE",
        expire_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
        traffic_limit_bytes=0,
        used_traffic_bytes=0,
        lifetime_used_traffic_bytes=0,
        subscription_url="",
    )


if __name__ == "__main__":
    unittest.main()
