"""FastAPI/main.py — Predvestnik Mini App entry point. Adapter layer only."""
import asyncio
import contextlib
import json
import os
import re
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
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

from infrastructure.database import PoolBusy, create_pool, get_pool
from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories import theme_templates, theme_meta, web_notifications, admin_log, system_flags, dev_settings, analytics as analytics_repo
from FastAPI.auth import (verify_login_widget, create_session_token,
                          verify_preprod_browser_ticket, verify_session_token,
                          verify_webapp_data)
from infrastructure.preprod import PREPROD_BROWSER_TEST_USER_ID, is_preprod, require_preprod_user
from FastAPI import notifications
from FastAPI.static_assets import StaticAsset, asset_version, compact_json, minify_js, prepare, respond
from FastAPI.deps import assert_account_active
from infrastructure import readiness
from FastAPI.routers import (profile, marriage, wallet, vip,
                              payments,
                              legal, analytics as analytics_router,
                              account,
                              rhythm_v2 as rhythm_v2_router, minesweeper_v2 as minesweeper_v2_router, mafia_v1 as mafia_v1_router, hub, leaderboards as leaderboards_router, public_profile_v3 as public_profile_v3_router, marks_v1 as marks_v1_router, appearance, cosmetics as cosmetics_router, skins_v3 as skins_v3_router, presence_v1 as presence_v1_router, pets_v1 as pets_v1_router, pets_v2 as pets_v2_router, pet_nudge_v1 as pet_nudge_v1_router, casino_v1 as casino_v1_router, star_dust as star_dust_router, quests_v1 as quests_v1_router, achievements_v1 as achievements_v1_router, chests_v1 as chests_v1_router, shop_v1 as shop_v1_router, gifts_v2 as gifts_v2_router, inventory_v1 as inventory_v1_router, player_exchange_v1 as player_exchange_v1_router, season_pass as season_pass_router)
from FastAPI.routers import legacy_combat_retirement as legacy_combat_retirement_router
from FastAPI.routers import promo_redeem as promo_redeem_router  # ввод промокода игроком
from FastAPI.routers import guide_v3 as guide_v3_router  # Путеводитель игрока: /guide-v3.json
from FastAPI.routers import bot_admin as bot_admin_router  # новая админка бота: /bot-admin
from FastAPI.routers import purge_v1 as purge_v1_router
from FastAPI.routers import league_v1 as league_v1_router  # демо Лиги, только ранний доступ
from FastAPI.routers import telemetry as telemetry_router  # анонимные ошибки Mini App для «Здоровья»
from FastAPI.ops_middleware import RequestMetrics
from services import ops_health
from FastAPI import game_shell
from FastAPI import support_middleware
from FastAPI.routers import support as support_router
from infrastructure.repositories.support_reports import ensure_tables as ensure_support_reports
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
from infrastructure.repositories.purge_sessions import ensure_operations as ensure_purge_operations
from infrastructure.repositories.word_chain import ensure_tables as ensure_word_chain
from infrastructure.repositories.mafia_online import ensure_tables as ensure_mafia_online
from FastAPI.routers import mafia_online as mafia_online_router
from services.mafia_online_scheduler import run as run_mafia_online_scheduler
from infrastructure.repositories.pets_v1 import ensure_tables as ensure_pets_v1
from infrastructure.repositories.quests_v1 import ensure_tables as ensure_quests_v1
from infrastructure.repositories.echo_shards_v1 import ensure_tables as ensure_echo_shards_v1
from infrastructure.repositories.achievements_v1 import ensure_tables as ensure_achievements_v1
from infrastructure.repositories.public_profiles_v1 import ensure_tables as ensure_public_profiles_v1
from infrastructure.repositories.global_skins_v1 import ensure_tables as ensure_global_skins_v1
from infrastructure.repositories.skins_v3 import ensure_tables as ensure_skins_v3
from infrastructure.repositories.marks_v1 import ensure_tables as ensure_marks_v1
from infrastructure.repositories.presence_v1 import ensure_tables as ensure_presence_v1
from services import skins_v3_migration
from infrastructure.repositories.chests_v1 import ensure_tables as ensure_chests_v1
from infrastructure.repositories.shop_v1 import ensure_tables as ensure_shop_v1
from infrastructure.repositories.gifts_v2 import ensure_tables as ensure_gifts_v2
from services.promo_v2 import ensure_schema as ensure_promo_v2
from infrastructure.repositories.player_exchange_v1 import ensure_tables as ensure_player_exchange_v1
from infrastructure.repositories.coin_market_v2 import ensure_tables as ensure_coin_market_v2
from infrastructure.repositories.pets_v2 import ensure_tables as ensure_pets_v2
from infrastructure.repositories.star_dust import ensure_tables as ensure_star_dust
from infrastructure.repositories.season_pass import ensure_tables as ensure_season_pass
from infrastructure.repositories.league_pass import ensure_tables as ensure_league_pass
from infrastructure.repositories.league_v1 import ensure_tables as ensure_league_v1
from FastAPI.routers import coin_market_v2 as coin_market_v2_router
from loguru import logger as _log


