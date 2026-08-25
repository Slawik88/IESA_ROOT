"""FastAPI/main.py — Predvestnik Mini App entry point. Adapter layer only."""
import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import BaseModel
from dotenv import load_dotenv

if os.getenv("PREDVESTNIK_ENV", "").strip().lower() == "preprod":
    _preprod_env = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env.test")
    if not os.path.isfile(_preprod_env):
        raise RuntimeError("Preprod requires local secret file '.env.test'.")
    load_dotenv(_preprod_env)
    from infrastructure.preprod import assert_preprod_environment
    assert_preprod_environment()
else:
    load_dotenv()

from infrastructure.database import create_pool, get_pool
from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories import theme_templates, theme_meta, web_notifications, admin_log, system_flags, dev_settings, analytics as analytics_repo
from FastAPI.auth import verify_login_widget, create_session_token, verify_session_token, verify_webapp_data
from FastAPI import notifications
from FastAPI.routers import (profile, top, inventory, shop, zoo, gacha,
                              craft, quests, auction, duels, achievements,
                              themes, streak, exchange, dark_mora,
                              marriage, daily_deal, promocodes, wallet,
                              events, admin, vip, battle_pass, global_admin,
                              dev_console, payments, relics, cosmetics, clans,
                              legal, analytics as analytics_router, showcase,
                              skill_games, clans2, dev_overlay, appeals, account,
                              barracks as barracks_router,
                              reconstruction as reconstruction_router)
from FastAPI.routers import legacy_combat_retirement as legacy_combat_retirement_router
from FastAPI.routers import notifications as notif_router  # алиас: FastAPI.notifications (WS) уже занял имя
from services.cosmetics import ensure_tables as ensure_cosmetics
from infrastructure.repositories.clans import ensure_tables as ensure_clans
from infrastructure.repositories.crypto import ensure_tables as ensure_crypto
from infrastructure.repositories.users import ensure_account_columns
from infrastructure.repositories.auction import ensure_columns as ensure_auction_columns
from infrastructure.repositories.push import ensure_table as ensure_push
from infrastructure.repositories.showcase import ensure_tables as ensure_showcase
from infrastructure.repositories.minigames import ensure_table as ensure_minigames
from infrastructure.repositories.global_permissions import ensure_table as ensure_rank_perms
from infrastructure.repositories.twin_signals import ensure_table as ensure_twin_signals
from infrastructure.repositories.reconstruction import ensure_tables as ensure_reconstruction
from infrastructure.repositories.gameplay_events import ensure_table as ensure_gameplay_events
from infrastructure.repositories.economy_ledger import ensure_tables as ensure_economy_ledger
from infrastructure.repositories.economy_shadow import ensure_table as ensure_economy_shadow
from infrastructure.repositories.reconstruction_settlements import ensure_table as ensure_reconstruction_settlements
from infrastructure.repositories.reconstruction_units import ensure_tables as ensure_reconstruction_units
from infrastructure.repositories.companions_v3 import ensure_tables as ensure_companions_v3
from infrastructure.repositories.alliance_v3 import ensure_table as ensure_alliance_v3
from FastAPI.deps import require_tab_enabled
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
            (dev_settings.ensure_table,      "dev_numeric_settings"),
            (analytics_repo.ensure_table,    "analytics"),
            (ensure_cosmetics,               "cosmetics"),
            (ensure_clans,                   "clans"),
            (ensure_crypto,                  "crypto"),
            (ensure_account_columns,         "account_columns"),
            (ensure_auction_columns,         "auction_columns"),
            (ensure_push,                    "push_queue"),
            (ensure_showcase,                "showcase"),
            (ensure_minigames,               "minigames"),
            (ensure_rank_perms,              "global_rank_permissions"),
            (ensure_twin_signals,            "twin_signals"),
            (ensure_reconstruction,          "reconstruction"),
            (ensure_gameplay_events,          "gameplay_events"),
            (ensure_economy_ledger,           "economy_ledger"),
            (ensure_economy_shadow,           "economy_shadow_rewards"),
            (ensure_reconstruction_settlements, "reconstruction_reward_settlements"),
            (ensure_reconstruction_units,     "reconstruction_unit_progress"),
            (ensure_companions_v3,             "companions_v3"),
            (ensure_alliance_v3,               "alliance_v3_shadow"),
        ]:
            try:
                await _fn(PGAdapter(conn))
            except Exception as _e:
                _log.error(f"[lifespan] {_label}.ensure_table failed: {_e}")
            finally:
                # Любой ensure мог оставить общее соединение в aborted-transaction
                # (multi-statement execute, гонка ON CONFLICT и т.п.). Тогда КАЖДЫЙ
                # следующий ensure молча падает на «current transaction is aborted»
                # — так на проде не создавались новые колонки users
                # (combat_tutorial_done, whatsnew_seen_id → /profile/me = 500).
                # Сбрасываем состояние перед следующим ensure.
                try:
                    if conn.is_in_transaction():
                        await conn.execute("ROLLBACK")
                except Exception:
                    pass
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
          payments.router, relics.router, cosmetics.router,
          clans.router, legal.router, notif_router.router,
          analytics_router.router, showcase.router, skill_games.router,
          clans2.router, dev_overlay.router, appeals.router, account.router,
          barracks_router.router, reconstruction_router.router]:
    app.include_router(r)
