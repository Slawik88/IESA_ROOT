"""FastAPI/main.py — Predvestnik Mini App entry point. Adapter layer only."""
import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
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
from FastAPI.auth import (verify_login_widget, create_session_token,
                          verify_preprod_browser_ticket, verify_session_token,
                          verify_webapp_data)
from infrastructure.preprod import PREPROD_BROWSER_TEST_USER_ID, is_preprod
from FastAPI import notifications
from FastAPI.routers import (profile, marriage, wallet,
                              admin, global_admin, dev_console, payments,
                              legal, analytics as analytics_router,
                              dev_overlay, appeals, account,
                              rhythm_v2 as rhythm_v2_router, minesweeper_v2 as minesweeper_v2_router, mafia_v1 as mafia_v1_router, hub, appearance, cosmetics as cosmetics_router, global_skins_v1 as global_skins_v1_router, pets_v1 as pets_v1_router, quests_v1 as quests_v1_router, achievements_v1 as achievements_v1_router, chests_v1 as chests_v1_router)
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
from infrastructure.repositories.retention_v3 import ensure_tables as ensure_retention_v3
from infrastructure.repositories.weekly_case_v1 import ensure_tables as ensure_weekly_case_v1
from infrastructure.repositories.chat_echo_v1 import ensure_tables as ensure_chat_echo_v1
from infrastructure.repositories.scar_map_v1 import ensure_tables as ensure_scar_map_v1
from infrastructure.repositories.feats_v1 import ensure_table as ensure_feats_v1
from infrastructure.repositories.sky_v1 import ensure_tables as ensure_sky_v1
from infrastructure.repositories.star_payments_v1 import ensure_tables as ensure_star_payments_v1
from infrastructure.repositories.rhythm_v2 import ensure_tables as ensure_rhythm_v2
from infrastructure.repositories.supporter_cosmetics_v1 import ensure_tables as ensure_supporter_cosmetics_v1
from infrastructure.repositories.minesweeper_v2 import ensure_tables as ensure_minesweeper_v2
from infrastructure.repositories.mafia_v1 import ensure_tables as ensure_mafia_v1
from infrastructure.repositories.pets_v1 import ensure_tables as ensure_pets_v1
from infrastructure.repositories.quests_v1 import ensure_tables as ensure_quests_v1
from infrastructure.repositories.echo_shards_v1 import ensure_tables as ensure_echo_shards_v1
from infrastructure.repositories.achievements_v1 import ensure_tables as ensure_achievements_v1
from infrastructure.repositories.public_profiles_v1 import ensure_tables as ensure_public_profiles_v1
from infrastructure.repositories.global_skins_v1 import ensure_tables as ensure_global_skins_v1
from infrastructure.repositories.chests_v1 import ensure_tables as ensure_chests_v1
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
            (ensure_retention_v3,              "retention_v3"),
            (ensure_weekly_case_v1,            "weekly_case_v1"),
            (ensure_chat_echo_v1,              "chat_echo_v1"),
            (ensure_scar_map_v1,               "scar_map_v1"),
            (ensure_feats_v1,                  "chronicle_feat_receipts_v1"),
            (ensure_sky_v1,                    "harbinger_sky_v1"),
            (ensure_star_payments_v1,          "stars_payment_receipts_v1"),
            (ensure_rhythm_v2,                  "rhythm_v2"),
            (ensure_supporter_cosmetics_v1,    "supporter_cosmetics_v1"),
            (ensure_minesweeper_v2,             "minesweeper_v2"),
            (ensure_mafia_v1,                    "mafia_v1"),
            (ensure_chests_v1,                   "chests_v1"),
            (ensure_pets_v1,                     "pets_v1"),
            (ensure_quests_v1,                    "quests_v1"),
            (ensure_echo_shards_v1,                "echo_shards_v1"),
            (ensure_achievements_v1,                "achievements_v1"),
            (ensure_public_profiles_v1,             "public_profiles_v1"),
            (ensure_global_skins_v1,                 "global_skins_v1"),
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

# Release Mini App boundary.  Historical game/economy routers are intentionally
# not registered: hiding their buttons is not sufficient because a cached
# client can still call a public endpoint directly.  Their data stays in the
# database solely for the owner-approved final compensation audit.
for r in [profile.router, marriage.router, wallet.router,
          admin.router, global_admin.router, dev_console.router,
          payments.router, legal.router, notif_router.router,
          analytics_router.router, dev_overlay.router, appeals.router, account.router,
          rhythm_v2_router.router, minesweeper_v2_router.router, mafia_v1_router.router, hub.router, appearance.router, cosmetics_router.router, global_skins_v1_router.router, pets_v1_router.router, quests_v1_router.router, achievements_v1_router.router, chests_v1_router.router]:
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