async def _run_coin_market_v2() -> None:
    """Web lifecycle owns price time even with no bot or site visitors."""
    from services.coin_market_v2 import maintenance
    while True:
        await asyncio.sleep(15)
        try:
            async with get_pool().acquire() as conn:
                await maintenance(PGAdapter(conn))
        except Exception:
            _log.exception("Coin market v2 maintenance failed; stale trading stays closed")


async def _run_skins_v3_migration() -> None:
    """One-off launch job: refund Zarniki spent on retired skins and archive the old ownership. Idempotent, set SKINS_V3_MIGRATION=off to skip."""
    try:
        await asyncio.sleep(8)       # let the app start serving first
        async with get_pool().acquire() as conn:
            await conn.execute("SET search_path TO predvestnik, public")
            await skins_v3_migration.run(PGAdapter(conn))
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        _log.error(f"[skins_v3] migration aborted, will retry on next start: {exc}")


async def _run_broadcast_scheduler() -> None:
    """Запускает отложенные рассылки из админки, когда наступает их время."""
    try:
        from FastAPI.routers.bot_admin.people import get_bot
        from services import broadcasts
        await broadcasts.scheduler(get_bot(), broadcasts.pool_db_factory())
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        _log.error(f"[broadcasts] scheduler stopped: {exc}")


