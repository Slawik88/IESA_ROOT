"""
web_app.py — FastAPI-сервер для Telegram Webhook + Mini App API + статика.

Запускается через uvicorn, работает в одном процессе с aiogram.
Полностью заменяет старый aiohttp-сервер.
Lifespan-контекст управляет запуском/остановкой фоновых задач.
"""
from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from aiogram import Bot, Dispatcher
from aiogram.types import Update

_log = logging.getLogger("web_app")


# Глобальные ссылки — инициализируются при запуске
_bot: Bot | None = None
_dp: Dispatcher | None = None

_WEB_DIR = Path(__file__).parent / "web"

# Фоновые задачи, запущенные в lifespan (для корректной отмены при shutdown)
_bg_tasks: list[asyncio.Task] = []


def set_bot_and_dp(bot: Bot, dp: Dispatcher) -> None:
    """Вызвать при старте бота — связывает FastAPI с aiogram."""
    global _bot, _dp
    _bot = bot
    _dp = dp


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Lifespan — управление жизненным циклом (запуск/остановка фоновых задач)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Запуск планировщика и фоновых циклов при старте; очистка при остановке."""
    _log.info("🚀 FastAPI lifespan: запуск фоновых задач...")

    if _bot:
        # Планировщик (авто-варн, напоминания, лотерея, и т.д.)
        from utils.scheduler import run_scheduler
        _bg_tasks.append(asyncio.create_task(run_scheduler(_bot), name="scheduler"))

        # Boss damage buffer flush (каждые 60с)
        async def _boss_flush_loop():
            from handlers import boss
            while True:
                await asyncio.sleep(60)
                try:
                    await boss.flush_damage_buffer()
                except Exception as _e:
                    _log.warning("boss flush error: %s", _e)
        _bg_tasks.append(asyncio.create_task(_boss_flush_loop(), name="boss_flush"))

        # Dev event queue — быстрый опрос каждые 30с
        async def _dev_event_fast_poll():
            await asyncio.sleep(10)
            from utils.scheduler import _task_dev_event_queue
            while True:
                try:
                    await _task_dev_event_queue(_bot)
                except Exception as _e:
                    _log.warning("dev_event_queue fast poll error: %s", _e)
                await asyncio.sleep(30)
        _bg_tasks.append(asyncio.create_task(_dev_event_fast_poll(), name="dev_event_poll"))

    _log.info("✅ Фоновые задачи запущены (%d шт.)", len(_bg_tasks))

    yield  # ← приложение работает

    # ── Shutdown ──────────────────────────────────────────────────────────────
    _log.info("🛑 FastAPI lifespan: остановка...")
    for task in _bg_tasks:
        task.cancel()
    for task in _bg_tasks:
        try:
            await task
        except asyncio.CancelledError:
            pass
    _bg_tasks.clear()

    if _bot:
        try:
            await _bot.session.close()
        except Exception:
            pass
    _log.info("🛑 FastAPI lifespan: завершено.")


app = FastAPI(title="PredvestnikBot API", docs_url=None, redoc_url=None, lifespan=_lifespan)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Telegram Webhook Endpoint
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")


@app.post("/webhook")
async def telegram_webhook(request: Request) -> Response:
    """Принимает Telegram-апдейты и передаёт их в dp.feed_update()."""
    if WEBHOOK_SECRET:
        header = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if header != WEBHOOK_SECRET:
            return Response(status_code=403)

    if not _bot or not _dp:
        _log.error("Webhook вызван до инициализации бота!")
        return Response(status_code=503)

    try:
        data = await request.json()
        update = Update.model_validate(data, context={"bot": _bot})
        await _dp.feed_update(bot=_bot, update=update)
    except Exception as exc:
        _log.exception("Ошибка обработки webhook-апдейта: %s", exc)

    return Response(status_code=200)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Healthcheck
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@app.get("/health")
async def healthcheck():
    return {"status": "ok"}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Mini App — index.html
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_INDEX_CACHE: bytes | None = None   # кешируем index.html в RAM (маленький файл)


def _read_index() -> bytes | None:
    """Читает index.html, кеширует при первом вызове."""
    global _INDEX_CACHE
    if _INDEX_CACHE is not None:
        return _INDEX_CACHE
    index = _WEB_DIR / "index.html"
    if not index.exists():
        return None
    _INDEX_CACHE = index.read_bytes()
    return _INDEX_CACHE


@app.get("/", response_class=HTMLResponse)
@app.get("/app", response_class=HTMLResponse)
@app.get("/app/", response_class=HTMLResponse)
@app.get("/app/{rest:path}", response_class=HTMLResponse)
async def serve_miniapp(rest: str = ""):
    """SPA-фоллбэк: любой маршрут /app/* → index.html (клиентская навигация)."""
    html = _read_index()
    if html is None:
        return HTMLResponse("<h1>Mini App not found</h1>", status_code=404)
    return HTMLResponse(html)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Mini App API: /api/user_data
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@app.get("/api/user_data")
@app.get("/api/user_data/")
async def api_user_data(user_id: int = 0):
    if not user_id:
        return JSONResponse({"error": "missing user_id"}, status_code=400)

    from database.db import get_user
    from database.postgres import connect as postgres_connect

    user = await get_user(user_id)
    if not user:
        return JSONResponse({"error": "user not found"}, status_code=404)

    async with postgres_connect() as db:
        async with db.execute(
            """SELECT um.chat_id, COALESCE(u.balance, 0) AS balance,
                      COALESCE(u.total_earned, 0) AS total_earned,
                      um.vip, um.vip_expires_at, um.top_frame, um.mora_public
               FROM user_mora um
               JOIN users u ON u.user_id = um.user_id
               WHERE um.user_id=? ORDER BY um.balance DESC LIMIT 1""",
            (user_id,),
        ) as c:
            mora = await c.fetchone()
        async with db.execute(
            "SELECT xp FROM user_stats WHERE user_id=? ORDER BY xp DESC LIMIT 1",
            (user_id,),
        ) as c:
            xp_row = await c.fetchone()
        chat_id = mora["chat_id"] if mora else 0
        async with db.execute(
            "SELECT b.bond_key, b.amount, COALESCE(p.price,100) as price "
            "FROM user_bonds b "
            "LEFT JOIN bond_prices p ON p.bond_key=b.bond_key AND p.chat_id=b.chat_id "
            "WHERE b.user_id=? AND b.chat_id=?",
            (user_id, chat_id),
        ) as c:
            bond_rows = await c.fetchall()
        async with db.execute(
            "SELECT item_name, rarity, equipped FROM gacha_inventory "
            "WHERE user_id=? AND chat_id=? LIMIT 20",
            (user_id, chat_id),
        ) as c:
            inv_rows = await c.fetchall()
        async with db.execute(
            "SELECT pet_type, name, COALESCE(fatigue,0) FROM pets_global WHERE user_id=?",
            (user_id,),
        ) as c:
            pet_row = await c.fetchone()
        async with db.execute(
            "SELECT partner_id, married_at FROM marriages_global WHERE user_id=?",
            (user_id,),
        ) as c:
            marriage_row = await c.fetchone()

    balance = mora["balance"] if mora else 0
    vip = bool(mora and mora["vip"])
    active_frame = mora["top_frame"] if mora else None
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

    partner_info = None
    if marriage_row:
        from database.db import get_user as _gu
        partner_user = await _gu(marriage_row["partner_id"])
        _mat = marriage_row["married_at"]
        married_iso = _mat.isoformat() if hasattr(_mat, 'isoformat') else str(_mat or "")
        partner_info = {
            "partner_id": marriage_row["partner_id"],
            "partner_name": partner_user["full_name"] if partner_user else "?",
            "married_at": married_iso,
        }

    payload = {
        "name": user["full_name"],
        "balance": balance,
        "xp": xp,
        "vip": vip,
        "active_frame": active_frame or "default",
        "bonds": bonds_data,
        "items": items,
        "pet": pet_info,
        "partner": partner_info,
    }
    return JSONResponse(payload, headers={"Access-Control-Allow-Origin": "*"})


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Mini App API: /api/profile/{user_id}  (legacy совместимость)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@app.get("/api/profile/{user_id}")
async def api_profile(user_id: int):
    return await api_user_data(user_id=user_id)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Season Pass API  (нативные FastAPI-эндпоинты, без aiohttp-прокси)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@app.get("/api/season/data")
async def season_data_route(user_id: int = 0):
    if not user_id:
        return JSONResponse({"error": "user_id required"}, status_code=400)
    from database.db import get_active_season, get_season_progress, get_season_rewards
    try:
        season = await get_active_season()
        if not season:
            return JSONResponse({"error": "No active season"}, status_code=404)
        season_id = season["id"]
        progress = await get_season_progress(user_id, season_id)
        rewards = await get_season_rewards(season_id)
        return JSONResponse({
            "season": {
                "id": season["id"],
                "name": season["name"],
                "start_date": season["start_date"].isoformat() if season["start_date"] else None,
                "end_date": season["end_date"].isoformat() if season["end_date"] else None,
                "active": season["active"],
            },
            "progress": progress,
            "rewards": rewards,
        })
    except Exception as exc:
        _log.exception("season_data error: %s", exc)
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.post("/api/season/claim")
async def season_claim_route(request: Request):
    from database.db import claim_season_reward
    try:
        data = await request.json()
        user_id = int(data.get("user_id", 0))
        season_id = int(data.get("season_id", 0))
        level = int(data.get("level", 0))
        is_premium = bool(data.get("is_premium", False))
        if not all([user_id, season_id, level]):
            return JSONResponse({"error": "user_id, season_id, and level required"}, status_code=400)
        result = await claim_season_reward(user_id, season_id, level, is_premium)
        if result["ok"]:
            return JSONResponse(result)
        return JSONResponse(result, status_code=400)
    except Exception as exc:
        _log.exception("season_claim error: %s", exc)
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.post("/api/season/premium")
async def season_premium_route(request: Request):
    from database.db import buy_season_premium
    try:
        data = await request.json()
        user_id = int(data.get("user_id", 0))
        season_id = int(data.get("season_id", 0))
        if not all([user_id, season_id]):
            return JSONResponse({"error": "user_id and season_id required"}, status_code=400)
        success = await buy_season_premium(user_id, season_id)
        if success:
            return JSONResponse({"ok": True})
        return JSONResponse({"error": "Purchase failed"}, status_code=400)
    except Exception as exc:
        _log.exception("season_premium error: %s", exc)
        return JSONResponse({"error": str(exc)}, status_code=500)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Achievements REST API
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@app.get("/api/achievements")
async def achievements_route(user_id: int = 0, chat_id: int = 0, mode: str = ""):
    """Достижения игрока или лидерборд.

    Параметры:
        mode=leaderboard         → GET /api/achievements?chat_id=X&mode=leaderboard
        mode=global_leaderboard  → GET /api/achievements?mode=global_leaderboard
        (по умолчанию)           → GET /api/achievements?user_id=X&chat_id=Y
    """
    from services.achievements import get_user_achievements, get_leaderboard, get_global_leaderboard
    try:
        if mode == "global_leaderboard":
            data = await get_global_leaderboard(limit=100)
            return JSONResponse({"leaderboard": data})
        if mode == "leaderboard":
            if not chat_id:
                return JSONResponse({"error": "chat_id required"}, status_code=400)
            data = await get_leaderboard(chat_id)
            return JSONResponse({"leaderboard": data})
        if not user_id or not chat_id:
            return JSONResponse({"error": "user_id and chat_id required"}, status_code=400)
        data = await get_user_achievements(user_id, chat_id)
        return JSONResponse(data)
    except Exception as exc:
        _log.exception("achievements error: %s", exc)
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.get("/api/achievements/badges")
async def badges_route(user_id: int = 0, chat_id: int = 0):
    """Список ключей бейджей игрока (для отображения в профиле)."""
    from services.achievements import get_user_badge_keys
    if not user_id or not chat_id:
        return JSONResponse({"error": "user_id and chat_id required"}, status_code=400)
    try:
        keys = await get_user_badge_keys(user_id, chat_id)
        return JSONResponse({"badges": keys})
    except Exception as exc:
        _log.exception("badges error: %s", exc)
        return JSONResponse({"error": str(exc)}, status_code=500)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Статика из /web  (Vite build: /assets/*.js, /assets/*.css)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Telemetry — /api/telemetry  (no auth, aggregated counters only)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@app.post("/api/telemetry")
async def api_telemetry(request: Request):
    try:
        data = await request.json()
        events = data.get("events", [])
        if not isinstance(events, list) or len(events) > 200:
            return JSONResponse({"ok": False, "error": "invalid"}, status_code=400)
        from database.db import upsert_telemetry_batch
        await upsert_telemetry_batch(events)
        return JSONResponse({"ok": True})
    except Exception as exc:
        _log.warning("api_telemetry error: %s", exc)
        return JSONResponse({"ok": False}, status_code=500)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Dev Analytics — /api/dev/analytics  (dev only)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@app.get("/api/dev/analytics")
async def api_dev_analytics(request: Request, period: str = "week"):
    init_data_header = request.headers.get("X-Telegram-Init-Data", "")
    if not init_data_header:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    try:
        from utils.tg_auth import validate_init_data
        user_info = validate_init_data(init_data_header)
        if not user_info:
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        from utils.ranks import is_developer
        if not is_developer(user_info.get("id", 0)):
            return JSONResponse({"error": "forbidden"}, status_code=403)
    except Exception:
        pass  # allow in dev/no-auth setups
    if period not in ("day", "week", "month"):
        period = "week"
    from database.db import get_telemetry_analytics
    result = await get_telemetry_analytics(period)
    return JSONResponse(result)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Статика из /web  (Vite build: /assets/*.js, /assets/*.css)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

if _WEB_DIR.exists():
    # Vite кладёт бандлы в /assets/ — монтируем если директория есть
    _assets_dir = _WEB_DIR / "assets"
    if _assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(_assets_dir)), name="assets")
    app.mount("/static", StaticFiles(directory=str(_WEB_DIR)), name="static")
