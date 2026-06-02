"""FastAPI/main.py — Predvestnik Mini App entry point. Adapter layer only."""
import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

from infrastructure.database import create_pool, get_pool
from infrastructure.pg_adapter import PGAdapter
from FastAPI.auth import verify_login_widget, create_session_token
from FastAPI import notifications
from FastAPI.routers import (profile, top, inventory, shop, zoo, gacha,
                              craft, quests, auction, duels, achievements,
                              themes, streak)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_pool()
    yield


app = FastAPI(title="Predvestnik Mini App", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

for r in [profile.router, top.router, inventory.router, shop.router, zoo.router,
          gacha.router, craft.router, quests.router, auction.router, duels.router,
          achievements.router, themes.router, streak.router]:
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

@app.get("/", response_class=HTMLResponse)
async def mini_app():
    return HTMLResponse(_HTML.replace("{{BOT_USERNAME}}", os.getenv("BOT_USERNAME","IIIPredvestnikIIIBot")))


_HTML = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1.0,viewport-fit=cover"/>
<title>Предвестник</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<script src="https://telegram.org/js/telegram-widget.js?22"
        data-telegram-login="{{BOT_USERNAME}}" data-size="large" data-radius="8"
        data-onauth="onTelegramWidgetAuth(user)" data-request-access="write" async></script>
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

/* Themes */
.theme-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.theme-card{background:var(--s);border-radius:var(--r);padding:12px;cursor:pointer;
            border:1px solid var(--border2);transition:.15s;position:relative}
.theme-card:hover{border-color:var(--border)}
.theme-card.owned{border-color:rgba(82,179,96,.3)}
.theme-card.active-theme{border-color:var(--gold);box-shadow:0 0 8px rgba(201,168,76,.2)}
.theme-preview{font-size:12px;color:var(--muted);margin:4px 0;font-family:monospace;overflow:hidden;white-space:nowrap;text-overflow:ellipsis}
.theme-name{font-size:13px;font-weight:600;color:var(--bright);margin-bottom:2px}
.theme-price{font-size:11px;color:var(--gold);margin-top:4px}

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

/* Modal */
dialog{background:var(--s);border:1px solid var(--border);border-radius:var(--r-lg);
       padding:0;max-width:380px;width:90%;color:var(--text);animation:slideUp .18s ease}
dialog::backdrop{background:rgba(0,0,0,.82);backdrop-filter:blur(5px)}
.mhead{display:flex;align-items:center;justify-content:space-between;
       padding:13px 15px;border-bottom:1px solid var(--border2)}
.mtitle{font-size:14px;font-weight:700;color:var(--bright)}
.mclose{background:none;border:none;color:var(--muted);font-size:20px;cursor:pointer;padding:2px 6px;line-height:1}
.mbody{padding:13px 15px;max-height:60vh;overflow-y:auto}
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
</style>
</head>
<body>
<div id="toast" class="toast"></div>

<div id="login-ov" class="login-ov hidden">
  <div style="font-size:52px;animation:glow 2s infinite">🔮</div>
  <h1>Предвестник</h1>
  <p>Войдите через Telegram для доступа к игровому профилю.</p>
  <div id="tg-login-widget"></div>
  <p style="font-size:10px;color:var(--dim)">Данные защищены подписью Telegram.</p>
</div>

<dialog id="modal">
  <div class="mhead"><span id="mt" class="mtitle"></span><button class="mclose" onclick="CM()">✕</button></div>
  <div id="mb" class="mbody"></div>
  <div id="mf" class="mfoot"></div>
</dialog>

<!-- 1. Профиль -->
<div id="pg-profile" class="page active">
  <div class="tabs">
    <button class="tb active" onclick="switchPro('main',this)">👤 Профиль</button>
    <button class="tb" onclick="switchPro('streak',this)">🔥 Стрик</button>
    <button class="tb" onclick="switchPro('ach',this)">🏆 Ачивки</button>
  </div>
  <div id="pro-main"><div class="sk" style="height:140px;border-radius:var(--r)"></div></div>
  <div id="pro-streak" style="display:none"></div>
  <div id="pro-ach" style="display:none"></div>
</div>

<!-- 2. Зоопарк -->
<div id="pg-zoo" class="page">
  <div id="zoo-exp-wrap"></div>
  <div class="tabs">
    <button class="tb active" onclick="swZoo('active',this)">⚔️ Актив.</button>
    <button class="tb" onclick="swZoo('passive',this)">🛡 Пасс.</button>
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
  </div>
  <div id="ar-quests"><div id="qc" class="loader">Загрузка...</div></div>
  <div id="ar-gacha" style="display:none"><div id="gc" class="loader">Загрузка...</div></div>
  <div id="ar-craft" style="display:none"><div id="cc" class="loader">Загрузка...</div></div>
  <div id="ar-duels" style="display:none"><div id="dc" class="loader">Загрузка...</div></div>
</div>

<!-- 4. Рынок -->
<div id="pg-market" class="page">
  <div class="tabs">
    <button class="tb active" onclick="swMkt('auc',this)">🏛 Аукцион</button>
    <button class="tb" onclick="swMkt('shop',this)">🛒 Магазин</button>
    <button class="tb" onclick="swMkt('inv',this)">🎒 Инвентарь</button>
  </div>
  <div id="balrow" class="balrow" style="display:none"></div>
  <div id="mkt-auc"><div class="loader">Загрузка...</div></div>
  <div id="mkt-shop" style="display:none"></div>
  <div id="mkt-inv" style="display:none"></div>
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
</nav>

<script>
const tg = window.Telegram?.WebApp;
if (tg) { tg.ready(); tg.expand(); tg.setHeaderColor('#08090f'); }

const BASE = (location.origin + location.pathname).replace(/\/$/, '');
const INIT_DATA = tg?.initData || '';
const SK = 'pv_sess';
const MEDALS = ['🥇','🥈','🥉'];
const PL = {active:'Активный',passive:'Пассивный',storage:'Склад'};
const RC = {common:'rc-common',uncommon:'rc-uncommon',rare:'rc-rare',
            epic:'rc-epic',legendary:'rc-legendary',shadow:'rc-shadow'};

let _cid = 0, _uid = 0, _actTab='quests', _zooTab='active', _arenaTab='quests';
let _zooData=null, _invData=[], _expTimer=null, _themeData=null, _mktTab='auc';
let _proTab='main';

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
  const titles = {expedition_done:'⚔️ Поход завершён!', quest_done:'✅ Квест выполнен!'};
  const bodies = {
    expedition_done: e => `${e.pet} вернулся: +${fmt(e.mora)} 🪙 +${e.xp} XP`,
    quest_done: e => `«${e.quest}» — получено!`,
  };
  const div = document.createElement('div');
  div.className = 'ws-notif';
  div.innerHTML = `<div class="wn-title">${titles[event.type]||'🔮 Уведомление'}</div>
                   <div class="wn-body">${(bodies[event.type]||(() => ''))(event)}</div>`;
  document.body.appendChild(div);
  setTimeout(() => div.remove(), 5000);
  if (_loaded.has('zoo') && event.type === 'expedition_done') { _zooData=null; loadZoo(); }
}

