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
#  Frontend Error Log — /api/frontend_error_log  (no auth, ErrorBoundary sink)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@app.post("/api/frontend_error_log")
async def api_frontend_error_log(request: Request):
    try:
        data = await request.json()
        error_msg = str(data.get("error", ""))[:500]
        stack = str(data.get("stack", ""))[:2000]
        _log.error("FRONTEND ERROR: %s | STACK: %s", error_msg, stack)
        return JSONResponse({"ok": True})
    except Exception as exc:
        _log.warning("api_frontend_error_log: %s", exc)
        return JSONResponse({"ok": False}, status_code=500)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Avatar Proxy  —  GET /api/proxy/avatar?url=...
#  Кэшируем аватарки Telegram в памяти на 24 часа, отдаём с правильными
#  заголовками, чтобы фронтенд не получал CORS-ошибки.
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

import time as _time
import urllib.request as _ur
import hashlib as _hl
from fastapi.responses import Response as _FaResponse

_avatar_cache: dict[str, tuple[bytes, str, float]] = {}  # url → (data, content_type, expires_ts)
_AVATAR_TTL = 86_400  # 24 h

@app.get("/api/proxy/avatar")
async def proxy_avatar(url: str = ""):
    if not url:
        return _FaResponse(status_code=400)
    # Разрешаем только Telegram CDN / t.me / file.bot.* чтобы не стать открытым прокси
    import urllib.parse as _up
    parsed = _up.urlparse(url)
    allowed_hosts = ("t.me", "telegram.org", "cdn4.telegram-cdn.org", "cdn1.telegram-cdn.org",
                     "cdn2.telegram-cdn.org", "cdn3.telegram-cdn.org",
                     "api.telegram.org", "cdn5.telegram-cdn.org")
    if parsed.scheme not in ("http", "https") or not any(parsed.netloc.endswith(h) for h in allowed_hosts):
        return _FaResponse(status_code=403)

    cache_key = _hl.md5(url.encode()).hexdigest()
    now = _time.time()
    if cache_key in _avatar_cache:
        data, ctype, expires = _avatar_cache[cache_key]
        if now < expires:
            return _FaResponse(content=data, media_type=ctype,
                               headers={"Cache-Control": "public, max-age=86400"})

    try:
        req = _ur.Request(url, headers={"User-Agent": "TelegramBot"})
        with _ur.urlopen(req, timeout=8) as resp:
            ctype = resp.headers.get_content_type() or "image/jpeg"
            data = resp.read(2 * 1024 * 1024)  # max 2 MB
        _avatar_cache[cache_key] = (data, ctype, now + _AVATAR_TTL)
        # Ограничиваем размер кэша в памяти
        if len(_avatar_cache) > 5000:
            oldest = sorted(_avatar_cache, key=lambda k: _avatar_cache[k][2])[:500]
            for k in oldest:
                del _avatar_cache[k]
        return _FaResponse(content=data, media_type=ctype,
                           headers={"Cache-Control": "public, max-age=86400"})
    except Exception as exc:
        _log.debug("proxy_avatar fetch error: %s", exc)
        return _FaResponse(status_code=502)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Leaderboard  —  /api/leaderboard
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@app.get("/api/leaderboard")
async def leaderboard_route(request: Request, chat_id: int = 0, type: str = "xp"):
    """Leaderboard по типу: xp | messages | boss | mora"""
    try:
        from api.user import get_leaderboard
        uid_raw = request.headers.get("X-User-Id", "0")
        try:
            uid = int(uid_raw)
        except ValueError:
            uid = 0
        result = await get_leaderboard(chat_id=chat_id, lb_type=type, uid=uid)
        return JSONResponse(result)
    except Exception as exc:
        _log.exception("leaderboard_route error: %s", exc)
        return JSONResponse({"error": str(exc)}, status_code=500)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Solo Boss  —  /api/solo_boss/*
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_BOSS_DAILY_LIMIT = 3


@app.get("/api/solo_boss/status")
async def solo_boss_status(user_id: int = 0, chat_id: int = 0):
    if not user_id or not chat_id:
        return JSONResponse({"error": "user_id and chat_id required"}, status_code=400)
    try:
        from database.db import (
            get_solo_boss_session, get_solo_boss_progress,
            get_boss_coupons,
        )
        from database.postgres import connect as postgres_connect
        from datetime import datetime, timezone

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        session = await get_solo_boss_session(user_id, chat_id)
        progress = await get_solo_boss_progress(user_id, chat_id)
        coupons, next_regen = await get_boss_coupons(user_id)

        async with postgres_connect() as db:
            async with db.execute(
                "SELECT COUNT(*) AS c FROM solo_boss_sessions WHERE user_id=? AND chat_id=? AND session_date=?",
                (user_id, chat_id, today),
            ) as cur:
                cnt_row = await cur.fetchone()
        daily_used = int(cnt_row["c"] or 0) if cnt_row else 0

        # Reset time (next UTC midnight)
        from datetime import timedelta
        now_utc = datetime.now(timezone.utc)
        tomorrow = (now_utc + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        reset_in_sec = int((tomorrow - now_utc).total_seconds())
        hrs, rem = divmod(reset_in_sec, 3600)
        mins = rem // 60
        reset_text = f"{hrs}ч {mins}м"

        next_level = (progress["max_level"] + 1) if progress else 1
        return JSONResponse({
            "session": session,
            "progress": progress,
            "next_level": next_level,
            "daily_limit": _BOSS_DAILY_LIMIT,
            "daily_used": daily_used,
            "daily_remaining": max(0, _BOSS_DAILY_LIMIT - daily_used),
            "reset_at": tomorrow.isoformat(),
            "reset_in_seconds": reset_in_sec,
            "reset_in_text": reset_text,
            "boss_coupons": coupons,
            "next_coupon_regen_at": next_regen,
        })
    except Exception as exc:
        _log.exception("solo_boss_status error: %s", exc)
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.post("/api/solo_boss/start")
async def solo_boss_start(request: Request):
    try:
        data = await request.json()
        user_id = int(data.get("user_id", 0))
        chat_id = int(data.get("chat_id", 0))
        boss_level = int(data.get("boss_level", 0))
        if not user_id or not chat_id:
            return JSONResponse({"ok": False, "error": "user_id and chat_id required"}, status_code=400)

        from database.db import (
            get_solo_boss_session, get_solo_boss_progress,
            create_solo_boss_session, use_boss_coupon,
        )
        from database.postgres import connect as postgres_connect
        from datetime import datetime, timezone

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # Check if already has active session
        existing = await get_solo_boss_session(user_id, chat_id)
        if existing and not existing.get("is_completed"):
            return JSONResponse({"ok": True, "session": existing})

        # Check daily limit
        async with postgres_connect() as db:
            async with db.execute(
                "SELECT COUNT(*) AS c FROM solo_boss_sessions WHERE user_id=? AND chat_id=? AND session_date=?",
                (user_id, chat_id, today),
            ) as cur:
                cnt_row = await cur.fetchone()
        daily_used = int(cnt_row["c"] or 0) if cnt_row else 0
        if daily_used >= _BOSS_DAILY_LIMIT:
            # Try coupon
            used = await use_boss_coupon(user_id)
            if not used:
                return JSONResponse({"ok": False, "error": "Дневной лимит исчерпан. Купи купон (7💎) или подожди завтра."})

        progress = await get_solo_boss_progress(user_id, chat_id)
        if not boss_level:
            boss_level = (progress["max_level"] + 1) if progress else 1
        session = await create_solo_boss_session(user_id, chat_id, boss_level)
        return JSONResponse({"ok": True, "session": session})
    except Exception as exc:
        _log.exception("solo_boss_start error: %s", exc)
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)


@app.post("/api/solo_boss/attack")
async def solo_boss_attack(request: Request):
    try:
        data = await request.json()
        user_id = int(data.get("user_id", 0))
        chat_id = int(data.get("chat_id", 0))
        if not user_id or not chat_id:
            return JSONResponse({"ok": False, "error": "user_id and chat_id required"}, status_code=400)

        from database.db import get_solo_boss_session, apply_solo_boss_damage
        import random as _rnd

        session = await get_solo_boss_session(user_id, chat_id)
        if not session:
            return JSONResponse({"ok": False, "error": "Нет активного боя. Начни сначала."})
        if session.get("is_completed"):
            return JSONResponse({"ok": False, "error": "Бой уже завершён."})

        base_damage = _rnd.randint(120, 220)
        result = await apply_solo_boss_damage(user_id, session, base_damage)

        rewards = None
        if result["boss_defeated"]:
            boss_level = session["boss_level"]
            mora_reward = 300 + boss_level * 200
            xp_reward   = 50  + boss_level * 30
            is_repeat = bool(session.get("is_repeat"))
            if not is_repeat:
                from database.db import add_mora, add_user_xp
                await add_mora(user_id, chat_id, mora_reward, source="solo_boss_win")
                try:
                    await add_user_xp(user_id, chat_id, xp_reward)
                except Exception:
                    pass
            rewards = {"mora": mora_reward if not is_repeat else 0, "xp": xp_reward if not is_repeat else 0}

        return JSONResponse({"ok": True, **result, "rewards": rewards})
    except Exception as exc:
        _log.exception("solo_boss_attack error: %s", exc)
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)


@app.post("/api/solo_boss/forfeit")
async def solo_boss_forfeit(request: Request):
    try:
        data = await request.json()
        user_id = int(data.get("user_id", 0))
        chat_id = int(data.get("chat_id", 0))
        if not user_id or not chat_id:
            return JSONResponse({"ok": False, "error": "user_id and chat_id required"}, status_code=400)

        from database.postgres import connect as postgres_connect
        from database.db import get_solo_boss_session

        session = await get_solo_boss_session(user_id, chat_id)
        if not session:
            return JSONResponse({"ok": True, "forfeited": False})

        async with postgres_connect() as db:
            await db.execute(
                "UPDATE solo_boss_sessions SET is_completed=1 WHERE id=?",
                (session["id"],),
            )
            await db.commit()
        return JSONResponse({"ok": True, "forfeited": True})
    except Exception as exc:
        _log.exception("solo_boss_forfeit error: %s", exc)
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Boss Coupon Purchase  —  POST /api/boss/buy_coupon
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_BOSS_COUPON_PRICE_CRYSTALS = 7


@app.post("/api/boss/buy_coupon")
async def boss_buy_coupon(request: Request):
    try:
        data = await request.json()
        user_id = int(data.get("user_id", 0))
        chat_id = int(data.get("chat_id", 0))
        if not user_id:
            return JSONResponse({"ok": False, "error": "user_id required"}, status_code=400)

        from database.db import (
            get_boss_coupons, add_boss_coupons,
            BOSS_COUPONS_MAX,
        )
        from database.postgres import connect as postgres_connect

        coupons, _ = await get_boss_coupons(user_id)
        if coupons >= BOSS_COUPONS_MAX:
            return JSONResponse({"ok": False, "error": "Купоны уже заполнены (макс. 5)."})

        # Deduct crystals
        async with postgres_connect() as db:
            async with db.execute(
                "SELECT COALESCE(crystals, 0) AS c FROM users WHERE user_id=?",
                (user_id,),
            ) as cur:
                row = await cur.fetchone()
            if not row or int(row["c"]) < _BOSS_COUPON_PRICE_CRYSTALS:
                return JSONResponse({"ok": False, "error": f"Недостаточно 💎 (нужно {_BOSS_COUPON_PRICE_CRYSTALS})"})
            await db.execute(
                "UPDATE users SET crystals = crystals - ? WHERE user_id=? AND crystals >= ?",
                (_BOSS_COUPON_PRICE_CRYSTALS, user_id, _BOSS_COUPON_PRICE_CRYSTALS),
            )
            await db.commit()

        new_count = await add_boss_coupons(user_id, 1)
        return JSONResponse({"ok": True, "coupons": new_count})
    except Exception as exc:
        _log.exception("boss_buy_coupon error: %s", exc)
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)


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