@app.get("/api/events")
async def api_events():
    # Legacy reader must obey the same retirement boundary as /events/. Do not
    # inspect exchange_events: an old row must never resurrect a premium or
    # progression conversion through an unmaintained endpoint.
    return {
        "retired": True,
        "message": "Старые валютные события закрыты.",
        "exchange_retired": True,
    }


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
# app.03.js and app.05.js contained only retired pet, Battle-Pass and old
# economy UI.  They are intentionally no longer delivered; archival database
# records remain.
_APP_JS_PARTS = [f"app.{i:02d}.js" for i in (1, 2, 4, 6, 7, 8, 9, 10, 11, 12, 13)]

# Cache-busting version = newest mtime among the static assets.
_ASSET_VER = str(int(max(
    *[os.path.getmtime(os.path.join(_STATIC_DIR, p)) for p in _APP_JS_PARTS],
    os.path.getmtime(os.path.join(_STATIC_DIR, "app.css")),
    os.path.getmtime(os.path.join(_STATIC_DIR, "rhythm-v2.css")),
    os.path.getmtime(os.path.join(_STATIC_DIR, "rhythm-v2.js")),
    os.path.getmtime(os.path.join(_STATIC_DIR, "minesweeper-v2.css")),
    os.path.getmtime(os.path.join(_STATIC_DIR, "minesweeper-v2.js")),
    os.path.getmtime(os.path.join(_STATIC_DIR, "global-skins-v1.css")),
    os.path.getmtime(os.path.join(_STATIC_DIR, "global-skins-v1.js")),
    os.path.getmtime(os.path.join(_STATIC_DIR, "skins", "lunar-archive-v1.webp")),
    os.path.getmtime(os.path.join(_STATIC_DIR, "skins", "void-atlas-v1.webp")),
)))
# Absolute asset base so external CSS/JS resolve correctly under the /predvestnik
# routing prefix regardless of trailing slash in the document URL.
_ASSET_BASE = os.getenv("ROOT_PATH", "").rstrip("/")
_BOT_USERNAME = os.getenv("BOT_USERNAME", "IIIPredvestnikIIIBot").strip().lstrip("@")
_LOGIN_SURFACE = (
    f'<a class="login-open-bot" href="https://t.me/{_BOT_USERNAME}?startapp=game">'
    'Открыть тестовый Mini App в Telegram <b>›</b></a>'
    if os.getenv("PREDVESTNIK_ENV", "").strip().lower() == "preprod"
    else '<div id="tg-login-widget"><script src="https://telegram.org/js/telegram-widget.js?22" '
         f'data-telegram-login="{_BOT_USERNAME}" data-size="large" data-radius="14" '
         'data-onauth="onTelegramWidgetAuth(user)" data-request-access="write"></script></div>'
)
_INDEX_HTML = (
    _read_static("index.html")
    .replace("{{BOT_USERNAME}}", _BOT_USERNAME)
    .replace("{{LOGIN_SURFACE}}", _LOGIN_SURFACE)
    .replace("{{ASSET_VER}}", _ASSET_VER)
    .replace("{{BASE}}", _ASSET_BASE)
)
_APP_CSS = _read_static("app.css")
_APP_JS = "".join(_read_static(p) for p in _APP_JS_PARTS)
# БЛОК 25: dev-оверлей — отдельный скрипт (НЕ в склейке), активируется только
# после 200 от /admin/dev-overlay/check; данные за гейтом на бэке.
_APP_DEVMODE_JS = _read_static("app.devmode.js")
_RHYTHM_V2_HTML = (
    _read_static("rhythm-v2.html")
    .replace('data-app-base=""', f'data-app-base="{_ASSET_BASE}"')
    # The Mini App is mounted under /predvestnik in the local and tunnelled
    # environments.  A literal href="/" leaves that mount and reaches a
    # non-existent host root, which is the source of the visible 404 on ‹.
    .replace('href="/"', f'href="{_ASSET_BASE}/"')
    .replace('href="/static/rhythm-v2.css"', f'href="{_ASSET_BASE}/static/rhythm-v2.css?v={_ASSET_VER}"')
    .replace('href="/static/global-skins-v1.css"', f'href="{_ASSET_BASE}/static/global-skins-v1.css?v={_ASSET_VER}"')
    .replace('src="/static/global-skins-v1.js"', f'src="{_ASSET_BASE}/static/global-skins-v1.js?v={_ASSET_VER}"')
    .replace('src="/static/rhythm-v2.js"', f'src="{_ASSET_BASE}/static/rhythm-v2.js?v={_ASSET_VER}"')
)
_MINESWEEPER_V2_HTML = (
    _read_static("minesweeper-v2.html")
    .replace('data-app-base=""', f'data-app-base="{_ASSET_BASE}"')
    .replace('href="/"', f'href="{_ASSET_BASE}/"')
    .replace('href="/static/minesweeper-v2.css"', f'href="{_ASSET_BASE}/static/minesweeper-v2.css?v={_ASSET_VER}"')
    .replace('href="/static/global-skins-v1.css"', f'href="{_ASSET_BASE}/static/global-skins-v1.css?v={_ASSET_VER}"')
    .replace('src="/static/global-skins-v1.js"', f'src="{_ASSET_BASE}/static/global-skins-v1.js?v={_ASSET_VER}"')
    .replace('src="/static/minesweeper-v2.js"', f'src="{_ASSET_BASE}/static/minesweeper-v2.js?v={_ASSET_VER}"')
)
# Лента «Что нового»: владелец правит FastAPI/static/updates.json как текст
# (при деплое перечитывается). Отдаётся как обычный JSON — фронт рендерит страницу.
_UPDATES_JSON = _read_static("updates.json")


