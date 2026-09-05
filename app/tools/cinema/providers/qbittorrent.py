from __future__ import annotations

import asyncio
import base64
import re
from urllib.parse import parse_qs, urlsplit

import httpx

from app.tools.cinema.models import AuthenticationError, CinemaError, TemporaryCinemaError


def magnet_hash(magnet: str) -> str:
    if not magnet.startswith("magnet:?"):
        raise CinemaError("Некорректная magnet-ссылка.")
    for xt in parse_qs(urlsplit(magnet).query).get("xt", []):
        value = xt.removeprefix("urn:btih:")
        if xt.startswith("urn:btih:"):
            if re.fullmatch(r"[0-9a-fA-F]{40}", value):
                return value.lower()
            if re.fullmatch(r"[A-Z2-7]{32}", value, re.I):
                return base64.b32decode(value.upper()).hex()
    raise CinemaError("Magnet-ссылка не содержит корректный хеш раздачи.")


class QBittorrentProvider:
    def __init__(self, client: httpx.AsyncClient, *, base_url: str, username: str, password: str, save_path: str = "", category: str = "cinema"):
        self.client = client
        self.base_url = base_url.rstrip("/")
        self.username, self.password = username, password
        self.save_path, self.category = save_path, category
        self.lock = asyncio.Lock()

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        try:
            headers = {"Referer": self.base_url + "/"}
            async with self.lock:
                response = await self.client.request(method, self.base_url + "/api/v2/" + path, headers=headers, **kwargs)
                if response.status_code == 403:
                    login = await self.client.post(self.base_url + "/api/v2/auth/login", data={"username": self.username, "password": self.password}, headers=headers)
                    if login.status_code != 200 or login.text.strip() != "Ok.":
                        raise AuthenticationError("qBittorrent: проверьте логин, пароль и доступ к WebUI.")
                    response = await self.client.request(method, self.base_url + "/api/v2/" + path, headers=headers, **kwargs)
            if response.status_code == 429 or response.status_code >= 500:
                raise TemporaryCinemaError("qBittorrent временно недоступен.")
            response.raise_for_status()
            return response
        except httpx.HTTPError:
            raise TemporaryCinemaError("Не удалось подключиться к qBittorrent.") from None

    async def add(self, magnet: str) -> str:
        info_hash = magnet_hash(magnet)
        if await self.status(info_hash):
            return info_hash
        data = {"urls": magnet, "category": self.category, "autoTMM": "false", "paused": "false", "stopped": "false"}
        if self.save_path:
            data["savepath"] = self.save_path
        response = await self._request("POST", "torrents/add", data=data)
        if response.text.strip() != "Ok.":
            raise CinemaError("qBittorrent не принял раздачу.")
        return info_hash

    async def status(self, info_hash: str) -> dict:
        if not re.fullmatch(r"[a-f0-9]{40}", info_hash):
            raise CinemaError("Некорректный хеш раздачи.")
        response = await self._request("GET", "torrents/info", params={"hashes": info_hash})
        try:
            rows = response.json()
            if not isinstance(rows, list):
                raise ValueError
            return rows[0] if rows else {}
        except (ValueError, TypeError):
            raise CinemaError("qBittorrent вернул некорректный ответ.") from None
