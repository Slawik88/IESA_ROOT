"""FastAPI/main.py — Predvestnik Mini App entry point.
Adapter layer only: registers routers, serves HTML shell.
"""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

from infrastructure.database import create_pool, get_pool
from infrastructure.pg_adapter import PGAdapter
from FastAPI.auth import verify_login_widget, create_session_token
from FastAPI.routers import profile, top, inventory, shop, zoo, gacha, craft, quests


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_pool()
    yield


app = FastAPI(title="Predvestnik Mini App", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

for r in [profile.router, top.router, inventory.router, shop.router,
          zoo.router, gacha.router, craft.router, quests.router]:
    app.include_router(r)


# ── Auth ───────────────────────────────────────────────────────────────────────

class _LoginWidgetPayload(BaseModel):
    id: int
    first_name: str
    auth_date: int
    hash: str
    last_name: str | None = None
    username:  str | None = None
    photo_url: str | None = None


@app.post("/auth/telegram-login")
async def telegram_login(payload: _LoginWidgetPayload):
    data = {k: v for k, v in payload.model_dump().items() if v is not None}
    user = verify_login_widget(data)
    if not user:
        raise HTTPException(401, "Неверная подпись Telegram.")
    return {"session_token": create_session_token(int(user["id"])),
            "user_id": user["id"], "username": user.get("username", ""),
            "first_name": user.get("first_name", "")}


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
        async with db.execute(
            "SELECT * FROM exchange_events WHERE status='scheduled' ORDER BY starts_at LIMIT 1"
        ) as c:
            scheduled = await c.fetchone()
    if active:
        return {"exchange": {"active": True, "ends_at": str(dict(active).get("ends_at",""))[:16]}}
    if scheduled:
        s = dict(scheduled)
        return {"exchange": {"active": False, "scheduled": True,
                             "starts_at": str(s.get("starts_at",""))[:16]}}
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
:root {
  --bg:#08090f; --s:#0d1019; --card:#111621; --card2:#161d2a;
  --gold:#c9a84c; --gold2:#e8c866; --gold-dim:rgba(201,168,76,.15);
  --teal:#3fb8af; --red:#e05252; --green:#52b360; --blue:#5a9cf5;
  --text:#cdd0de; --bright:#eef0f8; --muted:#5a6480; --dim:#2a3448;
  --border:rgba(201,168,76,.18); --border2:rgba(255,255,255,.06);
  --r:6px; --r-lg:10px;
}
*{margin:0;padding:0;box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{background:var(--bg);color:var(--text);
     font-family:-apple-system,BlinkMacSystemFont,'SF Pro Display','Segoe UI',sans-serif;
     min-height:100vh;padding-bottom:70px;overflow-x:hidden}

/* ── Keyframes ── */
@keyframes fadeUp{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}
@keyframes fadeIn{from{opacity:0}to{opacity:1}}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.55}}
@keyframes glow{0%,100%{box-shadow:0 0 8px rgba(201,168,76,.3)}50%{box-shadow:0 0 20px rgba(201,168,76,.6)}}
@keyframes shimmer{from{background-position:-200% 0}to{background-position:200% 0}}
@keyframes countdown{from{stroke-dashoffset:0}to{stroke-dashoffset:188}}
@keyframes slideUp{from{opacity:0;transform:translateY(20px)}to{opacity:1;transform:translateY(0)}}

/* ── Cards ── */
.card{background:var(--card);border:1px solid var(--border2);border-radius:var(--r);
      padding:14px;margin-bottom:10px;position:relative;animation:fadeUp .25s ease}
.card-gold{border-top:1px solid var(--gold)}
.card::before{content:'';position:absolute;top:0;left:0;width:20px;height:20px;
              border-top:1px solid var(--gold);border-left:1px solid var(--gold);
              border-radius:var(--r) 0 0 0}
.card-title{font-size:10px;text-transform:uppercase;letter-spacing:1.5px;
            color:var(--muted);margin-bottom:12px;display:flex;align-items:center;gap:6px}
.card-title::after{content:'';flex:1;height:1px;background:var(--border2)}

/* ── Skeleton ── */
.sk{background:linear-gradient(90deg,var(--s) 25%,rgba(255,255,255,.04) 50%,var(--s) 75%);
    background-size:200% 100%;animation:shimmer 1.4s infinite;border-radius:4px}
.sk-text{height:12px;margin:4px 0;border-radius:3px}
.sk-big{height:48px;border-radius:var(--r)}

/* ── Nav ── */
.nav{position:fixed;bottom:0;left:0;right:0;background:rgba(8,9,15,.96);
     border-top:1px solid var(--border2);display:flex;z-index:100;
     padding-bottom:env(safe-area-inset-bottom);backdrop-filter:blur(12px)}
.nb{flex:1;padding:9px 2px 7px;text-align:center;cursor:pointer;
    font-size:9px;color:var(--muted);transition:.2s;position:relative;user-select:none}
.nb.active{color:var(--gold2)}
.nb.active::after{content:'';position:absolute;bottom:0;left:25%;right:25%;
                  height:2px;background:var(--gold2);border-radius:1px}
.nb .ni{font-size:19px;display:block;margin-bottom:2px;transition:.2s}
.nb.active .ni{filter:drop-shadow(0 0 6px rgba(201,168,76,.5))}

/* ── Pages ── */
.page{display:none;padding:12px;animation:fadeIn .2s ease}
.page.active{display:block}

/* ── Sub-tabs ── */
.tabs{display:flex;gap:5px;margin-bottom:12px}
.tb{flex:1;padding:7px;border-radius:var(--r);border:1px solid var(--border2);cursor:pointer;
    background:transparent;color:var(--muted);font-size:11px;transition:.15s;font-family:inherit}
.tb.active{background:var(--gold-dim);color:var(--gold2);border-color:var(--border)}

