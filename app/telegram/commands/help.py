from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.telegram.menu import main_menu_keyboard

router = Router(name="help")

DEVELOPER_HELP = (
    "🧰 <b>Инструменты разработчика</b>\n\n"
    "<b>Сеть</b>\n"
    "<code>/whois домен/URL/IP</code> — регистрация и владелец\n"
    "<code>/ip домен/IP</code> — DNS или PTR\n"
    "<code>/ping хост</code> — доступность и задержка\n"
    "<code>/check URL</code> — HTTP-статус и время ответа\n"
    "<code>/mtr хост</code> — маршрут и потери\n"
    "<code>/geo хост</code>, <code>/rdns IP</code>, <code>/tls домен</code>\n\n"
    "<b>Текст и кодирование</b>\n"
    "<code>/urlencode текст</code>, <code>/urldecode текст</code>\n"
    "<code>/base64encode текст</code>, <code>/base64decode строка</code>\n"
    "<code>/length текст</code> или <code>/длина текст</code>\n\n"
    "<b>Хэши</b>\n"
    "<code>/md2</code>, <code>/md5</code>, <code>/sha1</code>, <code>/sha256</code>, "
    "<code>/sha384</code>, <code>/sha512</code> + текст\n\n"
    "<b>Генераторы</b>\n"
    "<code>/qr текст</code> — создать; ответьте <code>/qr</code> на картинку — прочитать\n"
    "<code>/getcolor [#HEX|R G B]</code> или <code>/цвет</code>\n"
    "<code>/unix [timestamp|дата]</code> · <code>/uuid</code> · <code>/password [длина]</code>\n\n"
    "💡 Для текстовых команд можно ответить командой на существующее сообщение."
    "\n\n🔐 <b>VPN (только владелец)</b>\n"
    "<code>/vpn</code> — меню управления Remnawave\n"
    "<code>/vpn_add имя [дней] [лимит_ГБ] [telegram_id]</code>\n"
    "<code>/vpn_extend имя дней</code> · <code>/vpn_report</code>"
    "\n\n🎬 <b>Кино (только владелец)</b>\n"
    "<code>/cinema название [год] [сезон N]</code> — раздачи RuTracker\n"
    "<code>/cinema_status</code> — загрузки qBittorrent"
)


@router.message(Command("help", "tools"))
async def help_command(message: Message) -> None:
    await message.answer(DEVELOPER_HELP, reply_markup=main_menu_keyboard())