async def _run_owner_digest() -> None:
    """Раз в сутки отправляет владельцу итоги дня (настройка в админке: вкладка «Состояние»)."""
    try:
        from FastAPI.routers.bot_admin.people import get_bot
        from services import broadcasts, owner_digest
        await owner_digest.scheduler(get_bot(), broadcasts.pool_db_factory())
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        _log.error(f"[owner_digest] scheduler stopped: {exc}")


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
        _failed_ensures: list[str] = []
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
            (ensure_purge_operations,             "purge_operations"),
            (ensure_word_chain,                   "word_chain"),
            (ensure_mafia_online,                "mafia_online"),
            (ensure_chests_v1,                   "chests_v1"),
            (ensure_shop_v1,                     "shop_v1"),
            (ensure_gifts_v2,                    "gifts_v2"),
            (ensure_promo_v2,                    "promo_v2"),   # show_in_app для GET /promo-v2/me, не дожидаясь старта бота
            (ensure_pets_v1,                     "pets_v1"),
            (ensure_pets_v2,                     "pets_v2"),
            (ensure_star_dust, "star_dust"),
            (ensure_season_pass,                 "season_pass"),
            (ensure_league_pass,                 "league_pass"),
            (ensure_league_v1,                   "league_v1"),
            (ensure_quests_v1,                    "quests_v1"),
            (ensure_echo_shards_v1,                "echo_shards_v1"),
            (ensure_achievements_v1,                "achievements_v1"),
            (ensure_public_profiles_v1,             "public_profiles_v1"),
            (ensure_global_skins_v1,                 "global_skins_v1"),
            (ensure_skins_v3,                        "skins_v3"),
            (ensure_marks_v1,                        "marks_v1"),
            (ensure_presence_v1,                     "presence_v1"),
            (ensure_player_exchange_v1,              "player_exchange_v1"),
            (ensure_coin_market_v2,                  "coin_market_v2"),
            (ensure_support_reports,                 "support_reports"),
        ]:
            try:
                await _fn(PGAdapter(conn))
            except Exception as _e:
                _failed_ensures.append(_label)
                _log.error(f"[lifespan] {_label}.ensure_table failed: {_e}")
                if _label == "player_exchange_v1":
                    try:
                        if conn.is_in_transaction():
                            await conn.execute("ROLLBACK")
                        _enabled = await conn.fetchval(
                            "SELECT enabled FROM system_flags WHERE key='economy_player_exchange_v1'"
                        )
                    except Exception:
                        _enabled = False
                    if _enabled:
                        raise RuntimeError(
                            "Enabled player exchange schema failed to initialize."
                        ) from _e
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
    # Standalone start (the co-hosted bot marks it itself): stay not-ready while
    # any ensure failed, so /api/ready never hides a half-created schema.
    if _failed_ensures:
        _log.error(f"[lifespan] not ready: failed ensures {', '.join(_failed_ensures)}")
    else:
        from services.player_release import activate
        async with get_pool().acquire() as connection:
            await activate(PGAdapter(connection))
        readiness.mark_startup_complete()
    migration_task = asyncio.create_task(_run_skins_v3_migration()) if skins_v3_migration.enabled() else None
    scheduler_task = asyncio.create_task(_run_broadcast_scheduler())
    digest_task = asyncio.create_task(_run_owner_digest())
    coin_market_task = asyncio.create_task(_run_coin_market_v2())
    mafia_online_task = asyncio.create_task(run_mafia_online_scheduler())
    yield
    for task in (migration_task, scheduler_task, digest_task, coin_market_task, mafia_online_task):
        if task:
            task.cancel()
            try:
                await task
            except BaseException:
                pass


app = FastAPI(title="Predvestnik Mini App", lifespan=lifespan)


@app.exception_handler(PoolBusy)
async def _pool_busy(request, exc: PoolBusy):
    # Every DB connection stayed busy past DB_ACQUIRE_TIMEOUT_SEC: a short «try again» instead of a hanging request.
    # 503 is what the Mini App already retries once for GET (static/app.01.js api()).
    return JSONResponse({"detail": "Сервер сейчас занят. Попробуй ещё раз через пару секунд."},
                        status_code=503, headers={"Retry-After": "2"})
app.include_router(mafia_online_router.router)
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# Release Mini App boundary.  Historical game/economy routers are intentionally
# not registered: hiding their buttons is not sufficient because a cached
# client can still call a public endpoint directly.  Their data stays in the
# database solely for the owner-approved final compensation audit.
for r in [profile.router, marriage.router, wallet.router, vip.router,
          payments.router, legal.router, notif_router.router,
          analytics_router.router, account.router,
          rhythm_v2_router.router, minesweeper_v2_router.router, mafia_v1_router.router, hub.router, leaderboards_router.router, public_profile_v3_router.router, marks_v1_router.router, appearance.router, cosmetics_router.router, skins_v3_router.router, presence_v1_router.router, pets_v1_router.router, pets_v2_router.router, pet_nudge_v1_router.router, casino_v1_router.router, star_dust_router.router, quests_v1_router.router, achievements_v1_router.router, chests_v1_router.router, shop_v1_router.router, gifts_v2_router.router, inventory_v1_router.router, season_pass_router.router]:
    app.include_router(r)
