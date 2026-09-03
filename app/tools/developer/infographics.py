from __future__ import annotations

import io
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from app.tools.developer.models import ColorResult

_FONT_DIR = Path(__file__).parents[1] / "network" / "assets" / "fonts"


@lru_cache(maxsize=16)
def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    filename = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    try:
        return ImageFont.truetype(str(_FONT_DIR / filename), size)
    except OSError:
        return ImageFont.load_default(size=size)


def render_color_card(color: ColorResult) -> bytes:
    width, height = 900, 540
    image = Image.new("RGB", (width, height), color.hex)
    draw = ImageDraw.Draw(image)
    foreground = color.foreground
    muted = _blend_hex(foreground, color.hex, 0.68)

    draw.rounded_rectangle((42, 42, width - 42, height - 42), radius=32, outline=foreground, width=3)
    draw.text((78, 78), color.hex, font=_font(68, True), fill=foreground)
    draw.text((80, 164), f"RGB  {color.red} · {color.green} · {color.blue}", font=_font(30, True), fill=foreground)
    draw.text(
        (80, 210),
        f"HSL  {color.hue}° · {color.saturation}% · {color.lightness}%",
        font=_font(26),
        fill=muted,
    )

    labels = (("R", color.red), ("G", color.green), ("B", color.blue))
    y = 310
    for label, value in labels:
        draw.text((80, y - 5), label, font=_font(23, True), fill=foreground)
        draw.rounded_rectangle((125, y, 790, y + 22), radius=11, outline=foreground, width=2)
        bar_width = round(661 * value / 255)
        if bar_width:
            draw.rounded_rectangle((127, y + 2, 127 + bar_width, y + 20), radius=9, fill=foreground)
        draw.text((805, y - 7), str(value), font=_font(21, True), fill=foreground, anchor="ra")
        y += 58

    draw.text((80, 485), f"Относительная яркость: {color.luminance:.3f}", font=_font(20), fill=muted)
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


def _blend_hex(left: str, right: str, ratio: float) -> str:
    a = tuple(int(left.removeprefix("#")[i : i + 2], 16) for i in (0, 2, 4))
    b = tuple(int(right.removeprefix("#")[i : i + 2], 16) for i in (0, 2, 4))
    mixed = tuple(round(x * ratio + y * (1 - ratio)) for x, y in zip(a, b, strict=True))
    return "#{:02X}{:02X}{:02X}".format(*mixed)
