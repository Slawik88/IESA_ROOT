from aiogram import Router

# Чат-команды и админка удалены (код); БД не тронута. Новые роутеры
# подключаются здесь по мере написания с нуля.
from bot.chat import router as chat_router

main_router = Router(name="main_router")
main_router.include_router(chat_router)
