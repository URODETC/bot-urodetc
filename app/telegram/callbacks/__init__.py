from aiogram import Router
from app.telegram.callbacks.cinema import router as cinema_callbacks_router

from app.telegram.callbacks.download import router as download_callbacks_router
from app.telegram.callbacks.menu import router as menu_callbacks_router
from app.telegram.callbacks.network import router as network_callbacks_router
from app.telegram.callbacks.vpn import router as vpn_callbacks_router

callbacks_router = Router(name="callbacks")
callbacks_router.include_router(cinema_callbacks_router)
callbacks_router.include_router(menu_callbacks_router)
callbacks_router.include_router(network_callbacks_router)
callbacks_router.include_router(download_callbacks_router)
callbacks_router.include_router(vpn_callbacks_router)
