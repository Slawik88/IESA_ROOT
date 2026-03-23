import asyncio
import json
import logging
import os
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramConflictError

from aiogram.types import ChatPermissions
from config import BOT_TOKEN
from database.db import get_locked_chats, init_db, set_chat_setting
from handlers import (admin, auto_mod, bank, casino, dev_panel, diligence, dm_roles, economy, espionage,
                     expeditions, extras, food, fun, gacha, gifts, helper,
                     moderator, notes, owner, pets, quests, reputation,
                     shop, tax_event, user, wallet, weather)
from middlewares.message_counter import AutoModMiddleware

logging.basicConfig(level=logging.INFO)


async def notify_developer(bot: Bot, text: str):
    from config import DEVELOPER_ID
    if not DEVELOPER_ID:
        return
    try:
        await bot.send_message(DEVELOPER_ID, text)
    except Exception:
        pass


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
    dp.include_router(pets.router)         # система питомцев
    dp.include_router(wallet.router)       # переводы и займы Моры
    dp.include_router(economy.router)      # экономика (Мора, балансы)
    dp.include_router(casino.router)       # казино (монетка, кубик, лотерея)
    dp.include_router(expeditions.router)  # экспедиции питомцев
    dp.include_router(gacha.router)        # молитвы (гача)
    dp.include_router(bank.router)         # банк вкладов
    dp.include_router(espionage.router)    # шпионаж + облигации
    dp.include_router(diligence.router)    # ивент «Дилижанс»
    dp.include_router(food.router)         # магазин еды для питомцев
    dp.include_router(dev_panel.router)    # панель разработчика
    dp.include_router(shop.router)         # магазин
    dp.include_router(gifts.router)        # подарки партнёру
    dp.include_router(tax_event.router)    # налоговая инспекция
    dp.include_router(weather.router)      # погода
    dp.include_router(user.router)
    dp.include_router(dm_roles.router)  # DM-онбординг ролей
    dp.include_router(extras.router)   # ← catch-all последним

    from config import BOT_STARTED_MSG, BOT_STOPPED_MSG
    print("✅ Бот запущен! Пиши 'бот помощь' в чат.")
    await notify_developer(bot, BOT_STARTED_MSG)

    # Фоновый планировщик (авто-варн, напоминания о чистке)
    from utils.scheduler import run_scheduler
    asyncio.create_task(run_scheduler(bot))

    # Mini App веб-сервер (aiohttp)
    asyncio.create_task(_run_webserver(bot))

    # Удаляем вебхук перед поллингом — предотвращает ConflictError,
    # если другой инстанс зарегистрировал webhook для этого же бота.
    try:
        await bot.delete_webhook(drop_pending_updates=True)
    except Exception as _wh_exc:
        logging.warning("Could not delete webhook before polling: %s", _wh_exc)

    try:
        await dp.start_polling(bot, drop_pending_updates=True)
    except TelegramConflictError:
        logging.critical(
            "TelegramConflictError: another bot instance is already running! "
            "Ensure only one process polls at a time. Exiting."
        )
        raise
    finally:
        try:
            await notify_developer(bot, BOT_STOPPED_MSG)
        finally:
            await bot.session.close()


async def _run_webserver(bot: Bot) -> None:
    """Запускает aiohttp-сервер для Mini App."""
    try:
        from aiohttp import web as _web
    except ImportError:
        logging.warning("aiohttp not installed — Mini App web server disabled.")
        return

    from database.db import get_mora, get_user, get_user_bonds, get_bond_prices, get_gacha_inventory, BOND_DEFAULTS

    _web_dir = Path(__file__).parent / "web"

    async def handle_index(request: _web.Request) -> _web.Response:
        index_file = _web_dir / "index.html"
        if not index_file.exists():
            raise _web.HTTPNotFound()
        return _web.Response(
            body=index_file.read_bytes(),
            content_type="text/html",
        )

    async def handle_profile(request: _web.Request) -> _web.Response:
        try:
            uid = int(request.match_info["user_id"])
        except (ValueError, KeyError):
            return _web.Response(status=400, text="bad user_id")

        user = await get_user(uid)
        if not user:
            return _web.Response(status=404, text="user not found")

        # Find a group chat for this user (use first mora row)
        from database.db import DATABASE_PATH
        import aiosqlite
        async with aiosqlite.connect(DATABASE_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM user_mora WHERE user_id=? ORDER BY balance DESC LIMIT 1",
                (uid,),
            ) as c:
                mora = await c.fetchone()
            async with db.execute(
                "SELECT xp FROM user_stats WHERE user_id=? ORDER BY xp DESC LIMIT 1",
                (uid,),
            ) as c:
                xp_row = await c.fetchone()

        chat_id = mora["chat_id"] if mora else 0
        balance = mora["balance"] if mora else 0
        vip = bool(mora and mora["vip"])
        active_frame = mora["top_frame"] if mora else None
        active_theme = mora.get("active_theme") if mora else None

        xp = xp_row["xp"] if xp_row else 0

        # Bonds
        bonds_data = []
        if chat_id:
            bond_prices = await get_bond_prices(chat_id)
            user_bond_rows = await get_user_bonds(uid, chat_id)
            for b in user_bond_rows:
                bkey = b["bond_key"]
                price = bond_prices.get(bkey, 0)
                bonds_data.append({
                    "name": BOND_DEFAULTS.get(bkey, {}).get("name", bkey),
                    "amount": b["amount"],
                    "value": b["amount"] * price,
                })

        # Items
        items_names: list[str] = []
        if chat_id:
            inv = await get_gacha_inventory(uid, chat_id)
            items_names = [
                f"{i['item_name']} ({'★Экип.' if i.get('equipped') else i['rarity']})"
                for i in inv
            ]

        payload = {
            "name": user["full_name"],
            "balance": balance,
            "xp": xp,
            "vip": vip,
            "active_frame": active_frame or "default",
            "active_theme": active_theme or "default",
            "bonds": bonds_data,
            "items": items_names,
        }
        return _web.Response(
            text=json.dumps(payload, ensure_ascii=False),
            content_type="application/json",
            headers={"Access-Control-Allow-Origin": "*"},
        )

    app = _web.Application()
    app.router.add_get("/", handle_index)
    app.router.add_get("/app", handle_index)
    app.router.add_get("/api/profile/{user_id}", handle_profile)
    # Serve static files from /web
    if _web_dir.exists():
        app.router.add_static("/static", _web_dir)

    port = int(os.environ.get("PORT", 8080))
    runner = _web.AppRunner(app)
    await runner.setup()
    site = _web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logging.info("Mini App web server started on port %d", port)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Бот остановлен.")