@app.get("/", response_class=HTMLResponse)
async def mini_app():
    return HTMLResponse(_INDEX_HTML)


@app.get("/__preprod/activate", response_class=RedirectResponse)
async def activate_preprod_browser_persona(ticket: str = ""):
    """Set the local test cookie only after a short signed loopback hand-off.

    The route is absent outside isolated preprod.  The ticket is purpose-bound,
    short-lived and only authorizes the artificial test identity, never a real
    Telegram account or a general browser session.
    """
    user_id = verify_preprod_browser_ticket(ticket)
    if not is_preprod() or user_id != PREPROD_BROWSER_TEST_USER_ID:
        raise HTTPException(404, "not found")
    response = RedirectResponse(f"{_ASSET_BASE}/", status_code=303)
    response.set_cookie(
        key="predvestnik_preprod_test_session",
        value=create_session_token(user_id),
        max_age=20 * 60,
        httponly=True,
        secure=False,
        samesite="strict",
        path=f"{_ASSET_BASE}/" or "/",
    )
    # Some automation WebViews intentionally isolate cookies during a
    # cross-port localhost redirect.  Their client consumes this short ticket
    # once and immediately removes it from the address bar; normal browsers
    # simply use the HttpOnly cookie above.
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Location"] = f"{_ASSET_BASE}/?__preprod_ticket={ticket}"
    return response


@app.get("/game", response_class=RedirectResponse)
async def retired_reconstruction_game():
    """Compatibility URL: never reopen the retired Reconstruction client."""
    return RedirectResponse(f"{_ASSET_BASE}/?startapp=games", status_code=307)


@app.get("/rhythm-v2", response_class=HTMLResponse)
async def rhythm_v2_game():
    # Telegram supplies initData to the WebApp JavaScript, not to this initial
    # document navigation.  The authenticated, feature-gated API router below
    # remains the security boundary; gating this static shell would reject a
    # legitimate Mini App before it can attach x-init-data.
    return HTMLResponse(_RHYTHM_V2_HTML)


@app.get("/minesweeper", response_class=HTMLResponse)
async def minesweeper_game():
    # The initial document must load before Telegram JavaScript exposes initData.
    # Its server-owned run and leaderboard APIs independently require the
    # authenticated, feature-gated contract; this shell exposes no economy.
    return HTMLResponse(_MINESWEEPER_V2_HTML)


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


@app.get("/static/rhythm-v2.css")
async def rhythm_v2_css():
    return Response(_read_static("rhythm-v2.css"), media_type="text/css; charset=utf-8")


@app.get("/static/rhythm-v2.js")
async def rhythm_v2_js():
    return Response(_read_static("rhythm-v2.js"), media_type="application/javascript; charset=utf-8")


@app.get("/static/minesweeper-v2.css")
async def minesweeper_css():
    return Response(_read_static("minesweeper-v2.css"), media_type="text/css; charset=utf-8")


@app.get("/static/global-skins-v1.css")
async def global_skins_css():
    return Response(_read_static("global-skins-v1.css"), media_type="text/css; charset=utf-8")


@app.get("/static/global-skins-v1.js")
async def global_skins_js():
    return Response(_read_static("global-skins-v1.js"), media_type="application/javascript; charset=utf-8")


@app.get("/static/skins/lunar-archive-v1.webp")
async def lunar_archive_skin_asset():
    with open(os.path.join(_STATIC_DIR, "skins", "lunar-archive-v1.webp"), "rb") as asset:
        return Response(asset.read(), media_type="image/webp")


@app.get("/static/skins/void-atlas-v1.webp")
async def void_atlas_skin_asset():
    with open(os.path.join(_STATIC_DIR, "skins", "void-atlas-v1.webp"), "rb") as asset:
        return Response(asset.read(), media_type="image/webp")


@app.get("/static/minesweeper-v2.js")
async def minesweeper_js():
    return Response(_read_static("minesweeper-v2.js"), media_type="application/javascript; charset=utf-8")
