from __future__ import annotations

import asyncio
import re
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx
from bs4 import BeautifulSoup

from app.tools.cinema.models import AuthenticationError, CinemaError, Release, TemporaryCinemaError


def parse_size(value: str) -> int:
    value = value.replace("\xa0", " ").strip()
    if value.isdigit():
        return int(value)
    match = re.fullmatch(r"([0-9]+(?:[.,][0-9]+)?)\s*([KMGT])(?:i?B|Б)", value, re.I)
    if not match:
        raise ValueError("Unrecognized torrent size")
    return int(float(match[1].replace(",", ".")) * 1024 ** ("KMGT".index(match[2].upper()) + 1))


def parse_results(html: str) -> list[Release]:
    soup = BeautifulSoup(html, "html.parser")
    if soup.select_one("#tor-tbl") is None:
        if "не найден" in soup.get_text().lower() or "нет подходящих" in soup.get_text().lower():
            return []
        raise CinemaError("RuTracker вернул неизвестную страницу поиска. Возможно, изменилась разметка.")
    results = []
    for row in soup.select("#tor-tbl tr"):
        link = row.select_one("a.tLink")
        size_cell = row.select_one("td.tor-size")
        if link is None or size_cell is None or size_cell.select_one("a.tr-dl") is None:
            continue
        try:
            topic_id = int(parse_qs(urlsplit(str(link.get("href", ""))).query)["t"][0])
            size_text = str(size_cell.get("data-ts_text", ""))
            if not size_text:
                hidden = size_cell.select_one("u")
                size_text = hidden.get_text(strip=True) if hidden else size_cell.select_one("a.tr-dl").get_text(strip=True)
            size = parse_size(size_text)
            category = row.select_one(".f-name-col")
            if category and re.search(r"аудиокниг|звуковые дорожки|саундтрек|soundtrack|игры", category.get_text(), re.I):
                continue
            seed = row.select_one(".seedmed b, b.seedmed")
            if seed is None:
                cells = row.find_all("td", recursive=False)
                seed = cells[6].find("b") if len(cells) > 6 else None
            seeders = int(re.sub(r"\s", "", seed.get_text())) if seed else 0
            results.append(Release(topic_id, link.get_text(" ", strip=True), size, seeders))
        except (ValueError, KeyError, IndexError):
            raise CinemaError("Не удалось разобрать результаты RuTracker. Требуется обновить парсер.") from None
    return results


class RutrackerProvider:
    def __init__(self, client: httpx.AsyncClient, *, base_url: str, username: str = "", password: str = "", session: str = "", pages: int = 3):
        self.client = client
        self.base_url = base_url.rstrip("/")
        if urlsplit(self.base_url).scheme != "https":
            raise ValueError("RUTRACKER_URL must use HTTPS")
        self.username, self.password = username, password
        self.pages = pages
        self.lock = asyncio.Lock()
        if session:
            client.cookies.set("bb_session", session, domain=urlsplit(self.base_url).hostname, path="/")

    async def _get(self, path: str, **kwargs) -> httpx.Response:
        try:
            response = await self.client.get(self.base_url + path, **kwargs)
            if response.status_code == 429 or response.status_code >= 500:
                raise TemporaryCinemaError("RuTracker временно недоступен. Повторите позже.")
            response.raise_for_status()
            response.encoding = "windows-1251"
            return response
        except httpx.HTTPError:
            raise TemporaryCinemaError("Не удалось подключиться к RuTracker.") from None

    async def _page(self, path: str, **kwargs) -> str:
        response = await self._get(path, **kwargs)
        if 'logged-in-username' in response.text:
            return response.text
        if not self.username or not self.password:
            raise AuthenticationError("Обновите RUTRACKER_SESSION или настройте логин и пароль RuTracker.")
        try:
            body = urlencode({"login_username": self.username, "login_password": self.password, "login": "Login"}, encoding="cp1251")
            login = await self.client.post(self.base_url + "/forum/login.php", content=body, headers={"Content-Type": "application/x-www-form-urlencoded", "Referer": self.base_url + "/forum/login.php"})
            login.raise_for_status()
        except (httpx.HTTPError, UnicodeError):
            raise AuthenticationError("Не удалось войти в RuTracker. Проверьте настройки сессии.") from None
        response = await self._get(path, **kwargs)
        if 'logged-in-username' not in response.text:
            raise AuthenticationError("RuTracker требует вход или CAPTCHA. Войдите в браузере и обновите RUTRACKER_SESSION.")
        return response.text

    async def search(self, title: str) -> list[Release]:
        async with self.lock:
            results = {}
            # A targeted UHD page prevents popular 1080p releases crowding out 4K.
            for search_title, pages in ((title + " 2160", 1), (title, self.pages)):
                for page in range(pages):
                    query = urlencode({"nm": search_title, "o": 10, "s": 2, "start": page * 50}, encoding="cp1251")
                    html = await self._page("/forum/tracker.php?" + query)
                    rows = parse_results(html)
                    for row in rows:
                        results[row.topic_id] = row
                    if len(rows) < 50:
                        break
                    await asyncio.sleep(1)
                await asyncio.sleep(1)
            return list(results.values())

    async def magnet(self, topic_id: int) -> str:
        if topic_id <= 0:
            raise CinemaError("Некорректная раздача.")
        async with self.lock:
            html = await self._page(f"/forum/viewtopic.php?t={topic_id}")
        soup = BeautifulSoup(html, "html.parser")
        link = soup.select_one('a.magnet-link[href^="magnet:?"]')
        if link is None:
            raise CinemaError("В раздаче отсутствует magnet-ссылка. Возможно, она удалена или закрыта.")
        return str(link["href"])
