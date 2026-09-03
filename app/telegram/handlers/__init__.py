from aiogram import Router

from app.telegram.handlers.state_inputs import router as state_inputs_router

handlers_router = Router(name="handlers")
handlers_router.include_router(state_inputs_router)
