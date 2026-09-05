from __future__ import annotations

import io

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, Message

from app.telegram.menu import main_menu_keyboard
from app.telegram.ui import esc
from app.tools.developer.infographics import render_color_card
from app.tools.developer.models import TextLengthResult, UnixTimeResult
from app.tools.developer.service import DeveloperInputError, DeveloperService

router = Router(name="developer-commands")

_HASHES = ("sha1", "sha256", "sha384", "sha512", "md2", "md5")
_CODECS = ("urlencode", "urldecode", "base64encode", "base64decode")


@router.message(Command(*_HASHES))
async def hash_command(message: Message, developer_service: DeveloperService) -> None:
    command, argument = _command_and_argument(message)
    argument = _argument_or_reply(message, argument)
    try:
        digest = developer_service.digest(command, argument)
    except DeveloperInputError as exc:
        await message.answer(
            f"Использование: <code>/{command} &lt;текст&gt;</code>\n{esc(str(exc))}",
            reply_markup=main_menu_keyboard(),
        )
        return
    warning = "\n\n⚠️ <i>MD2/MD5/SHA-1 не подходят для хранения паролей.</i>" if command in {"md2", "md5", "sha1"} else ""
    await message.answer(
        f"🔐 <b>{command.upper()}</b>\n<code>{digest}</code>{warning}",
        reply_markup=main_menu_keyboard(),
    )


@router.message(Command(*_CODECS))
async def codec_command(message: Message, developer_service: DeveloperService) -> None:
    command, argument = _command_and_argument(message)
    argument = _argument_or_reply(message, argument)
    try:
        result = getattr(developer_service, command)(argument)
    except DeveloperInputError as exc:
        await message.answer(
            f"Использование: <code>/{command} &lt;текст&gt;</code>\n{esc(str(exc))}",
            reply_markup=main_menu_keyboard(),
        )
        return
    await _answer_code(message, command, result)


@router.message(Command("length"))
@router.message(F.text.regexp(r"^/длина(?:@\w+)?(?:\s|$)"))
async def length_command(message: Message, developer_service: DeveloperService) -> None:
    _, argument = _command_and_argument(message)
    argument = _argument_or_reply(message, argument)
    try:
        result = developer_service.text_length(argument)
    except DeveloperInputError as exc:
        await message.answer(
            f"Использование: <code>/length &lt;текст&gt;</code>\n{esc(str(exc))}",
            reply_markup=main_menu_keyboard(),
        )
        return
    await message.answer(_format_length(result), reply_markup=main_menu_keyboard())


@router.message(Command("getcolor"))
@router.message(F.text.regexp(r"^/цвет(?:@\w+)?(?:\s|$)"))
async def color_command(message: Message, developer_service: DeveloperService) -> None:
    _, argument = _command_and_argument(message)
    try:
        color = developer_service.color(argument)
    except DeveloperInputError as exc:
        await message.answer(f"🎨 {esc(str(exc))}", reply_markup=main_menu_keyboard())
        return
    image = render_color_card(color)
    caption = (
        f"🎨 <b>{color.hex}</b>\n"
        f"RGB: <code>{color.red} {color.green} {color.blue}</code>\n"
        f"HSL: <code>{color.hue}° {color.saturation}% {color.lightness}%</code>"
    )
    await message.answer_photo(
        BufferedInputFile(image, filename=f"color-{color.hex[1:]}.png"),
        caption=caption,
        reply_markup=main_menu_keyboard(),
    )


@router.message(Command("unix"))
async def unix_command(message: Message, developer_service: DeveloperService) -> None:
    _, argument = _command_and_argument(message)
    try:
        result = developer_service.unix_time(argument)
    except DeveloperInputError as exc:
        await message.answer(f"🕒 {esc(str(exc))}", reply_markup=main_menu_keyboard())
        return
    await message.answer(_format_unix(result), reply_markup=main_menu_keyboard())


@router.message(Command("uuid"))
async def uuid_command(message: Message, developer_service: DeveloperService) -> None:
    await message.answer(
        f"🆔 UUID v4\n<code>{developer_service.uuid()}</code>",
        reply_markup=main_menu_keyboard(),
    )


