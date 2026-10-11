from aiogram import Router

# Чат-команды и админка удалены (код); БД не тронута. Новые роутеры
# подключаются здесь по мере написания с нуля.
from bot.chat import router as chat_router
from bot.chat.onboarding import router as onboarding_router
from bot.chat.payments import router as payments_router

main_router = Router(name="main_router")
# Оплата Stars и /start — раньше общего обработчика чата, который ловит все сообщения.
main_router.include_router(payments_router)
# Подключение бота к чату: /setup и кнопки мастера — тоже раньше общего обработчика чата.
main_router.include_router(onboarding_router)
main_router.include_router(chat_router)
