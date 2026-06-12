"""FastAPI/main.py — Predvestnik Mini App entry point. Adapter layer only."""
import asyncio
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
from FastAPI.auth import verify_login_widget, create_session_token
from FastAPI import notifications
from FastAPI.routers import (profile, top, inventory, shop, zoo, gacha,
                              craft, quests, auction, duels, achievements,
                              themes, streak, exchange, dark_mora,
                              marriage, daily_deal, promocodes, wallet,
                              events, admin, vip, battle_pass, global_admin,
                              dev_console)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_pool()
    yield


app = FastAPI(title="Predvestnik Mini App", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

for r in [profile.router, top.router, inventory.router, shop.router, zoo.router,
          gacha.router, craft.router, quests.router, auction.router, duels.router,
          achievements.router, themes.router, streak.router, exchange.router,
          dark_mora.router, marriage.router, daily_deal.router,
          promocodes.router, wallet.router, events.router, admin.router, vip.router,
          battle_pass.router, global_admin.router, dev_console.router]:
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
async def ws_endpoint(websocket: WebSocket, user_id: int):
    await websocket.accept()
    q: asyncio.Queue = asyncio.Queue()
    notifications.register(user_id, q)
    try:
        while True:
            event = await q.get()
            await websocket.send_json(event)
    except WebSocketDisconnect:
        notifications.unregister(user_id)


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


# Cache-busting version = newest mtime among the static assets.
_ASSET_VER = str(int(max(
    os.path.getmtime(os.path.join(_STATIC_DIR, "app.js")),
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
_APP_JS = _read_static("app.js")


@app.get("/", response_class=HTMLResponse)
async def mini_app():
    return HTMLResponse(_INDEX_HTML)


@app.get("/static/app.css")
async def static_css():
    return Response(_APP_CSS, media_type="text/css; charset=utf-8")


@app.get("/static/app.js")
async def static_js():
    return Response(_APP_JS, media_type="application/javascript; charset=utf-8")