@router.message(Command("password"))
async def password_command(message: Message, developer_service: DeveloperService) -> None:
    _, argument = _command_and_argument(message)
    try:
        length = int(argument) if argument else 20
        password = developer_service.password(length)
    except (DeveloperInputError, ValueError) as exc:
        text = str(exc) if isinstance(exc, DeveloperInputError) else "Длина должна быть целым числом"
        await message.answer(
            f"🔑 {esc(text)}\nИспользование: <code>/password 24</code>",
            reply_markup=main_menu_keyboard(),
        )
        return
    await message.answer(
        f"🔑 Пароль ({length} символов)\n<code>{esc(password)}</code>\n\n"
        "<i>Сообщение содержит секрет — удалите его после копирования.</i>",
        reply_markup=main_menu_keyboard(),
    )


@router.message(Command("qr"))
async def qr_command(message: Message, bot: Bot, developer_service: DeveloperService) -> None:
    _, argument = _command_and_argument(message)
    if argument:
        try:
            image = developer_service.qr_generate(argument)
        except (DeveloperInputError, RuntimeError) as exc:
            await message.answer(f"❌ {esc(str(exc))}", reply_markup=main_menu_keyboard())
            return
        await message.answer_photo(
            BufferedInputFile(image, filename="qr.png"),
            caption=f"◼️ QR-код создан · {len(argument.encode('utf-8'))} байт",
            reply_markup=main_menu_keyboard(),
        )
        return

    media = _image_media(message) or _image_media(message.reply_to_message)
    if media is None:
        await message.answer(
            "Создать: <code>/qr текст</code>\n"
            "Прочитать: отправьте /qr подписью к изображению или ответом на него.",
            reply_markup=main_menu_keyboard(),
        )
        return
    buffer = io.BytesIO()
    await bot.download(media, destination=buffer)
    try:
        decoded = developer_service.qr_decode(buffer.getvalue())
    except (DeveloperInputError, RuntimeError) as exc:
        await message.answer(f"❌ {esc(str(exc))}", reply_markup=main_menu_keyboard())
        return
    await _answer_code(message, "qr", decoded)


def _command_and_argument(message: Message) -> tuple[str, str]:
    text = (message.text or message.caption or "").strip()
    head, _, tail = text.partition(" ")
    return head.removeprefix("/").split("@", 1)[0].lower(), tail.strip()


def _argument_or_reply(message: Message, argument: str) -> str:
    if argument:
        return argument
    reply = message.reply_to_message
    return (reply.text or reply.caption or "") if reply else ""


def _image_media(message: Message | None):
    if message is None:
        return None
    if message.photo:
        return message.photo[-1]
    if message.document and (message.document.mime_type or "").startswith("image/"):
        return message.document
    return None


async def _answer_code(message: Message, label: str, value: str) -> None:
    rendered = f"🧰 <b>{esc(label)}</b>\n<code>{esc(value)}</code>"
    if len(rendered) <= 4000:
        await message.answer(rendered, reply_markup=main_menu_keyboard())
        return
    await message.answer_document(
        BufferedInputFile(value.encode(), filename=f"{label}.txt"),
        caption="Результат слишком длинный для сообщения — отправляю файлом.",
        reply_markup=main_menu_keyboard(),
    )


def _format_length(result: TextLengthResult) -> str:
    return (
        "📏 <b>Размер текста</b>\n\n"
        f"Символов: <b>{result.characters}</b>\n"
        f"Без пробелов: {result.characters_without_spaces}\n"
        f"Слов: {result.words}\nСтрок: {result.lines}\n"
        f"Вес UTF-8: <b>{result.utf8_bytes} Б</b>\n"
        f"Вес UTF-16: {result.utf16_bytes} Б"
    )


def _format_unix(result: UnixTimeResult) -> str:
    timestamp = int(result.timestamp) if result.timestamp.is_integer() else result.timestamp
    return (
        "🕒 <b>Unix-время</b>\n\n"
        f"Timestamp: <code>{timestamp}</code>\n"
        f"UTC: <code>{result.utc.isoformat(timespec='seconds')}</code>\n"
        f"Москва: <code>{result.local.isoformat(timespec='seconds')}</code>"
    )
