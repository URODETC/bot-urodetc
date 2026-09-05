from html import escape

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.jobs.persistent import PersistentJob

PAGE_SIZE = 5


def search_page(job: PersistentJob, page: int = 0) -> tuple[str, InlineKeyboardMarkup | None]:
    releases = job.result.get("releases", [])
    if not releases:
        return "По этому запросу раздачи не найдены. Попробуйте другое название, уточните год или сезон.", None
    page = max(0, min(page, (len(releases) - 1) // PAGE_SIZE))
    lines = [f"🎬 <b>{escape(job.payload['query'][:160])}</b>", "Среди доступных раздач первыми идут 2160p. Выберите вариант:\n"]
    buttons = []
    for index, r in enumerate(releases[page * PAGE_SIZE:(page + 1) * PAGE_SIZE], start=page * PAGE_SIZE + 1):
        quality = f"{r['resolution']}p" if r['resolution'] else "Разрешение не указано"
        lines.append(f"<b>{index}. {escape(r['title'][:150])}</b>\n{quality} · {escape(r['source'])} · {escape(r['dynamic_range'])}\nОзвучка: {escape(r['audio'])}\n💾 {r['size'] / 1024**3:.1f} ГиБ · 🌱 {r['seeders']} сидов" + (" · ⚠️ нет сидов" if not r['seeders'] else ""))
        buttons.append([InlineKeyboardButton(text=f"Скачать №{index} · {quality}", callback_data=f"cin:add:{job.id}:{r['topic_id']}"), InlineKeyboardButton(text="Описание", url=f"https://rutracker.org/forum/viewtopic.php?t={r['topic_id']}")])
    navigation = []
    if page:
        navigation.append(InlineKeyboardButton(text="← Назад", callback_data=f"cin:page:{job.id}:{page - 1}"))
    if (page + 1) * PAGE_SIZE < len(releases):
        navigation.append(InlineKeyboardButton(text="Далее →", callback_data=f"cin:page:{job.id}:{page + 1}"))
    if navigation:
        buttons.append(navigation)
    lines.append("\nОзвучка и HDR определены по заголовку раздачи. /cinema_status — состояние загрузок.")
    return "\n\n".join(lines), InlineKeyboardMarkup(inline_keyboard=buttons)


def format_status(jobs: list[PersistentJob]) -> str:
    if not jobs:
        return "Задач пока нет. /cinema название фильма или сериала"
    lines = ["🎬 <b>Последние задачи</b>"]
    labels = {"pending": "В очереди", "running": "Выполняется", "success": "Готово", "failed": "Ошибка"}
    for job in jobs:
        title = job.payload.get("query") or job.payload.get("release", {}).get("title", "Загрузка")
        state = labels.get(job.status, job.status)
        if job.type == "cinema.download" and job.result.get("hash") and job.status != "failed":
            state = f"{job.result.get('progress', 0) * 100:.1f}% · {escape(job.result.get('state', ''))}"
        lines.append(f"<b>{escape(title[:180])}</b>\n{state}" + (f"\n{escape(job.error)}" if job.error else ""))
    return "\n\n".join(lines)


def recent_results_keyboard(jobs: list[PersistentJob]) -> InlineKeyboardMarkup | None:
    rows = [[InlineKeyboardButton(text="Результаты: " + job.payload["query"][:40], callback_data=f"cin:page:{job.id}:0")] for job in jobs if job.type == "cinema.search" and job.status == "success"]
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None
