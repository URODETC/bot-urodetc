from __future__ import annotations

import base64
import colorsys
import hashlib
import io
import secrets
import string
import uuid as uuid_module
from datetime import datetime, timezone
from urllib.parse import quote, unquote
from zoneinfo import ZoneInfo

from PIL import Image

from app.tools.developer.md2 import md2_hex
from app.tools.developer.models import ColorResult, TextLengthResult, UnixTimeResult


class DeveloperInputError(ValueError):
    pass


class DeveloperService:
    def __init__(self, timezone_name: str = "Europe/Moscow") -> None:
        self._timezone = ZoneInfo(timezone_name)

    def urlencode(self, text: str) -> str:
        return quote(_require_text(text), safe="")

    def urldecode(self, text: str) -> str:
        return unquote(_require_text(text))

    def digest(self, algorithm: str, text: str) -> str:
        value = _require_text(text).encode("utf-8")
        normalized = algorithm.lower()
        if normalized == "md2":
            return md2_hex(value)
        if normalized not in {"md5", "sha1", "sha256", "sha384", "sha512"}:
            raise DeveloperInputError(f"Неизвестный алгоритм: {algorithm}")
        return hashlib.new(normalized, value, usedforsecurity=False).hexdigest()

    def text_length(self, text: str) -> TextLengthResult:
        value = _require_text(text, allow_whitespace=True)
        return TextLengthResult(
            characters=len(value),
            characters_without_spaces=sum(not char.isspace() for char in value),
            words=len(value.split()),
            lines=value.count("\n") + 1,
            utf8_bytes=len(value.encode("utf-8")),
            utf16_bytes=len(value.encode("utf-16-le")),
        )

    def color(self, raw: str | None = None) -> ColorResult:
        if raw is None or not raw.strip():
            red, green, blue = (secrets.randbelow(256) for _ in range(3))
        else:
            value = raw.strip()
            if value.startswith("#") or (len(value) in {3, 6} and " " not in value):
                hex_value = value.removeprefix("#")
                if len(hex_value) == 3:
                    hex_value = "".join(char * 2 for char in hex_value)
                try:
                    red, green, blue = (int(hex_value[index : index + 2], 16) for index in (0, 2, 4))
                except (ValueError, IndexError) as exc:
                    raise DeveloperInputError("HEX должен выглядеть так: #abcdef") from exc
            else:
                parts = value.replace(",", " ").split()
                if len(parts) != 3:
                    raise DeveloperInputError("Укажите HEX (#abcdef) или RGB (1 2 3)")
                try:
                    red, green, blue = (int(part) for part in parts)
                except ValueError as exc:
                    raise DeveloperInputError("RGB должен содержать три целых числа") from exc
                if any(channel < 0 or channel > 255 for channel in (red, green, blue)):
                    raise DeveloperInputError("Компоненты RGB должны быть от 0 до 255")
        hue, saturation, lightness = colorsys.rgb_to_hls(red / 255, green / 255, blue / 255)
        luminance = _relative_luminance(red, green, blue)
        return ColorResult(
            hex=f"#{red:02X}{green:02X}{blue:02X}",
            red=red,
            green=green,
            blue=blue,
            hue=round(hue * 360),
            saturation=round(saturation * 100),
            lightness=round(lightness * 100),
            luminance=luminance,
            foreground="#0B1220" if luminance > 0.45 else "#FFFFFF",
        )

    def unix_time(self, raw: str | None = None) -> UnixTimeResult:
        value = (raw or "").strip()
        source_was_timestamp = False
        if not value:
            moment = datetime.now(timezone.utc)
        else:
            try:
                timestamp = float(value)
            except ValueError:
                moment = _parse_datetime(value, self._timezone).astimezone(timezone.utc)
            else:
                source_was_timestamp = True
                try:
                    moment = datetime.fromtimestamp(timestamp, timezone.utc)
                except (OverflowError, OSError, ValueError) as exc:
                    raise DeveloperInputError("Unix timestamp вне поддерживаемого диапазона") from exc
        return UnixTimeResult(
            timestamp=moment.timestamp(),
            utc=moment,
            local=moment.astimezone(self._timezone),
            source_was_timestamp=source_was_timestamp,
        )

    def base64encode(self, text: str) -> str:
        return base64.b64encode(_require_text(text).encode()).decode()

    def base64decode(self, text: str) -> str:
        try:
            return base64.b64decode(_require_text(text), validate=True).decode("utf-8")
        except (ValueError, UnicodeDecodeError) as exc:
            raise DeveloperInputError("Некорректная Base64-строка или результат не является UTF-8 текстом") from exc

    def uuid(self) -> str:
        return str(uuid_module.uuid4())

    def password(self, length: int = 20) -> str:
        if length < 8 or length > 128:
            raise DeveloperInputError("Длина пароля должна быть от 8 до 128")
        alphabet = string.ascii_letters + string.digits + "!@#$%^&*_-+="
        while True:
            value = "".join(secrets.choice(alphabet) for _ in range(length))
            if all(any(char in group for char in value) for group in (string.ascii_lowercase, string.ascii_uppercase, string.digits)):
                return value

    def qr_generate(self, text: str) -> bytes:
        value = _require_text(text)
        if len(value.encode("utf-8")) > 2000:
            raise DeveloperInputError("Для QR используйте не более 2000 байт")
        try:
            import qrcode
        except ImportError as exc:
            raise RuntimeError("Пакет qrcode не установлен") from exc
        qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=12, border=4)
        qr.add_data(value)
        qr.make(fit=True)
        image = qr.make_image(fill_color="#0B1220", back_color="white").convert("RGB")
        buffer = io.BytesIO()
        image.save(buffer, "PNG")
        return buffer.getvalue()

    def qr_decode(self, image_bytes: bytes) -> str:
        try:
            import zxingcpp
        except ImportError as exc:
            raise RuntimeError("Пакет zxing-cpp не установлен") from exc
        try:
            image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            results = zxingcpp.read_barcodes(image)
        except (OSError, ValueError) as exc:
            raise DeveloperInputError("Не удалось прочитать изображение") from exc
        qr_codes = [item for item in results if item.format == zxingcpp.BarcodeFormat.QRCode]
        if not qr_codes:
            raise DeveloperInputError("QR-код на изображении не найден")
        return "\n".join(item.text for item in qr_codes if item.text)


def _require_text(text: str, *, allow_whitespace: bool = False) -> str:
    if not text or (not allow_whitespace and not text.strip()):
        raise DeveloperInputError("После команды нужен текст")
    return text


def _parse_datetime(value: str, local_timezone: ZoneInfo) -> datetime:
    normalized = value.strip().replace("Z", "+00:00")
    try:
        moment = datetime.fromisoformat(normalized)
    except ValueError:
        for pattern in ("%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M", "%d.%m.%Y", "%Y-%m-%d"):
            try:
                moment = datetime.strptime(normalized, pattern)
                break
            except ValueError:
                continue
        else:
            raise DeveloperInputError("Дата: ISO 8601 или ДД.ММ.ГГГГ ЧЧ:ММ") from None
    return moment.replace(tzinfo=local_timezone) if moment.tzinfo is None else moment


def _relative_luminance(red: int, green: int, blue: int) -> float:
    channels = []
    for value in (red, green, blue):
        channel = value / 255
        channels.append(channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4)
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]
