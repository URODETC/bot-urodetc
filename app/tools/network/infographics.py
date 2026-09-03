from __future__ import annotations

import io
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from app.tools.network.models import GeoResult, IpOwnerResult

_ASSETS_DIR = Path(__file__).parent / "assets" / "fonts"
_FONT_REGULAR = _ASSETS_DIR / "DejaVuSans.ttf"
_FONT_BOLD = _ASSETS_DIR / "DejaVuSans-Bold.ttf"

_WIDTH, _HEIGHT = 1000, 620
_BG = "#0b1220"
_PANEL = "#111a2e"
_LABEL_COLOR = "#7f8db0"
_VALUE_COLOR = "#f4f6fb"
_GRID_COLOR = "#22304f"

_RIR_COLORS: dict[str, str] = {
    "ARIN": "#38bdf8",
    "RIPE NCC": "#a78bfa",
    "APNIC": "#f472b6",
    "LACNIC": "#facc15",
    "AFRINIC": "#4ade80",
}


@lru_cache(maxsize=32)
def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    path = _FONT_BOLD if bold else _FONT_REGULAR
    try:
        return ImageFont.truetype(str(path), size=size)
    except OSError:
        # Falls back to Pillow's bundled font if the asset is ever missing;
        # it lacks Cyrillic glyphs but keeps the card from crashing.
        return ImageFont.load_default(size=size)


def _new_canvas(accent: str) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", (_WIDTH, _HEIGHT), _BG)
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((0, 0, _WIDTH - 1, _HEIGHT - 1), radius=28, outline=_GRID_COLOR, width=2)
    draw.rounded_rectangle((0, 0, _WIDTH - 1, 12), radius=28, fill=accent)
    draw.rectangle((0, 6, _WIDTH - 1, 12), fill=accent)
    return img, draw


def _header(
    draw: ImageDraw.ImageDraw,
    *,
    badge: str,
    title: str,
    subtitle: str,
    accent: str,
) -> None:
    badge_font = _font(22, bold=True)
    badge_width = int(draw.textlength(badge, font=badge_font)) + 40
    draw.rounded_rectangle((40, 36, 40 + badge_width, 78), radius=18, fill=accent)
    draw.text((60, 46), badge, font=badge_font, fill=_BG)
    draw.text((40, 96), title, font=_font(46, bold=True), fill=_VALUE_COLOR)
    draw.text((40, 152), subtitle, font=_font(24), fill=_LABEL_COLOR)
    draw.line((40, 196, _WIDTH - 40, 196), fill=_GRID_COLOR, width=2)


def _rows(
    draw: ImageDraw.ImageDraw,
    rows: list[tuple[str, str]],
    *,
    top: int,
    left: int = 40,
    width: int = 500,
    row_height: int = 56,
) -> int:
    y = top
    label_font = _font(20)
    value_font = _font(24, bold=True)
    for label, value in rows:
        draw.text((left, y), label.upper(), font=label_font, fill=_LABEL_COLOR)
        draw.text((left, y + 24), value, font=value_font, fill=_VALUE_COLOR)
        y += row_height
    return y


def _to_png(img: Image.Image) -> bytes:
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


def render_geo_card(geo: GeoResult) -> bytes:
    accent = "#22d3ee"
    img, draw = _new_canvas(accent)
    badge = f"GEO IP · {geo.country_code}" if geo.country_code else "GEO IP"
    _header(
        draw,
        badge=badge,
        title=geo.ip,
        subtitle=", ".join(filter(None, [geo.city, geo.region, geo.country])) or "Местоположение неизвестно",
        accent=accent,
    )

    left_rows = [
        ("Страна", geo.country or "—"),
        ("Регион", geo.region or "—"),
        ("Город", geo.city or "—"),
        ("Часовой пояс", geo.timezone or "—"),
    ]
    right_rows = [
        ("Провайдер (ISP)", _truncate(geo.isp or "—", 34)),
        ("Организация", _truncate(geo.org or "—", 34)),
        ("AS-номер", geo.asn or "—"),
        ("Координаты", _coords(geo.lat, geo.lon)),
    ]
    _rows(draw, left_rows, top=220, left=40, width=440)
    _rows(draw, right_rows, top=220, left=520, width=440)

    _draw_world_map(draw, geo.lat, geo.lon, accent, top=460, left=40, width=_WIDTH - 80, height=120)
    return _to_png(img)


