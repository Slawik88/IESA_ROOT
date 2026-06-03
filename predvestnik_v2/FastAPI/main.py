"""FastAPI/main.py — Predvestnik Mini App entry point. Adapter layer only."""
import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
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
                              marriage, daily_deal, promocodes, wallet)


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
          promocodes.router, wallet.router]:
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


@app.get("/", response_class=HTMLResponse)
async def mini_app():
    return HTMLResponse(_HTML.replace("{{BOT_USERNAME}}", os.getenv("BOT_USERNAME","IIIPredvestnikIIIBot")))


_HTML = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1.0,viewport-fit=cover"/>
<title>Предвестник</title>
<link rel="manifest" href="./manifest.json"/>
<meta name="theme-color" content="#c9a84c"/>
<meta name="apple-mobile-web-app-capable" content="yes"/>
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent"/>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>
:root{
  --bg:#08090f;--s:#0d1019;--card:#111621;--card2:#161d2a;
  --gold:#c9a84c;--gold2:#e8c866;--gold-dim:rgba(201,168,76,.14);
  --teal:#3fb8af;--red:#e05252;--green:#52b360;--blue:#5a9cf5;--purple:#9d72ff;
  --text:#cdd0de;--bright:#eef0f8;--muted:#5a6480;--dim:#1e2538;
  --border:rgba(201,168,76,.18);--border2:rgba(255,255,255,.06);
  --r:6px;--r-lg:10px;
}
*{margin:0;padding:0;box-sizing:border-box}
body{background:var(--bg);color:var(--text);
     font-family:-apple-system,BlinkMacSystemFont,'SF Pro Display','Segoe UI',sans-serif;
     min-height:100vh;padding-bottom:70px;overflow-x:hidden}

@keyframes fadeUp{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}
@keyframes fadeIn{from{opacity:0}to{opacity:1}}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.5}}
@keyframes shimmer{from{background-position:-200% 0}to{background-position:200% 0}}
@keyframes slideUp{from{opacity:0;transform:translateY(16px)}to{opacity:1;transform:translateY(0)}}
@keyframes glow{0%,100%{box-shadow:0 0 8px rgba(201,168,76,.25)}50%{box-shadow:0 0 18px rgba(201,168,76,.5)}}
@keyframes popIn{from{opacity:0;transform:scale(.9)}to{opacity:1;transform:scale(1)}}

.card{background:var(--card);border:1px solid var(--border2);border-radius:var(--r);
      padding:14px;margin-bottom:10px;position:relative;animation:fadeUp .2s ease}
.card-gold{border-top:1px solid var(--gold)}
.card::before{content:'';position:absolute;top:0;left:0;width:18px;height:18px;
              border-top:1px solid var(--gold);border-left:1px solid var(--gold);
              border-radius:var(--r) 0 0 0;pointer-events:none}
.card-title{font-size:10px;text-transform:uppercase;letter-spacing:1.5px;
            color:var(--muted);margin-bottom:12px;display:flex;align-items:center;gap:6px}
.card-title::after{content:'';flex:1;height:1px;background:var(--border2)}

.sk{background:linear-gradient(90deg,var(--s) 25%,rgba(255,255,255,.04) 50%,var(--s) 75%);
    background-size:200% 100%;animation:shimmer 1.4s infinite;border-radius:4px;min-height:14px}

.nav{position:fixed;bottom:0;left:0;right:0;background:rgba(8,9,15,.95);
     border-top:1px solid var(--border2);display:flex;z-index:100;
     padding-bottom:env(safe-area-inset-bottom);backdrop-filter:blur(16px)}
.nb{flex:1;padding:9px 2px 7px;text-align:center;cursor:pointer;
    font-size:9px;color:var(--muted);transition:.2s;position:relative;user-select:none}
.nb.active{color:var(--gold2)}
.nb.active::after{content:'';position:absolute;bottom:0;left:25%;right:25%;
                  height:2px;background:var(--gold2);border-radius:1px;animation:fadeIn .2s}
.nb .ni{font-size:19px;display:block;margin-bottom:2px;transition:.2s}
.nb.active .ni{filter:drop-shadow(0 0 5px rgba(201,168,76,.4))}

.page{display:none;padding:12px;animation:fadeIn .15s ease}
.page.active{display:block}

.tabs{display:flex;gap:5px;margin-bottom:12px}
.tb{flex:1;padding:7px 4px;border-radius:var(--r);border:1px solid var(--border2);cursor:pointer;
    background:transparent;color:var(--muted);font-size:11px;transition:.15s;font-family:inherit}
.tb.active{background:var(--gold-dim);color:var(--gold2);border-color:var(--border)}

