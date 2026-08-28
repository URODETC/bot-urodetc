from aiogram import Router

from app.telegram.commands.start import router as start_router

commands_router = Router(name="commands")
commands_router.include_router(start_router)