app.include_router(legacy_combat_retirement_router.router)


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
    except asyncio.CancelledError:
        # Деплой/рестарт (SIGTERM) отменяет все ASGI-таски, включая открытые WS —
        # это ожидаемое завершение, не ошибка. ws_session уже почистил себя в
        # своём finally (unregister + выход из комнат) до того, как отмена сюда
        # долетела. Подавляем, чтобы не шуметь в логах на каждом рестарте.
        pass


# ── Health & legacy ────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/api/ready")
async def ready():
    """Readiness is stricter than liveness: pool + application schema must exist."""
    try:
        await create_pool()
        async with get_pool().acquire() as conn:
            schema = await conn.fetchval("SELECT to_regnamespace('predvestnik')")
        if schema != "predvestnik":
            raise RuntimeError("application schema is missing")
    except Exception as exc:
        _log.warning(f"[ready] unavailable: {type(exc).__name__}")
        raise HTTPException(status_code=503, detail="Service is not ready.") from exc
    return {"status": "ready"}


@app.get("/profile/{user_id}")
async def legacy_profile(user_id: int):
    await create_pool()
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
    await create_pool()
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
_APP_JS_PARTS = [f"app.{i:02d}.js" for i in range(1, 12)]  # app.01.js … app.11.js

# Cache-busting version = newest mtime among the static assets.
_ASSET_VER = str(int(max(
    *[os.path.getmtime(os.path.join(_STATIC_DIR, p)) for p in _APP_JS_PARTS],
    os.path.getmtime(os.path.join(_STATIC_DIR, "app.css")),
    os.path.getmtime(os.path.join(_STATIC_DIR, "reconstruction-lab.css")),
    os.path.getmtime(os.path.join(_STATIC_DIR, "reconstruction-lab.js")),
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
# БЛОК 25: dev-оверлей — отдельный скрипт (НЕ в склейке), активируется только
# после 200 от /admin/dev-overlay/check; данные за гейтом на бэке.
_APP_DEVMODE_JS = _read_static("app.devmode.js")
_RECONSTRUCTION_CSS = _read_static("reconstruction-lab.css")
_RECONSTRUCTION_JS = _read_static("reconstruction-lab.js")
# Compatibility shim for the pre-2026-08-24 saved-look delete button.  The
# current stylesheet does not reference this asset; retain it for one release
# because an already-open Telegram WebView can still have its old CSS cached.
_LEGACY_CLOSE_ICON_SVG = _read_static("icons/x.svg")
_RECONSTRUCTION_HTML = (
    _read_static("reconstruction-lab.html")
    .replace('data-runtime="preview"', 'data-runtime="production"')
    .replace('data-api-base="/__reconstruction"', 'data-api-base=""')
    .replace('data-app-base=""', f'data-app-base="{_ASSET_BASE}"')
    .replace(
        'href="/static/reconstruction-lab.css"',
        f'href="{_ASSET_BASE}/static/reconstruction-lab.css?v={_ASSET_VER}"',
    )
    .replace(
        'src="/static/reconstruction-lab.js"',
        f'src="{_ASSET_BASE}/static/reconstruction-lab.js?v={_ASSET_VER}"',
    )
)
# Лента «Что нового»: владелец правит FastAPI/static/updates.json как текст
# (при деплое перечитывается). Отдаётся как обычный JSON — фронт рендерит страницу.
_UPDATES_JSON = _read_static("updates.json")


@app.get("/", response_class=HTMLResponse)
async def mini_app():
    return HTMLResponse(_INDEX_HTML)


@app.get(
    "/game",
    response_class=HTMLResponse,
    dependencies=[Depends(require_tab_enabled("game_reconstruction_v1"))],
)
async def reconstruction_game():
    return HTMLResponse(_RECONSTRUCTION_HTML)


@app.get("/updates.json")
async def updates_feed():
    return Response(_UPDATES_JSON, media_type="application/json; charset=utf-8")


@app.get("/static/app.css")
async def static_css():
    return Response(_APP_CSS, media_type="text/css; charset=utf-8")


@app.get("/static/app.js")
async def static_js():
    return Response(_APP_JS, media_type="application/javascript; charset=utf-8")


@app.get("/static/app.devmode.js")
async def static_devmode_js():
    return Response(_APP_DEVMODE_JS, media_type="application/javascript; charset=utf-8")


@app.get("/static/reconstruction-lab.css")
async def reconstruction_css():
    return Response(_RECONSTRUCTION_CSS, media_type="text/css; charset=utf-8")


@app.get("/static/reconstruction-lab.js")
async def reconstruction_js():
    return Response(_RECONSTRUCTION_JS, media_type="application/javascript; charset=utf-8")


@app.get("/static/icons/x.svg")
async def static_close_icon():
    """Serve the one-release cache-compatibility asset for an older stylesheet."""
    return Response(_LEGACY_CLOSE_ICON_SVG, media_type="image/svg+xml")
