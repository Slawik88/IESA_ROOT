"""FastAPI/main.py — Predvestnik Mini App entry point. Adapter layer only."""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

from infrastructure.database import create_pool, get_pool
from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories import theme_templates, theme_meta, web_notifications, admin_log, system_flags, analytics as analytics_repo
from FastAPI.auth import verify_login_widget, create_session_token, verify_session_token, verify_webapp_data
from FastAPI import notifications
from FastAPI.routers import (profile, top, inventory, shop, zoo, gacha,
                              craft, quests, auction, duels, achievements,
                              themes, streak, exchange, dark_mora,
                              marriage, daily_deal, promocodes, wallet,
                              events, admin, vip, battle_pass, global_admin,
                              dev_console, payments, games, relics, cosmetics, clans,
                              combat, legal, analytics as analytics_router, showcase,
                              skill_games, battle, clans2)
from FastAPI.routers import notifications as notif_router  # алиас: FastAPI.notifications (WS) уже занял имя
from services.cosmetics import ensure_tables as ensure_cosmetics
from infrastructure.repositories.clans import ensure_tables as ensure_clans
from infrastructure.repositories.crypto import ensure_tables as ensure_crypto
from infrastructure.repositories.pet_combat import ensure_tables as ensure_combat
from infrastructure.repositories.users import ensure_account_columns
from infrastructure.repositories.auction import ensure_columns as ensure_auction_columns
from infrastructure.repositories.push import ensure_table as ensure_push
from infrastructure.repositories.showcase import ensure_tables as ensure_showcase
from infrastructure.repositories.minigames import ensure_table as ensure_minigames
from infrastructure.repositories.battles import ensure_table as ensure_battles
from infrastructure.repositories.clans2 import ensure_tables as ensure_clans2
from loguru import logger as _log


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_pool()
    # Theme Lab нужна эта таблица, а init_db() (со всеми миграциями) гоняется
    # только в процессе бота — без этого веб-процесс падает на "relation
    # profile_theme_overrides does not exist" без рестарта бота.
    # Каждый ensure независим: падение одного не должно блокировать остальные.
    async with get_pool().acquire() as conn:
        # RESET ALL (asyncpg pool cleanup) сбрасывает search_path к дефолту.
        # Явно устанавливаем перед ensure-вызовами чтобы DDL шёл в нужную схему.
        await conn.execute("SET search_path TO predvestnik, public")
        for _fn, _label in [
            (theme_templates.ensure_table,   "theme_templates"),
            (theme_meta.ensure_table,        "theme_meta"),
            (web_notifications.ensure_table, "web_notifications"),
            (admin_log.ensure_table,         "admin_log"),
            (system_flags.ensure_table,      "system_flags"),
            (analytics_repo.ensure_table,    "analytics"),
            (ensure_cosmetics,               "cosmetics"),
            (ensure_clans,                   "clans"),
            (ensure_crypto,                  "crypto"),
            (ensure_combat,                  "combat"),
            (ensure_account_columns,         "account_columns"),
            (ensure_auction_columns,         "auction_columns"),
            (ensure_push,                    "push_queue"),
            (ensure_showcase,                "showcase"),
            (ensure_minigames,               "minigames"),
            (ensure_battles,                 "battles"),
            (ensure_clans2,                  "clans2"),
        ]:
            try:
                await _fn(PGAdapter(conn))
            except Exception as _e:
                _log.error(f"[lifespan] {_label}.ensure_table failed: {_e}")
    yield