def render_ip_owner_card(owner: IpOwnerResult) -> bytes:
    accent = _RIR_COLORS.get(owner.rir or "", "#f59e0b")
    img, draw = _new_canvas(accent)
    _header(
        draw,
        badge=owner.rir or "RIR",
        title=owner.query,
        subtitle=owner.network_range or "Блок адресов неизвестен",
        accent=accent,
    )

    left_rows = [
        ("Владелец / LIR", _truncate(owner.lir or "—", 32)),
        ("Диапазон сети", _truncate(owner.network_range or "—", 32)),
        ("Регистратура (RIR)", owner.rir or "—"),
        ("Страна", owner.country or "—"),
    ]
    _rows(draw, left_rows, top=220, left=40, width=440)

    y = 220
    draw.text((520, y), "РОЛИ / КОНТАКТЫ", font=_font(20), fill=_LABEL_COLOR)
    y += 34
    for entity in owner.entities[:4]:
        label = entity.name or entity.handle or "—"
        roles = ", ".join(entity.roles) or "role?"
        draw.text((520, y), f"• {_truncate(label, 26)}", font=_font(22, bold=True), fill=_VALUE_COLOR)
        draw.text((540, y + 26), roles, font=_font(18), fill=_LABEL_COLOR)
        y += 58

    _draw_block_bar(draw, owner, accent, top=500, left=40, width=_WIDTH - 80, height=64)
    return _to_png(img)


def _draw_world_map(
    draw: ImageDraw.ImageDraw,
    lat: float | None,
    lon: float | None,
    accent: str,
    *,
    top: int,
    left: int,
    width: int,
    height: int,
) -> None:
    draw.rounded_rectangle(
        (left, top, left + width, top + height), radius=12, outline=_GRID_COLOR, width=2, fill=_PANEL
    )
    for fraction in (0.25, 0.5, 0.75):
        x = left + int(width * fraction)
        draw.line((x, top, x, top + height), fill=_GRID_COLOR, width=1)
    mid_y = top + height // 2
    draw.line((left, mid_y, left + width, mid_y), fill=_GRID_COLOR, width=1)
    tick_font = _font(14)
    draw.text((left + 6, top + 4), "-180°", font=tick_font, fill=_LABEL_COLOR)
    draw.text((left + width - 48, top + 4), "180°", font=tick_font, fill=_LABEL_COLOR)
    draw.text((left + 6, top + height - 20), "90°N/S", font=tick_font, fill=_LABEL_COLOR)

    if lat is None or lon is None:
        return
    x = left + int((lon + 180) / 360 * width)
    y = top + int((90 - lat) / 180 * height)
    radius = 8
    draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=accent)
    draw.ellipse((x - radius - 5, y - radius - 5, x + radius + 5, y + radius + 5), outline=accent, width=2)
    draw.line((x - 16, y, x + 16, y), fill=accent, width=1)
    draw.line((x, y - 16, x, y + 16), fill=accent, width=1)


def _draw_block_bar(
    draw: ImageDraw.ImageDraw,
    owner: IpOwnerResult,
    accent: str,
    *,
    top: int,
    left: int,
    width: int,
    height: int,
) -> None:
    draw.rounded_rectangle(
        (left, top, left + width, top + height), radius=12, outline=_GRID_COLOR, width=2, fill=_PANEL
    )
    draw.rounded_rectangle((left + 8, top + 8, left + width - 8, top + height - 8), radius=8, fill=accent)
    label = owner.network_range or owner.query
    draw.text(
        (left + 20, top + height // 2 - 12),
        _truncate(label, 60),
        font=_font(22, bold=True),
        fill=_BG,
    )


def _coords(lat: float | None, lon: float | None) -> str:
    if lat is None or lon is None:
        return "—"
    return f"{lat:.3f}, {lon:.3f}"


def _truncate(value: str, limit: int) -> str:
    return value if len(value) <= limit else value[: limit - 1] + "…"