/* ── Profile header ── */
.phead{display:flex;align-items:center;gap:12px;margin-bottom:14px}
.ava{width:48px;height:48px;border-radius:50%;flex-shrink:0;font-size:22px;
     display:flex;align-items:center;justify-content:center;
     background:linear-gradient(135deg,#1a2035,#2a3355);
     border:1px solid var(--border)}
.pname{font-size:16px;font-weight:700;color:var(--bright)}
.prank{font-size:11px;color:var(--gold);margin-top:2px}

/* ── Stat grid ── */
.stats{display:grid;grid-template-columns:1fr 1fr;gap:7px;margin-bottom:12px}
.stat{background:var(--s);border-radius:var(--r);padding:10px;text-align:center;
      border:1px solid var(--border2)}
.stat .sicon{font-size:16px}
.stat .sval{font-size:16px;font-weight:700;color:var(--bright);margin:3px 0;
            font-variant-numeric:tabular-nums}
.stat .slbl{font-size:9px;text-transform:uppercase;letter-spacing:1px;color:var(--muted)}

/* ── Pet cards ── */
.pcard{display:flex;align-items:flex-start;gap:10px;padding:11px 0;
       border-bottom:1px solid var(--border2)}
.pcard:last-child{border:none}
.pcol{flex:1;min-width:0}
.pn{font-size:13px;font-weight:600;color:var(--bright)}
.ps{font-size:11px;color:var(--muted);margin-top:1px}
.fat-bar{height:4px;background:var(--dim);border-radius:2px;margin:6px 0 4px}
.fat-fill{height:100%;border-radius:2px;transition:.4s}
.badge{display:inline-block;padding:1px 7px;border-radius:99px;font-size:10px;font-weight:600}
.bg-gold{background:rgba(201,168,76,.15);color:var(--gold)}
.bg-teal{background:rgba(63,184,175,.15);color:var(--teal)}
.bg-red{background:rgba(224,82,82,.15);color:var(--red)}
.bg-green{background:rgba(82,179,96,.15);color:var(--green)}
.bg-blue{background:rgba(90,156,245,.15);color:var(--blue)}
.bg-dim{background:var(--dim);color:var(--muted)}
.rarity-common{color:var(--muted)}
.rarity-rare{color:var(--blue)}
.rarity-epic{color:#b57bee}
.rarity-legendary{color:var(--gold)}

/* ── Expedition card ── */
.exp-card{background:var(--s);border-radius:var(--r);padding:12px;margin-bottom:8px;
          border:1px solid var(--border2);border-left:2px solid var(--teal)}
.exp-timer{font-size:22px;font-weight:700;color:var(--teal);
           font-variant-numeric:tabular-nums;font-family:monospace}
.exp-timer.urgent{color:var(--red);animation:pulse 1s infinite}

/* ── Top rows ── */
.trow{display:flex;align-items:center;padding:8px 0;border-bottom:1px solid var(--border2)}
.trow:last-child{border:none}
.tpos{width:28px;font-size:15px;text-align:center;flex-shrink:0}
.tname{font-size:13px;flex:1;padding:0 8px;color:var(--text)}
.tcnt{font-size:12px;color:var(--gold);font-weight:600;font-variant-numeric:tabular-nums}

/* ── Inventory ── */
.inv-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.icard{background:var(--s);border-radius:var(--r);padding:12px;cursor:pointer;
       border:1px solid var(--border2);transition:.15s;position:relative}
.icard:hover,.icard:active{border-color:var(--border);background:var(--card2)}
.icard .iname{font-size:12px;font-weight:600;color:var(--bright);margin-bottom:4px}
.icard .iqty{font-size:22px;font-weight:700;color:var(--gold)}
.icard .idesc{font-size:10px;color:var(--muted);margin-top:4px;line-height:1.4}
.icard .ibadge{position:absolute;top:8px;right:8px;font-size:9px;padding:2px 5px;
               border-radius:3px;background:var(--dim);color:var(--muted)}

/* ── Shop ── */
.shop-row{display:flex;align-items:center;gap:10px;padding:10px 0;
          border-bottom:1px solid var(--border2)}
.shop-row:last-child{border:none}
.sico{font-size:22px;width:32px;text-align:center;flex-shrink:0}
.sinfo{flex:1}
.sname{font-size:13px;font-weight:600;color:var(--bright)}
.sprice{font-size:11px;color:var(--gold);margin-top:2px}
.sdesc{font-size:10px;color:var(--muted);margin-top:1px}

/* ── Quest ── */
.qitem{padding:10px 0;border-bottom:1px solid var(--border2)}
.qitem:last-child{border:none}
.qtitle{font-size:13px;font-weight:600;color:var(--bright);margin-bottom:4px}
.qrw{font-size:11px;color:var(--gold);margin-bottom:6px}
.qbar{height:5px;background:var(--dim);border-radius:3px;margin-bottom:3px}
.qfill{height:100%;border-radius:3px;background:var(--gold);transition:.4s}
.qprog{font-size:10px;color:var(--muted)}

/* ── Gacha ── */
.spin-row{display:flex;align-items:center;gap:10px;padding:11px;
          background:var(--s);border-radius:var(--r);border:1px solid var(--border2);
          cursor:pointer;transition:.15s;margin-bottom:7px}
.spin-row:hover{border-color:var(--border);background:var(--card2)}
.spin-label{flex:1;font-size:13px;font-weight:600;color:var(--bright)}
.spin-cost{font-size:12px;color:var(--gold)}
.spin-tok{font-size:11px;color:var(--green)}
.spin-res{background:var(--s);border:1px solid var(--gold);border-radius:var(--r);
          padding:14px;margin-top:10px;animation:slideUp .25s ease}
.spin-res-title{font-size:13px;font-weight:700;color:var(--gold2);margin-bottom:6px}

/* ── Buttons ── */
.btn{padding:8px 16px;border-radius:var(--r);border:none;cursor:pointer;font-family:inherit;
     font-size:12px;font-weight:600;transition:.15s;display:inline-flex;align-items:center;gap:5px}
.btn-gold{background:var(--gold-dim);color:var(--gold2);border:1px solid var(--border)}
.btn-gold:hover{background:rgba(201,168,76,.25)}
.btn-ghost{background:transparent;color:var(--muted);border:1px solid var(--border2)}
.btn-red{background:rgba(224,82,82,.15);color:var(--red);border:1px solid rgba(224,82,82,.3)}
.btn-green{background:rgba(82,179,96,.15);color:var(--green);border:1px solid rgba(82,179,96,.3)}
.btn-teal{background:rgba(63,184,175,.15);color:var(--teal);border:1px solid rgba(63,184,175,.3)}
.btn:disabled{opacity:.35;cursor:not-allowed}
.btn-sm{padding:5px 10px;font-size:11px}
.btn-full{width:100%;justify-content:center}

/* ── Balance bar ── */
.balrow{display:flex;gap:7px;margin-bottom:12px}
.bal{flex:1;background:var(--s);border-radius:var(--r);padding:9px;text-align:center;
     border:1px solid var(--border2)}
.bal .bval{font-size:14px;font-weight:700;color:var(--bright);font-variant-numeric:tabular-nums}
.bal .blbl{font-size:9px;text-transform:uppercase;letter-spacing:1px;color:var(--muted);margin-top:1px}

/* ── Modal ── */
dialog{background:var(--s);border:1px solid var(--border);border-radius:var(--r-lg);
       padding:0;max-width:380px;width:90%;color:var(--text);
       animation:slideUp .2s ease}
dialog::backdrop{background:rgba(0,0,0,.82);backdrop-filter:blur(4px)}
.modal-head{display:flex;align-items:center;justify-content:space-between;
            padding:14px 16px;border-bottom:1px solid var(--border2)}
.modal-title{font-size:15px;font-weight:700;color:var(--bright)}
.modal-close{background:none;border:none;color:var(--muted);font-size:20px;
             cursor:pointer;line-height:1;padding:2px 6px}
.modal-body{padding:14px 16px;max-height:60vh;overflow-y:auto}
.modal-foot{padding:10px 16px;border-top:1px solid var(--border2);
            display:flex;gap:7px;justify-content:flex-end}

/* ── Misc ── */
.loader{text-align:center;color:var(--muted);padding:28px;font-size:13px}
.err{background:rgba(224,82,82,.1);border:1px solid rgba(224,82,82,.25);
     border-radius:var(--r);padding:11px;color:var(--red);font-size:12px;margin:6px 0}
.ok-box{background:rgba(82,179,96,.1);border:1px solid rgba(82,179,96,.25);
        border-radius:var(--r);padding:11px;color:var(--green);font-size:12px;margin:6px 0}
.divider{height:1px;background:var(--border2);margin:10px 0}
.row2{display:flex;align-items:center;justify-content:space-between;padding:5px 0}
.info-row{font-size:12px;color:var(--muted);display:flex;justify-content:space-between;
          padding:5px 0;border-bottom:1px solid var(--border2)}
.info-row:last-child{border:none}
.info-row span:last-child{color:var(--text)}

/* ── Login overlay ── */
.login-ov{position:fixed;inset:0;background:var(--bg);z-index:200;
          display:flex;flex-direction:column;align-items:center;
          justify-content:center;gap:20px;padding:32px;text-align:center}
.login-ov h1{font-size:28px;font-weight:800;color:var(--gold2);
             text-shadow:0 0 30px rgba(201,168,76,.4)}
.login-ov p{color:var(--muted);font-size:13px;max-width:260px;line-height:1.5}
.login-ov.hidden{display:none}

/* ── Toast ── */
.toast{position:fixed;top:14px;left:50%;transform:translateX(-50%);
       padding:9px 16px;border-radius:99px;font-size:12px;font-weight:600;
       z-index:9999;opacity:0;transition:.25s;pointer-events:none;
       backdrop-filter:blur(8px);white-space:nowrap}
.toast.show{opacity:1}

/* ── Rarity stars visual ── */
.rarity-dots{display:flex;gap:2px;margin-top:3px}
.rarity-dot{width:5px;height:5px;border-radius:50%;background:var(--dim)}
.rarity-dot.on-common{background:#6b7a99}
.rarity-dot.on-rare{background:var(--blue)}
.rarity-dot.on-epic{background:#b57bee}
.rarity-dot.on-legendary{background:var(--gold)}

/* ── Food option ── */
.food-opt{display:flex;align-items:center;gap:8px;padding:9px;
          background:var(--card);border-radius:var(--r);cursor:pointer;
          border:1px solid var(--border2);margin-bottom:6px;transition:.15s}
.food-opt:hover{border-color:var(--border)}
.food-opt .fn{font-size:12px;flex:1;color:var(--text)}
.food-opt .fq{font-size:11px;color:var(--muted)}
.food-opt .fr{font-size:11px;color:var(--green);font-weight:600}

/* ── Booster option ── */
.boost-opt{display:flex;align-items:center;gap:8px;padding:9px;
           background:var(--card);border-radius:var(--r);cursor:pointer;
           border:1px solid var(--border2);margin-bottom:6px;transition:.15s}
.boost-opt:hover{border-color:var(--teal);background:rgba(63,184,175,.07)}
.boost-opt .bname{font-size:12px;flex:1;color:var(--text)}
.boost-opt .bqty{font-size:11px;color:var(--muted)}
.boost-opt .bval{font-size:11px;color:var(--teal);font-weight:600}
</style>
</head>
<body>
<div id="toast" class="toast"></div>

<div id="login-ov" class="login-ov hidden">
  <div style="font-size:48px;animation:glow 2s infinite">🔮</div>
  <h1>Предвестник</h1>
  <p>Войдите через Telegram для доступа к профилю, питомцам и магазину.</p>
  <div id="tg-login-widget"></div>
  <p style="font-size:10px;color:var(--dim)">Данные не передаются третьим лицам.</p>
</div>

<!-- Reusable modal -->
<dialog id="modal">
  <div class="modal-head">
    <span id="modal-title" class="modal-title"></span>
    <button class="modal-close" onclick="closeModal()">✕</button>
  </div>
  <div id="modal-body" class="modal-body"></div>
  <div id="modal-foot" class="modal-foot"></div>
</dialog>

<!-- 1. Profile -->
<div id="pg-profile" class="page active">
  <div id="profile-content"><div class="card sk sk-big" style="height:120px"></div></div>
</div>

<!-- 2. Zoo -->
<div id="pg-zoo" class="page">
  <div id="zoo-exp-wrap"></div>
  <div class="tabs">
    <button class="tb active" onclick="switchZoo('active',this)">⚔️ Активные</button>
    <button class="tb" onclick="switchZoo('passive',this)">🛡 Пассивные</button>
    <button class="tb" onclick="switchZoo('storage',this)">📦 Склад</button>
    <button class="tb" onclick="switchZoo('guide',this)">📖 Справка</button>
  </div>
  <div id="zoo-content" class="loader">Загрузка...</div>
</div>

<!-- 3. Activity -->
<div id="pg-activity" class="page">
  <div class="tabs">
    <button class="tb active" onclick="switchAct('quests',this)">📋 Квесты</button>
    <button class="tb" onclick="switchAct('gacha',this)">🎲 Гача</button>
    <button class="tb" onclick="switchAct('craft',this)">⚗️ Крафт</button>
  </div>
  <div id="act-quests"><div id="quests-c" class="loader">Загрузка...</div></div>
  <div id="act-gacha" style="display:none"><div id="gacha-c" class="loader">Загрузка...</div></div>
  <div id="act-craft" style="display:none"><div id="craft-c" class="loader">Загрузка...</div></div>
</div>

<!-- 4. Shop -->
<div id="pg-shop" class="page">
  <div class="tabs">
    <button class="tb active" onclick="switchShop('buy',this)">🛒 Купить</button>
    <button class="tb" onclick="switchShop('inv',this)">🎒 Инвентарь</button>
  </div>
  <div id="balrow" class="balrow"></div>
  <div id="shop-buy"><div class="loader">Загрузка...</div></div>
  <div id="shop-inv" style="display:none"></div>
</div>

<!-- 5. Top -->
<div id="pg-top" class="page">
  <div class="tabs">
    <button class="tb active" onclick="switchTop('local',this)">🏘 Чат</button>
    <button class="tb" onclick="switchTop('global',this)">🌍 Глобальный</button>
  </div>
  <div id="top-c" class="loader">Загрузка...</div>
</div>

<nav class="nav">
  <div class="nb active" onclick="switchPage('profile',this)"><span class="ni">👤</span>Профиль</div>
  <div class="nb" onclick="switchPage('zoo',this)"><span class="ni">🐾</span>Зоопарк</div>
  <div class="nb" onclick="switchPage('activity',this)"><span class="ni">🎮</span>Активность</div>
  <div class="nb" onclick="switchPage('shop',this)"><span class="ni">🛒</span>Магазин</div>
  <div class="nb" onclick="switchPage('top',this)"><span class="ni">🏆</span>Топ</div>
</nav>

<script>
const tg = window.Telegram?.WebApp;
if (tg) { tg.ready(); tg.expand(); tg.setHeaderColor('#08090f'); }

const BASE = (location.origin + location.pathname).replace(/\/$/, '');
const INIT_DATA = tg?.initData || '';
const SK = 'pv_sess';
const MEDALS = ['🥇','🥈','🥉'];
const PLACE_LABEL = {active:'Активный', passive:'Пассивный', storage:'Склад'};
const RARITY_COLORS = {common:'bg-dim', rare:'bg-blue', epic:'', legendary:'bg-gold'};

let _cid = 0;       // primary chat_id from profile
let _actTab = 'quests';
let _zooTab = 'active';
let _zooData = null; // cache for zoo data
let _expTimer = null;

// ── Auth ──────────────────────────────────────────────────────────────────────
const sess = () => localStorage.getItem(SK) || '';
const hdrs = () => {
  const h = {'content-type':'application/json'};
  if (INIT_DATA) h['x-init-data'] = INIT_DATA;
  if (sess()) h['x-session-token'] = sess();
  return h;
};
function api(path, opts = {}) {
  return fetch(BASE + path, {...opts, headers:{...hdrs(),...(opts.headers||{})}})
    .then(r => {
      if (r.status === 401) {
        localStorage.removeItem(SK);
        el('login-ov').classList.remove('hidden');
        return Promise.reject('Войдите снова.');
      }
      return r.ok ? r.json() : r.json().then(e => Promise.reject(e.detail || 'Ошибка'));
    });
}

window.onTelegramWidgetAuth = u => {
  api('/auth/telegram-login', {method:'POST', body:JSON.stringify(u)})
    .then(d => { localStorage.setItem(SK, d.session_token); el('login-ov').classList.add('hidden'); loadProfile(); })
    .catch(e => alert('Ошибка: ' + e));
};
if (!INIT_DATA && !sess()) el('login-ov').classList.remove('hidden');

// ── Utils ─────────────────────────────────────────────────────────────────────
const el = id => document.getElementById(id);
const fmt = n => Number(n).toLocaleString('ru');
const fatColor = f => f < 40 ? 'var(--green)' : f < 70 ? 'var(--gold)' : 'var(--red)';
const rarityClass = r => ({common:'rarity-common',rare:'rarity-rare',epic:'rarity-epic',legendary:'rarity-legendary'}[r]||'');
const rarityDots = r => {
  const n = {common:1,rare:2,epic:3,legendary:4}[r]||0;
  return '<div class="rarity-dots">' + Array(4).fill(0).map((_,i) =>
    `<div class="rarity-dot ${i<n?'on-'+r:''}"></div>`).join('') + '</div>';
};

function toast(msg, ok = true) {
  const t = el('toast');
  t.textContent = msg;
  t.style.cssText = `background:${ok?'rgba(82,179,96,.9)':'rgba(224,82,82,.9)'};color:#fff;border:1px solid ${ok?'rgba(82,179,96,.5)':'rgba(224,82,82,.5)'}`;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 2500);
}

function countdown(endsAt) {
  const ends = new Date(endsAt.includes('T') ? endsAt : endsAt + 'Z');
  const diff = Math.max(0, Math.floor((ends - Date.now()) / 1000));
  if (diff <= 0) return '<span style="color:var(--green)">Завершено ✓</span>';
  const h = Math.floor(diff / 3600), m = Math.floor((diff % 3600) / 60), s = diff % 60;
  const str = h ? `${h}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}` : `${m}:${String(s).padStart(2,'0')}`;
  const cls = diff < 300 ? 'exp-timer urgent' : 'exp-timer';
  return `<span class="${cls}">${str}</span>`;
}

// ── Modal ─────────────────────────────────────────────────────────────────────
function openModal(title, bodyHtml, footBtns = []) {
  el('modal-title').textContent = title;
  el('modal-body').innerHTML = bodyHtml;
  el('modal-foot').innerHTML = footBtns.map(b =>
    `<button class="btn btn-sm ${b.cls||'btn-ghost'}" onclick="${b.fn}" ${b.disabled?'disabled':''}>${b.label}</button>`
  ).join('');
  el('modal').showModal();
}
function closeModal() { el('modal').close(); }
el('modal').addEventListener('click', e => { if (e.target === el('modal')) closeModal(); });

// ── Navigation ────────────────────────────────────────────────────────────────
const _loaded = new Set();
function switchPage(name, btn) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nb').forEach(b => b.classList.remove('active'));
  el('pg-' + name).classList.add('active');
  btn.classList.add('active');
  if (!_loaded.has(name)) {
    _loaded.add(name);
    ({zoo:loadZoo, activity:loadActivity, shop:loadShop, top:loadTop}[name] || (()=>{}))();
  }
}

// ── Profile ───────────────────────────────────────────────────────────────────
function loadProfile() {
  el('profile-content').innerHTML = '<div class="sk sk-big" style="height:120px;border-radius:10px"></div>';
  api('/profile/me')
    .then(d => {
      if (d.chats?.length) _cid = d.chats[0].chat_tg_id;
      const pets = d.pets.filter(p => p.placement !== 'storage').slice(0, 3);
      el('profile-content').innerHTML = `
        <div class="card card-gold">
          <div class="phead">
            <div class="ava">🔮</div>
            <div>
              <div class="pname">@${d.username||'Игрок'}</div>
              <div class="prank">${d.rank}</div>
            </div>
          </div>
          <div class="stats">
            <div class="stat"><div class="sicon">🪙</div><div class="sval">${fmt(d.mora)}</div><div class="slbl">Мора</div></div>
            <div class="stat"><div class="sicon">💎</div><div class="sval">${d.diamonds.toFixed(1)}</div><div class="slbl">Алмазы</div></div>
            <div class="stat"><div class="sicon">🔥</div><div class="sval">${d.streak}</div><div class="slbl">Стрик</div></div>
            <div class="stat"><div class="sicon">🏆</div><div class="sval">${d.achievements}</div><div class="slbl">Ачивки</div></div>
          </div>
        </div>
        ${pets.length ? `<div class="card">
          <div class="card-title">🐾 Питомцы в питомнике</div>
          ${pets.map(p => `<div class="pcard">
            <div class="pcol">
              <div class="pn">${p.name||p.species_id} <span class="${rarityClass(p.rarity)}" style="font-size:10px">${p.rarity}</span></div>
              <div class="ps">Lv${p.pet_level} · ${PLACE_LABEL[p.placement]}</div>
              <div class="fat-bar"><div class="fat-fill" style="width:${p.fatigue}%;background:${fatColor(p.fatigue)}"></div></div>
              <div style="font-size:10px;color:var(--muted)">${p.fatigue}% усталости</div>
            </div>
          </div>`).join('')}
        </div>` : ''}
        ${d.chats.length ? `<div class="card">
          <div class="card-title">💬 Активность в чатах</div>
          ${d.chats.map(c => `<div class="info-row"><span>${c.chat_title||'Чат'}</span><span>Lv${c.user_level} · ${fmt(c.user_messages_count_all_time)} сообщ.</span></div>`).join('')}
        </div>` : ''}`;
    })
    .catch(e => { el('profile-content').innerHTML = `<div class="err">${typeof e==='string'?e:'Напишите боту чтобы создать профиль.'}</div>`; });
}
if (INIT_DATA || sess()) { loadProfile(); _loaded.add('profile'); }

// ── Zoo ───────────────────────────────────────────────────────────────────────
function loadZoo() {
  Promise.all([api('/zoo/'), api('/zoo/expeditions')])
    .then(([data, expData]) => {
      _zooData = data;
      renderExpeditions(expData);
      renderZooTab(_zooTab);
    })
    .catch(e => { el('zoo-content').innerHTML = `<div class="err">${e}</div>`; });
}

function renderExpeditions(expData) {
  if (_expTimer) clearInterval(_expTimer);
  const wrap = el('zoo-exp-wrap');
  if (!expData.expeditions.length) { wrap.innerHTML = ''; return; }
  const boosters = expData.boosters;
  wrap.innerHTML = expData.expeditions.map(e => `
    <div class="exp-card">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
        <div>
          <div style="font-size:13px;font-weight:600;color:var(--bright)">${e.name} <span style="color:var(--muted);font-size:11px">· ${e.duration_hours}ч поход</span></div>
        </div>
        <div id="timer-${e.pet_id}" style="text-align:right">${countdown(e.ends_at)}</div>
      </div>
      ${Object.keys(boosters).length ? `
      <div style="margin-top:8px;padding-top:8px;border-top:1px solid var(--border2)">
        <div style="font-size:10px;color:var(--muted);margin-bottom:6px;text-transform:uppercase;letter-spacing:1px">Ускорители</div>
        ${Object.entries(boosters).map(([bid, b]) => `
          <div class="boost-opt" onclick="boostExp(${e.pet_id},'${bid}',this)">
            <span style="font-size:18px">⏩</span>
            <span class="bname">${b.name}</span>
            <span class="bqty">×${b.qty}</span>
            <span class="bval">−${b.boost_hours}ч</span>
          </div>`).join('')}
      </div>` : ''}
    </div>`).join('');

  // Live countdown
  _expTimer = setInterval(() => {
    expData.expeditions.forEach(e => {
      const t = el(`timer-${e.pet_id}`);
      if (t) t.innerHTML = countdown(e.ends_at);
    });
  }, 1000);
}

function switchZoo(tab, btn) {
  _zooTab = tab;
  document.querySelectorAll('#pg-zoo .tb').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  if (!_zooData) { loadZoo(); return; }
  renderZooTab(tab);
}

function renderZooTab(tab) {
  if (tab === 'guide') { renderZooGuide(); return; }
  if (!_zooData) return;
  const pets = _zooData.pets.filter(p =>
    tab === 'storage' ? p.placement === 'storage' : p.placement === tab
  );
  const food = _zooData.available_food;
  const foodHtml = Object.entries(food).map(([fid, f]) =>
    `<div class="food-opt" onclick="feedPet(event,${null},'${fid}',${f.restore})">
      <span class="fn">${f.name}</span><span class="fq">×${f.qty}</span>
      <span class="fr">−${f.restore} уст.</span></div>`).join('') ||
    '<div style="color:var(--muted);font-size:12px;padding:6px">Нет корма в инвентаре</div>';

  el('zoo-content').innerHTML = pets.length
    ? pets.map(p => `
      <div class="pcard">
        <div class="pcol">
          <div class="pn">${p.name||p.species_id}
            <span style="font-size:10px" class="${rarityClass(p.rarity)}"> ${p.rarity}</span>
          </div>
          <div class="ps">Lv${p.pet_level} · ${PLACE_LABEL[p.placement]||p.placement}</div>
          <div class="fat-bar"><div class="fat-fill" style="width:${p.fatigue}%;background:${fatColor(p.fatigue)}"></div></div>
          <div style="display:flex;align-items:center;gap:8px;margin-top:5px">
            <span style="font-size:10px;color:var(--muted)">${p.fatigue}% уст.</span>
            ${p.placement !== 'storage'
              ? `<button class="btn btn-sm btn-teal" onclick="openFeedModal(${p.id},${p.fatigue},'${p.name||p.species_id}')">🍖 Покормить</button>`
              : ''}
            <button class="btn btn-sm btn-ghost" onclick="openMoveModal(${p.id},'${p.placement}','${p.name||p.species_id}')">↔ Переместить</button>
          </div>
          <div id="feed-${p.id}" style="display:none;margin-top:8px">${foodHtml}</div>
        </div>
      </div>`).join('')
    : `<div class="loader" style="padding:20px">Питомцев в «${PLACE_LABEL[tab]||tab}» нет.</div>`;
}

function openFeedModal(petId, fatigue, petName) {
  if (!_zooData) return;
  const food = _zooData.available_food;
  const foodHtml = Object.entries(food).map(([fid, f]) => `
    <div class="food-opt" onclick="doFeed(${petId},'${fid}',this)">
      <span class="fn">${f.name}</span><span class="fq">×${f.qty}</span>
      <span class="fr">−${f.restore} уст.</span>
    </div>`).join('') || '<div class="err">Корма нет — купите в Магазине.</div>';
  openModal(`🍖 Кормить: ${petName}`, `
    <div class="info-row"><span>Текущая усталость</span><span style="color:${fatColor(fatigue)}">${fatigue}%</span></div>
    <div class="divider"></div>
    <div style="font-size:11px;color:var(--muted);margin-bottom:8px;text-transform:uppercase;letter-spacing:1px">Выберите корм</div>
    ${foodHtml}`, [{label:'Закрыть', cls:'btn-ghost', fn:'closeModal()'}]);
}

function doFeed(petId, foodId, btn) {
  btn.style.opacity = '.4';
  api('/zoo/feed', {method:'POST', body:JSON.stringify({pet_id:petId, food_id:foodId})})
    .then(r => {
      toast(`✅ ${r.fatigue_before}% → ${r.fatigue_after}%`);
      closeModal();
      _zooData = null; loadZoo();
    })
    .catch(e => { toast(e, false); btn.style.opacity = '1'; });
}

function openMoveModal(petId, currentPlacement, petName) {
  const opts = ['active', 'passive', 'storage'].filter(p => p !== currentPlacement);
  const html = opts.map(p => `
    <button class="btn btn-full ${p==='storage'?'btn-ghost':p==='active'?'btn-teal':'btn-green'}" style="margin-bottom:7px"
            onclick="doMove(${petId},'${p}',this)">
      ${p==='active'?'⚔️ В Активные':p==='passive'?'🛡 В Пассивные':'📦 На Склад'}
    </button>`).join('');
  openModal(`↔ Переместить: ${petName}`,
    `<div class="info-row"><span>Сейчас</span><span>${PLACE_LABEL[currentPlacement]||currentPlacement}</span></div>
     <div class="divider"></div>${html}`,
    [{label:'Отмена', cls:'btn-ghost', fn:'closeModal()'}]);
}

function doMove(petId, placement, btn) {
  btn.disabled = true;
  api('/zoo/move', {method:'POST', body:JSON.stringify({pet_id:petId, placement})})
    .then(() => { toast('✅ Перемещено!'); closeModal(); _zooData = null; loadZoo(); })
    .catch(e => { toast(e, false); btn.disabled = false; });
}

function boostExp(petId, boosterId, row) {
  row.style.opacity = '.4';
  api('/zoo/boost', {method:'POST', body:JSON.stringify({pet_id:petId, booster_id:boosterId})})
    .then(r => { toast(`⏩ Ускорено на ${r.boosted_hours}ч!`); _loaded.delete('zoo'); loadZoo(); })
    .catch(e => { toast(e, false); row.style.opacity = '1'; });
}

function renderZooGuide() {
  el('zoo-content').innerHTML = '<div class="loader">Загрузка...</div>';
  api('/zoo/species')
    .then(list => {
      const groups = {};
      list.forEach(s => (groups[s.rarity] = groups[s.rarity] || []).push(s));
      el('zoo-content').innerHTML = Object.entries(groups).map(([rarity, pets]) => `
        <div class="card">
          <div class="card-title ${rarityClass(rarity)}">${{common:'⬜ Обычные',rare:'🟦 Редкие',epic:'🟣 Эпические',legendary:'🟡 Легендарные'}[rarity]||rarity}</div>
          ${pets.map(p => `<div style="padding:8px 0;border-bottom:1px solid var(--border2)">
            <div style="font-size:13px;font-weight:600;color:var(--bright);margin-bottom:3px">${p.name}</div>
            <div class="badge ${p.role==='active'?'bg-teal':'bg-blue'}" style="margin-bottom:5px">
              ${p.role==='active'?'⚔️ Активная роль':'🛡 Пассивная роль'}
            </div>
            <div style="font-size:11px;color:var(--muted);line-height:1.4">${p.desc}</div>
          </div>`).join('')}
        </div>`).join('');
    })
    .catch(e => { el('zoo-content').innerHTML = `<div class="err">${e}</div>`; });
}

// Auto-refresh expeditions every 30s
setInterval(() => { if (_loaded.has('zoo')) api('/zoo/expeditions').then(d => renderExpeditions(d)).catch(()=>{}); }, 30000);

// ── Activity ──────────────────────────────────────────────────────────────────
function loadActivity() { switchAct(_actTab, document.querySelector('#pg-activity .tb')); }
function switchAct(tab, btn) {
  _actTab = tab;
  document.querySelectorAll('#pg-activity .tb').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  ['quests','gacha','craft'].forEach(t => el('act-'+t).style.display = t===tab?'':'none');
  ({quests:loadQuests, gacha:loadGacha, craft:loadCraft}[tab])();
}

function loadQuests() {
  if (!_cid) { el('quests-c').innerHTML = '<div class="err">Нужен Профиль с чатом.</div>'; return; }
  api(`/quests/${_cid}`)
    .then(qs => {
      el('quests-c').innerHTML = qs.length
        ? '<div class="card">' + qs.map(q => {
            const pct = Math.min(100, Math.round((q.progress||0)/(q.target||1)*100));
            const r = q.reward||{}; const rw = [r.mora&&`+${fmt(r.mora)} 🪙`,r.diamonds&&`+${r.diamonds} 💎`].filter(Boolean).join(' ');
            return `<div class="qitem">
              <div class="qtitle">${q.completed?'✅':'🔲'} ${q.id}</div>
              ${rw?`<div class="qrw">${rw}</div>`:''}
              <div class="qbar"><div class="qfill" style="width:${pct}%"></div></div>
              <div class="qprog">${Math.round(q.progress||0)} / ${q.target}</div>
            </div>`;
          }).join('') + '</div>'
        : '<div class="loader">Нет квестов — напишите боту «бот задания».</div>';
    })
    .catch(e => { el('quests-c').innerHTML = `<div class="err">${e}</div>`; });
}

function loadGacha() {
  api('/gacha/').then(d => {
    el('gacha-c').innerHTML =
      `<div class="balrow">
        <div class="bal"><div class="bval">🪙 ${fmt(d.mora)}</div><div class="blbl">Мора</div></div>
      </div>
      <div class="card"><div class="card-title">Выберите крутку</div>` +
      d.spin_types.map(s => {
        const cost = s.cost_mora ? `${fmt(s.cost_mora)} 🪙` : `${s.cost_dia} 💎`;
        return `<div class="spin-row" onclick="doSpin('${s.spin_type}',this)">
          <span style="font-size:22px">🎲</span>
          <span class="spin-label">${s.label}</span>
          ${s.token_qty?`<span class="spin-tok">🎟 ×${s.token_qty}</span>`:''}
          <span class="spin-cost">${cost}</span>
        </div>`;
      }).join('') + '</div><div id="spin-res"></div>';
  }).catch(e => { el('gacha-c').innerHTML = `<div class="err">${e}</div>`; });
}
function doSpin(spinType, row) {
  row.style.opacity = '.5'; row.style.pointerEvents = 'none';
  api('/gacha/spin', {method:'POST', body:JSON.stringify({spin_type:spinType})})
    .then(r => {
      const mora = r.mora ? `🪙 ${fmt(r.mora)}` : '';
      const dia = r.diamonds ? `💎 ${r.diamonds}` : '';
      const items = (r.items||[]).map(i=>`${i.name} ×${i.qty}`).join(', ');
      const dups = (r.dup_outcomes||[]).map(d=>`${d.species||''} дубликат`).join(', ');
      const got = [mora,dia,items,dups].filter(Boolean).join('  ·  ') || '—';
      el('spin-res').innerHTML = `<div class="spin-res"><div class="spin-res-title">🎉 Результат!</div><div style="font-size:13px">${got}</div></div>`;
      loadGacha();
    })
    .catch(e => { toast(e, false); row.style.opacity='1'; row.style.pointerEvents=''; });
}

function loadCraft() {
  api('/craft/').then(recipes => {
    el('craft-c').innerHTML = recipes.length
      ? '<div class="card"><div class="card-title">Рецепты</div>' +
        recipes.map(r => {
          const ings = r.ingredients_status.map(i =>
            `<span style="color:${i.ok?'var(--green)':'var(--red)'};font-size:11px">${i.item_name}: ${i.have}/${i.needed}</span>`
          ).join('  ');
          return `<div style="padding:10px 0;border-bottom:1px solid var(--border2)">
            <div style="font-size:13px;font-weight:600;color:var(--bright);margin-bottom:5px">${r.name}</div>
            <div style="margin-bottom:8px">${ings}</div>
            <button class="btn btn-sm ${r.can_craft?'btn-gold':'btn-ghost'}" ${r.can_craft?'':'disabled'}
                    onclick="doCraft('${r.recipe_id}',this)">
              ${r.can_craft?'⚗️ Скрафтить':'🔒 Не хватает'}
            </button>
          </div>`;
        }).join('') + '</div>'
      : '<div class="loader">Рецептов нет.</div>';
  }).catch(e => { el('craft-c').innerHTML = `<div class="err">${e}</div>`; });
}
function doCraft(id, btn) {
  btn.disabled = true;
  api(`/craft/${id}`, {method:'POST'})
    .then(r => { toast(`✅ ${r.name} скрафтен!`); loadCraft(); })
    .catch(e => { toast(e, false); btn.disabled = false; });
}

// ── Shop ──────────────────────────────────────────────────────────────────────
function loadShop() { switchShop('buy', document.querySelector('#pg-shop .tb')); }
function switchShop(tab, btn) {
  document.querySelectorAll('#pg-shop .tb').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  el('shop-buy').style.display = tab==='buy' ? '' : 'none';
  el('shop-inv').style.display  = tab==='inv' ? '' : 'none';
  tab === 'buy' ? loadShopCatalog() : loadInventory();
}
function loadShopCatalog() {
  api('/shop/').then(d => {
    el('balrow').innerHTML =
      `<div class="bal"><div class="bval">🪙 ${fmt(d.mora)}</div><div class="blbl">Мора</div></div>
       <div class="bal"><div class="bval">💎 ${d.diamonds.toFixed(1)}</div><div class="blbl">Алмазы</div></div>`;
    const cats = {food:'🥩 Еда и корм', egg:'🥚 Яйца питомцев', utility:'🛠 Утилиты', booster:'⚗️ Зелья'};
    const groups = {};
    d.items.forEach(it => (groups[it.category]=groups[it.category]||[]).push(it));
    el('shop-buy').innerHTML = Object.entries(groups).map(([cat,list]) =>
      `<div class="card"><div class="card-title">${cats[cat]||cat}</div>` +
      list.map(it => {
        const price = it.price_mora ? `${fmt(it.price_mora)} 🪙` : `${it.price_diamonds} 💎`;
        return `<div class="shop-row">
          <div class="sico">${it.name.split(' ')[0]}</div>
          <div class="sinfo">
            <div class="sname">${it.name}</div>
            <div class="sprice">${price}${it.discount_active?' <span style="color:var(--green);font-size:10px">🐢</span>':''}</div>
            <div class="sdesc">${it.description||''}</div>
          </div>
          <button class="btn btn-sm btn-gold" onclick="buyItem('${it.item_id}',this)">Купить</button>
        </div>`;
      }).join('') + '</div>').join('');
  }).catch(e => { el('shop-buy').innerHTML = `<div class="err">${e}</div>`; });
}
function buyItem(itemId, btn) {
  btn.disabled = true;
  api('/shop/buy', {method:'POST', body:JSON.stringify({item_id:itemId, quantity:1})})
    .then(r => { toast(`✅ Куплено: ${r.item_name}`); loadShopCatalog(); })
    .catch(e => { toast(e, false); btn.disabled = false; });
}

// ── Inventory with modal interactions ─────────────────────────────────────────
let _invData = [];
function loadInventory() {
  el('shop-inv').innerHTML = '<div class="loader">Загрузка...</div>';
  api('/inventory/').then(items => {
    _invData = items;
    el('shop-inv').innerHTML = items.length
      ? '<div class="inv-grid">' + items.map(it => `
          <div class="icard" onclick="openItemModal('${it.item_id}')">
            <div class="ibadge">${it.category}</div>
            <div class="iname">${it.name}</div>
            <div class="iqty">×${it.quantity}</div>
            <div class="idesc">${it.description||''}</div>
          </div>`).join('') + '</div>'
      : '<div class="loader">Инвентарь пуст.</div>';
  }).catch(e => { el('shop-inv').innerHTML = `<div class="err">${e}</div>`; });
}

function openItemModal(itemId) {
  const it = _invData.find(i => i.item_id === itemId);
  if (!it) return;
  const {item_id, name, quantity, category, description, spin_type, boost_hours, fatigue_restore, gacha_rates} = it;

  let body = `<div class="info-row"><span>В инвентаре</span><span>×${quantity}</span></div>`;
  if (description) body += `<div style="font-size:12px;color:var(--muted);margin-top:8px;line-height:1.4">${description}</div>`;
  body += '<div class="divider"></div>';

  const actions = [{label:'Закрыть', cls:'btn-ghost', fn:'closeModal()'}];

  if (category === 'egg') {
    if (gacha_rates) {
      const rates = gacha_rates;
      body += `<div class="card-title" style="margin-top:0">Шансы при открытии</div>
        ${Object.entries(rates).filter(([,v])=>v>0).map(([r,v])=>
          `<div class="info-row"><span class="${rarityClass(r)}">${r}</span><span>${v}%</span></div>`
        ).join('')}`;
    }
    if (quantity > 0) {
      actions.unshift({label:'🥚 Открыть 1', cls:'btn-gold', fn:`doOpenEgg('${item_id}',1)`});
      if (quantity >= 5) actions.unshift({label:'🥚×5 Открыть 5', cls:'btn-gold', fn:`doOpenEgg('${item_id}',5)`});
    }
  } else if (category === 'food') {
    body += `<div class="card-title" style="margin-top:0">Восстанавливает усталость</div>
      <div class="info-row"><span>Эффект</span><span style="color:var(--green)">−${fatigue_restore} усталости</span></div>`;
    if (quantity > 0) actions.unshift({label:'🍖 Покормить питомца', cls:'btn-gold', fn:`openFeedSelectModal('${item_id}')`});
  } else if (category === 'booster' && boost_hours) {
    body += `<div class="info-row"><span>Ускорение</span><span style="color:var(--teal)">−${boost_hours} часа</span></div>`;
    if (quantity > 0) actions.unshift({label:'⏩ Применить к походу', cls:'btn-teal', fn:`openBoostSelectModal('${item_id}')`});
  } else if (category === 'spin_token') {
    body += `<div class="info-row"><span>Тип крутки</span><span>${spin_type||'?'}</span></div>`;
    if (quantity > 0) actions.unshift({label:'🎲 Открыть Гачу', cls:'btn-gold', fn:`gotoGacha()`});
  } else if (item_id.startsWith('star_dust')) {
    const dups = item_id === 'star_dust_l' ? 5 : 1;
    body += `<div class="info-row"><span>Даёт дубликатов</span><span style="color:var(--gold)">+${dups}</span></div>`;
    if (quantity > 0) actions.unshift({label:'✨ Применить к питомцу', cls:'btn-gold', fn:`openDustModal('${item_id}')`});
  }

  openModal(name, body, actions);
}

function doOpenEgg(eggId, count) {
  closeModal();
  api('/inventory/open-egg', {method:'POST', body:JSON.stringify({egg_id:eggId, count})})
    .then(r => {
      const results = r.results || [];
      const lines = results.map(res => {
        const outcome = {first_copy_created:'🆕 Новый питомец', leveled_up:'⬆️ Уровень вырос',
                         added:'➕ Дубликат', new_copy_created:'🆕 Новая копия', overflow:'💫 Переполнение'}[res.outcome] || res.outcome;
        return `<div class="info-row"><span>${res.species||''}</span><span>${outcome} ${res.new_level ? 'Lv'+res.new_level : ''}</span></div>`;
      }).join('');
      openModal('🎉 Яйцо открыто!', lines || '<div class="ok-box">Готово!</div>',
        [{label:'OK', cls:'btn-gold', fn:'closeModal()'}]);
      loadInventory();
    })
    .catch(e => toast(e, false));
}

function openFeedSelectModal(foodId) {
  if (!_zooData) { toast('Зайдите в Зоопарк сначала.', false); return; }
  const activePets = _zooData.pets.filter(p => p.placement !== 'storage');
  if (!activePets.length) { toast('Нет питомцев в питомнике.', false); return; }
  const html = activePets.map(p => `
    <div class="food-opt" onclick="doFeedFromInv(${p.id},'${foodId}',this)">
      <span class="fn">${p.name||p.species_id}</span>
      <span class="fq">${p.fatigue}% уст.</span>
    </div>`).join('');
  openModal('🍖 Выберите питомца', html, [{label:'Отмена', cls:'btn-ghost', fn:'closeModal()'}]);
}
function doFeedFromInv(petId, foodId, el) {
  el.style.opacity='.4';
  api('/zoo/feed', {method:'POST', body:JSON.stringify({pet_id:petId, food_id:foodId})})
    .then(r => { toast(`✅ ${r.fatigue_before}%→${r.fatigue_after}%`); closeModal(); _zooData=null; loadInventory(); })
    .catch(e => { toast(e,false); el.style.opacity='1'; });
}

function openBoostSelectModal(boosterId) {
  api('/zoo/expeditions').then(d => {
    if (!d.expeditions.length) { toast('Нет активных экспедиций.', false); return; }
    const html = d.expeditions.map(e => `
      <div class="boost-opt" onclick="doBoostFromInv(${e.pet_id},'${boosterId}',this)">
        <span style="font-size:18px">⚔️</span>
        <span class="bname">${e.name}</span>
        <span class="bval">${countdown(e.ends_at)}</span>
      </div>`).join('');
    openModal('⏩ Выберите экспедицию', html, [{label:'Отмена', cls:'btn-ghost', fn:'closeModal()'}]);
  }).catch(e => toast(e, false));
}
function doBoostFromInv(petId, boosterId, row) {
  row.style.opacity='.4';
  api('/zoo/boost', {method:'POST', body:JSON.stringify({pet_id:petId, booster_id:boosterId})})
    .then(r => { toast(`⏩ Ускорено на ${r.boosted_hours}ч!`); closeModal(); _loaded.delete('zoo'); loadZoo(); loadInventory(); })
    .catch(e => { toast(e,false); row.style.opacity='1'; });
}

function openDustModal(dustId) {
  if (!_zooData) { toast('Зайдите в Зоопарк сначала.', false); return; }
  const html = _zooData.pets.map(p => `
    <div class="food-opt" onclick="doApplyDust('${dustId}',${p.id},this)">
      <span class="fn">${p.name||p.species_id}</span>
      <span class="fq ${rarityClass(p.rarity)}">${p.rarity} · Lv${p.pet_level}</span>
    </div>`).join('');
  openModal('✨ Выберите питомца', html, [{label:'Отмена', cls:'btn-ghost', fn:'closeModal()'}]);
}
function doApplyDust(dustId, petId, row) {
  row.style.opacity='.4';
  api('/inventory/apply-dust', {method:'POST', body:JSON.stringify({dust_id:dustId, pet_id:petId})})
    .then(r => { toast(`✅ +${r.duplicates_added} дубликат(а)`); closeModal(); _zooData=null; loadInventory(); })
    .catch(e => { toast(e,false); row.style.opacity='1'; });
}

function gotoGacha() {
  closeModal();
  document.querySelectorAll('.nb')[2].click();
  switchAct('gacha', document.querySelectorAll('#pg-activity .tb')[1]);
}

// ── Top ───────────────────────────────────────────────────────────────────────
function loadTop() { switchTop('local', document.querySelector('#pg-top .tb')); }
function switchTop(mode, btn) {
  document.querySelectorAll('#pg-top .tb').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  if (mode==='local' && !_cid) { el('top-c').innerHTML = '<div class="err">Нужен Профиль с чатом.</div>'; return; }
  el('top-c').innerHTML = '<div class="loader">Загрузка...</div>';
  api(mode==='global' ? '/top/global' : `/top/local/${_cid}`)
    .then(rows => {
      el('top-c').innerHTML = rows.length
        ? '<div class="card">' + rows.slice(0,30).map((r,i) =>
            `<div class="trow">
              <div class="tpos">${MEDALS[i]||(i+1)+'.'}</div>
              <div class="tname">${r.username}</div>
              <div class="tcnt">${fmt(r.count)} 💬</div>
            </div>`).join('') + '</div>'
        : '<div class="loader">Данных пока нет.</div>';
    })
    .catch(e => { el('top-c').innerHTML = `<div class="err">${e}</div>`; });
}

// Profile auto-refresh every 5 min
setInterval(() => { if (_loaded.has('profile')) loadProfile(); }, 300000);
</script>
</body>
</html>"""
