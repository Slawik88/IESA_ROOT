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
#  Mini App API — все /api/* эндпоинты собраны в api/router.py
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from api.router import router as _api_router  # noqa: E402 — после создания app
app.include_router(_api_router)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Статика из /web  (Vite build: /assets/*.js, /assets/*.css)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

if _WEB_DIR.exists():
    # Vite кладёт бандлы в /assets/ — монтируем если директория есть
    _assets_dir = _WEB_DIR / "assets"
    if _assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(_assets_dir)), name="assets")
    app.mount("/static", StaticFiles(directory=str(_WEB_DIR)), name="static")