// ── Utils ─────────────────────────────────────────────────────────────────────
const el = id => document.getElementById(id);
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
  el('pro-main').innerHTML='<div class="sk" style="height:140px;border-radius:var(--r)"></div>';
  api('/profile/me').then(d=>{
    _cid=d.chats?.[0]?.chat_tg_id||0;
    if(d.user_id) _uid=d.user_id;
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

function loadAch() {
  el('pro-ach').innerHTML='<div class="loader">Загрузка...</div>';
  api('/achievements/').then(achs=>{
    el('pro-ach').innerHTML='<div class="card"><div class="card-title">Достижения</div>'+
      achs.map(a=>`<div class="ach-item">
        <div class="ach-head">
          <div class="ach-icon">${a.icon}</div>
          <div class="ach-name">${a.name}</div>
          <div class="ach-lvl">${a.completed?'MAX':a.level>0?`Lv${a.level}`:'—'} / ${a.max_level}</div>
        </div>
        <div class="ach-bar"><div class="ach-fill" style="width:${a.pct}%"></div></div>
        <div class="ach-prog">${fmt(a.progress)} / ${fmt(a.next_threshold||a.progress)} ${a.completed?'✅':''}</div>
      </div>`).join('')+'</div>';
  }).catch(e=>{el('pro-ach').innerHTML=`<div style="color:var(--red);padding:10px;font-size:12px">${e}</div>`;});
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
  const pets=_zooData.pets.filter(p=>tab==='storage'?p.placement==='storage':p.placement===tab);
  const food=_zooData.available_food;
  const foodHtml=Object.entries(food).map(([fid,f])=>`<div class="fopt" onclick="doFeed(${null},'${fid}',this)"><span class="fn">${f.name}</span><span class="fq">×${f.qty}</span><span class="fr" style="color:var(--green)">−${f.restore}</span></div>`).join('')||'<div style="color:var(--muted);font-size:11px;padding:5px">Нет корма</div>';
  el('zoo-c').innerHTML=pets.length
    ?pets.map(p=>`<div class="pcard"><div class="pcol">
      <div class="pn">${p.name||p.species_id} ${rc(p.rarity)}</div>
      <div class="ps">Lv${p.pet_level} · ${PL[p.placement]||p.placement}</div>
      <div class="fat-bar"><div class="fat-fill" style="width:${p.fatigue}%;background:${fatC(p.fatigue)}"></div></div>
      <div style="display:flex;gap:7px;margin-top:5px;align-items:center">
        <span style="font-size:10px;color:var(--muted)">${p.fatigue}% уст.</span>
        ${p.placement!=='storage'?`<button class="btn btn-sm btn-teal" onclick="openFeedModal(${p.id},${p.fatigue},'${p.name||p.species_id}')">🍖</button>`:''}
        <button class="btn btn-sm btn-ghost" onclick="openMoveModal(${p.id},'${p.placement}','${p.name||p.species_id}')">↔</button>
      </div>
    </div></div>`).join('')
    :`<div style="color:var(--muted);font-size:12px;padding:16px;text-align:center">Питомцев в «${PL[tab]||tab}» нет.</div>`;
}
function openFeedModal(pid,fat,name) {
  if(!_zooData)return;
  const fHtml=Object.entries(_zooData.available_food).map(([fid,f])=>`<div class="fopt" onclick="doFeed(${pid},'${fid}',this)"><span class="fn">${f.name}</span><span class="fq">×${f.qty}</span><span class="fr" style="color:var(--green)">−${f.restore}</span></div>`).join('')||'<div style="color:var(--red);font-size:12px">Корма нет — купите в Рынке.</div>';
  OM(`🍖 ${name}`,`<div class="irow"><span class="ik">Усталость</span><span style="color:${fatC(fat)}">${fat}%</span></div><div class="divider"></div>${fHtml}`,[{l:'Отмена',c:'btn-ghost',f:'CM()'}]);
}
function doFeed(pid,fid,row) {
  row.style.opacity='.4';
  api('/zoo/feed',{method:'POST',body:JSON.stringify({pet_id:pid,food_id:fid})})
    .then(r=>{toast(`✅ ${r.fatigue_before}%→${r.fatigue_after}%`);CM();_zooData=null;loadZoo();})
    .catch(e=>{toast(e,false);row.style.opacity='1';});
}
function openMoveModal(pid,cur,name) {
  const opts=['active','passive','storage'].filter(p=>p!==cur);
  const html=opts.map(p=>`<button class="btn btn-full ${p==='storage'?'btn-ghost':p==='active'?'btn-teal':'btn-green'}" onclick="doMove(${pid},'${p}',this)">
    ${p==='active'?'⚔️ В Активные':p==='passive'?'🛡 В Пассивные':'📦 На Склад'}</button>`).join('');
  OM(`↔ ${name}`,`<div class="irow"><span class="ik">Сейчас</span><span>${PL[cur]||cur}</span></div><div class="divider"></div>${html}`,[{l:'Отмена',c:'btn-ghost',f:'CM()'}]);
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
  api('/zoo/species').then(list=>{
    const g={};list.forEach(s=>(g[s.rarity]=g[s.rarity]||[]).push(s));
    el('zoo-c').innerHTML=Object.entries(g).map(([r,pets])=>`<div class="card">
      <div class="card-title">${{common:'⬜ Обычные',rare:'🟦 Редкие',epic:'🟣 Эпические',legendary:'🟡 Легендарные'}[r]||r}</div>
      ${pets.map(p=>`<div style="padding:8px 0;border-bottom:1px solid var(--border2)">
        <div style="font-size:13px;font-weight:600;color:var(--bright);margin-bottom:3px">${p.name}</div>
        <div style="font-size:10px;color:${p.role==='active'?'var(--teal)':'var(--blue)'};margin-bottom:4px">${p.role==='active'?'⚔️ Активная':'🛡 Пассивная'} роль</div>
        <div style="font-size:11px;color:var(--muted);line-height:1.4">${p.desc}</div>
      </div>`).join('')}
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
  ['quests','gacha','craft','duels'].forEach(t=>el('ar-'+t).style.display=t===tab?'':'none');
  ({quests:loadQuests,gacha:loadGacha,craft:loadCraft,duels:loadDuels}[tab])();
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
    el('gc').innerHTML=`<div class="balrow"><div class="bal"><div class="bv">🪙 ${fmt(d.mora)}</div><div class="bl">Мора</div></div></div>
      <div class="card"><div class="card-title">Выберите крутку</div>${d.spin_types.map(s=>`<div class="spin-row" onclick="doSpin('${s.spin_type}',this)">
        <span style="font-size:20px">🎲</span>
        <span style="flex:1;font-size:13px;font-weight:600">${s.label}</span>
        ${s.token_qty?`<span style="font-size:11px;color:var(--green)">🎟 ×${s.token_qty}</span>`:''}
        <span style="font-size:12px;color:var(--gold)">${s.cost_mora?fmt(s.cost_mora)+' 🪙':s.cost_dia+' 💎'}</span>
      </div>`).join('')}</div><div id="spin-res"></div>`;
  }).catch(e=>{el('gc').innerHTML=`<div style="color:var(--red);font-size:12px;padding:10px">${e}</div>`;});
}
function doSpin(st,row) {
  row.style.opacity='.5';row.style.pointerEvents='none';
  api('/gacha/spin',{method:'POST',body:JSON.stringify({spin_type:st})}).then(r=>{
    const mora=r.mora?`🪙 ${fmt(r.mora)}`:'',dia=r.diamonds?`💎 ${r.diamonds}`:'';
    const items=(r.items||[]).map(i=>`${i.name} ×${i.qty}`).join(', ');
    const dups=(r.dup_outcomes||[]).map(d=>`${d.species||''} дубл`).join(', ');
    const got=[mora,dia,items,dups].filter(Boolean).join(' · ')||'—';
    el('spin-res').innerHTML=`<div class="spin-res"><div style="font-size:13px;font-weight:700;color:var(--gold2);margin-bottom:5px">🎉 Результат!</div><div style="font-size:13px">${got}</div></div>`;
    loadGacha();
  }).catch(e=>{toast(e,false);row.style.opacity='1';row.style.pointerEvents='';});
}
function loadCraft() {
  api('/craft/').then(r=>{
    el('cc').innerHTML=r.length?'<div class="card"><div class="card-title">Рецепты</div>'+r.map(rc=>
      `<div style="padding:10px 0;border-bottom:1px solid var(--border2)">
        <div style="font-size:13px;font-weight:600;color:var(--bright);margin-bottom:4px">${rc.name}</div>
        <div>${rc.ingredients_status.map(i=>`<span style="color:${i.ok?'var(--green)':'var(--red)'};font-size:11px">${i.item_name}: ${i.have}/${i.needed}</span>`).join('  ')}</div>
        <button class="btn btn-sm ${rc.can_craft?'btn-gold':'btn-ghost'}" style="margin-top:7px" ${rc.can_craft?'':'disabled'} onclick="doCraft('${rc.recipe_id}',this)">${rc.can_craft?'⚗️ Скрафтить':'🔒 Не хватает'}</button>
      </div>`).join('')+'</div>':'<div class="loader">Рецептов нет.</div>';
  }).catch(e=>{el('cc').innerHTML=`<div style="color:var(--red);font-size:12px;padding:10px">${e}</div>`;});
}
function doCraft(id,btn) {
  btn.disabled=true;
  api(`/craft/${id}`,{method:'POST'}).then(r=>{toast(`✅ ${r.name}!`);loadCraft();}).catch(e=>{toast(e,false);btn.disabled=false;});
}
function loadDuels() {
  Promise.all([api('/duels/active'),api('/duels/history')]).then(([active,hist])=>{
    let html='';
    if(active.length) {
      html+=`<div class="card"><div class="card-title">⏳ Входящие вызовы</div>${active.filter(d=>d.challenged_id==_uid).map(d=>`
        <div class="duel-card">
          <div class="duel-vs">${d.challenger_name||'Игрок'} вызывает на дуэль</div>
          <div class="duel-stake">Ставка: ${fmt(d.stake)} 🪙</div>
          <button class="btn btn-sm btn-red" style="margin-top:6px" onclick="declineDuel(${d.id},this)">❌ Отклонить</button>
        </div>`).join('')}</div>`;
    }
    if(hist.length) {
      html+=`<div class="card"><div class="card-title">📜 История дуэлей</div>${hist.map(d=>{
        const won=d.winner_id==_uid;const isDone=d.status==='finished';
        const vs=d.challenger_id==_uid?d.challenged_name:d.challenger_name;
        return `<div class="duel-card">
          <div style="display:flex;justify-content:space-between">
            <div class="duel-vs">vs ${vs||'Игрок'}</div>
            <div class="duel-result${isDone?(won?' win':' lose'):''}">
              ${isDone?(won?'Победа ✓':'Поражение'):{pending:'В ожидании',timeout:'Истёк',declined:'Отклонён'}[d.status]||d.status}
            </div>
          </div>
          <div class="duel-stake">${fmt(d.stake)} 🪙</div>
        </div>`;
      }).join('')}</div>`;
    }
    el('dc').innerHTML=html||'<div class="loader">Дуэлей нет. Вызывайте соперников в чате!</div>';
  }).catch(e=>{el('dc').innerHTML=`<div style="color:var(--red);font-size:12px;padding:10px">${e}</div>`;});
}
function declineDuel(id,btn) {
  btn.disabled=true;
  api('/duels/decline',{method:'POST',body:JSON.stringify({duel_id:id})})
    .then(()=>{toast('✅ Вызов отклонён.');loadDuels();}).catch(e=>{toast(e,false);btn.disabled=false;});
}

// ── Market ────────────────────────────────────────────────────────────────────
function loadMarket(){swMkt('auc',document.querySelector('#pg-market .tb'));}
function swMkt(tab,btn) {
  _mktTab=tab;
  document.querySelectorAll('#pg-market .tb').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');
  const bd=el('balrow'); bd.style.display=tab!=='auc'?'flex':'none';
  el('mkt-auc').style.display=tab==='auc'?'':'none';
  el('mkt-shop').style.display=tab==='shop'?'':'none';
  el('mkt-inv').style.display=tab==='inv'?'':'none';
  ({auc:loadAuction,shop:loadShopCatalog,inv:loadInventory}[tab])();
}

function loadAuction() {
  api('/auction/lots').then(lots=>{
    el('mkt-auc').innerHTML=lots.length
      ?'<div class="card"><div class="card-title">Активные лоты</div>'+lots.map(l=>{
        const ends=new Date((l.ends_at+'').includes('T')?l.ends_at:l.ends_at+'Z');
        const diff=Math.max(0,Math.floor((ends-Date.now())/1000));
        const timeLeft=diff>3600?Math.floor(diff/3600)+'ч':(Math.floor(diff/60))+'мин';
        return `<div class="lot-card">
          <div class="lot-name">${l.item_name} ${l.quantity>1?'×'+l.quantity:''}</div>
          <div class="lot-meta">
            <span>от ${l.seller_name||'Игрок'}</span>
            <span>⏳ ${timeLeft}</span>
          </div>
          <div style="display:flex;align-items:center;justify-content:space-between">
            <div class="lot-bid">${fmt(l.current_bid||l.min_bid)} 🪙</div>
            <button class="btn btn-sm btn-gold" onclick="openBidModal(${l.id},'${l.item_name}',${l.current_bid||l.min_bid},this)">💰 Ставка</button>
          </div>
        </div>`;
      }).join('')+'</div>'
      :'<div class="loader">Лотов нет.</div>';
  }).catch(e=>{el('mkt-auc').innerHTML=`<div style="color:var(--red);font-size:12px;padding:10px">${e}</div>`;});
}
function openBidModal(lotId,name,minBid,btn) {
  const suggestedBid=Math.ceil(minBid*1.05);
  OM(`💰 Ставка: ${name}`,
    `<div class="irow"><span class="ik">Текущая ставка</span><span class="iv">${fmt(minBid)} 🪙</span></div>
     <div class="irow"><span class="ik">Минимум для обгона</span><span style="color:var(--gold)">${fmt(Math.ceil(minBid+1))} 🪙</span></div>
     <div class="divider"></div>
     <div style="margin-bottom:8px;font-size:11px;color:var(--muted)">Введите вашу ставку:</div>
     <input id="bid-val" type="number" value="${suggestedBid}" min="${Math.ceil(minBid+1)}"
       style="width:100%;background:var(--card);border:1px solid var(--border2);border-radius:var(--r);
              padding:9px 12px;color:var(--bright);font-size:14px;font-family:inherit"/>`,
    [{l:'💰 Поставить',c:'btn-gold',f:`doBid(${lotId},this)`},{l:'Отмена',c:'btn-ghost',f:'CM()'}]);
}
function doBid(lotId,btn) {
  const v=parseFloat(el('bid-val').value);
  if(isNaN(v)||v<=0){toast('Введите сумму.',false);return;}
  btn.disabled=true;
  api('/auction/bid',{method:'POST',body:JSON.stringify({lot_id:lotId,amount:v})})
    .then(r=>{toast(r.is_buyout?'🎉 Выкуплено!':'✅ Ставка принята!');CM();loadAuction();})
    .catch(e=>{toast(e,false);btn.disabled=false;});
}

function loadShopCatalog() {
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
        </div>
        <button class="btn btn-sm btn-gold" onclick="buyItem('${it.item_id}',this)">Купить</button>
      </div>`).join('')}</div>`).join('');
  }).catch(e=>{el('mkt-shop').innerHTML=`<div style="color:var(--red);font-size:12px;padding:10px">${e}</div>`;});
}
function buyItem(id,btn) {
  btn.disabled=true;
  api('/shop/buy',{method:'POST',body:JSON.stringify({item_id:id,quantity:1})})
    .then(r=>{toast('✅ Куплено: '+r.item_name);loadShopCatalog();}).catch(e=>{toast(e,false);btn.disabled=false;});
}
let _invData=[];
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

// ── Collection ────────────────────────────────────────────────────────────────
function loadColl(){swColl('themes',document.querySelector('#pg-coll .tb'));}
function swColl(tab,btn) {
  document.querySelectorAll('#pg-coll .tb').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');
  el('col-themes').style.display=tab==='themes'?'':'none';
  el('col-top').style.display=tab==='top'?'':'none';
  if(tab==='themes')loadThemes();
  else if(tab==='top'&&!el('top-c').textContent.includes('🥇'))loadTop();
}
function loadThemes() {
  api('/themes/').then(themes=>{
    _themeData=themes;
    const groups={};
    themes.forEach(t=>(groups[t.rarity]=groups[t.rarity]||[]).push(t));
    const order=['common','uncommon','rare','epic','legendary','mythic','shadow','zarniki','seasonal'];
    el('col-themes').innerHTML=order.filter(r=>groups[r]).map(r=>`<div class="card">
      <div class="card-title">${themes.find(t=>t.rarity===r)?.badge||''} ${themes.find(t=>t.rarity===r)?.rarity_label||r}</div>
      <div class="theme-grid">${groups[r].map(t=>`<div class="theme-card${t.owned?' owned':''}${t.active?' active-theme':''}" onclick="openThemeModal('${t.theme_id}')">
        <div class="theme-name">${t.name}</div>
        <div class="theme-preview">${t.top||'—'}</div>
        <div style="font-size:10px;color:var(--muted)">${t.desc||''}</div>
        ${t.active?'<div style="font-size:10px;color:var(--gold);margin-top:4px">✓ Активна</div>':t.owned?'<div style="font-size:10px;color:var(--green);margin-top:4px">В коллекции</div>':t.price_mora?`<div class="theme-price">${fmt(t.price_mora)} 🪙</div>`:t.price_diamonds?`<div class="theme-price">${t.price_diamonds} 💎</div>`:'<div style="font-size:10px;color:var(--muted);margin-top:4px">${t.source}</div>'}
      </div>`).join('')}</div></div>`).join('');
  }).catch(e=>{el('col-themes').innerHTML=`<div style="color:var(--red);font-size:12px;padding:10px">${e}</div>`;});
}
function openThemeModal(tid) {
  if(!_themeData)return;
  const t=_themeData.find(x=>x.theme_id===tid);if(!t)return;
  const price=t.price_mora?`${fmt(t.price_mora)} 🪙`:t.price_diamonds?`${t.price_diamonds} 💎`:null;
  let body=`<div style="text-align:center;padding:12px 0">
    <div style="font-size:11px;color:var(--muted);font-family:monospace;margin-bottom:6px">${t.top||''}</div>
    <div style="font-size:14px;font-weight:600;color:var(--bright);margin:4px 0">${t.name}</div>
    <div style="font-size:11px;color:var(--muted);font-family:monospace">${t.bot_line||''}</div>
  </div>
  <div class="divider"></div>
  <div class="irow"><span class="ik">Редкость</span><span>${t.badge} ${t.rarity_label}</span></div>
  <div class="irow"><span class="ik">Источник</span><span class="iv">${t.source}</span></div>
  ${price?`<div class="irow"><span class="ik">Цена</span><span style="color:var(--gold)">${price}</span></div>`:''}
  ${t.desc?`<div style="font-size:11px;color:var(--muted);margin-top:8px">${t.desc}</div>`:''}`;
  const btns=[{l:'Закрыть',c:'btn-ghost',f:'CM()'}];
  if(t.active){}
  else if(t.owned)btns.unshift({l:'✓ Надеть',c:'btn-gold',f:`doEquipTheme('${tid}')`});
  else if(price&&(t.source==='shop_mora'||t.source==='shop_diamond'))btns.unshift({l:`Купить ${price}`,c:'btn-gold',f:`doBuyTheme('${tid}')`});
  OM(t.name,body,btns);
}
function doBuyTheme(tid) {
  api('/themes/buy',{method:'POST',body:JSON.stringify({theme_id:tid})})
    .then(r=>{toast(`✅ ${r.theme_name} куплена!`);CM();loadThemes();}).catch(e=>toast(e,false));
}
function doEquipTheme(tid) {
  api('/themes/equip',{method:'POST',body:JSON.stringify({theme_id:tid})})
    .then(()=>{toast('✅ Тема активирована!');CM();loadThemes();}).catch(e=>toast(e,false));
}

// ── Top ───────────────────────────────────────────────────────────────────────
function loadTop(){switchTop('local',document.querySelector('#col-top .tb'));}
function switchTop(mode,btn) {
  document.querySelectorAll('#col-top .tb').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');
  if(mode==='local'&&!_cid){el('top-c').innerHTML='<div style="color:var(--muted);font-size:12px;padding:10px">Нужен Профиль с чатом.</div>';return;}
  el('top-c').innerHTML='<div class="loader">Загрузка...</div>';
  api(mode==='global'?'/top/global':`/top/local/${_cid}`).then(rows=>{
    el('top-c').innerHTML=rows.length?'<div class="card">'+rows.slice(0,30).map((r,i)=>`<div class="trow">
      <div class="tpos">${MEDALS[i]||(i+1)+'.'}</div>
      <div class="tname">${r.username}</div>
      <div class="tcnt">${fmt(r.count)} 💬</div>
    </div>`).join('')+'</div>':'<div class="loader">Данных пока нет.</div>';
  }).catch(e=>{el('top-c').innerHTML=`<div style="color:var(--red);font-size:12px;padding:10px">${e}</div>`;});
}

// Auto-refresh
setInterval(()=>{if(_loaded.has('profile'))loadProfile();},300000);
setInterval(()=>{if(_loaded.has('zoo'))api('/zoo/expeditions').then(d=>renderExps(d)).catch(()=>{});},30000);
</script>
</body>
</html>"""