app.include_router(player_exchange_v1_router.router)
app.include_router(coin_market_v2_router.router)
app.include_router(promo_redeem_router.router)   # ввод промокода в Mini App
app.include_router(guide_v3_router.router)
app.include_router(legacy_combat_retirement_router.router)
app.include_router(bot_admin_router.router)
app.include_router(purge_v1_router.router)
app.include_router(league_v1_router.router)
app.include_router(support_router.router)
app.include_router(telemetry_router.router)
app.middleware("http")(bot_admin_router.site_gate)   # выключатели сайта из админки
app.middleware("http")(support_middleware.record_request)


@app.middleware("http")
async def revalidate_mini_app_assets(request, call_next):
    response = await call_next(request)
    # HTML must discover each release's content hash; bare asset URLs must also
    # revalidate. This does not change caching of authenticated API responses.
    path = request.url.path
    if path.startswith("/static/") and request.query_params.get("v"):
        # Content-addressed URL: HTML всегда ссылается на текущий хэш релиза,
        # поэтому байты за данным ?v= неизменны — кэшируем навсегда без стейл-риска.
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    elif path in ("/", "/rhythm-v2", "/minesweeper", "/league", "/league-demo") or path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-cache"
    return response


# Сжатие текстовых ответов (статика ~1МБ JS, CSS, JSON API). Уже сжатые ответы
# middleware пропускает (защита content_encoding_set в Starlette).
app.add_middleware(GZipMiddleware, minimum_size=1024)
# Outermost: request time per route for the health panel, compression included.
app.add_middleware(RequestMetrics)


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

_WS_AUTH_TIMEOUT_SEC = 5
_WS_AUTH_MAX_CHARS = 8192
_WS_AUTH_MAX_PENDING = 300      # accepted sockets still waiting for their credential (all clients together)
_ws_pending_auth = 0


async def _ws_first_message_credentials(websocket: WebSocket) -> dict[str, str]:
    """The client sends {"type":"auth","init"|"token": ...} right after connecting, so credentials
    never appear in the connection address (addresses are written to proxy logs)."""
    try:
        raw = await asyncio.wait_for(websocket.receive_text(), _WS_AUTH_TIMEOUT_SEC)
        message = json.loads(raw) if len(raw) <= _WS_AUTH_MAX_CHARS else {}
    except (asyncio.TimeoutError, WebSocketDisconnect, KeyError, ValueError):
        return {}
    if not isinstance(message, dict) or message.get("type") != "auth":
        return {}
    return {key: message[key] for key in ("init", "token") if isinstance(message.get(key), str)}


