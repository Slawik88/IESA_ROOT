import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from aiogram.exceptions import TelegramConflictError

from aiogram.types import ChatPermissions, MenuButtonWebApp, WebAppInfo
from config import BOT_TOKEN, MINI_APP_URL
from database.db import get_locked_chats, init_db, set_chat_setting

# Время запуска бота (для игнорирования старых сообщений)
BOT_START_TIME = datetime.now(timezone.utc)
from handlers import (admin, auto_mod, bank, boss, casino, checkin, dev_panel, diligence, dm_roles, economy, espionage,
                     expeditions, extras, food, fun, gacha, gifts, helper,
                     moderator, notes, owner, pets, quests, reputation,
                     shop, stars, tax_event, user, wallet, weather)
from handlers import auction as auction_handler

logging.basicConfig(level=logging.INFO)


async def notify_developer(bot: Bot, text: str):
    from config import DEVELOPER_ID
    if not DEVELOPER_ID:
        return
    try:
        await bot.send_message(DEVELOPER_ID, text)
    except Exception:
        pass


async def configure_mini_app_menu_button(bot: Bot):
    if not MINI_APP_URL:
        return
    try:
        await bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(
                text="Открыть App",
                web_app=WebAppInfo(url=MINI_APP_URL),
            )
        )
        logging.info("Mini App menu button configured: %s", MINI_APP_URL)
    except Exception as exc:
        logging.warning("Could not configure Mini App menu button: %s", exc)


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
    from middlewares.message_counter import AutoModMiddleware, set_bot_start_time
    set_bot_start_time(BOT_START_TIME)  # Защита от обработки старых сообщений
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
    dp.include_router(checkin.router)      # ежедневный чекин
    dp.include_router(boss.router)         # битва с боссом
    dp.include_router(auction_handler.router)  # аукцион
    dp.include_router(dev_panel.router)    # панель разработчика
    dp.include_router(shop.router)         # магазин
    dp.include_router(stars.router)        # Telegram Stars (кристаллы)
    dp.include_router(gifts.router)        # подарки партнёру
    dp.include_router(tax_event.router)    # налоговая инспекция
    dp.include_router(weather.router)      # погода
    dp.include_router(user.router)
    dp.include_router(dm_roles.router)  # DM-онбординг ролей
    dp.include_router(extras.router)   # ← catch-all последним

    from config import BOT_STARTED_MSG, BOT_STOPPED_MSG
    print("✅ Бот запущен! Пиши 'бот помощь' в чат.")
    await notify_developer(bot, BOT_STARTED_MSG)
    await configure_mini_app_menu_button(bot)

    # Фоновый планировщик (авто-варн, напоминания о чистке)
    from utils.scheduler import run_scheduler
    asyncio.create_task(run_scheduler(bot))

    # Boss damage buffer flush (every 60s)
    async def _boss_flush_loop():
        while True:
            await asyncio.sleep(60)
            try:
                await boss.flush_damage_buffer()
            except Exception as _e:
                logging.warning("boss flush error: %s", _e)
    asyncio.create_task(_boss_flush_loop())

    # Dev event queue — fast poll every 30 seconds so events from Mini App fire quickly
    async def _dev_event_fast_poll():
        await asyncio.sleep(10)
        from utils.scheduler import _task_dev_event_queue
        while True:
            try:
                await _task_dev_event_queue(bot)
            except Exception as _e:
                logging.warning("dev_event_queue fast poll error: %s", _e)
            await asyncio.sleep(30)
    asyncio.create_task(_dev_event_fast_poll())

    # Mini App веб-сервер (aiohttp)
    asyncio.create_task(_run_webserver(bot))

    # ─────────────────────────────────────────────────────────────────────────
    # WEBHOOK vs POLLING GUARD — двухуровневая защита от TelegramConflictError
    #
    # Уровень 1: env-переменная (быстро, без сети)
    # Уровень 2: Telegram API — если у бота зарегистрирован webhook, поллинг
    #            КАТЕГОРИЧЕСКИ запрещён независимо от env-переменных.
    # ─────────────────────────────────────────────────────────────────────────
    _webhook_url = (
        os.getenv("BOT_WEBHOOK_URL") or
        os.getenv("WEBHOOK_URL") or
        ""
    ).strip()

    # Уровень 2: спросить Telegram, есть ли активный webhook
    _registered_webhook = ""
    try:
        _whi = await bot.get_webhook_info()
        _registered_webhook = (_whi.url or "").strip()
    except Exception as _whi_exc:
        logging.warning("Could not fetch webhook info from Telegram: %s", _whi_exc)
        # Fail-safe: if we can't query Telegram AND either the webhook URL env var is
        # set or DATABASE_URL is present (production indicator), assume a webhook IS
        # active and refuse to fall through to polling — avoids TelegramConflictError.
        if _webhook_url or os.getenv("DATABASE_URL"):
            _registered_webhook = "assumed-active (get_webhook_info failed)"

    _use_webhook = bool(_webhook_url or _registered_webhook)

    if _use_webhook:
        active = _webhook_url or _registered_webhook
        logging.info("⛔ POLLING DISABLED — webhook mode active: %s", active)
        try:
            await asyncio.Event().wait()
        finally:
            try:
                await notify_developer(bot, BOT_STOPPED_MSG)
            finally:
                await bot.session.close()
        return

    # ── Polling-режим (только локальная разработка без webhook) ───────────────
    logging.info("📡 No webhook registered — starting polling mode (local dev only).")
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
        from database.postgres import connect as postgres_connect
        async with postgres_connect() as db:
            async with db.execute(
                """SELECT um.chat_id, COALESCE(u.balance, 0) AS balance,
                          COALESCE(u.total_earned, 0) AS total_earned,
                          um.vip, um.vip_expires_at, um.top_frame, um.mora_public
                   FROM user_mora um
                   JOIN users u ON u.user_id = um.user_id
                   WHERE um.user_id=? ORDER BY um.balance DESC LIMIT 1""",
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

    async def handle_user_data(request: _web.Request) -> _web.Response:
        """Alias for /api/user_data?user_id=N (standalone bot mode)."""
        try:
            uid = int(request.rel_url.query.get("user_id", "0"))
        except ValueError:
            return _web.Response(status=400, text="bad user_id")
        if not uid:
            return _web.Response(status=400, text="missing user_id")

        user = await get_user(uid)
        if not user:
            return _web.Response(status=404, text="user not found")

        from database.postgres import connect as postgres_connect
        async with postgres_connect() as db:
            async with db.execute(
                """SELECT um.chat_id, COALESCE(u.balance, 0) AS balance,
                          COALESCE(u.total_earned, 0) AS total_earned,
                          um.vip, um.vip_expires_at, um.top_frame, um.mora_public
                   FROM user_mora um
                   JOIN users u ON u.user_id = um.user_id
                   WHERE um.user_id=? ORDER BY um.balance DESC LIMIT 1""",
                (uid,),
            ) as c:
                mora = await c.fetchone()
            async with db.execute(
                "SELECT xp FROM user_stats WHERE user_id=? ORDER BY xp DESC LIMIT 1",
                (uid,),
            ) as c:
                xp_row = await c.fetchone()
            async with db.execute(
                "SELECT b.bond_key, b.amount, COALESCE(p.price,100) as price "
                "FROM user_bonds b "
                "LEFT JOIN bond_prices p ON p.bond_key=b.bond_key AND p.chat_id=b.chat_id "
                "WHERE b.user_id=? AND b.chat_id=?",
                (uid, mora["chat_id"] if mora else 0),
            ) as c:
                bond_rows = await c.fetchall()
            async with db.execute(
                "SELECT item_name, rarity, equipped FROM gacha_inventory "
                "WHERE user_id=? AND chat_id=? LIMIT 20",
                (uid, mora["chat_id"] if mora else 0),
            ) as c:
                inv_rows = await c.fetchall()
            async with db.execute(
                "SELECT pet_type, name, COALESCE(fatigue,0) FROM pets_global "
                "WHERE user_id=?",
                (uid,),
            ) as c:
                pet_row = await c.fetchone()

        chat_id = mora["chat_id"] if mora else 0
        balance = mora["balance"] if mora else 0
        vip = bool(mora and mora["vip"])
        active_frame = mora["top_frame"] if mora else None
        active_theme = mora.get("active_theme") if mora else None
        xp = xp_row["xp"] if xp_row else 0

        bonds_data = [
            {"name": r["bond_key"], "amount": r["amount"], "value": r["amount"] * r["price"]}
            for r in bond_rows
        ]
        items = [
            f"{'★' if r['equipped'] else ''}{r['item_name']} ({r['rarity']})"
            for r in inv_rows
        ]
        pet_info = None
        if pet_row:
            emoji = {"cat": "🐱", "dog": "🐶"}.get(pet_row[0], "🐾")
            pet_info = {"type": pet_row[0], "name": pet_row[1] or "безымянный",
                        "emoji": emoji, "fatigue": pet_row[2]}

        payload = {
            "name": user["full_name"],
            "balance": balance,
            "xp": xp,
            "vip": vip,
            "active_frame": active_frame or "default",
            "active_theme": active_theme or "default",
            "bonds": bonds_data,
            "items": items,
            "pet": pet_info,
        }
        return _web.Response(
            text=json.dumps(payload, ensure_ascii=False),
            content_type="application/json",
            headers={"Access-Control-Allow-Origin": "*"},
        )

    app = _web.Application()
    app.router.add_get("/", handle_index)
    app.router.add_get("/app", handle_index)
    app.router.add_get("/app/", handle_index)
    app.router.add_get("/api/user_data", handle_user_data)
    app.router.add_get("/api/user_data/", handle_user_data)
    # Legacy /api/profile/{user_id} kept for backwards compat
    app.router.add_get("/api/profile/{user_id}", handle_profile)
    
    # Season Pass API routes
    from api.season import season_data, claim_reward, buy_premium
    app.router.add_get("/api/season/data", season_data)
    app.router.add_post("/api/season/claim", claim_reward)
    app.router.add_post("/api/season/premium", buy_premium)
    
    # Serve static files from /web
    if _web_dir.exists():
        app.router.add_static("/static", _web_dir)

    # Use BOT_WEB_PORT (default 8081) to avoid conflicting with Django/Daphne on PORT=8080
    # Use BOT_WEB_PORT only — never inherit PORT (Daphne/Gunicorn holds that).
    port = int(os.environ.get("BOT_WEB_PORT", 8081))
    runner = _web.AppRunner(app)
    await runner.setup()
    site = _web.TCPSite(runner, "0.0.0.0", port)
    try:
        await site.start()
        logging.info("Mini App web server started on port %d", port)
    except OSError as _port_err:
        logging.error(
            "Mini App web server could not bind to port %d: %s. "
            "Set BOT_WEB_PORT to a free port. Bot continues without web server.",
            port, _port_err,
        )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Бот остановлен.")