.phead{display:flex;align-items:center;gap:12px;margin-bottom:14px}
.ava{width:48px;height:48px;border-radius:50%;flex-shrink:0;font-size:20px;
     display:flex;align-items:center;justify-content:center;
     background:linear-gradient(135deg,#1a2035,#2a3355);border:1px solid var(--border)}
.pname{font-size:16px;font-weight:700;color:var(--bright)}
.prank{font-size:11px;color:var(--gold);margin-top:2px}

.stats{display:grid;grid-template-columns:1fr 1fr;gap:7px;margin-bottom:12px}
.stat{background:var(--s);border-radius:var(--r);padding:10px;text-align:center;border:1px solid var(--border2)}
.stat .sv{font-size:16px;font-weight:700;color:var(--bright);margin:3px 0;font-variant-numeric:tabular-nums}
.stat .sl{font-size:9px;text-transform:uppercase;letter-spacing:1px;color:var(--muted)}

/* Streak calendar */
.cal{display:grid;grid-template-columns:repeat(10,1fr);gap:3px;margin-top:8px}
.cal-day{aspect-ratio:1;border-radius:2px;background:var(--dim);transition:.2s}
.cal-day.on{background:var(--green)}
.cal-day.today{box-shadow:0 0 0 1px var(--gold)}
.streak-num{font-size:32px;font-weight:800;color:var(--gold);
            text-shadow:0 0 20px rgba(201,168,76,.3);margin:8px 0 2px}

/* Achievements */
.ach-item{padding:10px 0;border-bottom:1px solid var(--border2)}
.ach-item:last-child{border:none}
.ach-head{display:flex;align-items:center;gap:8px;margin-bottom:6px}
.ach-icon{font-size:20px;width:28px;text-align:center}
.ach-name{font-size:13px;font-weight:600;color:var(--bright);flex:1}
.ach-lvl{font-size:11px;color:var(--gold)}
.ach-bar{height:4px;background:var(--dim);border-radius:2px;margin-bottom:3px}
.ach-fill{height:100%;border-radius:2px;background:var(--gold);transition:.4s}
.ach-prog{font-size:10px;color:var(--muted)}

/* Themes / Cosmetics */
.theme-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.theme-card{background:var(--s);border-radius:var(--r);padding:10px;cursor:pointer;
            border:1px solid var(--border2);transition:.15s;position:relative;overflow:hidden}
.theme-card:hover{border-color:var(--border);transform:translateY(-1px)}
.theme-card.owned{border-color:rgba(82,179,96,.35)}
.theme-card.active-theme{border-color:var(--gold);box-shadow:0 0 10px rgba(201,168,76,.25),0 0 0 1px rgba(201,168,76,.1)}
.theme-deco{font-size:10px;color:var(--muted);font-family:monospace;overflow:hidden;white-space:nowrap;text-overflow:ellipsis;letter-spacing:0}
.theme-name{font-size:12px;font-weight:700;color:var(--bright);margin:5px 0 2px}
.theme-price{font-size:10px;color:var(--gold);margin-top:4px}
.theme-status{font-size:9px;padding:2px 6px;border-radius:99px;font-weight:600}
.ts-active{background:rgba(201,168,76,.2);color:var(--gold)}
.ts-owned{background:rgba(82,179,96,.2);color:var(--green)}
.ts-event{background:rgba(99,102,241,.2);color:#818cf8}
.ts-gacha{background:rgba(157,114,255,.2);color:var(--purple)}
.ts-dark{background:rgba(100,80,150,.2);color:#9080c0}

/* Profile preview in theme modal */
.profile-preview{background:var(--card);border-radius:var(--r);padding:12px;margin:10px 0;border:1px solid var(--border2)}
.pp-deco{font-size:11px;font-family:monospace;color:var(--muted);text-align:center;letter-spacing:0}
.pp-content{padding:8px 0;text-align:center}
.pp-name{font-size:14px;font-weight:700;color:var(--bright);margin-bottom:3px}
.pp-info{font-size:11px;color:var(--muted)}

/* Auction */
.lot-card{padding:11px 0;border-bottom:1px solid var(--border2)}
.lot-card:last-child{border:none}
.lot-name{font-size:13px;font-weight:600;color:var(--bright);margin-bottom:3px}
.lot-meta{font-size:11px;color:var(--muted);display:flex;gap:10px;margin-bottom:6px}
.lot-bid{font-size:15px;font-weight:700;color:var(--gold);font-variant-numeric:tabular-nums}

/* Duels */
.duel-card{padding:11px 0;border-bottom:1px solid var(--border2)}
.duel-card:last-child{border:none}
.duel-vs{font-size:13px;color:var(--bright)}
.duel-stake{font-size:12px;color:var(--gold)}
.duel-result{font-size:12px}
.duel-result.win{color:var(--green)}
.duel-result.lose{color:var(--red)}

/* Pets */
.pcard{display:flex;align-items:flex-start;gap:10px;padding:11px 0;
       border-bottom:1px solid var(--border2)}
.pcard:last-child{border:none}
.pcol{flex:1;min-width:0}
.pn{font-size:13px;font-weight:600;color:var(--bright)}
.ps{font-size:11px;color:var(--muted);margin-top:1px}
.fat-bar{height:4px;background:var(--dim);border-radius:2px;margin:6px 0 4px}
.fat-fill{height:100%;border-radius:2px;transition:.4s}

/* Exp */
.exp-card{background:var(--s);border-radius:var(--r);padding:12px;margin-bottom:8px;
          border:1px solid var(--border2);border-left:2px solid var(--teal)}
.exp-timer{font-size:22px;font-weight:700;color:var(--teal);font-family:monospace;font-variant-numeric:tabular-nums}
.exp-timer.urgent{color:var(--red);animation:pulse 1s infinite}

/* Top */
.trow{display:flex;align-items:center;padding:8px 0;border-bottom:1px solid var(--border2)}
.trow:last-child{border:none}
.tpos{width:28px;font-size:15px;text-align:center;flex-shrink:0}
.tname{font-size:13px;flex:1;padding:0 8px}
.tcnt{font-size:12px;color:var(--gold);font-weight:600;font-variant-numeric:tabular-nums}

/* Shop & inventory */
.inv-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.icard{background:var(--s);border-radius:var(--r);padding:12px;cursor:pointer;
       border:1px solid var(--border2);transition:.15s;position:relative}
.icard:hover{border-color:var(--border)}
.icard .iname{font-size:12px;font-weight:600;color:var(--bright);margin-bottom:4px}
.icard .iqty{font-size:22px;font-weight:700;color:var(--gold)}
.icard .idesc{font-size:10px;color:var(--muted);margin-top:4px;line-height:1.4}
.icard .icat{position:absolute;top:7px;right:7px;font-size:9px;padding:2px 5px;
             border-radius:3px;background:var(--dim);color:var(--muted)}

.shop-row{display:flex;align-items:center;gap:10px;padding:10px 0;
          border-bottom:1px solid var(--border2)}
.shop-row:last-child{border:none}

/* Quests */
.qitem{padding:10px 0;border-bottom:1px solid var(--border2)}
.qitem:last-child{border:none}
.qbar{height:5px;background:var(--dim);border-radius:3px;margin:6px 0 3px}
.qfill{height:100%;border-radius:3px;background:var(--gold);transition:.4s}

/* Gacha */
.spin-row{display:flex;align-items:center;gap:10px;padding:11px;
          background:var(--s);border-radius:var(--r);border:1px solid var(--border2);
          cursor:pointer;transition:.15s;margin-bottom:7px}
.spin-row:hover{border-color:var(--border)}
.spin-res{background:var(--s);border:1px solid var(--gold);border-radius:var(--r);
          padding:14px;margin-top:10px;animation:slideUp .2s ease}

/* Buttons */
.btn{padding:8px 14px;border-radius:var(--r);border:none;cursor:pointer;font-family:inherit;
     font-size:12px;font-weight:600;transition:.15s;display:inline-flex;align-items:center;gap:5px}
.btn-gold{background:var(--gold-dim);color:var(--gold2);border:1px solid var(--border)}
.btn-gold:hover{background:rgba(201,168,76,.22)}
.btn-ghost{background:transparent;color:var(--muted);border:1px solid var(--border2)}
.btn-red{background:rgba(224,82,82,.12);color:var(--red);border:1px solid rgba(224,82,82,.25)}
.btn-green{background:rgba(82,179,96,.12);color:var(--green);border:1px solid rgba(82,179,96,.25)}
.btn-teal{background:rgba(63,184,175,.12);color:var(--teal);border:1px solid rgba(63,184,175,.25)}
.btn:disabled{opacity:.35;cursor:not-allowed}
.btn-sm{padding:5px 10px;font-size:11px}
.btn-full{width:100%;justify-content:center;margin-bottom:7px}

/* Balance row */
.balrow{display:flex;gap:7px;margin-bottom:12px}
.bal{flex:1;background:var(--s);border-radius:var(--r);padding:9px;text-align:center;border:1px solid var(--border2)}
.bal .bv{font-size:14px;font-weight:700;color:var(--bright);font-variant-numeric:tabular-nums}
.bal .bl{font-size:9px;text-transform:uppercase;letter-spacing:1px;color:var(--muted);margin-top:1px}

/* Modal — explicit centering for mobile/Telegram WebApp */
dialog{background:var(--s);border:1px solid var(--border);border-radius:var(--r-lg);
       padding:0;max-width:360px;width:calc(100% - 24px);color:var(--text);
       animation:slideUp .18s ease;
       position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);margin:0}
dialog::backdrop{background:rgba(0,0,0,.85);backdrop-filter:blur(6px)}
.mbody{padding:13px 15px;max-height:55vh;overflow-y:auto;-webkit-overflow-scrolling:touch}
.mhead{display:flex;align-items:center;justify-content:space-between;
       padding:13px 15px;border-bottom:1px solid var(--border2)}
.mtitle{font-size:14px;font-weight:700;color:var(--bright)}
.mclose{background:none;border:none;color:var(--muted);font-size:20px;cursor:pointer;padding:2px 6px;line-height:1}
/* mbody also defined above with mobile-scroll fix */
.mfoot{padding:10px 15px;border-top:1px solid var(--border2);display:flex;gap:7px;justify-content:flex-end}

/* Info row */
.irow{display:flex;justify-content:space-between;align-items:center;
      padding:5px 0;border-bottom:1px solid var(--border2);font-size:12px}
.irow:last-child{border:none}
.irow .ik{color:var(--muted)}
.irow .iv{color:var(--text)}
.divider{height:1px;background:var(--border2);margin:10px 0}

/* Food / boost options */
.fopt{display:flex;align-items:center;gap:8px;padding:9px;background:var(--card);
      border-radius:var(--r);cursor:pointer;border:1px solid var(--border2);margin-bottom:6px;transition:.15s}
.fopt:hover{border-color:var(--border)}
.fopt .fn{font-size:12px;flex:1}
.fopt .fq{font-size:11px;color:var(--muted)}
.fopt .fr{font-size:11px;font-weight:600}

/* WS toast */
.ws-notif{position:fixed;top:14px;right:12px;max-width:260px;
          background:var(--card);border:1px solid var(--border);border-radius:var(--r-lg);
          padding:12px 14px;z-index:9999;animation:popIn .2s ease;
          box-shadow:0 4px 20px rgba(0,0,0,.5)}
.ws-notif .wn-title{font-size:12px;font-weight:700;color:var(--gold2);margin-bottom:3px}
.ws-notif .wn-body{font-size:11px;color:var(--muted)}

/* Toast */
.toast{position:fixed;top:14px;left:50%;transform:translateX(-50%);
       padding:9px 16px;border-radius:99px;font-size:12px;font-weight:600;
       z-index:9998;opacity:0;transition:.25s;pointer-events:none;white-space:nowrap}
.toast.show{opacity:1}

/* Login overlay */
.login-ov{position:fixed;inset:0;background:var(--bg);z-index:200;
          display:flex;flex-direction:column;align-items:center;
          justify-content:center;gap:20px;padding:32px;text-align:center}
.login-ov h1{font-size:26px;font-weight:800;color:var(--gold2);text-shadow:0 0 30px rgba(201,168,76,.35)}
.login-ov p{color:var(--muted);font-size:13px;max-width:260px;line-height:1.5}
.login-ov.hidden{display:none}

/* Rarity badges */
.rc{font-size:10px;padding:1px 6px;border-radius:3px;font-weight:600}
.rc-common{background:rgba(90,100,128,.2);color:#6b7a99}
.rc-uncommon{background:rgba(82,179,96,.15);color:var(--green)}
.rc-rare{background:rgba(90,156,245,.15);color:var(--blue)}
.rc-epic{background:rgba(157,114,255,.15);color:var(--purple)}
.rc-legendary{background:rgba(201,168,76,.15);color:var(--gold)}
.rc-shadow{background:rgba(100,80,150,.2);color:#9080c0}

/* ── Gacha flip animation ── */
@keyframes flipIn{0%{opacity:0;transform:rotateY(-90deg) scale(.8)}100%{opacity:1;transform:rotateY(0) scale(1)}}
.spin-card{background:var(--s);border-radius:var(--r);padding:12px;margin:5px 0;
           border:1px solid var(--border2);animation:flipIn .35s ease}
.spin-card.rare{border-color:var(--blue)}
.spin-card.epic{border-color:var(--purple)}
.spin-card.legendary{border-color:var(--gold);box-shadow:0 0 10px rgba(201,168,76,.25)}

/* ── Exchange ── */
.exch-rate{text-align:center;padding:16px;background:var(--gold-dim);border-radius:var(--r);
           border:1px solid var(--border);margin-bottom:12px}
.exch-rate .er{font-size:20px;font-weight:700;color:var(--gold2)}
.exch-rate .el{font-size:11px;color:var(--muted);margin-top:3px}
.range-wrap{padding:8px 0}
.range-wrap input[type=range]{width:100%;accent-color:var(--gold)}
.num-input{width:100%;background:var(--card);border:1px solid var(--border2);
           border-radius:var(--r);padding:9px 12px;color:var(--bright);
           font-size:15px;font-family:inherit;margin:8px 0}
.num-input:focus{border-color:var(--border);outline:none}
</style>
</head>
<body>
<div id="toast" class="toast"></div>

<div id="login-ov" class="login-ov hidden">
  <div style="font-size:52px;animation:glow 2s infinite">🔮</div>
  <h1>Предвестник</h1>
  <p>Войдите через Telegram для доступа к игровому профилю.</p>
  <div id="tg-login-widget">
    <!-- Widget script here so Telegram renders the button in this exact location -->
    <script src="https://telegram.org/js/telegram-widget.js?22"
            data-telegram-login="{{BOT_USERNAME}}" data-size="large" data-radius="8"
            data-onauth="onTelegramWidgetAuth(user)" data-request-access="write"></script>
  </div>
  <p style="font-size:10px;color:var(--dim)">Данные защищены подписью Telegram.</p>
</div>

<dialog id="modal">
  <div class="mhead"><span id="mt" class="mtitle"></span><button class="mclose" onclick="CM()">✕</button></div>
  <div id="mb" class="mbody"></div>
  <div id="mf" class="mfoot"></div>
</dialog>

<!-- 1. Профиль -->
<div id="pg-profile" class="page active">
  <div class="tabs" style="flex-wrap:wrap;gap:4px">
    <button class="tb active" onclick="switchPro('main',this)">👤 Профиль</button>
    <button class="tb" onclick="switchPro('streak',this)">🔥 Стрик</button>
    <button class="tb" onclick="switchPro('ach',this)">🏆 Ачивки</button>
    <button class="tb" onclick="switchPro('marriage',this)">💍 Брак</button>
    <button class="tb" onclick="switchPro('wallet',this)">💰 Кошелёк</button>
  </div>
  <div id="pro-main"><div class="sk" style="height:120px;border-radius:var(--r);margin-bottom:8px"></div><div class="sk" style="height:60px;border-radius:var(--r)"></div></div>
  <div id="pro-streak" style="display:none"></div>
  <div id="pro-ach" style="display:none"></div>
  <div id="pro-marriage" style="display:none"></div>
  <div id="pro-wallet" style="display:none"></div>
</div>

<!-- 2. Зоопарк -->
<div id="pg-zoo" class="page">
  <div id="zoo-exp-wrap"></div>
  <div class="tabs">
    <button class="tb active" onclick="swZoo('nursery',this)">🐾 В питомнике</button>
    <button class="tb" onclick="swZoo('storage',this)">📦 Склад</button>
    <button class="tb" onclick="swZoo('guide',this)">📖 Справка</button>
  </div>
  <div id="zoo-c" class="loader">Загрузка...</div>
</div>

<!-- 3. Арена -->
<div id="pg-arena" class="page">
  <div class="tabs">
    <button class="tb active" onclick="swArena('quests',this)">📋 Квесты</button>
    <button class="tb" onclick="swArena('gacha',this)">🎲 Гача</button>
    <button class="tb" onclick="swArena('craft',this)">⚗️ Крафт</button>
    <button class="tb" onclick="swArena('duels',this)">⚔️ Дуэли</button>
    <button class="tb" onclick="swArena('dark',this)">🌑 Тёмная</button>
  </div>
  <div id="ar-quests"><div id="qc" class="loader">Загрузка...</div></div>
  <div id="ar-gacha" style="display:none"><div id="gc" class="loader">Загрузка...</div></div>
  <div id="ar-craft" style="display:none"><div id="cc" class="loader">Загрузка...</div></div>
  <div id="ar-duels" style="display:none"><div id="dc" class="loader">Загрузка...</div></div>
  <div id="ar-dark" style="display:none"><div id="dkc"></div></div>
</div>

<!-- 4. Рынок -->
<div id="pg-market" class="page">
  <div class="tabs" style="flex-wrap:wrap;gap:4px">
    <button class="tb active" onclick="swMkt('auc',this)">🏛 Аукцион</button>
    <button class="tb" onclick="swMkt('shop',this)">🛒 Магазин</button>
    <button class="tb" onclick="swMkt('inv',this)">🎒 Инвентарь</button>
    <button class="tb" onclick="swMkt('exch',this)">💱 Обмен</button>
    <button class="tb" onclick="swMkt('deal',this)">🏷 Акция</button>
    <button class="tb" onclick="swMkt('promo',this)">🎫 Промо</button>
  </div>
  <div id="balrow" class="balrow" style="display:none"></div>
  <div id="mkt-auc"><div class="loader">Загрузка...</div></div>
  <div id="mkt-shop" style="display:none"></div>
  <div id="mkt-inv" style="display:none"></div>
  <div id="mkt-exch" style="display:none"><div class="loader">Загрузка...</div></div>
  <div id="mkt-deal" style="display:none"><div class="loader">Загрузка...</div></div>
  <div id="mkt-promo" style="display:none"></div>
</div>

<!-- 5. Коллекция -->
<div id="pg-coll" class="page">
  <div class="tabs">
    <button class="tb active" onclick="swColl('themes',this)">🎨 Темы</button>
    <button class="tb" onclick="swColl('top',this)">🏆 Топ</button>
  </div>
  <div id="col-themes"><div class="loader">Загрузка...</div></div>
  <div id="col-top" style="display:none">
    <div class="tabs" style="margin-top:4px">
      <button class="tb active" onclick="switchTop('local',this)">🏘 Чат</button>
      <button class="tb" onclick="switchTop('global',this)">🌍 Глобально</button>
    </div>
    <div id="top-c" class="loader">Загрузка...</div>
  </div>
</div>

<nav class="nav">
  <div class="nb active" onclick="switchPage('profile',this)"><span class="ni">👤</span>Профиль</div>
  <div class="nb" onclick="switchPage('zoo',this)"><span class="ni">🐾</span>Зоопарк</div>
  <div class="nb" onclick="switchPage('arena',this)"><span class="ni">⚔️</span>Арена</div>
  <div class="nb" onclick="switchPage('market',this)"><span class="ni">🏛</span>Рынок</div>
  <div class="nb" onclick="switchPage('coll',this)"><span class="ni">🎨</span>Коллекция</div>
  <div class="nb" onclick="refreshPage()" style="max-width:40px"><span class="ni">🔄</span></div>
</nav>

<script>
const tg = window.Telegram?.WebApp;
if (tg) { tg.ready(); tg.expand(); }  // setHeaderColor removed — deprecated in TG WebApp v6.0

const BASE = (location.origin + location.pathname).replace(/[/]$/, '');

// el() defined here — BEFORE any usage to avoid TDZ ReferenceError
const el = id => document.getElementById(id);
const INIT_DATA = tg?.initData || '';
const SK = 'pv_sess';
const MEDALS = ['🥇','🥈','🥉'];
const PL = {active:'Активный',passive:'Пассивный',storage:'Склад'};
const RC = {common:'rc-common',uncommon:'rc-uncommon',rare:'rc-rare',
            epic:'rc-epic',legendary:'rc-legendary',shadow:'rc-shadow'};

// Chat where the mini app was opened from (from Telegram WebApp context)
const _tgChat = tg?.initDataUnsafe?.chat || null;
const _initChatId = _tgChat?.id || 0;   // primary chat_id for local top
const _initChatTitle = _tgChat?.title || '';

let _cid = 0, _uid = 0, _actTab='quests', _zooTab='nursery', _arenaTab='quests';
let _zooData=null, _invData=[], _expTimer=null, _themeData=null, _mktTab='auc';
let _proTab='main', _profileData=null;

// ── Auth ──────────────────────────────────────────────────────────────────────
const sess = () => localStorage.getItem(SK)||'';
const hdrs = () => {
  const h={'content-type':'application/json'};
  if (INIT_DATA) h['x-init-data']=INIT_DATA;
  if (sess()) h['x-session-token']=sess();
  return h;
};
function api(path, opts={}) {
  return fetch(BASE+path,{...opts,headers:{...hdrs(),...(opts.headers||{})}})
    .then(r=>{
      if(r.status===401){localStorage.removeItem(SK);el('login-ov').classList.remove('hidden');return Promise.reject('Войдите снова.');}
      return r.ok?r.json():r.json().then(e=>Promise.reject(e.detail||'Ошибка'));
    });
}
window.onTelegramWidgetAuth = u => {
  api('/auth/telegram-login',{method:'POST',body:JSON.stringify(u)})
    .then(d=>{localStorage.setItem(SK,d.session_token);_uid=d.user_id||0;el('login-ov').classList.add('hidden');loadProfile();connectWS();})
    .catch(e=>alert('Ошибка: '+e));
};
if (!INIT_DATA && !sess()) el('login-ov').classList.remove('hidden');

// ── WebSocket ─────────────────────────────────────────────────────────────────
let _ws=null;
function connectWS() {
  if (!_uid) return;
  const wsUrl = BASE.replace('https://','wss://').replace('http://','ws://') + '/ws/'+_uid;
  _ws = new WebSocket(wsUrl);
  _ws.onmessage = e => showWsNotif(JSON.parse(e.data));
  _ws.onclose = () => { setTimeout(connectWS, 4000); };
  _ws.onerror = () => {};
}
function showWsNotif(event) {
  const titles = {
    expedition_done: '⚔️ Поход завершён!',
    quest_done: '✅ Квест выполнен!',
    duel_challenge: '⚔️ Вызов на дуэль!',
  };
  const bodies = {
    expedition_done: e => `${e.pet} вернулся: +${fmt(e.mora)} 🪙 +${e.xp} XP`,
    quest_done: e => `«${e.quest}» — получено!`,
    duel_challenge: e => `@${e.from} ставка ${fmt(e.stake)} 🪙 · Ответьте в чате: бот принять`,
  };
  // Play sound for duel challenge
  if(event.type === 'duel_challenge') {
    if('vibrate' in navigator) navigator.vibrate([200, 100, 200]);
    browserNotif('⚔️ Вызов на дуэль!', bodies.duel_challenge(event));
    // Auto-reload duels if on arena page
    if(_loaded.has('arena') && _arenaTab === 'duels') loadDuels();
  }
  const div = document.createElement('div');
  div.className = 'ws-notif';
  div.innerHTML = `<div class="wn-title">${titles[event.type]||'🔮 Уведомление'}</div>
                   <div class="wn-body">${(bodies[event.type]||(() => ''))(event)}</div>`;
  document.body.appendChild(div);
  setTimeout(() => div.remove(), 5000);
  if (_loaded.has('zoo') && event.type === 'expedition_done') { _zooData=null; loadZoo(); }
}

// ── Utils ─────────────────────────────────────────────────────────────────────
const fmt = n => Number(n).toLocaleString('ru');
const fatC = f => f<40?'var(--green)':f<70?'var(--gold)':'var(--red)';
function rc(r) { return `<span class="rc ${RC[r]||'rc-common'}">${r}</span>`; }

function toast(msg,ok=true) {
  const t=el('toast');
  t.textContent=msg;
  t.style.cssText=`background:${ok?'rgba(82,179,96,.9)':'rgba(224,82,82,.9)'};color:#fff;border:1px solid ${ok?'rgba(82,179,96,.5)':'rgba(224,82,82,.5)'}`;
  t.classList.add('show');
  setTimeout(()=>t.classList.remove('show'),2500);
}

function countdown(endsAt) {
  const ends=new Date((endsAt+'').includes('T')?endsAt:endsAt+'Z');
  const diff=Math.max(0,Math.floor((ends-Date.now())/1000));
  if(diff<=0)return'<span style="color:var(--green)">Готово ✓</span>';
  const h=Math.floor(diff/3600),m=Math.floor((diff%3600)/60),s=diff%60;
  const str=h?`${h}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`:`${m}:${String(s).padStart(2,'0')}`;
  return `<span class="exp-timer${diff<300?' urgent':''}">${str}</span>`;
}

// ── Modal ─────────────────────────────────────────────────────────────────────
function OM(title,body,btns=[]) {
  el('mt').textContent=title;
  el('mb').innerHTML=body;
  el('mf').innerHTML=btns.map(b=>`<button class="btn btn-sm ${b.c||'btn-ghost'}" onclick="${b.f}" ${b.d?'disabled':''}>${b.l}</button>`).join('');
  el('modal').showModal();
}
const CM=()=>el('modal').close();
el('modal').addEventListener('click',e=>{if(e.target===el('modal'))CM();});

// ── Navigation ────────────────────────────────────────────────────────────────
const _loaded=new Set();
function switchPage(name,btn) {
  document.querySelectorAll('.page').forEach(p=>p.classList.remove('active'));
  document.querySelectorAll('.nb').forEach(b=>b.classList.remove('active'));
  el('pg-'+name).classList.add('active');
  btn.classList.add('active');
  if(!_loaded.has(name)){
    _loaded.add(name);
    ({zoo:loadZoo,arena:loadArena,market:loadMarket,coll:loadColl}[name]||(() => {}))();
  }
}

// ── Profile ───────────────────────────────────────────────────────────────────
function switchPro(tab,btn) {
  _proTab=tab;
  document.querySelectorAll('#pg-profile .tb').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');
  ['main','streak','ach'].forEach(t=>el('pro-'+t).style.display=t===tab?'':'none');
  if(tab==='streak')loadStreak();
  else if(tab==='ach')loadAch();
}

function loadProfile() {
  el('pro-main').innerHTML='<div class="sk" style="height:120px;border-radius:var(--r);margin-bottom:8px"></div><div class="sk" style="height:60px;border-radius:var(--r)"></div>';
  api('/profile/me').then(d=>{
    if(!d || typeof d !== 'object') throw new Error('Неверный формат ответа сервера');
    _cid = d.chats?.[0]?.chat_tg_id || 0;
    if(d.user_id) _uid = d.user_id;
    _profileData = d;
    const pets=d.pets.filter(p=>p.placement!=='storage').slice(0,3);
    el('pro-main').innerHTML=`
      <div class="card card-gold">
        <div class="phead">
          <div class="ava">🔮</div>
          <div><div class="pname">@${d.username||'Игрок'}</div><div class="prank">${d.rank}</div></div>
        </div>
        <div class="stats">
          <div class="stat"><div>🪙</div><div class="sv">${fmt(d.mora)}</div><div class="sl">Мора</div></div>
          <div class="stat"><div>💎</div><div class="sv">${d.diamonds.toFixed(1)}</div><div class="sl">Алмазы</div></div>
          <div class="stat"><div>🔥</div><div class="sv">${d.streak}</div><div class="sl">Стрик</div></div>
          <div class="stat"><div>🏆</div><div class="sv">${d.achievements}</div><div class="sl">Ачивки</div></div>
        </div>
      </div>
      ${pets.length?`<div class="card"><div class="card-title">🐾 Питомники</div>${pets.map(p=>`
        <div class="pcard"><div class="pcol">
          <div class="pn">${p.name||p.species_id} ${rc(p.rarity)}</div>
          <div class="ps">Lv${p.pet_level} · ${PL[p.placement]}</div>
          <div class="fat-bar"><div class="fat-fill" style="width:${p.fatigue}%;background:${fatC(p.fatigue)}"></div></div>
        </div></div>`).join('')}</div>`:''}
      ${d.chats.length?`<div class="card"><div class="card-title">💬 Активность</div>${d.chats.map(c=>`<div class="irow"><span class="ik">${c.chat_title||'Чат'}</span><span class="iv">Lv${c.user_level} · ${fmt(c.user_messages_count_all_time)}</span></div>`).join('')}</div>`:''}`;
    if(!_ws && _uid) connectWS();
  }).catch(e=>{el('pro-main').innerHTML=`<div style="color:var(--red);padding:20px;font-size:12px">${typeof e==='string'?e:'Напишите боту чтобы создать профиль.'}</div>`;});
}
if(INIT_DATA||sess()){loadProfile();_loaded.add('profile');}

function loadStreak() {
  el('pro-streak').innerHTML='<div class="loader">Загрузка...</div>';
  api('/streak/calendar').then(d=>{
    const today=new Date().toISOString().slice(0,10);
    el('pro-streak').innerHTML=`<div class="card card-gold">
      <div style="text-align:center">
        <div style="font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:1px">Текущий стрик</div>
        <div class="streak-num">${d.streak} 🔥</div>
        <div style="font-size:11px;color:var(--muted)">дней подряд</div>
      </div>
      <div class="divider"></div>
      <div class="card-title">Последние 60 дней</div>
      <div class="cal">${d.calendar.map(day=>`<div class="cal-day${day.active?' on':''}${day.date===today?' today':''}" title="${day.date}: ${day.count} сообщ."></div>`).join('')}</div>
      <div style="display:flex;gap:10px;margin-top:8px;font-size:10px;color:var(--muted)">
        <span>⬜ Нет активности</span><span style="color:var(--green)">■ Есть активность</span>
      </div>
    </div>`;
  }).catch(e=>{el('pro-streak').innerHTML=`<div style="color:var(--red);padding:10px;font-size:12px">${e}</div>`;});
}

// What each achievement tracks and how to earn it
const ACH_HOW = {
  egg_opener:  {how:'Открывайте яйца питомцев',     where:'Инвентарь → нажмите на яйцо'},
  gacha_addict:{how:'Крутите гачу',                  where:'Арена → Гача'},
  collector:   {how:'Получайте новые виды питомцев', where:'Открывайте яйца — каждый новый вид'},
  trainer:     {how:'Прокачивайте питомцев до Lv10', where:'Открывайте дубликаты одного вида'},
  wanderer:    {how:'Отправляйте питомцев в походы', where:'Зоопарк → питомец → команда бота'},
  persistent:  {how:'Поддерживайте ежедневный стрик',where:'Пишите в бот каждый день'},
  vow_keeper:  {how:'Состоите в браке',              where:'бот брак — оформить брак'},
  patron:      {how:'Тратьте Мору в магазине',       where:'Рынок → Магазин'},
  magnate:     {how:'Накапливайте Мору',             where:'Автоматически от баланса'},
  treasury:    {how:'Накапливайте Алмазы',           where:'Автоматически от баланса'},
  dealer:      {how:'Продавайте лоты на аукционе',   where:'Рынок → Аукцион → выставить лот'},
  lucky_one:   {how:'Побеждайте в мини-играх',       where:'бот кости / монета / рулетка'},
  duelist:     {how:'Побеждайте в дуэлях',           where:'бот дуэль в чате'},
  talker:      {how:'Пишите сообщения в боте',       where:'Любой чат с ботом — просто общайтесь'},
  star:        {how:'Будьте топ-1 в чате за неделю', where:'Пишите активнее всех в чате'},
};

function loadAch() {
  el('pro-ach').innerHTML='<div class="loader">Загрузка...</div>';
  api('/achievements/').then(achs=>{
    el('pro-ach').innerHTML='<div class="card"><div class="card-title">Достижения (нажмите для деталей)</div>'+
      achs.map(a=>{
        const hw=ACH_HOW[a.id]||{};
        return `<div class="ach-item" style="cursor:pointer" onclick="openAchModal(${JSON.stringify(a).replace(/"/g,"'")})">
          <div class="ach-head">
            <div class="ach-icon">${a.icon}</div>
            <div class="ach-name">${a.name}</div>
            <div class="ach-lvl" style="color:${a.completed?'var(--gold)':a.level>0?'var(--green)':'var(--muted)'}">
              ${a.completed?'★ MAX':a.level>0?`Lv${a.level}`:'—'}
            </div>
          </div>
          <div style="font-size:10px;color:var(--muted);margin-bottom:5px">${hw.how||''}</div>
          <div class="ach-bar"><div class="ach-fill" style="width:${a.pct}%"></div></div>
          <div class="ach-prog">${fmt(a.progress)} / ${fmt(a.next_threshold||a.progress)}${a.completed?' ✅':''}</div>
        </div>`;
      }).join('')+'</div>';
  }).catch(e=>{el('pro-ach').innerHTML=`<div style="color:var(--red);padding:10px;font-size:12px">${e}</div>`;});
}

function openAchModal(a) {
  const hw=ACH_HOW[a.id]||{};
  const rw=a.next_reward||{};
  const rwParts=[rw.mora&&`+${fmt(rw.mora)} 🪙`,rw.diamonds&&`+${rw.diamonds} 💎`].filter(Boolean).join(', ');
  OM(`${a.icon} ${a.name}`,`
    <div style="text-align:center;padding:8px 0 14px">
      <div style="font-size:28px;font-weight:800;color:${a.completed?'var(--gold)':'var(--text)'}">
        ${a.completed?'★ МАКСИМУМ':`Lv${a.level} / ${a.max_level}`}
      </div>
      <div class="ach-bar" style="height:8px;margin:10px 0 4px">
        <div class="ach-fill" style="width:${a.pct}%"></div>
      </div>
      <div style="font-size:12px;color:var(--muted)">${fmt(a.progress)} / ${fmt(a.next_threshold||a.progress)}</div>
    </div>
    <div class="divider"></div>
    <div class="irow"><span class="ik">Что нужно делать</span><span style="color:var(--text);text-align:right;max-width:60%">${hw.how||'—'}</span></div>
    <div class="irow"><span class="ik">Где делать</span><span style="color:var(--teal);text-align:right;max-width:60%">${hw.where||'—'}</span></div>
    ${!a.completed&&rwParts?`<div class="irow"><span class="ik">Награда Lv${a.level+1}</span><span style="color:var(--gold)">${rwParts}</span></div>`:''}
    ${a.completed?`<div style="text-align:center;padding:10px;color:var(--gold);font-size:13px;font-weight:600">🏆 Достижение полностью выполнено!</div>`:''}
  `,[{l:'Закрыть',c:'btn-ghost',f:'CM()'}]);
}

// ── Zoo ───────────────────────────────────────────────────────────────────────
function loadZoo() {
  Promise.all([api('/zoo/'),api('/zoo/expeditions')]).then(([data,expData])=>{
    _zooData=data;
    renderExps(expData);
    renderZoo(_zooTab);
  }).catch(e=>{el('zoo-c').innerHTML=`<div style="color:var(--red);font-size:12px;padding:10px">${e}</div>`;});
}
function renderExps(d) {
  if(_expTimer)clearInterval(_expTimer);
  const w=el('zoo-exp-wrap');
  if(!d.expeditions.length){w.innerHTML='';return;}
  const boo=d.boosters;
  w.innerHTML=d.expeditions.map(e=>`<div class="exp-card">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
      <div style="font-size:13px;font-weight:600;color:var(--bright)">${e.name} <span style="font-size:11px;color:var(--muted)">· ${e.duration_hours}ч</span></div>
      <div id="tm-${e.pet_id}">${countdown(e.ends_at)}</div>
    </div>
    ${Object.keys(boo).length?`<div style="padding-top:8px;border-top:1px solid var(--border2)">
      ${Object.entries(boo).map(([bid,b])=>`<div class="fopt" onclick="boostExp(${e.pet_id},'${bid}',this)">
        <span style="font-size:16px">⏩</span>
        <span class="fn">${b.name}</span><span class="fq">×${b.qty}</span>
        <span class="fr" style="color:var(--teal)">−${b.boost_hours}ч</span>
      </div>`).join('')}
    </div>`:''}
  </div>`).join('');
  _expTimer=setInterval(()=>d.expeditions.forEach(e=>{const t=el('tm-'+e.pet_id);if(t)t.innerHTML=countdown(e.ends_at);}),1000);
}
// ── Zoo helpers ───────────────────────────────────────────────────────────────
function bonusLines(sid, b) {
  const p = v => `${(v*100).toFixed(0)}%`, ln = [];
  ({
    hamster: b => { ln.push(`🪙 ${b.mora_per_hour}/ч · Кап ${b.cap}`);
      if(b.ignore_exhaustion) ln.push('✅ Копит при 100% усталости');
      if(b.double_chance>0) ln.push(`🎲 Шанс ×2: ${p(b.double_chance)}`);
      if(b.daily_diamond>0) ln.push(`💎 +${b.daily_diamond}/день`); },
    owl: b => { ln.push(`📚 +${b.bonus_xp} XP каждые ${b.trigger_every_n_msg} сообщ.`);
      if(b.expedition_xp_bonus>0) ln.push(`🗺 +${p(b.expedition_xp_bonus)} XP похода`);
      if(b.weekend_double) ln.push('✅ ×2 XP в выходные');
      if(b.daily_free_spin_token) ln.push('🎟 Жетон/день'); },
    dog: b => { ln.push(`⏱ −${p(b.speed_reduction)} время похода`);
      if(b.self_fatigue_reduction>0) ln.push(`💪 Пёс: −${p(b.self_fatigue_reduction)} усталости`);
      if(b.zero_fatigue_chance>0) ln.push(`🍀 0 усталости: ${p(b.zero_fatigue_chance)}`);
      if(b.expedition_cost_reduction>0) ln.push(`💰 −${p(b.expedition_cost_reduction)} стоимость`); },
    turtle: b => { if(b.shop_discount>0) ln.push(`🛒 −${p(b.shop_discount)} магазин`);
      if(b.expedition_discount>0) ln.push(`🗺 −${p(b.expedition_discount)} поход`);
      if(b.gacha_daily_discount>0) ln.push(`🏷 −${p(b.gacha_daily_discount)} акция дня`);
      if(b.double_egg_chance>0) ln.push(`🥚 ×2 яйцо: ${p(b.double_egg_chance)}`); },
    falcon: b => { ln.push(`💰 +${p(b.mora_bonus)} Мора похода`);
      if(b.xp_bonus>0) ln.push(`📚 +${p(b.xp_bonus)} XP`);
      if(b.double_loot_chance>0) ln.push(`🎁 Двойной лут: ${p(b.double_loot_chance)}`);
      if(b.capstone_8h_treasure_map) ln.push('🗺 Карта сокровищ (8ч, гарант.)'); },
    wolf: b => { if(b.passive_reduction>0) ln.push(`😴 Пасс. −${p(b.passive_reduction)}/день`);
      if(b.active_reduction>0) ln.push(`⚔️ Актив. −${p(b.active_reduction)}/день`);
      if(b.food_extra>0) ln.push(`🍖 Корм +${b.food_extra} ед.`);
      if(b.daily_restore_uses>0) ln.push(`♻️ ${b.daily_restore_uses}×/день +${b.daily_restore_amount} ед.`);
      if(b.movement_immunity) ln.push('✅ Бесплатное перемещение'); },
    fox: b => { if(b.diamond_chance_per_2h>0) ln.push(`💎 Алмаз каждые 2ч: ${p(b.diamond_chance_per_2h)}`);
      if(b.common_dup_bonus>0) ln.push(`🐾 +${p(b.common_dup_bonus)} Common дубли`);
      if(b.weekly_guaranteed_diamond) ln.push('✅ Гарант. 💎/неделю');
      if(b.crystal_egg_chance>0) ln.push(`🔷 Кристальное яйцо: ${p(b.crystal_egg_chance)}`); },
    dragon: b => { ln.push(`🏦 Кап банка: +${fmt(b.bank_bonus)} 🪙`);
      if(b.free_food_chance>0) ln.push(`🍖 Бесплатный корм: ${p(b.free_food_chance)}`);
      if(b.hamster_collect_bonus>0) ln.push(`🐹 Хомяк +${b.hamster_collect_bonus}`);
      if(b.weekly_bank_grant>0) ln.push(`💰 +${b.weekly_bank_grant} в банк/нед.`); },
    unicorn: b => { ln.push(`😴 −${p(b.daily_fatigue_reduction)}/день всем`);
      if(b.immunity_uses>0) ln.push(`🛡 ${b.immunity_uses}×/день иммун. ${b.immunity_hours}ч`);
      if(b.active_recovery_per_hour>0) ln.push(`♻️ +${b.active_recovery_per_hour} ед./ч`);
      if(b.auto_recover) ln.push('✅ Авто-восст. при 100%'); },
  }[sid]||(() => {}))(b);
  return ln;
}

function petCard(p) {
  const fatPct = p.fatigue || 0;
  const nursery = p.placement !== 'storage';
  const placeBadge = p.placement === 'active'
    ? '<span style="color:var(--teal);font-size:10px">⚔️ Активный</span>'
    : p.placement === 'passive'
    ? '<span style="color:var(--blue);font-size:10px">🛡 Пассивный</span>'
    : '<span style="color:var(--muted);font-size:10px">📦 Склад</span>';
  return `<div class="pcard" style="cursor:pointer" onclick="openPetModal(${p.id})">
    <div class="pcol">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:2px">
        <div class="pn">${p.name||p.species_id} ${rc(p.rarity)}</div>
        ${placeBadge}
      </div>
      <div class="ps">Lv${p.pet_level||1} · ${p.duplicates_collected||0} дубл.</div>
      <div class="fat-bar"><div class="fat-fill" style="width:${fatPct}%;background:${fatC(fatPct)}"></div></div>
      <div style="font-size:10px;color:var(--muted)">${fatPct}% усталости</div>
    </div>
  </div>`;
}

function swZoo(tab,btn) {
  _zooTab=tab;
  document.querySelectorAll('#pg-zoo .tb').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');
  if(!_zooData){loadZoo();return;}
  renderZoo(tab);
}

function renderZoo(tab) {
  if(tab==='guide'){renderZooGuide();return;}
  if(!_zooData)return;
  let pets;
  if(tab==='nursery') pets=_zooData.pets.filter(p=>p.placement!=='storage');
  else pets=_zooData.pets.filter(p=>p.placement==='storage');

  if(!pets.length){
    el('zoo-c').innerHTML=`<div style="color:var(--muted);font-size:13px;text-align:center;padding:24px">
      ${tab==='nursery'?'Питомников нет. Посадите питомца из склада.':'Склад пустой.'}
    </div>`;
    return;
  }

  if(tab==='nursery'){
    const active=pets.filter(p=>p.placement==='active');
    const passive=pets.filter(p=>p.placement==='passive');
    let html='';
    if(active.length) html+=`<div class="card-title" style="margin:8px 0 4px">⚔️ Активные (${active.length})</div>${active.map(petCard).join('')}`;
    if(passive.length) html+=`<div class="card-title" style="margin:12px 0 4px">🛡 Пассивные (${passive.length})</div>${passive.map(petCard).join('')}`;
    el('zoo-c').innerHTML=html;
  } else {
    el('zoo-c').innerHTML=pets.map(petCard).join('');
  }
}

// Full pet modal
function openPetModal(petId) {
  OM('🐾 Питомец', '<div class="loader">Загрузка...</div>', []);
  api(`/zoo/pet/${petId}`).then(p=>{
    const fatPct = p.fatigue||0;
    const lvl = p.pet_level||1;
    const dups = p.duplicates_collected||0;
    const toNext = p.dups_for_next_level||0;

    // Current bonus lines
    const curBonus = bonusLines(p.species_id, p.current_bonus||{});
    const bonusHtml = curBonus.length
      ? curBonus.map(l=>`<div style="font-size:11px;color:var(--text);padding:3px 0">• ${l}</div>`).join('')
      : '<div style="font-size:11px;color:var(--muted)">Нет активных бонусов</div>';

    // Level progression (show tiers)
    const tiers = p.levels ? [1,4,8,10].map(lv=>{
      const tier = p.levels.find(t=>t.level===lv);
      if(!tier) return '';
      const tlines = bonusLines(p.species_id, tier.bonus||{});
      const isUnlocked = lv<=lvl;
      const isCurrent = lv===lvl;
      const color = isUnlocked ? (isCurrent?'var(--gold)':'var(--green)') : 'var(--dim)';
      return `<div style="padding:8px;border-radius:var(--r);background:${isCurrent?'rgba(201,168,76,.1)':'var(--s)'};
              border:1px solid ${isCurrent?'var(--border)':'var(--border2)'};margin-bottom:6px">
        <div style="font-size:11px;font-weight:700;color:${color};margin-bottom:4px">
          ${isUnlocked?'✓':'○'} Lv${lv}${lv===4?' (Уровень 2)':lv===8?' (Уровень 3)':lv===10?' ★ Финал':''}
          ${tier.milestone?` — 🎁 ${tier.milestone.mora?'+'+fmt(tier.milestone.mora)+' 🪙':''} ${tier.milestone.diamonds?'+'+tier.milestone.diamonds+' 💎':''}`:'' }
        </div>
        ${tlines.map(l=>`<div style="font-size:10px;color:${isUnlocked?'var(--muted)':'var(--dim)'};padding:1px 0">• ${l}</div>`).join('')}
      </div>`;
    }).join('') : '';

    // Food options
    const foodHtml = Object.entries(p.available_food||{}).length
      ? Object.entries(p.available_food).map(([fid,f])=>`
          <div class="fopt" onclick="doFeed(${petId},'${fid}',this)">
            <span class="fn">${f.name}</span>
            <span class="fq">×${f.qty}</span>
            <span class="fr" style="color:var(--green)">−${f.restore} уст.</span>
          </div>`)
        .join('')
      : '<div style="font-size:11px;color:var(--muted);padding:5px">Корма нет — купите в Магазине.</div>';

    const body = `
      <div style="text-align:center;padding:10px 0 14px">
        <div style="font-size:22px;margin-bottom:4px">${p.species_name||p.name}</div>
        <div>${rc(p.rarity)} <span style="font-size:11px;color:var(--muted)">${PL[p.placement]||p.placement}</span></div>
        <div style="font-size:11px;color:var(--muted);margin-top:6px;line-height:1.4">${p.species_desc||''}</div>
      </div>
      <div class="divider"></div>

      <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:12px">
        <div style="background:var(--s);border-radius:var(--r);padding:10px;text-align:center">
          <div style="font-size:20px;font-weight:700;color:var(--gold)">${lvl}<span style="font-size:12px">/10</span></div>
          <div style="font-size:10px;color:var(--muted)">Уровень</div>
        </div>
        <div style="background:var(--s);border-radius:var(--r);padding:10px;text-align:center">
          <div style="font-size:20px;font-weight:700;color:var(--text)">${dups}</div>
          <div style="font-size:10px;color:var(--muted)">Дубликатов</div>
        </div>
      </div>

      <div style="margin-bottom:12px">
        <div style="font-size:10px;color:var(--muted);margin-bottom:6px;display:flex;justify-content:space-between">
          <span>УСТАЛОСТЬ</span>
          <span style="color:${fatC(fatPct)}">${fatPct}%</span>
        </div>
        <div class="fat-bar" style="height:8px"><div class="fat-fill" style="width:${fatPct}%;background:${fatC(fatPct)}"></div></div>
        ${lvl<10?`<div style="font-size:10px;color:var(--muted);margin-top:5px">До Lv${lvl+1}: ещё ${toNext} дублик.</div>`:'<div style="font-size:10px;color:var(--gold);margin-top:5px">★ Максимальный уровень!</div>'}
      </div>

      <div class="card-title">Бонус текущего уровня</div>
      <div style="margin-bottom:12px">${bonusHtml}</div>

      <div class="card-title">Прогресс уровней</div>
      <div style="margin-bottom:12px">${tiers}</div>

      <div class="card-title">🍖 Покормить (−усталость)</div>
      <div style="margin-bottom:8px">${foodHtml}</div>

      <div class="card-title">↔ Переместить</div>
      <div>${['active','passive','storage'].filter(pl=>pl!==p.placement).map(pl=>`
        <button class="btn btn-full ${pl==='storage'?'btn-ghost':pl==='active'?'btn-teal':'btn-green'}" onclick="doMove(${petId},'${pl}',this)">
          ${pl==='active'?`⚔️ В активные (−${p.fatigue||0}% уст.)`:pl==='passive'?'🛡 В пассивные':'📦 На склад'}
        </button>`).join('')}
      </div>`;

    el('mt').textContent=p.name||p.species_name||p.species_id;
    el('mb').innerHTML=body;
    el('mf').innerHTML=`<button class="btn btn-ghost btn-sm" onclick="CM()">Закрыть</button>`;
  }).catch(e=>{el('mb').innerHTML=`<div style="color:var(--red);font-size:12px">${e}</div>`;});
}

function doFeed(pid,fid,row) {
  row.style.opacity='.4';
  api('/zoo/feed',{method:'POST',body:JSON.stringify({pet_id:pid,food_id:fid})})
    .then(r=>{toast(`✅ Усталость: ${r.fatigue_before}% → ${r.fatigue_after}%`);CM();_zooData=null;loadZoo();})
    .catch(e=>{toast(e,false);row.style.opacity='1';});
}

function doMove(pid,pl,btn) {
  btn.disabled=true;
  api('/zoo/move',{method:'POST',body:JSON.stringify({pet_id:pid,placement:pl})})
    .then(()=>{toast('✅ Перемещено!');CM();_zooData=null;loadZoo();})
    .catch(e=>{toast(e,false);btn.disabled=false;});
}

function boostExp(pid,bid,row) {
  row.style.opacity='.4';
  api('/zoo/boost',{method:'POST',body:JSON.stringify({pet_id:pid,booster_id:bid})})
    .then(r=>{toast(`⏩ −${r.boosted_hours}ч!`);_loaded.delete('zoo');loadZoo();})
    .catch(e=>{toast(e,false);row.style.opacity='1';});
}

function renderZooGuide() {
  el('zoo-c').innerHTML='<div class="loader">Загрузка...</div>';
  const ORDER = {common:0,rare:1,epic:2,legendary:3};
  const RARITY_LABEL = {common:'⬜ Обычные',rare:'🟦 Редкие',epic:'🟣 Эпические',legendary:'🟡 Легендарные'};
  api('/zoo/species').then(list=>{
    list.sort((a,b)=>(ORDER[a.rarity]||0)-(ORDER[b.rarity]||0));
    const g={};list.forEach(s=>(g[s.rarity]=g[s.rarity]||[]).push(s));
    el('zoo-c').innerHTML=Object.entries(g).map(([r,pets])=>`<div class="card">
      <div class="card-title">${RARITY_LABEL[r]||r} (${pets.length})</div>
      ${pets.map(p=>{
        const t1=bonusLines(p.species_id,(p.bonus_tiers||{})['1']||{});
        const t4=bonusLines(p.species_id,(p.bonus_tiers||{})['4']||{});
        const t10=bonusLines(p.species_id,(p.bonus_tiers||{})['10']||{});
        return `<div style="padding:10px 0;border-bottom:1px solid var(--border2)">
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
            <div style="font-size:13px;font-weight:700;color:var(--bright)">${p.name}</div>
            <div style="font-size:10px;color:${p.role==='active'?'var(--teal)':'var(--blue)'}">${p.role==='active'?'⚔️ Активный':'🛡 Пассивный'}</div>
          </div>
          <div style="font-size:11px;color:var(--muted);margin-bottom:7px;line-height:1.4">${p.desc}</div>
          <div style="font-size:10px">
            <span style="color:var(--muted)">Lv1: </span>${t1[0]||'—'}
            ${t4.length?`<span style="color:var(--muted)"> · Lv4: </span>${t4[0]||'—'}`:''}
            ${t10.length?`<span style="color:var(--muted)"> · Lv10: </span>${t10[t10.length-1]||'—'}`:''}
          </div>
        </div>`;
      }).join('')}
    </div>`).join('');
  }).catch(e=>{el('zoo-c').innerHTML=`<div style="color:var(--red);font-size:12px;padding:10px">${e}</div>`;});
}
setInterval(()=>{if(_loaded.has('zoo'))api('/zoo/expeditions').then(d=>renderExps(d)).catch(()=>{});},30000);

// ── Arena ─────────────────────────────────────────────────────────────────────
function loadArena(){swArena(_arenaTab,document.querySelector('#pg-arena .tb'));}
function swArena(tab,btn) {
  _arenaTab=tab;
  document.querySelectorAll('#pg-arena .tb').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');
  ['quests','gacha','craft','duels','dark'].forEach(t=>el('ar-'+t).style.display=t===tab?'':'none');
  ({quests:loadQuests,gacha:loadGacha,craft:loadCraft,duels:loadDuels,dark:loadDarkMora}[tab]||loadQuests)();
}
function loadQuests() {
  if(!_cid){el('qc').innerHTML='<div style="color:var(--muted);font-size:12px;padding:10px">Нужен Профиль с чатом.</div>';return;}
  api(`/quests/${_cid}`).then(qs=>{
    el('qc').innerHTML=qs.length?'<div class="card">'+qs.map(q=>{
      const pct=Math.min(100,Math.round((q.progress||0)/(q.target||1)*100));
      const rw=q.reward?.mora?`+${fmt(q.reward.mora)} 🪙`:'';
      return `<div class="qitem"><div style="font-size:13px;font-weight:600;color:var(--bright);margin-bottom:3px">${q.completed?'✅':'🔲'} ${q.id}</div>${rw?`<div style="font-size:11px;color:var(--gold)">${rw}</div>`:''}
        <div class="qbar"><div class="qfill" style="width:${pct}%"></div></div>
        <div style="font-size:10px;color:var(--muted)">${Math.round(q.progress||0)} / ${q.target}</div></div>`;
    }).join('')+'</div>':'<div class="loader">Нет квестов — откройте «бот задания».</div>';
  }).catch(e=>{el('qc').innerHTML=`<div style="color:var(--red);font-size:12px;padding:10px">${e}</div>`;});
}
function loadGacha() {
  api('/gacha/').then(d=>{
    el('gc').innerHTML=`<div class="balrow"><div class="bal"><div class="bv" id="gacha-bal">🪙 ${fmt(d.mora)}</div><div class="bl">Мора</div></div></div>
      <div class="card"><div class="card-title">Выберите крутку</div>${d.spin_types.map(s=>`<div class="spin-row" onclick="doSpin('${s.spin_type}',this)">
        <span style="font-size:20px">🎲</span>
        <span style="flex:1;font-size:13px;font-weight:600">${s.label}</span>
        ${s.token_qty?`<span style="font-size:11px;color:var(--green)">🎟 ×${s.token_qty}</span>`:''}
        <span style="font-size:12px;color:var(--gold)">${s.cost_mora?fmt(s.cost_mora)+' 🪙':s.cost_dia+' 💎'}</span>
      </div>`).join('')}</div><div id="spin-res"></div>`;
  }).catch(e=>{el('gc').innerHTML=`<div style="color:var(--red);font-size:12px;padding:10px">${e}</div>`;});
}
// doSpin — does NOT call loadGacha() to preserve the result display
function doSpin(st, row) {
  row.style.opacity = '.5'; row.style.pointerEvents = 'none';
  api('/gacha/spin', {method:'POST', body:JSON.stringify({spin_type:st})}).then(r => {
    const cards = [];
    if(r.mora) cards.push({text:`🪙 ${fmt(r.mora)} Мора`, cls:''});
    if(r.diamonds) cards.push({text:`💎 ${r.diamonds} Алмазов`, cls:''});
    (r.items||[]).forEach(i => cards.push({text:`${i.name} ×${i.qty}`, cls:''}));
    (r.dup_outcomes||[]).forEach(d => cards.push({text:`🐾 ${d.species||''} дубл.`, cls:d.rarity||''}));
    const html = cards.length
      ? cards.map((c,i)=>`<div class="spin-card ${c.cls}" style="animation-delay:${i*0.1}s">${c.text}</div>`).join('')
      : '<div class="spin-card">—</div>';
    el('spin-res').innerHTML = `
      <div style="font-size:12px;font-weight:700;color:var(--gold2);margin-bottom:8px">🎉 Результат!</div>
      ${html}
      <button class="btn btn-gold btn-full" style="margin-top:10px" onclick="closeSpinResult()">🔄 Крутить ещё</button>`;
    const balEl = el('gacha-bal');
    if(balEl) api('/profile/me').then(d=>{ if(d.mora!==undefined) balEl.textContent=`🪙 ${fmt(d.mora)}`; }).catch(()=>{});
    row.style.opacity = '1'; row.style.pointerEvents = '';
  }).catch(e => { toast(e, false); row.style.opacity='1'; row.style.pointerEvents=''; });
}
function closeSpinResult() { const s=el('spin-res'); if(s)s.innerHTML=''; loadGacha(); }
function loadCraft() {
  api('/craft/').then(recipes => {
    if (!recipes.length) { el('cc').innerHTML='<div class="loader">Рецептов пока нет.</div>'; return; }
    el('cc').innerHTML = recipes.map(rc => `
      <div class="card card-gold">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px">
          <div style="font-size:15px;font-weight:700;color:var(--bright)">${rc.name}</div>
          ${rc.can_craft_times>1?`<span style="font-size:11px;color:var(--green);background:rgba(82,179,96,.15);padding:2px 8px;border-radius:99px">×${rc.can_craft_times} возможно</span>`:''}
        </div>
        ${rc.what_is?`<div style="font-size:12px;color:var(--text);line-height:1.5;margin-bottom:10px">${rc.what_is}</div>`:''}
        ${rc.how_use?`<div class="irow"><span class="ik">Как использовать</span><span style="color:var(--teal);font-size:11px">${rc.how_use}</span></div>`:''}
        ${rc.gacha_rates?`<div class="irow"><span class="ik">Шансы при открытии</span><span style="font-size:11px">${rc.gacha_rates}</span></div>`:''}
        ${rc.special_note?`<div style="background:rgba(224,82,82,.1);border:1px solid rgba(224,82,82,.25);border-radius:var(--r);padding:8px 10px;font-size:11px;color:var(--red);margin:8px 0">${rc.special_note}</div>`:''}
        <div class="divider"></div>
        <div class="card-title">Нужно для крафта</div>
        ${rc.ingredients_status.map(i=>`
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
            <span style="font-size:18px">${i.have>=i.needed?'✅':'❌'}</span>
            <div style="flex:1">
              <div style="font-size:12px;font-weight:600">${i.item_name}</div>
              <div style="font-size:10px;color:var(--muted)">${i.have} из ${i.needed} в инвентаре</div>
            </div>
            <div style="font-size:14px;font-weight:700;color:${i.have>=i.needed?'var(--green)':'var(--red)'}">${i.have}/${i.needed}</div>
          </div>`).join('')}
        ${rc.ingredient_tip?`<div style="font-size:11px;color:var(--muted);margin-top:6px;padding:8px;background:var(--s);border-radius:var(--r)">💡 ${rc.ingredient_tip}</div>`:''}
        <button class="btn btn-full ${rc.can_craft?'btn-gold':'btn-ghost'}" style="margin-top:12px"
                ${rc.can_craft?'':'disabled'} onclick="doCraft('${rc.recipe_id}',this)">
          ${rc.can_craft?`⚗️ Скрафтить ${rc.name}`:'🔒 Недостаточно ингредиентов'}
        </button>
      </div>`).join('');
  }).catch(e => { el('cc').innerHTML=`<div style="color:var(--red);font-size:12px;padding:10px">${e}</div>`; });
}
function doCraft(recipeId, btn) {
  btn.disabled = true;
  api(`/craft/${recipeId}`, {method:'POST'})
    .then(r => { toast(`✅ Скрафтено: ${r.name}!`); loadCraft(); })
    .catch(e => { toast(e, false); btn.disabled = false; });
}
function loadDuels() {
  el('dc').innerHTML='<div class="loader">Загрузка...</div>';
  Promise.all([api('/duels/active'), api('/duels/history')]).then(([active, hist]) => {
    let html = '';

    // Challenge button
    html += `<button class="btn btn-red btn-full" style="margin-bottom:10px" onclick="openDuelChallenge()">⚔️ Вызвать игрока на дуэль</button>`;

    // Incoming challenges
    const incoming = active.filter(d => d.challenged_id == _uid);
    if(incoming.length) {
      html += `<div class="card"><div class="card-title">⏳ Входящие вызовы (${incoming.length})</div>
        ${incoming.map(d=>`<div class="duel-card">
          <div class="duel-vs">${d.challenger_name||'Игрок'} вызывает вас</div>
          <div class="duel-stake">Ставка: ${fmt(d.stake)} 🪙</div>
          <div style="font-size:10px;color:var(--muted);margin-top:2px">Принять можно ответив на вызов в чате: <code>бот принять</code></div>
          <button class="btn btn-sm btn-red" style="margin-top:6px" onclick="declineDuel(${d.id},this)">❌ Отклонить</button>
        </div>`).join('')}
      </div>`;
    }

    // Outgoing pending
    const outgoing = active.filter(d => d.challenger_id == _uid);
    if(outgoing.length) {
      html += `<div class="card"><div class="card-title">📤 Мои вызовы</div>
        ${outgoing.map(d=>`<div class="duel-card">
          <div class="duel-vs">→ ${d.challenged_name||'Игрок'}</div>
          <div class="duel-stake">Ставка: ${fmt(d.stake)} 🪙</div>
          <div style="font-size:10px;color:var(--muted)">Ожидание ответа...</div>
        </div>`).join('')}
      </div>`;
    }

    // History
    if(hist.length) {
      html += `<div class="card"><div class="card-title">📜 История (последние 20)</div>
        ${hist.map(d => {
          const won = d.winner_id == _uid;
          const isDone = d.status === 'finished';
          const vs = d.challenger_id == _uid ? d.challenged_name : d.challenger_name;
          const statusMap = {pending:'⏳ Ожидание', timeout:'⏰ Истёк', declined:'❌ Отклонён', finished:''};
          return `<div class="duel-card">
            <div style="display:flex;align-items:center;justify-content:space-between">
              <div class="duel-vs">vs ${vs||'Игрок'}</div>
              <div class="duel-result${isDone?(won?' win':' lose'):''}">
                ${isDone?(won?'✓ Победа':'✗ Поражение'):statusMap[d.status]||d.status}
              </div>
            </div>
            <div class="duel-stake">${fmt(d.stake)} 🪙</div>
          </div>`;
        }).join('')}
      </div>`;
    }

    el('dc').innerHTML = html || '<div class="loader">Дуэлей пока нет.</div>';
  }).catch(e => { el('dc').innerHTML=`<div style="color:var(--red);font-size:12px;padding:10px">${e}</div>`; });
}

function declineDuel(id, btn) {
  btn.disabled = true;
  api('/duels/decline', {method:'POST', body:JSON.stringify({duel_id:id})})
    .then(() => { toast('✅ Вызов отклонён.'); loadDuels(); })
    .catch(e => { toast(e, false); btn.disabled = false; });
}

function openDuelChallenge() {
  if(!_cid) { toast('Нужен Профиль с чатом для вызова.', false); return; }
  OM('⚔️ Вызов на дуэль', `
    <div style="font-size:11px;color:var(--muted);margin-bottom:12px;line-height:1.5">
      Введите @username игрока и ставку. Вызов придёт в чат — там соперник сможет принять его через бота.
    </div>
    <div style="font-size:11px;color:var(--muted);margin-bottom:4px">@username соперника</div>
    <input id="duel-user" type="text" class="num-input" placeholder="@username (без @)"/>
    <div style="font-size:11px;color:var(--muted);margin:8px 0 4px">Ставка 🪙 (200 – 15 000)</div>
    <input id="duel-stake" type="number" class="num-input" placeholder="500" min="200" max="15000"/>
    <div style="font-size:10px;color:var(--muted);margin-top:6px">
      ⚠️ Ставка замораживается до завершения дуэли.
    </div>
  `, [
    {l:'⚔️ Вызвать', c:'btn-red', f:'submitDuelChallenge(this)'},
    {l:'Отмена', c:'btn-ghost', f:'CM()'},
  ]);
}

function submitDuelChallenge(btn) {
  const username = el('duel-user')?.value?.trim().replace('@','');
  const stake = parseFloat(el('duel-stake')?.value||0);
  if(!username) { toast('Введите @username.', false); return; }
  if(!stake || stake < 200) { toast('Мин. ставка 200 🪙.', false); return; }
  btn.disabled = true;
  api('/duels/challenge', {method:'POST', body:JSON.stringify({username, stake, chat_id:_cid})})
    .then(() => { toast('⚔️ Вызов отправлен в чат!'); CM(); loadDuels(); })
    .catch(e => { toast(e, false); btn.disabled = false; });
}

// ── Market ────────────────────────────────────────────────────────────────────
function loadMarket(){swMkt('auc',document.querySelector('#pg-market .tb'));}
function swMkt(tab, _btn) {
  const btn = _btn || document.querySelector('#pg-market .tb');
  _mktTab = tab;
  document.querySelectorAll('#pg-market .tb').forEach(b=>b.classList.remove('active'));
  if(btn) btn.classList.add('active');
  const bd = el('balrow'); bd.style.display = tab === 'shop' ? 'flex' : 'none';
  el('mkt-auc').style.display  = tab === 'auc'  ? '' : 'none';
  el('mkt-shop').style.display = tab === 'shop' ? '' : 'none';
  el('mkt-inv').style.display  = tab === 'inv'  ? '' : 'none';
  el('mkt-exch').style.display = tab === 'exch' ? '' : 'none';
  ({auc:loadAuction, shop:loadShopCatalog, inv:loadInventory, exch:loadExchange}[tab]||loadAuction)();
}

let _aucPage = 0, _aucTotal = 0, _aucPerPage = 20;

function loadAuction(page) {
  if(page !== undefined) _aucPage = page;
  api(`/auction/lots?page=${_aucPage}&per_page=${_aucPerPage}`).then(data=>{
    _allLots = data.lots || data;  // backward compat
    _aucTotal = data.total || _allLots.length;
    const totalPages = Math.ceil(_aucTotal / _aucPerPage);

    el('mkt-auc').innerHTML=`
      <div style="display:flex;gap:7px;margin-bottom:8px">
        <input type="text" class="num-input" style="margin:0;flex:1;font-size:12px"
               placeholder="🔍 Поиск..." oninput="filterAuction(this.value)"/>
        <button class="btn btn-gold btn-sm" onclick="openCreateLotModal()">+ Выставить</button>
      </div>
      <!-- Reserved mora -->
      <div id="auc-reserve" style="margin-bottom:8px"></div>
      <div id="lot-list"></div>
      <!-- Pagination -->
      ${totalPages > 1 ? `<div style="display:flex;gap:6px;justify-content:center;margin-top:10px">
        ${_aucPage > 0 ? `<button class="btn btn-ghost btn-sm" onclick="loadAuction(${_aucPage-1})">← Пред.</button>` : ''}
        <span style="font-size:11px;color:var(--muted);padding:6px">${_aucPage+1} / ${totalPages} (${_aucTotal} лотов)</span>
        ${data.has_more ? `<button class="btn btn-ghost btn-sm" onclick="loadAuction(${_aucPage+1})">След. →</button>` : ''}
      </div>` : `<div style="font-size:10px;color:var(--muted);text-align:center;margin-top:6px">${_aucTotal} лотов</div>`}`;

    renderLots(_allLots);
    loadAucReserve();
  }).catch(e=>{el('mkt-auc').innerHTML=`<div style="color:var(--red);font-size:12px;padding:10px">${e}</div>`;_allLots=[];});
}

function loadAucReserve() {
  if(!_uid && !sess()) return;
  api('/auction/reserved').then(r=>{
    const div = el('auc-reserve'); if(!div) return;
    if(!r.reserved_total || !r.bids?.length) { div.innerHTML=''; return; }
    const bidsHtml = r.bids.map(b=>{
      const ends = new Date((b.ends_at+'').includes('T')?b.ends_at:b.ends_at+'Z');
      const diff = Math.max(0,Math.floor((ends-Date.now())/1000));
      const tl = diff>3600?Math.floor(diff/3600)+'ч':Math.floor(diff/60)+'м';
      return `<div style="display:flex;justify-content:space-between;align-items:center;padding:4px 0;border-bottom:1px solid var(--border2)">
        <div>
          <span style="font-size:11px;color:var(--bright)">${b.item_name||'Лот #'+b.lot_id}</span>
          <span style="font-size:10px;color:var(--muted)"> · ⏳${tl}</span>
        </div>
        <span style="font-size:11px;color:var(--gold);font-weight:600">${fmt(b.amount)} 🪙</span>
      </div>`;
    }).join('');
    div.innerHTML=`<div style="background:var(--gold-dim);border:1px solid var(--border);border-radius:var(--r);padding:8px 10px;font-size:11px">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
        <span style="font-weight:600;color:var(--gold2)">🔒 Зарезервировано: ${fmt(r.reserved_total)} 🪙</span>
        <span style="font-size:10px;color:var(--muted)">${r.bids.length} ставок</span>
      </div>
      ${bidsHtml}
    </div>`;
  }).catch(()=>{});
}
// ── Create lot modal ─────────────────────────────────────────────────────────
let _invForAuction = [];
function openCreateLotModal() {
  if(!_invData.length) { loadInventory(); }
  // Filter tradable items
  const items = _invData.filter(it => it.quantity > 0 && ['egg','food','utility','booster','spin_token','material'].includes(it.category));
  if(!items.length) {
    OM('🏛 Выставить лот', '<div class="err">Инвентарь пуст. Нечего выставлять.</div>', [{l:'Закрыть',c:'btn-ghost',f:'CM()'}]);
    return;
  }
  _invForAuction = items;
  const listHtml = items.map(it=>`
    <div class="fopt" onclick="selectLotItem('${it.item_id}','${it.name.replace(/'/g,'')}',${it.quantity})">
      <span class="fn">${it.name}</span>
      <span class="fq">×${it.quantity}</span>
    </div>`).join('');
  OM('🏛 Выбери предмет', `
    <div style="font-size:11px;color:var(--muted);margin-bottom:8px">Выберите предмет для продажи:</div>
    ${listHtml}
  `, [{l:'Отмена',c:'btn-ghost',f:'CM()'}]);
}
function selectLotItem(itemId, itemName, maxQty) {
  el('mt').textContent = `🏛 ${itemName}`;
  el('mb').innerHTML = `
    <div class="irow"><span class="ik">Предмет</span><span>${itemName}</span></div>
    <div class="irow"><span class="ik">Доступно</span><span>×${maxQty}</span></div>
    <div class="divider"></div>
    <div style="font-size:11px;color:var(--muted);margin-bottom:6px">Количество (1–${Math.min(maxQty,10)})</div>
    <input id="lot-qty" type="number" class="num-input" min="1" max="${Math.min(maxQty,10)}" value="1"/>
    <div style="font-size:11px;color:var(--muted);margin:8px 0 4px">Мин. ставка 🪙</div>
    <input id="lot-bid" type="number" class="num-input" min="50" value="500" placeholder="Минимальная ставка..."/>
    <div style="font-size:11px;color:var(--muted);margin:8px 0 4px">Выкуп 🪙 (необязательно)</div>
    <input id="lot-buyout" type="number" class="num-input" placeholder="Цена мгновенного выкупа (опционально)"/>
  `;
  el('mf').innerHTML = `
    <button class="btn btn-ghost btn-sm" onclick="openCreateLotModal()">← Назад</button>
    <button class="btn btn-gold btn-sm" onclick="submitLot('${itemId}')">✅ Выставить</button>
  `;
}
function submitLot(itemId) {
  const qty = parseInt(el('lot-qty')?.value||1);
  const minBid = parseFloat(el('lot-bid')?.value||0);
  const buyout = parseFloat(el('lot-buyout')?.value||0)||null;
  if(!minBid||minBid<50){toast('Мин. ставка от 50 🪙',false);return;}
  const btn = document.querySelector('#mf .btn-gold');
  if(btn) btn.disabled=true;
  api('/auction/create',{method:'POST',body:JSON.stringify({item_id:itemId,quantity:qty,min_bid:minBid,buyout})})
    .then(r=>{toast(`✅ Лот #${r.lot_id} создан! (24ч)`);CM();loadAuction();})
    .catch(e=>{toast(e,false);if(btn)btn.disabled=false;});
}

// openBidModal(lotId, name, currentBid, minNextBid, hasBids, buyout)
// minNextBid comes from server (min_bid if no bids, ceil(cur*1.05) if bids exist)
function openBidModal(lotId, name, currentBid, minNextBid, hasBids, buyout) {
  const firstBid = !hasBids;
  const minLabel = firstBid
    ? `Первая ставка — не менее <b>${fmt(minNextBid)} 🪙</b>`
    : `Мин. для обгона — <b>${fmt(minNextBid)} 🪙</b> (текущая × 1.05)`;
  const buyoutBtn = buyout
    ? `<button class="btn btn-teal btn-full" style="margin-top:8px"
             onclick="doBid(${lotId},this,${buyout})">⚡ Выкупить за ${fmt(buyout)} 🪙</button>`
    : '';
  OM(`💰 Ставка: ${name}`, `
    <div class="irow"><span class="ik">Текущая ставка</span><span style="color:var(--gold);font-weight:700">${fmt(currentBid)} 🪙</span></div>
    <div style="font-size:11px;color:var(--muted);margin:8px 0">${minLabel}</div>
    <div class="divider"></div>
    <input id="bid-val" class="num-input" type="number"
           value="${minNextBid}" min="${minNextBid}" step="1"
           placeholder="Ваша ставка 🪙"/>
    <div style="font-size:10px;color:var(--muted);margin-top:6px">
      Мора будет зарезервирована до завершения аукциона.
    </div>
    ${buyoutBtn}
  `, [{l:'💰 Поставить ставку', c:'btn-gold', f:`doBid(${lotId},this,0)`}, {l:'Отмена', c:'btn-ghost', f:'CM()'}]);
}
function doBid(lotId, btn, fixedAmount) {
  const v = fixedAmount > 0 ? fixedAmount : parseFloat(el('bid-val')?.value || 0);
  if (!v || v <= 0) { toast('Введите сумму.', false); return; }
  btn.disabled = true;
  api('/auction/bid', {method:'POST', body:JSON.stringify({lot_id:lotId, amount:v})})
    .then(r => { toast(r.is_buyout ? '🎉 Выкуплено!' : '✅ Ставка принята!'); CM(); loadAuction(); })
    .catch(e => { toast(e, false); btn.disabled = false; });
}

function loadShopCatalog() {
  // Load inventory first so we can show "already have" badges
  if(!_invData.length) api('/inventory/').then(items=>{_invData=items;}).catch(()=>{});
  api('/shop/').then(d=>{
    el('balrow').style.display='flex';
    el('balrow').innerHTML=`<div class="bal"><div class="bv">🪙 ${fmt(d.mora)}</div><div class="bl">Мора</div></div>
      <div class="bal"><div class="bv">💎 ${d.diamonds.toFixed(1)}</div><div class="bl">Алмазы</div></div>`;
    const cats={food:'🥩 Еда',egg:'🥚 Яйца',utility:'🛠 Утилиты',booster:'⚗️ Зелья'};
    const grps={};d.items.forEach(it=>(grps[it.category]=grps[it.category]||[]).push(it));
    el('mkt-shop').innerHTML=Object.entries(grps).map(([cat,list])=>
      `<div class="card"><div class="card-title">${cats[cat]||cat}</div>${list.map(it=>`<div class="shop-row">
        <span style="font-size:22px;width:32px;text-align:center">${it.name.split(' ')[0]}</span>
        <div style="flex:1">
          <div style="font-size:13px;font-weight:600;color:var(--bright)">${it.name}</div>
          <div style="font-size:11px;color:var(--gold)">${it.price_mora?fmt(it.price_mora)+' 🪙':it.price_diamonds+' 💎'}${it.discount_active?' 🐢':''}</div>
          <div style="font-size:10px;color:var(--muted)">${it.description||''}</div>
          ${_invData.find(i=>i.item_id===it.item_id)
            ? `<div style="font-size:10px;color:var(--green);margin-top:2px">✓ В инвентаре: ×${_invData.find(i=>i.item_id===it.item_id).quantity}</div>`
            : ''}
        </div>
        <button class="btn btn-sm btn-gold" onclick="buyItem('${it.item_id}',this)">Купить</button>
      </div>`).join('')}</div>`).join('');
  }).catch(e=>{el('mkt-shop').innerHTML=`<div style="color:var(--red);font-size:12px;padding:10px">${e}</div>`;});
}
// Block 9: warn before buying if already in inventory
function buyItem(id, btn) {
  const existing = _invData.find(i => i.item_id === id);
  if (existing) {
    OM('⚠️ Уже в инвентаре', `
      <div style="text-align:center;padding:10px 0 14px">
        <div style="font-size:24px;margin-bottom:8px">⚠️</div>
        <div style="font-size:13px;font-weight:600;color:var(--bright);margin-bottom:6px">У вас уже есть этот предмет</div>
        <div style="font-size:12px;color:var(--muted)">В инвентаре: <b style="color:var(--gold)">×${existing.quantity}</b></div>
        <div style="font-size:11px;color:var(--muted);margin-top:8px">Купить ещё?</div>
      </div>
    `, [
      {l:'✅ Да, купить ещё', c:'btn-gold', f:`doBuyConfirmed('${id}')`},
      {l:'Отмена', c:'btn-ghost', f:'CM()'},
    ]);
    return;
  }
  _execBuy(id, btn);
}
function doBuyConfirmed(id) {
  CM();
  api('/shop/buy', {method:'POST', body:JSON.stringify({item_id:id, quantity:1})})
    .then(r => { toast('✅ Куплено: ' + r.item_name); loadShopCatalog(); })
    .catch(e => toast(e, false));
}
function _execBuy(id, btn) {
  if(btn) btn.disabled = true;
  api('/shop/buy', {method:'POST', body:JSON.stringify({item_id:id, quantity:1})})
    .then(r => { toast('✅ Куплено: ' + r.item_name); loadShopCatalog(); })
    .catch(e => { toast(e, false); if(btn) btn.disabled = false; });
}
function loadInventory() {
  el('mkt-inv').innerHTML='<div class="loader">Загрузка...</div>';
  api('/inventory/').then(items=>{
    _invData=items;
    el('mkt-inv').innerHTML=items.length
      ?'<div class="inv-grid">'+items.map(it=>`<div class="icard" onclick="openItemModal('${it.item_id}')">
          <div class="icat">${it.category}</div>
          <div class="iname">${it.name}</div>
          <div class="iqty">×${it.quantity}</div>
          <div class="idesc">${it.description||''}</div>
        </div>`).join('')+'</div>'
      :'<div class="loader">Инвентарь пуст.</div>';
  }).catch(e=>{el('mkt-inv').innerHTML=`<div style="color:var(--red);font-size:12px;padding:10px">${e}</div>`;});
}
function openItemModal(iid) {
  const it=_invData.find(i=>i.item_id===iid);if(!it)return;
  const {item_id,name,quantity,category,description,spin_type,boost_hours,fatigue_restore,gacha_rates}=it;
  let body=`<div class="irow"><span class="ik">В инвентаре</span><span>×${quantity}</span></div>`;
  if(description)body+=`<div style="font-size:11px;color:var(--muted);margin-top:7px;line-height:1.4">${description}</div>`;
  body+='<div class="divider"></div>';
  const btns=[{l:'Закрыть',c:'btn-ghost',f:'CM()'}];
  if(category==='egg'&&gacha_rates){
    body+=Object.entries(gacha_rates).filter(([,v])=>v>0).map(([r,v])=>`<div class="irow"><span class="${RC[r]||'rc-common'}" style="font-size:11px">${r}</span><span>${v}%</span></div>`).join('');
    if(quantity>0)btns.unshift({l:'🥚 Открыть',c:'btn-gold',f:`doOpenEgg('${item_id}',1)`});
  } else if(category==='food'&&fatigue_restore){
    body+=`<div class="irow"><span class="ik">Восстанавливает</span><span style="color:var(--green)">−${fatigue_restore} уст.</span></div>`;
    if(quantity>0)btns.unshift({l:'🍖 Покормить питомца',c:'btn-gold',f:`openFeedSelModal('${item_id}')`});
  } else if(boost_hours){
    body+=`<div class="irow"><span class="ik">Ускорение</span><span style="color:var(--teal)">−${boost_hours}ч</span></div>`;
    if(quantity>0)btns.unshift({l:'⏩ К экспедиции',c:'btn-teal',f:`openBoostSelModal('${item_id}')`});
  } else if(category==='spin_token'){
    if(quantity>0)btns.unshift({l:'🎲 В Гачу',c:'btn-gold',f:`goArenaGacha()`});
  } else if(item_id.startsWith('star_dust')){
    body+=`<div class="irow"><span class="ik">Даёт дубликатов</span><span style="color:var(--gold)">+${item_id.includes('_l')?5:1}</span></div>`;
    if(quantity>0)btns.unshift({l:'✨ Применить',c:'btn-gold',f:`openDustModal('${item_id}')`});
  }
  OM(name,body,btns);
}
function doOpenEgg(eid,cnt) {
  CM();
  api('/inventory/open-egg',{method:'POST',body:JSON.stringify({egg_id:eid,count:cnt})}).then(r=>{
    const results=r.results||[];
    OM('🎉 Яйцо открыто!',results.map(res=>{
      const oc={first_copy_created:'🆕 Новый питомец',leveled_up:'⬆️ Уровень',added:'➕ Дубликат',overflow:'💫 Переполнение'}[res.outcome]||res.outcome;
      return `<div class="irow"><span>${res.species||''}</span><span>${oc}${res.new_level?' Lv'+res.new_level:''}</span></div>`;
    }).join('')||'<div style="color:var(--green);font-size:12px">Готово!</div>',[{l:'OK',c:'btn-gold',f:'CM()'}]);
    loadInventory();
  }).catch(e=>toast(e,false));
}
function openFeedSelModal(fid) {
  if(!_zooData){toast('Зайдите в Зоопарк.',false);return;}
  const pets=_zooData.pets.filter(p=>p.placement!=='storage');
  if(!pets.length){toast('Нет питомцев.',false);return;}
  OM('🍖 Выберите питомца',pets.map(p=>`<div class="fopt" onclick="doFeedFromInv(${p.id},'${fid}',this)"><span class="fn">${p.name||p.species_id}</span><span class="fq">${p.fatigue}% уст.</span></div>`).join(''),[{l:'Отмена',c:'btn-ghost',f:'CM()'}]);
}
function doFeedFromInv(pid,fid,row) {
  row.style.opacity='.4';
  api('/zoo/feed',{method:'POST',body:JSON.stringify({pet_id:pid,food_id:fid})})
    .then(r=>{toast(`✅ ${r.fatigue_before}%→${r.fatigue_after}%`);CM();_zooData=null;loadInventory();})
    .catch(e=>{toast(e,false);row.style.opacity='1';});
}
function openBoostSelModal(bid) {
  api('/zoo/expeditions').then(d=>{
    if(!d.expeditions.length){toast('Нет активных экспедиций.',false);return;}
    OM('⏩ Выберите экспедицию',d.expeditions.map(e=>`<div class="fopt" onclick="doBoostFromInv(${e.pet_id},'${bid}',this)">
      <span class="fn">${e.name}</span><span style="font-size:11px;color:var(--teal)">${countdown(e.ends_at)}</span></div>`).join(''),[{l:'Отмена',c:'btn-ghost',f:'CM()'}]);
  }).catch(e=>toast(e,false));
}
function doBoostFromInv(pid,bid,row) {
  row.style.opacity='.4';
  api('/zoo/boost',{method:'POST',body:JSON.stringify({pet_id:pid,booster_id:bid})})
    .then(r=>{toast(`⏩ −${r.boosted_hours}ч!`);CM();_loaded.delete('zoo');loadZoo();loadInventory();})
    .catch(e=>{toast(e,false);row.style.opacity='1';});
}
function openDustModal(did) {
  if(!_zooData){toast('Зайдите в Зоопарк.',false);return;}
  OM('✨ Выберите питомца',_zooData.pets.map(p=>`<div class="fopt" onclick="doApplyDust('${did}',${p.id},this)">
    <span class="fn">${p.name||p.species_id}</span><span style="font-size:11px">${rc(p.rarity)} Lv${p.pet_level}</span></div>`).join(''),[{l:'Отмена',c:'btn-ghost',f:'CM()'}]);
}
function doApplyDust(did,pid,row) {
  row.style.opacity='.4';
  api('/inventory/apply-dust',{method:'POST',body:JSON.stringify({dust_id:did,pet_id:pid})})
    .then(r=>{toast(`✅ +${r.duplicates_added} дубл.`);CM();_zooData=null;loadInventory();})
    .catch(e=>{toast(e,false);row.style.opacity='1';});
}
function goArenaGacha() { CM(); document.querySelectorAll('.nb')[2].click(); swArena('gacha',document.querySelectorAll('#pg-arena .tb')[1]); }

// ── Source info for themes ────────────────────────────────────────────────────
const SRC = {
  start:          {label:'Стартовая',     desc:'Есть у всех игроков с самого начала. Бесплатно!', action:null},
  shop_mora:      {label:'Магазин 🪙',    desc:'Купите напрямую в Магазине за Мору.', action:null},
  shop_diamond:   {label:'Магазин 💎',    desc:'Купите в Магазине за Алмазы.', action:null},
  dark:           {label:'Чёрный Рынок 🌑', desc:'Покупается за Тёмную Мору на Чёрном Рынке. Зарабатывайте Тёмную Мору через Контрабанду и Ритуал Культа Бездны.', action:{l:'🌑 Открыть Тёмную Мору', f:"goTo('arena','dark')"}},
  zarniki:        {label:'Зарники ✨',     desc:'Приобретается за донат-валюту Зарники (Telegram Stars). 1 Звезда = 10 Зарников.', action:null},
  gacha_novice:   {label:'Гача 🎲',       desc:'Может выпасть из Ученической крутки гачи. Шанс — случайный.', action:{l:'🎲 Открыть Гачу', f:"goTo('arena','gacha')"}},
  gacha_standard: {label:'Гача 🎲',       desc:'Может выпасть из Стандартной крутки гачи (1000 🪙 / спин).', action:{l:'🎲 Открыть Гачу', f:"goTo('arena','gacha')"}},
  gacha_premium:  {label:'Гача 🎲',       desc:'Может выпасть из Премиум крутки гачи (2800 🪙 / спин).', action:{l:'🎲 Открыть Гачу', f:"goTo('arena','gacha')"}},
  gacha_diamond:  {label:'Гача 💎',       desc:'Выпадает из Алмазной крутки гачи (5 💎 / спин). Самые редкие темы.', action:{l:'🎲 Открыть Гачу', f:"goTo('arena','gacha')"}},
  event:          {label:'Ивент 🎪',      desc:'Выдаётся за участие в особых мировых событиях. Следите за объявлениями в чате.', action:null},
  auction:        {label:'Аукцион 🏛',    desc:'Можно купить у других игроков на Аукционе.', action:{l:'🏛 Открыть Аукцион', f:"goTo('market','auc')"}},
};

function goTo(page, sub) {
  CM();
  const pageBtn = [...document.querySelectorAll('.nb')].find(b=>b.onclick?.toString().includes(`'${page}'`));
  if(pageBtn) pageBtn.click();
  setTimeout(() => {
    const subBtn = document.querySelector(`#pg-${page} .tb`);
    if(sub && subBtn) {
      const allTabs = document.querySelectorAll(`#pg-${page} .tb`);
      const target = [...allTabs].find(b=>b.onclick?.toString().includes(`'${sub}'`));
      if(target) target.click();
    }
  }, 100);
}

// ── Collection ────────────────────────────────────────────────────────────────
// _profileData declared in globals above

function loadColl(){swColl('themes',document.querySelector('#pg-coll .tb'));}
function swColl(tab,btn) {
  document.querySelectorAll('#pg-coll .tb').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');
  el('col-themes').style.display=tab==='themes'?'':'none';
  el('col-top').style.display=tab==='top'?'':'none';
  if(tab==='themes') loadThemes();
  else if(tab==='top') loadTop();
}

function themeStatusBadge(t) {
  if(t.active)   return '<span class="theme-status ts-active">✓ Активна</span>';
  if(t.owned)    return '<span class="theme-status ts-owned">В коллекции</span>';
  if(t.source && t.source.startsWith('gacha')) return '<span class="theme-status ts-gacha">Гача 🎲</span>';
  if(t.source === 'event')   return '<span class="theme-status ts-event">Ивент 🎪</span>';
  if(t.source === 'dark')    return '<span class="theme-status ts-dark">🌑</span>';
  if(t.price_mora)    return `<div class="theme-price">${fmt(t.price_mora)} 🪙</div>`;
  if(t.price_diamonds)return `<div class="theme-price">${t.price_diamonds} 💎</div>`;
  return '';
}

function loadThemes() {
  api('/themes/').then(themes => {
    _themeData = themes;
    const groups = {};
    themes.forEach(t => (groups[t.rarity] = groups[t.rarity]||[]).push(t));
    const ORDER = ['common','uncommon','rare','epic','legendary','mythic','shadow','zarniki','seasonal'];
    el('col-themes').innerHTML = ORDER.filter(r => groups[r]).map(r => {
      const label = `${groups[r][0]?.badge||''} ${groups[r][0]?.rarity_label||r}`;
      return `<div class="card">
        <div class="card-title">${label}</div>
        <div class="theme-grid">${groups[r].map(t => `
          <div class="theme-card${t.owned?' owned':''}${t.active?' active-theme':''}" onclick="openThemeModal('${t.theme_id}')">
            <div class="theme-deco">${t.top||'━━━━━━━━'}</div>
            <div class="theme-name">${t.name}</div>
            <div class="theme-deco" style="margin-top:3px">${t.bot_line||'━━━━━━━━'}</div>
            <div style="margin-top:6px">${themeStatusBadge(t)}</div>
          </div>`).join('')}
        </div>
      </div>`;
    }).join('');
  }).catch(e => { el('col-themes').innerHTML=`<div style="color:var(--red);font-size:12px;padding:10px">${e}</div>`; });
}

function buildProfilePreview(t) {
  const p = _profileData;
  const name = p ? `@${p.username||'Игрок'}` : '@Игрок';
  const info = p ? `Lv${p.chats?.[0]?.user_level||1} · 🔥${p.streak||0} стрик · 🪙 ${fmt(p.mora||0)}` : 'Загрузка...';
  return `<div class="profile-preview">
    <div class="pp-deco">${t.top||''}</div>
    <div class="pp-content">
      <div class="pp-name">${t.accent||'🔮'} ${name}</div>
      <div class="pp-info">${t.rarity_label} · ${info}</div>
    </div>
    <div class="pp-deco">${t.bot_line||''}</div>
  </div>`;
}

function openThemeModal(tid) {
  if(!_themeData) return;
  const t = _themeData.find(x => x.theme_id === tid);
  if(!t) return;

  const price = t.price_mora ? `${fmt(t.price_mora)} 🪙` : t.price_diamonds ? `${t.price_diamonds} 💎` : null;
  const src = SRC[t.source] || SRC[t.source?.split('_')[0]+'_'+t.source?.split('_').slice(1).join('_')] || {label:t.source, desc:'', action:null};
  const buyable = price && (t.source === 'shop_mora' || t.source === 'shop_diamond');

  const body = `
    <div style="margin-bottom:12px">
      <div style="font-size:10px;color:var(--muted);margin-bottom:6px;text-transform:uppercase;letter-spacing:1px">Предпросмотр профиля</div>
      ${buildProfilePreview(t)}
    </div>
    <div class="divider"></div>
    <div class="irow"><span class="ik">Редкость</span><span>${t.badge} ${t.rarity_label}</span></div>
    ${t.desc ? `<div style="font-size:11px;color:var(--muted);margin:8px 0;line-height:1.4">${t.desc}</div>` : ''}
    <div class="divider"></div>
    <div style="font-size:10px;color:var(--muted);margin-bottom:8px;text-transform:uppercase;letter-spacing:1px">Как получить</div>
    <div style="background:var(--card);border-radius:var(--r);padding:10px">
      <div style="font-size:12px;font-weight:600;color:var(--bright);margin-bottom:4px">${src.label}</div>
      <div style="font-size:11px;color:var(--muted);line-height:1.4">${src.desc}</div>
      ${src.action ? `<button class="btn btn-ghost btn-sm btn-full" style="margin-top:8px" onclick="${src.action.f}">${src.action.l}</button>` : ''}
    </div>
    ${price ? `<div class="irow" style="margin-top:10px"><span class="ik">Цена</span><span style="color:var(--gold);font-weight:700">${price}</span></div>` : ''}
    ${t.active ? `<div style="text-align:center;padding:10px;color:var(--gold);font-size:12px;font-weight:600">✓ Это ваша активная тема</div>` : ''}
  `;

  const btns = [{l:'Закрыть', c:'btn-ghost', f:'CM()'}];
  if(!t.active && t.owned) btns.unshift({l:'✓ Надеть', c:'btn-gold', f:`doEquipTheme('${tid}')`});
  else if(buyable && !t.owned) btns.unshift({l:`Купить — ${price}`, c:'btn-gold', f:`doBuyTheme('${tid}')`});

  OM(t.name, body, btns);

  // Lazy-load profile for preview
  if(!_profileData && (INIT_DATA || sess())) {
    api('/profile/me').then(d => { _profileData=d; el('mb').innerHTML=body; }).catch(()=>{});
  }
}

function doBuyTheme(tid) {
  api('/themes/buy', {method:'POST', body:JSON.stringify({theme_id:tid})})
    .then(r => { toast(`✅ ${r.theme_name} куплена!`); CM(); loadThemes(); })
    .catch(e => toast(e, false));
}
function doEquipTheme(tid) {
  api('/themes/equip', {method:'POST', body:JSON.stringify({theme_id:tid})})
    .then(() => { toast('✅ Тема активирована!'); CM(); loadThemes(); })
    .catch(e => toast(e, false));
}

// ── Top ───────────────────────────────────────────────────────────────────────
// Priority: chat where mini app was opened (_initChatId) → profile chat (_cid)
function loadTop(){switchTop('local',document.querySelector('#col-top .tb'));}
function switchTop(mode, btn) {
  document.querySelectorAll('#col-top .tb').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');

  const localChatId = _initChatId || _cid;
  const localChatName = _initChatTitle || '(из профиля)';

  if (mode === 'local' && !localChatId) {
    el('top-c').innerHTML='<div style="color:var(--muted);font-size:12px;padding:10px">Откройте мини-апп через кнопку в чате, чтобы видеть его топ.</div>';
    return;
  }
  el('top-c').innerHTML='<div class="loader">Загрузка...</div>';
  api(mode==='global' ? '/top/global' : `/top/local/${localChatId}`)
    .then(rows => {
      const header = mode === 'local'
        ? `<div style="font-size:11px;color:var(--muted);padding:0 0 8px">📍 Чат: ${localChatName}</div>`
        : `<div style="font-size:11px;color:var(--muted);padding:0 0 8px">🌍 Все чаты · за всё время</div>`;
      el('top-c').innerHTML = rows.length
        ? '<div class="card">' + header + rows.slice(0,30).map((r,i)=>`<div class="trow">
            <div class="tpos">${MEDALS[i]||(i+1)+'.'}</div>
            <div class="tname">${r.username}</div>
            <div class="tcnt">${fmt(r.count)} 💬</div>
          </div>`).join('') + '</div>'
        : '<div class="loader">Данных пока нет.</div>';
    })
    .catch(e => { el('top-c').innerHTML=`<div style="color:var(--red);font-size:12px;padding:10px">${e}</div>`; });
}

// ── Exchange ──────────────────────────────────────────────────────────────────
function loadExchange() {
  el('mkt-exch').innerHTML='<div class="loader">Загрузка...</div>';
  api('/exchange/').then(d=>{
    if(!d.active){
      const when=d.scheduled?`<div class="irow" style="margin-top:10px"><span class="ik">Следующий ивент</span><span style="color:var(--teal)">${d.scheduled.starts_at||'—'}</span></div>`:'';
      el('mkt-exch').innerHTML=`<div class="card card-gold">
        <div style="text-align:center;padding:16px 0 12px">
          <div style="font-size:36px;margin-bottom:8px">💱</div>
          <div style="font-size:15px;font-weight:700;color:var(--bright);margin-bottom:6px">Ивент обмена Мора → Алмазы</div>
          <div style="font-size:11px;color:var(--muted)">Сейчас неактивен</div>
        </div>
        <div class="divider"></div>
        <div style="font-size:13px;font-weight:600;color:var(--bright);margin-bottom:8px">Что такое ивент обмена?</div>
        <div style="font-size:12px;color:var(--muted);line-height:1.6">
          Один раз в неделю (случайный день) открывается возможность
          обменять Мору на Алмазы по фиксированному курсу.<br><br>
          💡 <b>Курс обмена:</b> 3 000 🪙 = 1 💎<br>
          📊 <b>Дневной лимит:</b> 300 💎<br>
          ⏱ <b>Длительность:</b> 24 часа<br><br>
          Когда ивент начнётся — бот объявит в чатах!
        </div>
        ${when}
      </div>`;
      return;
    }
    el('mkt-exch').innerHTML=`
      <div class="exch-rate">
        <div class="er">1 💎 = ${fmt(d.rate)} 🪙</div>
        <div class="el">Осталось квоты: ${d.remaining.toFixed(1)} / ${d.daily_cap} 💎</div>
      </div>
      <div class="card">
        <div class="card-title">Сколько Алмазов получить?</div>
        <div class="irow"><span class="ik">У вас</span><span>${fmt(d.mora)} 🪙</span></div>
        <div class="irow"><span class="ik">Стоимость</span><span id="exch-cost" style="color:var(--gold)">—</span></div>
        <div class="range-wrap">
          <input type="range" id="exch-dia" min="1" max="${Math.floor(Math.min(d.remaining, d.mora/d.rate))}" value="1" step="1"
                 oninput="updExch(${d.rate},${d.mora})"/>
        </div>
        <div style="display:flex;align-items:center;gap:8px">
          <input type="number" id="exch-num" class="num-input" style="max-width:120px"
                 min="1" max="${Math.floor(Math.min(d.remaining, d.mora/d.rate))}" value="1"
                 oninput="syncExchRange(${d.rate},${d.mora})"/>
          <span style="font-size:14px">💎</span>
        </div>
        <button class="btn btn-gold btn-full" style="margin-top:10px" onclick="doExchange(this)">💱 Обменять</button>
      </div>`;
    updExch(d.rate, d.mora);
  }).catch(e=>{el('mkt-exch').innerHTML=`<div style="color:var(--red);font-size:12px;padding:10px">${e}</div>`;});
}
function updExch(rate, mora) {
  const v=parseInt(el('exch-dia')?.value||1);
  if(el('exch-num'))el('exch-num').value=v;
  const cost=v*rate;
  const c=el('exch-cost');
  if(c)c.textContent=`${fmt(cost)} 🪙${cost>mora?' ❌ недостаточно':''}`;
}
function syncExchRange(rate, mora) {
  const v=parseInt(el('exch-num')?.value||1);
  if(el('exch-dia'))el('exch-dia').value=v;
  updExch(rate, mora);
}
function doExchange(btn) {
  const v=parseInt(el('exch-num')?.value||0);
  if(!v){toast('Введите количество.',false);return;}
  btn.disabled=true;
  api('/exchange/convert',{method:'POST',body:JSON.stringify({diamonds:v})})
    .then(r=>{toast(`✅ +${r.diamonds_gained} 💎  −${fmt(r.mora_spent)} 🪙`);loadExchange();})
    .catch(e=>{toast(e,false);btn.disabled=false;});
}

// ── Dark Mora ─────────────────────────────────────────────────────────────────
function loadDarkMora() {
  // Load merchant status in parallel
  api('/dark-mora/merchant-status').then(m=>{
    const div = document.createElement('div');
    div.className = 'card';
    div.style.marginBottom = '10px';
    let merchantHtml = '';
    if(m.active) {
      merchantHtml = `<div style="background:rgba(201,168,76,.12);border:1px solid var(--border);border-radius:var(--r);padding:10px;margin-bottom:10px">
        <div style="font-size:13px;font-weight:700;color:var(--gold2);margin-bottom:4px">🕵️ Теневой Торговец ЗДЕСЬ!</div>
        <div style="font-size:11px;color:var(--muted)">Найди ключевое слово в пророчестве в чате → <code>бот слово, [слово]</code></div>
      </div>`;
    } else if(m.next_expected) {
      const next = new Date(m.next_expected);
      const diff = Math.max(0, Math.floor((next - Date.now()) / 1000));
      const days = Math.floor(diff/86400), hours = Math.floor((diff%86400)/3600);
      merchantHtml = `<div style="background:var(--dim);border-radius:var(--r);padding:10px;margin-bottom:10px">
        <div style="font-size:12px;font-weight:600;color:var(--bright);margin-bottom:3px">🕵️ Теневой Торговец</div>
        <div style="font-size:11px;color:var(--muted)">Следующий примерно через ${days ? days+'д '+hours+'ч' : hours+'ч'}</div>
        <div style="font-size:10px;color:var(--muted);margin-top:3px">${m.how_it_works}</div>
      </div>`;
    } else {
      merchantHtml = `<div style="background:var(--dim);border-radius:var(--r);padding:10px;margin-bottom:10px">
        <div style="font-size:12px;font-weight:600;color:var(--bright);margin-bottom:3px">🕵️ Теневой Торговец</div>
        <div style="font-size:11px;color:var(--muted)">${m.how_it_works}</div>
        <div style="font-size:10px;color:var(--muted);margin-top:3px">Появляется каждые ${m.cooldown_days} дня · Награда: ${m.reward_min}–${m.reward_max} 🌑</div>
      </div>`;
    }
    const wrap = el('dkc-merchant');
    if(wrap) wrap.innerHTML = merchantHtml;
  }).catch(()=>{});

  el('dkc').innerHTML=`
    <div id="dkc-merchant"></div>
    <div class="card card-gold">
    <div class="card-title">🌑 Тёмная Мора</div>
    <div style="font-size:12px;color:var(--muted);line-height:1.5;margin-bottom:12px">
      Нелегальная валюта. Нельзя купить — только заработать нечестным путём.<br>
      Тратится на Реликвии и Теневые темы.
    </div>
    <div class="divider"></div>
    <div style="font-size:12px;font-weight:600;color:var(--bright);margin:10px 0 6px">🎲 Контрабанда</div>
    <div style="font-size:11px;color:var(--muted);margin-bottom:8px">
      Ставь Мору на рискованную сделку. 40% — успех, 35% — провал, 25% — поймали.<br>
      Кулдаун: 7 дней. При поимке — штраф 14 дней.
    </div>
    <input id="contra-stake" type="number" class="num-input" placeholder="Ставка (100–5000 🪙)" min="100" max="5000" step="50"/>
    <button class="btn btn-gold btn-full" onclick="doContrabanda(this)">🎲 Рискнуть</button>
    <div class="divider"></div>
    <div style="font-size:12px;font-weight:600;color:var(--bright);margin:10px 0 6px">🌑 Культ Бездны</div>
    <div style="font-size:11px;color:var(--muted);margin-bottom:8px">
      Ритуал доступен с 23:00 до 01:00 UTC при стрике 7+, уровне 6+, 3+ питомцах.<br>
      Награда: 10–20 🌑 раз в 30 дней.
    </div>
    <button class="btn btn-ghost btn-full" onclick="doRitual(this)">🌑 Провести ритуал</button>
  </div>`;
}
function doContrabanda(btn) {
  const v=parseInt(el('contra-stake')?.value||0);
  if(!v){toast('Введите ставку.',false);return;}
  OM('🎲 Подтверждение',`<div class="irow"><span class="ik">Ставка</span><span style="color:var(--gold)">${fmt(v)} 🪙</span></div>
    <div style="font-size:11px;color:var(--muted);margin-top:8px">40% успех · 35% провал · 25% поймают (штраф 14д)</div>`,
    [{l:'🎲 Рискнуть',c:'btn-red',f:`runContrabanda(${v})`},{l:'Отмена',c:'btn-ghost',f:'CM()'}]);
}
function runContrabanda(stake) {
  CM();
  api('/dark-mora/contrabanda',{method:'POST',body:JSON.stringify({stake})})
    .then(r=>toast(r.result_text||'Готово!',r.success))
    .catch(e=>toast(e,false));
}
function doRitual(btn) {
  btn.disabled=true;
  api('/dark-mora/ritual',{method:'POST'}).then(r=>toast(r.message||'✅',true)).catch(e=>{toast(e,false);btn.disabled=false;});
}

// swArena and swMkt are defined above with correct dark/exch handling

// ── Auction search ────────────────────────────────────────────────────────────
let _allLots=[];
function filterAuction(q) {
  const f=q.toLowerCase();
  const lots=f?_allLots.filter(l=>l.item_name.toLowerCase().includes(f)):_allLots;
  renderLots(lots);
}
function renderLots(lots) {
  if (!el('lot-list')) return;
  el('lot-list').innerHTML = lots.length ? lots.map(l => {
    const ends = new Date((l.ends_at+'').includes('T') ? l.ends_at : l.ends_at+'Z');
    const diff = Math.max(0, Math.floor((ends - Date.now()) / 1000));
    const tl = diff > 3600 ? Math.floor(diff/3600)+'ч' : Math.floor(diff/60)+'м';
    const hasBids = !!l.has_bids;
    const curBid = l.current_bid || l.min_bid;
    const minNext = l.min_next_bid || (hasBids ? Math.ceil(curBid * 1.05) + 1 : Math.ceil(l.min_bid));
    const buyout = l.buyout || 0;
    const bidArgs = `${l.id},'${(l.item_name||'').replace(/'/g,'')}',${curBid},${minNext},${hasBids},${buyout}`;
    return `<div class="lot-card">
      <div class="lot-name">${l.item_name}${l.quantity>1?' ×'+l.quantity:''}</div>
      <div class="lot-meta">
        <span>от ${l.seller_name||'Игрок'}</span>
        <span>⏳ ${tl}</span>
        ${hasBids ? '<span style="color:var(--green);font-size:10px">🔥 Есть ставки</span>' : '<span style="color:var(--muted);font-size:10px">Первая ставка</span>'}
      </div>
      <div style="display:flex;align-items:center;justify-content:space-between">
        <div>
          <div class="lot-bid">${fmt(curBid)} 🪙</div>
          ${buyout ? `<div style="font-size:10px;color:var(--teal)">⚡ Выкуп: ${fmt(buyout)} 🪙</div>` : ''}
        </div>
        <button class="btn btn-sm btn-gold" onclick="openBidModal(${bidArgs})">💰 Ставка</button>
      </div>
    </div>`;
  }).join('') : '<div style="color:var(--muted);font-size:12px;padding:12px;text-align:center">Лотов нет.</div>';
}

// ── Duel challenge via web ────────────────────────────────────────────────────
function openDuelChallenge() {
  OM('⚔️ Вызов на дуэль',`
    <div style="font-size:11px;color:var(--muted);margin-bottom:10px">
      Вызов отправляется в чат. Соперник принимает через бота.
    </div>
    <input id="duel-user" type="text" class="num-input" placeholder="@username соперника"/>
    <input id="duel-stake" type="number" class="num-input" placeholder="Ставка 🪙 (200–15000)" min="200" max="15000"/>`,
    [{l:'⚔️ Вызвать',c:'btn-red',f:'submitDuelChallenge(this)'},{l:'Отмена',c:'btn-ghost',f:'CM()'}]);
}
function submitDuelChallenge(btn) {
  const username=el('duel-user')?.value?.trim().replace('@','');
  const stake=parseFloat(el('duel-stake')?.value||0);
  if(!username||!stake){toast('Заполните все поля.',false);return;}
  if(!_cid){toast('Нужен Профиль с чатом.',false);return;}
  btn.disabled=true;
  api('/duels/challenge',{method:'POST',body:JSON.stringify({username,stake,chat_id:_cid})})
    .then(()=>{toast('⚔️ Вызов отправлен!');CM();loadDuels();})
    .catch(e=>{toast(e,false);btn.disabled=false;});
}

// doSpin and closeSpinResult defined above (no loadGacha to avoid overwriting result)

// ── Browser Notifications ─────────────────────────────────────────────────────
function requestBrowserNotif() {
  if ('Notification' in window && Notification.permission === 'default') {
    Notification.requestPermission().then(p => { if(p==='granted') toast('✅ Уведомления включены!'); });
  }
}
function browserNotif(title, body) {
  if ('Notification' in window && Notification.permission === 'granted' && document.hidden) {
    new Notification(title, {body, icon: './favicon.ico'});
  }
}
// Request permission when user first connects WS
// Override connectWS with browser notification support
function connectWS() {
  if (!_uid) return;
  requestBrowserNotif();
  const wsUrl = BASE.replace('https://','wss://').replace('http://','ws://') + '/ws/'+_uid;
  _ws = new WebSocket(wsUrl);
  _ws.onmessage = e => {
    const ev = JSON.parse(e.data);
    if(ev.type!=='pong') showWsNotif(ev);
  };
  _ws.onclose = () => { setTimeout(connectWS, 4000); };
  _ws.onerror = () => {};
}

// ── WS ping/pong — prevents Cloudflare 100s idle timeout ─────────────────────
setInterval(() => { if (_ws?.readyState === WebSocket.OPEN) _ws.send('ping'); }, 25000);

// ── Refresh button helper ─────────────────────────────────────────────────────
function addRefreshBtn(containerId, reloadFn) {
  const c = el(containerId);
  if(!c) return;
  const ts = new Date().toLocaleTimeString('ru', {hour:'2-digit',minute:'2-digit'});
  const btn = `<div style="text-align:right;padding:0 0 8px">
    <button class="btn btn-ghost" style="font-size:10px;padding:3px 8px"
            onclick="${reloadFn}">🔄 Обновить · ${ts}</button>
  </div>`;
  if(!c.querySelector('[onclick*="Обновить"]')) c.insertAdjacentHTML('afterbegin', btn);
}

// ── Marriage ──────────────────────────────────────────────────────────────────
function loadMarriage() {
  el('pro-marriage').innerHTML='<div class="loader">Загрузка...</div>';
  api('/marriage/').then(m=>{
    if(!m.married){
      el('pro-marriage').innerHTML=`<div class="card" style="text-align:center;padding:20px">
        <div style="font-size:32px;margin-bottom:8px">💔</div>
        <div style="font-size:14px;font-weight:600;color:var(--bright)">Вы не состоите в браке</div>
        <div style="font-size:11px;color:var(--muted);margin-top:6px">Команда в боте: <code>бот брак, @username</code></div>
      </div>`;
      return;
    }
    const pets=m.family_pets||[];
    el('pro-marriage').innerHTML=`
      <div class="card card-gold">
        <div style="text-align:center;padding:10px 0 14px">
          <div style="font-size:28px;margin-bottom:6px">💍</div>
          <div style="font-size:14px;font-weight:700;color:var(--bright)">${m.partner_name||'Партнёр'}</div>
          <div style="font-size:11px;color:var(--muted);margin-top:3px">В браке ${m.days} дней</div>
        </div>
        <div class="irow"><span class="ik">Семейный банк</span><span style="color:var(--gold);font-weight:700">${fmt(m.family_balance)} 🪙</span></div>
        <div style="display:flex;gap:7px;margin-top:10px">
          <input id="bank-amt" type="number" class="num-input" style="margin:0;flex:1" placeholder="Сумма 🪙" min="1"/>
          <button class="btn btn-sm btn-gold" onclick="familyBank('deposit')">📥 Вложить</button>
          <button class="btn btn-sm btn-ghost" onclick="familyBank('withdraw')">📤 Забрать</button>
        </div>
      </div>
      ${pets.length?`<div class="card"><div class="card-title">🐾 Питомцы семьи (${pets.length})</div>
        ${pets.map(p=>`<div class="pcard"><div class="pcol">
          <div class="pn">${p.name||p.species_id} ${rc(p.rarity)}</div>
          <div class="ps">Lv${p.pet_level} · ${PL[p.placement]||p.placement}</div>
          <div class="fat-bar"><div class="fat-fill" style="width:${p.fatigue}%;background:${fatC(p.fatigue)}"></div></div>
        </div></div>`).join('')}
      </div>`:''}`;
    el('pro-marriage')._mid=m.marriage_id;
  }).catch(e=>{el('pro-marriage').innerHTML=`<div class="err">${e}</div>`;});
}
function familyBank(action) {
  const v=parseFloat(el('bank-amt')?.value||0);
  if(!v||v<=0){toast('Введите сумму.',false);return;}
  const mid=el('pro-marriage')?._mid;
  if(!mid){toast('Нет данных о браке.',false);return;}
  api('/marriage/bank',{method:'POST',body:JSON.stringify({marriage_id:mid,amount:v,action})})
    .then(r=>{toast(`✅ ${r.message}`);loadMarriage();})
    .catch(e=>toast(e,false));
}

// ── Wallet history ────────────────────────────────────────────────────────────
function loadWallet() {
  el('pro-wallet').innerHTML='<div class="loader">Загрузка...</div>';
  api('/wallet/history').then(txs=>{
    if(!txs.length){el('pro-wallet').innerHTML='<div class="loader">Транзакций нет.</div>';return;}
    el('pro-wallet').innerHTML='<div class="card"><div class="card-title">История транзакций</div>'+
      txs.map(t=>{
        const mora=t.delta_mora?`<span style="color:${t.delta_mora>0?'var(--green)':'var(--red)'};font-weight:600">${t.delta_mora>0?'+':''}${fmt(t.delta_mora)} 🪙</span>`:'';
        const dia=t.delta_diamonds?`<span style="color:${t.delta_diamonds>0?'var(--blue)':'var(--red)'};font-weight:600">${t.delta_diamonds>0?'+':''}${t.delta_diamonds} 💎</span>`:'';
        return `<div style="display:flex;align-items:center;gap:8px;padding:8px 0;border-bottom:1px solid var(--border2)">
          <div style="flex:1">
            <div style="font-size:12px;font-weight:600;color:var(--bright)">${t.label}</div>
            ${t.note?`<div style="font-size:10px;color:var(--muted)">${t.note}</div>`:''}
            <div style="font-size:10px;color:var(--muted)">${t.created_at}</div>
          </div>
          <div style="text-align:right">${mora} ${dia}</div>
        </div>`;
      }).join('')+'</div>';
  }).catch(e=>{el('pro-wallet').innerHTML=`<div class="err">${e}</div>`;});
}

// ── Daily Deal ────────────────────────────────────────────────────────────────
let _dealRefreshAt = null;
function loadDeal() {
  el('mkt-deal').innerHTML='<div class="loader">Загрузка...</div>';
  api('/daily-deal/').then(d=>{
    _dealRefreshAt = d.refreshes_at;
    const deals = d.deals||[];
    el('mkt-deal').innerHTML=`
      <div style="background:var(--gold-dim);border:1px solid var(--border);border-radius:var(--r);padding:10px;margin-bottom:12px;text-align:center">
        <div style="font-size:11px;color:var(--gold);text-transform:uppercase;letter-spacing:1px">Акция обновится через</div>
        <div id="deal-timer" style="font-size:20px;font-weight:700;color:var(--gold2);font-family:monospace">--:--:--</div>
      </div>
      <div class="balrow">
        <div class="bal"><div class="bv">🪙 ${fmt(d.mora)}</div><div class="bl">Мора</div></div>
        <div class="bal"><div class="bv">💎 ${d.diamonds.toFixed(1)}</div><div class="bl">Алмазы</div></div>
      </div>
      ${deals.length?'<div class="card"><div class="card-title">🏷 Предложения сегодня</div>'+
        deals.map(deal=>{
          const price=deal.price_mora?`${fmt(deal.price_mora)} 🪙`:deal.price_diamonds?`${deal.price_diamonds} 💎`:'—';
          const purchased=deal.user_purchased>=deal.max_per_user;
          return `<div class="shop-row">
            <div class="shop-icon">${(deal.item_name||'?').split(' ')[0]}</div>
            <div class="shop-info">
              <div class="shop-name">${deal.item_name||'?'} ${deal.quantity>1?'×'+deal.quantity:''}</div>
              <div class="shop-price">${price}</div>
              <div class="shop-desc">${deal.item_description||''}</div>
            </div>
            <button class="btn btn-sm ${purchased?'btn-ghost':'btn-gold'}" ${purchased?'disabled':''} onclick="buyDeal(${deal.id},this)">
              ${purchased?'✓ Куплено':'Купить'}
            </button>
          </div>`;
        }).join('')+'</div>'
      :'<div class="loader">Акций нет.</div>'}`;
    startDealTimer();
  }).catch(e=>{el('mkt-deal').innerHTML=`<div class="err">${e}</div>`;});
}
function startDealTimer() {
  if(_dealRefreshAt) {
    const tick=()=>{
      const t=el('deal-timer');if(!t)return;
      const diff=Math.max(0,Math.floor((new Date(_dealRefreshAt)-Date.now())/1000));
      if(diff<=0){t.textContent='Скоро обновится...';return;}
      const h=Math.floor(diff/3600),m=Math.floor((diff%3600)/60),s=diff%60;
      t.textContent=`${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`;
    };
    tick();
    setInterval(tick,1000);
  }
}
function buyDeal(dealId,btn) {
  btn.disabled=true;
  api('/daily-deal/buy',{method:'POST',body:JSON.stringify({deal_id:dealId})})
    .then(r=>{toast(`✅ Куплено! +${r.qty}×${r.item_id}`);loadDeal();})
    .catch(e=>{toast(e,false);btn.disabled=false;});
}

// ── Promo code ────────────────────────────────────────────────────────────────
function loadPromo() {
  el('mkt-promo').innerHTML=`
    <div class="card card-gold">
      <div class="card-title">🎫 Активировать промокод</div>
      <div style="font-size:12px;color:var(--muted);margin-bottom:10px;line-height:1.5">
        Введите промокод и нажмите «Активировать».<br>
        Каждый промокод — одноразовый.
      </div>
      <input id="promo-input" type="text" class="num-input"
             placeholder="ПРОМОКОД" style="text-transform:uppercase"
             oninput="this.value=this.value.toUpperCase()"/>
      <button class="btn btn-gold btn-full" style="margin-top:8px" onclick="redeemPromo(this)">
        🎫 Активировать
      </button>
      <div id="promo-result" style="margin-top:8px"></div>
    </div>`;
}
function redeemPromo(btn) {
  const code=el('promo-input')?.value?.trim();
  if(!code){toast('Введите промокод.',false);return;}
  btn.disabled=true;
  api('/promo/redeem',{method:'POST',body:JSON.stringify({code})})
    .then(r=>{
      el('promo-result').innerHTML=`<div class="ok-box">✅ ${r.message}</div>`;
      el('promo-input').value='';
    })
    .catch(e=>{
      el('promo-result').innerHTML=`<div class="err">${e}</div>`;
    })
    .finally(()=>{btn.disabled=false;});
}

// ── switchPro update for new profile tabs ─────────────────────────────────────
function switchPro(tab, btn) {
  _proTab = tab;
  document.querySelectorAll('#pg-profile .tb').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');
  ['main','streak','ach','marriage','wallet'].forEach(t=>el('pro-'+t).style.display=t===tab?'':'none');
  if(tab==='streak') loadStreak();
  else if(tab==='ach') loadAch();
  else if(tab==='marriage') loadMarriage();
  else if(tab==='wallet') loadWallet();
}

// swMkt: add deal and promo
function swMkt(tab, _btn) {
  const btn = _btn || document.querySelector('#pg-market .tb');
  _mktTab = tab;
  document.querySelectorAll('#pg-market .tb').forEach(b=>b.classList.remove('active'));
  if(btn) btn.classList.add('active');
  const bd = el('balrow'); bd.style.display = tab === 'shop' ? 'flex' : 'none';
  ['auc','shop','inv','exch','deal','promo'].forEach(t=>el('mkt-'+t).style.display=t===tab?'':'none');
  ({auc:loadAuction, shop:loadShopCatalog, inv:loadInventory,
    exch:loadExchange, deal:loadDeal, promo:loadPromo}[tab]||loadAuction)();
}

// ── Auto-refresh ──────────────────────────────────────────────────────────────
setInterval(()=>{if(_loaded.has('profile'))loadProfile();},300000);
setInterval(()=>{if(_loaded.has('zoo'))api('/zoo/expeditions').then(d=>renderExps(d)).catch(()=>{});},30000);

// Refresh current page data
function refreshPage() {
  const page = document.querySelector('.nb.active')?.getAttribute('onclick')?.match(/'(\w+)'/)?.[1];
  const loaders = {profile:loadProfile, zoo:()=>{_zooData=null;loadZoo();},
                   arena:loadArena, market:loadMarket, coll:loadColl};
  if(page && loaders[page]) { _loaded.delete(page); loaders[page](); toast('🔄 Обновлено!'); }
}
</script>
</body>
</html>"""