@app.websocket("/ws/{user_id}")
async def ws_endpoint(websocket: WebSocket, user_id: int, token: str = "", init: str = ""):
    # H6: верифицируем, что подключающийся — это и есть user_id (WebApp шлёт initData,
    # браузер — session-token). Иначе можно было слушать чужой поток уведомлений.
    # Current clients send the credential as the first message; ?init=/?token= stays for
    # clients opened before that release.
    global _ws_pending_auth
    accepted = not (init or token)
    if accepted:
        if _ws_pending_auth >= _WS_AUTH_MAX_PENDING:
            await websocket.close(code=1013)   # try again later: too many silent sockets right now
            return
        _ws_pending_auth += 1
        try:
            await websocket.accept()
            sent = await _ws_first_message_credentials(websocket)
        finally:
            _ws_pending_auth -= 1
        init, token = sent.get("init", ""), sent.get("token", "")
        if not (init or token):
            with contextlib.suppress(RuntimeError, OSError):   # a silent client may already have hung up
                await websocket.close(code=1008)
            return

    def credential_valid() -> bool:
        if init:
            _u = verify_webapp_data(init)
            return bool(_u and int(_u.get("id", 0)) == user_id)
        if token:
            return verify_session_token(token) == user_id
        return False

    async def account_allowed() -> bool:
        # The same gates as HTTP gameplay (deps.require_tg_user): preprod
        # allowlist and account deletion (audit A06). DB errors propagate.
        if not require_preprod_user(user_id):
            return False
        await create_pool()
        async with get_pool().acquire() as conn:
            try:
                await assert_account_active(PGAdapter(conn), user_id)
            except HTTPException:
                return False
        return True

    if not credential_valid():
        await websocket.close(code=1008)  # policy violation
        return
    try:
        allowed = await account_allowed()
    except Exception as exc:
        _log.warning(f"[ws] account check unavailable: {type(exc).__name__}")
        await websocket.close(code=1011)  # fail closed; client retries with backoff
        return
    if not allowed:
        await websocket.close(code=1008)
        return

    async def still_allowed() -> bool:
        if not credential_valid():
            return False
        try:
            return await account_allowed()
        except Exception:
            return True   # transient DB error keeps an already admitted session

    if not accepted:
        await websocket.accept()
    # Единый протокол сессии (отправка событий + keep-alive клиента) —
    # вся логика в notifications.ws_session, чистка гарантирована внутри.
    try:
        await notifications.ws_session(websocket, user_id, app_version=_ASSET_VER,
                                       still_allowed=still_allowed)
    except WebSocketDisconnect:
        pass
    except asyncio.CancelledError:
        # Деплой/рестарт (SIGTERM) отменяет все ASGI-таски, включая открытые WS —
        # это ожидаемое завершение, не ошибка. ws_session уже почистил себя в
        # своём finally (unregister) до того, как отмена сюда
        # долетела. Подавляем, чтобы не шуметь в логах на каждом рестарте.
        pass


# ── Health & legacy ────────────────────────────────────────────────────────────

@app.get("/api/player-release")
async def player_release_status():
    from core import player_release as policy
    from infrastructure.repositories import player_release as release_repo
    await create_pool()
    async with get_pool().acquire() as connection:
        return JSONResponse({"release":policy.RELEASE_ID, **(await release_repo.status(PGAdapter(connection),(*policy.FLAGS,'coin_market_v2','game_mafia_online','star_dust_v1','game_casino_v1')))},headers={"Cache-Control":"no-store"})


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/api/health/deep")
async def health_deep():
    """For people and external monitors, not for the platform probe: a slow database turns it red
    (503) while /api/health keeps the container alive. Body: database ping and metrics freshness."""
    status, body = await ops_health.deep_check()
    return JSONResponse(body, status_code=status, headers={"Cache-Control": "no-store"})


@app.get("/api/ready")
async def ready():
    """Readiness is stricter than liveness: startup must have finished its schema
    work and every table the first requests read must exist (audit A04)."""
    try:
        if not readiness.startup_complete():
            raise RuntimeError("startup schema initialization has not finished")
        await create_pool()
        async with get_pool().acquire() as conn:
            missing = await readiness.missing_tables(conn)
        if missing:
            raise RuntimeError(f"required tables are missing: {', '.join(missing)}")
    except Exception as exc:
        _log.warning(f"[ready] unavailable: {exc if isinstance(exc, RuntimeError) else type(exc).__name__}")
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


_STATIC_CACHE: dict[str, str] = {}


def _read_static(name: str) -> str:
    # Исходник читается один раз и держится в памяти (раздача готовит файлы при старте, _STORE);
    # ручная правка файла на диске подхватывается только после рестарта процесса.
    source = _STATIC_CACHE.get(name)
    if source is None:
        with open(os.path.join(_STATIC_DIR, name), encoding="utf-8") as f:
            source = f.read()
        _STATIC_CACHE[name] = source
    return source


