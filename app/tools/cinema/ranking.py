from __future__ import annotations

import re
from dataclasses import replace

from app.tools.cinema.models import CinemaError, Release, SearchQuery


def normalize(text: str) -> str:
    return " ".join(re.findall(r"[a-zа-я0-9]+", text.lower().replace("ё", "е")))


def parse_query(text: str) -> SearchQuery:
    text = re.sub(r"^(?:хочу\s+(?:посмотреть|скачать)|скачай|найди|посмотреть)\s+", "", text.strip(), flags=re.I)
    text = re.sub(r"^(?:фильм|сериал)\s+", "", text, flags=re.I)
    season = re.search(r"\b(?:сезон\s*[:№]?\s*|s)(\d{1,2})\b|\b(\d{1,2})\s*(?:-й\s*)?сезон\b", text, re.I)
    season_number = int(season.group(1) or season.group(2)) if season else None
    if season:
        text = text[:season.start()] + " " + text[season.end():]
    years = list(re.finditer(r"\b(?:19|20)\d{2}\b", text))
    year = years[-1] if years and normalize(text[:years[-1].start()] + text[years[-1].end():]) else None
    year_number = int(year.group()) if year else None
    if year:
        text = text[:year.start()] + " " + text[year.end():]
    title = normalize(text)
    if not 2 <= len(title) <= 160:
        raise CinemaError("Укажите название (2–160 символов), при необходимости год и сезон.")
    return SearchQuery(title, year_number, season_number)


def enrich(release: Release) -> Release:
    title = release.title
    match = re.search(r"\b(2160|1080|720)[pi]?\b", title, re.I)
    resolution = int(match.group(1)) if match else (2160 if re.search(r"\b(?:4k|uhd)\b", title, re.I) else 0)
    source = next((label for pattern, label in [
        (r"remux", "REMUX"), (r"web[ -]?dl(?!rip)", "WEB-DL"),
        (r"blu[ -]?ray|bdrip", "BluRay/BDRip"), (r"webrip|web-dlrip", "WEBRip"),
        (r"hdtv", "HDTV"),
    ] if re.search(pattern, title, re.I)), "Не указан")
    audio = next((label for pattern, label in [
        (r"\b(?:dub|дб|дубляж)\b", "Дубляж"),
        (r"\b(?:mvo|мво)\b|многоголос", "Многоголосая"),
        (r"\b(?:dvo|дво)\b|двухголос", "Двухголосая"),
        (r"\b(?:avo|vo)\b|одноголос", "Одноголосая"),
    ] if re.search(pattern, title, re.I)), "Не указана")
    ranges = [label for pattern, label in [
        (r"dolby\s*vision|\bdv\b|\bdovi\b", "Dolby Vision"),
        (r"hdr10\+", "HDR10+"), (r"\bhdr(?:10)?\b(?!\+)", "HDR"), (r"\bsdr\b", "SDR"),
    ] if re.search(pattern, title, re.I)]
    return replace(release, resolution=resolution, source=source, audio=audio, dynamic_range=" / ".join(ranges) or "Не указан")


def rank_releases(query: SearchQuery, releases: list[Release]) -> list[Release]:
    result = {}
    for raw in releases:
        release = enrich(raw)
        if not release.resolution and release.source == "Не указан" and not re.search(r"dvd|hdrip|satrip|tvrip|camrip", release.title, re.I):
            continue
        # Match title aliases before the metadata, not words in descriptions/audio.
        title_part = re.split(r"[\[(]|/\s*сезон|/\s*season", release.title, maxsplit=1, flags=re.I)[0]
        if not set(query.title.split()).issubset(set(normalize(title_part).split())):
            continue
        if query.year and not re.search(rf"\b{query.year}\b", release.title):
            continue
        if query.season is not None:
            seasons = re.findall(r"(?:сезон[ы]?\s*[:№]?\s*|\bs)(\d{1,2})(?:\s*[-–]\s*(\d{1,2}))?", release.title, re.I)
            if not any(int(start) <= query.season <= int(end or start) for start, end in seasons):
                continue
        result[release.topic_id] = release
    # Availability first; within live releases, strongly prefer UHD.
    return sorted(result.values(), key=lambda r: (
        r.seeders > 0, r.resolution, r.audio != "Не указана", r.seeders,
        {"REMUX": 3, "BluRay/BDRip": 2, "WEB-DL": 2}.get(r.source, 0), -r.size, -r.topic_id,
    ), reverse=True)
