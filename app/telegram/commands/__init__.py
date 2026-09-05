from aiogram import Router
from app.telegram.commands.cinema import router as cinema_router

from app.telegram.commands.download import router as download_router
from app.telegram.commands.developer import router as developer_router
from app.telegram.commands.help import router as help_router
from app.telegram.commands.network import router as network_router
from app.telegram.commands.start import router as start_router
from app.telegram.commands.vpn import router as vpn_router

commands_router = Router(name="commands")
commands_router.include_router(cinema_router)
commands_router.include_router(start_router)
commands_router.include_router(help_router)
commands_router.include_router(download_router)
commands_router.include_router(network_router)
commands_router.include_router(developer_router)
commands_router.include_router(vpn_router)