# app.js разбит на части (рефакторинг §5: меньше файлы → проще grep/Read/правки).
# КРИТИЧНО: части СКЛЕИВАЮТСЯ в ОДИН скрипт и отдаются одним <script>, а НЕ N тегами —
# top-level let/const классического скрипта живут в ОДНОЙ лексической области, и
# раздача отдельными тегами сломала бы cross-file ссылки. Порядок = порядок в исходнике.
# app.03.js and app.05.js contained only retired pet, Battle-Pass and old
# economy UI.  They are intentionally no longer delivered; archival database
# records remain.
_APP_JS_PARTS = [f"app.{i:02d}.js" for i in (1, 2, 4, 6, 7, 11, 12, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57)]

# Shell V3 stylesheets (loaded after app.css, in this order); each is served at /static/<name>.
_SHELL_V3_CSS = ("support-feedback.css", "shell-v3.css", "skins-v3.css", "shell-v3-home.css", "mafia-online-v3.css", "fx-tiers-v3.css", "appearance-v3.css",
                 "appearance-ring-v3.css", "appearance-stage-v3.css", "looks-v3.css", "settings-v3.css", "skin-signatures-v3.css", "skin-signatures-2-v3.css", "skins-exclusive-v3.css", "skin-sig-a-v3.css", "skin-sig-b-v3.css", "skin-sig-c-v3.css", "skin-sig-d-v3.css", "skin-scene-v3.css", "skin-holidays-v3.css", "nickname-v3.css",
                 "public-card-v3.css", "collect-v3.css", "toast-v3.css", "toast-gift-v3.css", "quests-v3.css", "marks-v3.css", "inventory-v3.css", "trail-v3.css", "guide-v3.css", "news-v3.css", "pass-v3.css", "store-v3.css", "motion-v3.css", "confirm-v3.css", "monolith-v3.css", "monolith-player-v3.css", "pets-v3.css", "promo-v3.css", "achievements-v3.css", "chests-v3.css", "top-board-v3.css", "art-v3.css", "casino-v3.css", "desktop-v3.css")

# The scene pictures of the looks (tools/scene_art.py, ~830 KB) are never linked from index.html: a scene asks for a file when it draws a layer with one
# of its pictures (apScene, app.35.js), so a player in the default look downloads none of them. A new scene picture file goes here, not into index.html.
_SKIN_SCENE_ART = tuple(f"skin-scene-{letter}-v3.css" for letter in "abcdefg")

# Game pages render leaderboard nicks like the Mini App tops: they load the same skin CSS and one small script.
# The page look, the «Обычный | Рейтинг» switch and the shared header come from the League assets (/static/league-demo/…, FastAPI/game_shell.py).
_GAME_BOARD_ASSETS = ("fx-tiers-v3.css", "appearance-v3.css", "appearance-ring-v3.css", "appearance-stage-v3.css", "skin-scene-v3.css", "skin-signatures-v3.css", "skin-signatures-2-v3.css", "skins-exclusive-v3.css",
                      "skin-sig-a-v3.css", "skin-sig-b-v3.css", "skin-sig-c-v3.css", "skin-sig-d-v3.css", "marks-v3.css", "nickname-v3.css", "top-board-v3.css",
                      "nickname-v3.js", "game-board-v3.js", "top-board.js", "page-transitions.js")
# Their leaderboard is the Mini App's own top: top-board.js is the game-page shim (top-board-v3.js) followed by the very same app parts that draw
# «Топ» and «Топ-10» (row 17, look/nick/avatar 20, ornaments 22, mark 29, scenes and signature details 32–38/48/53, podium 50). Not a copy: a change to the Mini App top reaches the games too.
_TOP_BOARD_PARTS = ("top-board-v3.js", *(f"app.{i:02d}.js" for i in (17, 20, 22, 29, 32, 33, 34, 35, 36, 37, 38, 48, 50, 53)))   # in the order of app.js

TELEGRAM_SDK_FALLBACK = "vendor/telegram-web-app.js"

