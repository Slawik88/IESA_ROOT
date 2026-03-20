import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from aiogram.types import ChatPermissions
from config import BOT_TOKEN
from database.db import get_active_chats, get_locked_chats, init_db, is_group_allowed, set_chat_active, set_chat_setting
from handlers import admin, auto_mod, extras, fun, helper, moderator, notes, owner, quests, reputation, user
from middlewares.message_counter import AutoModMiddleware

logging.basicConfig(level=logging.INFO)


async def broadcast_status(bot: Bot, text: str):
    chats = await get_active_chats()
    for chat in chats:
        # Отправляем только в группы — не в личные чаты
        if chat["chat_type"] not in ("group", "supergroup"):
            continue
        # Если белый список включён — только в разрешённые группы
        if not is_group_allowed(chat["chat_id"]):
            continue
        try:
            await bot.send_message(chat["chat_id"], text)
        except Exception:
            await set_chat_active(chat["chat_id"], 0)


async def main():
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()

    # Инициализация базы данных
    await init_db()

    # Авто-разблокировка чатов, которые остались заблокированы после "бот чистка"
    _full_perms = ChatPermissions(
        can_send_messages=True, can_send_audios=True, can_send_documents=True,
        can_send_photos=True, can_send_videos=True, can_send_video_notes=True,
        can_send_voice_notes=True, can_send_polls=True,
        can_send_other_messages=True, can_add_web_page_previews=True,
    )
    for _locked_chat_id in await get_locked_chats():
        try:
            await bot.set_chat_permissions(_locked_chat_id, _full_perms)
            await set_chat_setting(_locked_chat_id, "cleanup_locked", 0)
            logging.info("Auto-unlocked chat %s after bot restart", _locked_chat_id)
        except Exception as _e:
            logging.warning("Could not auto-unlock chat %s: %s", _locked_chat_id, _e)

    # Middleware: регистрация юзеров + антифлуд + замки + чёрный список
    dp.message.outer_middleware(AutoModMiddleware())

    # Роутеры — от специфичных к общим (extras должен быть последним!)
    dp.include_router(owner.router)
    dp.include_router(admin.router)
    dp.include_router(moderator.router)
    dp.include_router(helper.router)
    dp.include_router(notes.router)
    dp.include_router(auto_mod.router)
    dp.include_router(reputation.router)   # репутация/XP/bio — до catch-all
    dp.include_router(fun.router)          # весёлые команды
    dp.include_router(quests.router)       # ежедневные задания
    dp.include_router(user.router)
    dp.include_router(extras.router)   # ← catch-all последним

    from config import BOT_STARTED_MSG, BOT_STOPPED_MSG
    print("✅ Бот запущен! Пиши 'бот помощь' в чат.")
    await broadcast_status(bot, BOT_STARTED_MSG)

    try:
        await dp.start_polling(bot, drop_pending_updates=True)
    finally:
        try:
            await broadcast_status(bot, BOT_STOPPED_MSG)
        finally:
            await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Бот остановлен.")