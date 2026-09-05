from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SearchQuery:
    title: str
    year: int | None = None
    season: int | None = None


@dataclass(frozen=True)
class Release:
    topic_id: int
    title: str
    size: int
    seeders: int
    resolution: int = 0
    source: str = "Не указан"
    audio: str = "Не указана"
    dynamic_range: str = "Не указан"


class CinemaError(Exception):
    """Safe message that may be displayed by any interface."""


class TemporaryCinemaError(CinemaError):
    pass


class AuthenticationError(CinemaError):
    pass