# Buildpacks normalize mtimes (1980 on production), so only content identifies
# a release. Hash source HTML before ASSET_VER substitution to avoid recursion.
_ASSET_SOURCES = tuple(dict.fromkeys((
    *_APP_JS_PARTS, "page-transitions.js", "support-diagnostics.js", "support-feedback.js", TELEGRAM_SDK_FALLBACK, "app.css", *_SHELL_V3_CSS, *_SKIN_SCENE_ART,
    "nickname-v3.js", "index.html", "rhythm-v2.html", "minesweeper-v2.html", "game-shell-v3.html",
    "rhythm-v2.js", "minesweeper-v2.js", "local-games-v1.js", "local-games-sw.js",
    "skin-runtime-v3.js", "coin-market-v2.css", "coin-market-chart.js", "coin-market-v2.js", *(n for n in _GAME_BOARD_ASSETS if n != "top-board.js"), *_TOP_BOARD_PARTS,
)))
# The release: the «update available» banner and error reports name it (<meta name="pv-release"> in index.html).
_ASSET_VER = asset_version(_STATIC_DIR, _ASSET_SOURCES)
app.state.asset_version = _ASSET_VER

# Every text asset is prepared once per process: JS minified, gzipped once (not on every request), with its own content hash. A page links
# /static/<name>?v=<that hash>, so a deploy makes clients download again only the files whose bytes changed (FastAPI/static_assets.py).
_JS = "application/javascript; charset=utf-8"
_CSS = "text/css; charset=utf-8"
_JS_SOURCES = {"app.js": "".join(_read_static(p) for p in _APP_JS_PARTS), "top-board.js": "".join(_read_static(p) for p in _TOP_BOARD_PARTS), **{name: _read_static(name) for name in (
    "page-transitions.js", "support-diagnostics.js", "support-feedback.js", "nickname-v3.js", "game-board-v3.js", "skin-runtime-v3.js",
    "rhythm-v2.js", "minesweeper-v2.js", "local-games-v1.js", "coin-market-chart.js", "coin-market-v2.js")}}
_STORE: dict[str, StaticAsset] = {name: prepare(minify_js(source), _JS) for name, source in _JS_SOURCES.items()}
_STORE[TELEGRAM_SDK_FALLBACK] = prepare(_read_static(TELEGRAM_SDK_FALLBACK), _JS)   # the official file, served as it is
for _css_name in ("app.css", *_SHELL_V3_CSS, *_SKIN_SCENE_ART, "coin-market-v2.css"):
    _STORE[_css_name] = prepare(_read_static(_css_name), _CSS)
_VERSIONED_LINK = re.compile(r"/static/([\w./-]+)\?v=\{\{ASSET_VER\}\}")


def _link_versions(html: str) -> str:
    """/static/<name>?v={{ASSET_VER}} -> the file's own version (an unknown name stops the start: a typo must not ship)."""
    return _VERSIONED_LINK.sub(lambda m: f"/static/{m[1]}?v={_STORE[m[1]].version}", html)


def _scene_art() -> str:
    """For apScene: which file holds each scene picture, {letter: [address, "name name …"]}."""
    files = {}
    for name in _SKIN_SCENE_ART:
        letter = name.split("-")[2]
        pictures = re.findall(r"^\.i-([\w-]+) \{", _read_static(name), re.M)
        files[letter] = [f"{_ASSET_BASE}/static/{name}?v={_STORE[name].version}", " ".join(pictures)]
    return json.dumps(files, separators=(",", ":"))


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
_INDEX = prepare(
    _link_versions(_read_static("index.html"))
    .replace("{{BOT_USERNAME}}", _BOT_USERNAME)
    .replace("{{LOGIN_SURFACE}}", _LOGIN_SURFACE)
    .replace("{{RELEASE}}", _ASSET_VER)
    .replace("{{SCENE_ART}}", _scene_art())
    .replace("{{BASE}}", _ASSET_BASE),
    "text/html; charset=utf-8",
)
def _game_page(source: str, *, title: str, game: str, script: str) -> str:
    """A casual game page: the shared header and League look first, then the app's own versioned scripts."""
    html = game_shell.render(_read_static(source), base=_ASSET_BASE, version=league_v1_router.ASSET_VERSION,
                             eyebrow="Сезон · обычный", title=title, game=game, mode="casual")
    for name in (script, "skin-runtime-v3.js", "local-games-v1.js"):
        html = html.replace(f'src="/static/{name}"', f'src="{_ASSET_BASE}/static/{name}?v={_STORE[name].version}"')
    return html


