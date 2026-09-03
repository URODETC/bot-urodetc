from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class TextLengthResult:
    characters: int
    characters_without_spaces: int
    words: int
    lines: int
    utf8_bytes: int
    utf16_bytes: int


@dataclass(frozen=True)
class ColorResult:
    hex: str
    red: int
    green: int
    blue: int
    hue: int
    saturation: int
    lightness: int
    luminance: float
    foreground: str


@dataclass(frozen=True)
class UnixTimeResult:
    timestamp: float
    utc: datetime
    local: datetime
    source_was_timestamp: bool
