from aiogram import Router

from app.telegram.commands.download import router as download_router
from app.telegram.commands.start import router as start_router

commands_router = Router(name="commands")
commands_router.include_router(start_router)
commands_router.include_router(download_router)