def _with_game_board_assets(html: str) -> str:
    html = html.replace("{{SCENE_ART}}", _scene_art())   # the scene of a look asks for its picture file by this map (apScene, app.35.js), as in index.html
    for name in _GAME_BOARD_ASSETS:
        attr = "src" if name.endswith(".js") else "href"
        html = html.replace(f'{attr}="/static/{name}"', f'{attr}="{_ASSET_BASE}/static/{name}?v={_STORE[name].version}"')
    return html


_RHYTHM_V2_HTML = _with_game_board_assets(_game_page("rhythm-v2.html", title="Ритм", game="rhythm", script="rhythm-v2.js"))
_MINESWEEPER_V2_HTML = _with_game_board_assets(_game_page("minesweeper-v2.html", title="Сапёр", game="minesweeper", script="minesweeper-v2.js"))

# Лента «Что нового»: владелец правит FastAPI/static/updates.json как текст
# (при деплое перечитывается). Отдаётся JSON без пробелов, сжатым, с ETag: пока лента та же, ответ 304 без тела.
_UPDATES = prepare(compact_json(_read_static("updates.json")), "application/json; charset=utf-8")


@app.get("/", response_class=HTMLResponse)
async def mini_app(request: Request):
    return respond(_INDEX, request)


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
        path=f"{_ASSET_BASE}/",
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
async def updates_feed(request: Request):
    return respond(_UPDATES, request)


def _register_asset(name: str) -> None:
    async def _serve(request: Request) -> Response:
        return respond(_STORE[name], request)
    app.add_api_route(f"/static/{name}", _serve, methods=["GET"], include_in_schema=False)


# vendor/telegram-web-app.js: a copy of the Telegram SDK, loaded by index.html only when telegram.org fails.
for _asset_name in _STORE:
    _register_asset(_asset_name)


@app.get("/local-games-sw.js")
async def local_games_worker():
    assets = [f"{_ASSET_BASE}/rhythm-v2", f"{_ASSET_BASE}/minesweeper"]
    assets += [f"{_ASSET_BASE}/static/{name}?v={_STORE[name].version}" for name in (
        "support-diagnostics.js", "support-feedback.js", "support-feedback.css",
        "local-games-v1.js", "rhythm-v2.js", "minesweeper-v2.js", "skin-runtime-v3.js", *_GAME_BOARD_ASSETS)]
    # the look and the shared header of the casual pages come from the League assets: they must play offline too
    assets += [f"{_ASSET_BASE}/static/league-demo/{name}?v={league_v1_router.ASSET_VERSION}" for name in league_v1_router.CASUAL_PAGE_ASSETS]
    source = _read_static("local-games-sw.js").replace("{{VERSION}}", _ASSET_VER).replace("{{PRECACHE}}", json.dumps(assets))
    return Response(source, media_type="application/javascript; charset=utf-8", headers={"Cache-Control": "no-cache"})


@app.get("/static/mafia-art/{name}")
async def mafia_art(name: str):
    # Public fictional role art, never a projection of an active player's role.
    if name not in {f"{role}.{ext}" for role in ("city", "citizen", "mafia", "don", "doctor", "detective") for ext in ("jpg", "webp")}:
        raise HTTPException(404)
    return FileResponse(os.path.join(_STATIC_DIR, "mafia-art", name),
                        media_type="image/webp" if name.endswith(".webp") else "image/jpeg")