app = FastAPI(title="Predvestnik Mini App", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

for r in [profile.router, top.router, inventory.router, shop.router, zoo.router,
          gacha.router, craft.router, quests.router, auction.router, duels.router,
          achievements.router, themes.router, streak.router, exchange.router,
          dark_mora.router, marriage.router, daily_deal.router,
          promocodes.router, wallet.router, events.router, admin.router, vip.router,
          battle_pass.router, global_admin.router, dev_console.router,
          payments.router, games.router, relics.router, cosmetics.router,
          clans.router, combat.router, legal.router, notif_router.router,
          analytics_router.router, showcase.router, skill_games.router, battle.router, clans2.router]:
    app.include_router(r)


# ── Auth ───────────────────────────────────────────────────────────────────────

class _LoginWidgetPayload(BaseModel):
    id: int; first_name: str; auth_date: int; hash: str
    last_name: str | None = None; username: str | None = None; photo_url: str | None = None


@app.post("/auth/telegram-login")
async def telegram_login(payload: _LoginWidgetPayload):
    data = {k: v for k, v in payload.model_dump().items() if v is not None}
    user = verify_login_widget(data)
    if not user:
        raise HTTPException(401, "Неверная подпись Telegram.")
    return {"session_token": create_session_token(int(user["id"])),
            "user_id": user["id"], "username": user.get("username",""),
            "first_name": user.get("first_name","")}


# ── WebSocket notifications ────────────────────────────────────────────────────

@app.websocket("/ws/{user_id}")
async def ws_endpoint(websocket: WebSocket, user_id: int, token: str = "", init: str = ""):
    # H6: верифицируем, что подключающийся — это и есть user_id (WebApp шлёт initData,
    # браузер — session-token). Иначе можно было слушать чужой поток уведомлений.
    authed = False
    if init:
        _u = verify_webapp_data(init)
        authed = bool(_u and int(_u.get("id", 0)) == user_id)
    elif token:
        authed = verify_session_token(token) == user_id
    if not authed:
        await websocket.close(code=1008)  # policy violation
        return
    await websocket.accept()
    # R5: единый протокол сессии (отправка событий + команды комнат лотов) —
    # вся логика в notifications.ws_session, чистка гарантирована внутри.
    try:
        await notifications.ws_session(websocket, user_id)
    except WebSocketDisconnect:
        pass


# ── Health & legacy ────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/profile/{user_id}")
async def legacy_profile(user_id: int):
    async with get_pool().acquire() as conn:
        db = PGAdapter(conn)
        async with db.execute(
            "SELECT user_tg_id, user_tg_username, global_rank, "
            "user_balance_mora, user_balance_diamonds FROM users WHERE user_tg_id = ?",
            (user_id,)
        ) as c:
            row = await c.fetchone()
    if not row:
        raise HTTPException(404, "Not found")
    return dict(row)


@app.get("/api/events")
async def api_events():
    async with get_pool().acquire() as conn:
        db = PGAdapter(conn)
        async with db.execute("SELECT * FROM exchange_events WHERE status='active' LIMIT 1") as c:
            active = await c.fetchone()
        async with db.execute("SELECT * FROM exchange_events WHERE status='scheduled' ORDER BY starts_at LIMIT 1") as c:
            scheduled = await c.fetchone()
    if active:
        return {"exchange": {"active": True, "ends_at": str(dict(active).get("ends_at",""))[:16]}}
    if scheduled:
        s = dict(scheduled)
        return {"exchange": {"active": False, "scheduled": True, "starts_at": str(s.get("starts_at",""))[:16]}}
    return {"exchange": {"active": False, "scheduled": False}}


# ── Mini App HTML ──────────────────────────────────────────────────────────────

@app.get("/manifest.json")
async def pwa_manifest():
    return JSONResponse({
        "name": "Предвестник",
        "short_name": "Предвестник",
        "description": "Telegram-игра с питомцами и экономикой",
        "start_url": "./",
        "display": "standalone",
        "background_color": "#08090f",
        "theme_color": "#c9a84c",
        "icons": [
            {"src": "https://telegram.org/img/t_logo.png", "sizes": "512x512", "type": "image/png"},
        ],
    })

# ── Static assets (CSS / JS extracted from the former inline HTML) ──────────────
_STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")


def _read_static(name: str) -> str:
    with open(os.path.join(_STATIC_DIR, name), encoding="utf-8") as f:
        return f.read()


# app.js разбит на части (рефакторинг §5: меньше файлы → проще grep/Read/правки).
# КРИТИЧНО: части СКЛЕИВАЮТСЯ в ОДИН скрипт и отдаются одним <script>, а НЕ N тегами —
# top-level let/const классического скрипта живут в ОДНОЙ лексической области, и
# раздача отдельными тегами сломала бы cross-file ссылки. Порядок = порядок в исходнике.
_APP_JS_PARTS = [f"app.{i:02d}.js" for i in range(1, 11)]  # app.01.js … app.10.js

# Cache-busting version = newest mtime among the static assets.
_ASSET_VER = str(int(max(
    *[os.path.getmtime(os.path.join(_STATIC_DIR, p)) for p in _APP_JS_PARTS],
    os.path.getmtime(os.path.join(_STATIC_DIR, "app.css")),
)))
# Absolute asset base so external CSS/JS resolve correctly under the /predvestnik
# routing prefix regardless of trailing slash in the document URL.
_ASSET_BASE = os.getenv("ROOT_PATH", "").rstrip("/")
_INDEX_HTML = (
    _read_static("index.html")
    .replace("{{BOT_USERNAME}}", os.getenv("BOT_USERNAME", "IIIPredvestnikIIIBot"))
    .replace("{{ASSET_VER}}", _ASSET_VER)
    .replace("{{BASE}}", _ASSET_BASE)
)
_APP_CSS = _read_static("app.css")
_APP_JS = "".join(_read_static(p) for p in _APP_JS_PARTS)


@app.get("/", response_class=HTMLResponse)
async def mini_app():
    return HTMLResponse(_INDEX_HTML)


@app.get("/static/app.css")
async def static_css():
    return Response(_APP_CSS, media_type="text/css; charset=utf-8")


@app.get("/static/app.js")
async def static_js():
    return Response(_APP_JS, media_type="application/javascript; charset=utf-8")
