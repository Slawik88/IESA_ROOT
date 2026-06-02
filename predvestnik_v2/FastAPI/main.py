"""FastAPI/main.py — Predvestnik Mini App entry point.
Adapter layer: registers routers, serves HTML shell. No business logic.
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
    await create_pool()   # idempotent — no-op if bot already initialised pool
    yield


app = FastAPI(title="Predvestnik Mini App", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for router in [profile.router, top.router, inventory.router, shop.router,
               zoo.router, gacha.router, craft.router, quests.router]:
    app.include_router(router)


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
    return {
        "session_token": create_session_token(int(user["id"])),
        "user_id":       user["id"],
        "username":      user.get("username", ""),
        "first_name":    user.get("first_name", ""),
    }


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
            "user_balance_mora, user_balance_diamonds "
            "FROM users WHERE user_tg_id = ?", (user_id,)
        ) as c:
            row = await c.fetchone()
    if not row:
        raise HTTPException(404, "Not found")
    return dict(row)


@app.get("/api/events")
async def api_events():
    async with get_pool().acquire() as conn:
        db = PGAdapter(conn)
        async with db.execute(
            "SELECT * FROM exchange_events WHERE status = 'active' LIMIT 1"
        ) as c:
            active = await c.fetchone()
        async with db.execute(
            "SELECT * FROM exchange_events WHERE status = 'scheduled' "
            "ORDER BY starts_at LIMIT 1"
        ) as c:
            scheduled = await c.fetchone()
    if active:
        a = dict(active)
        return {"exchange": {"active": True, "ends_at": str(a.get("ends_at", ""))[:16]}}
    if scheduled:
        s = dict(scheduled)
        return {"exchange": {"active": False, "scheduled": True,
                             "starts_at": str(s.get("starts_at", ""))[:16]}}
    return {"exchange": {"active": False, "scheduled": False}}


# ── Mini App HTML ──────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def mini_app():
    bot_username = os.getenv("BOT_USERNAME", "IIIPredvestnikIIIBot")
    return HTMLResponse(_HTML.replace("{{BOT_USERNAME}}", bot_username))


_HTML = """<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0,viewport-fit=cover"/>
  <title>Предвестник</title>
  <script src="https://telegram.org/js/telegram-web-app.js"></script>
  <script src="https://telegram.org/js/telegram-widget.js?22"
          data-telegram-login="{{BOT_USERNAME}}"
          data-size="large" data-radius="10"
          data-onauth="onTelegramWidgetAuth(user)"
          data-request-access="write" async></script>
  <style>
    :root{--bg:#0d0d1a;--surface:#151528;--card:#1e1e38;
          --accent:#7b5cff;--accent2:#c084fc;
          --text:#e2e2f0;--muted:#8888aa;
          --gold:#f5c542;--green:#4ade80;--red:#f87171}
    *{margin:0;padding:0;box-sizing:border-box}
    body{background:var(--bg);color:var(--text);
         font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
         min-height:100vh;padding-bottom:72px}
    .nav{position:fixed;bottom:0;left:0;right:0;background:var(--surface);
         border-top:1px solid rgba(255,255,255,.07);display:flex;z-index:100;
         padding-bottom:env(safe-area-inset-bottom)}
    .nav-btn{flex:1;padding:8px 2px;text-align:center;cursor:pointer;
             font-size:10px;color:var(--muted);transition:.15s}
    .nav-btn.active{color:var(--accent)}
    .nav-btn .icon{font-size:20px;display:block;margin-bottom:2px}
    .page{display:none;padding:12px}
    .page.active{display:block}
    .card{background:var(--card);border-radius:16px;padding:14px;margin-bottom:10px;
          border:1px solid rgba(123,92,255,.12)}
    .card-title{font-size:11px;text-transform:uppercase;letter-spacing:1px;
                color:var(--muted);margin-bottom:10px}
    .stat-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:12px}
    .stat{background:var(--surface);border-radius:12px;padding:10px;text-align:center}
    .stat .icon{font-size:18px}
    .stat .val{font-size:17px;font-weight:700;margin:2px 0}
    .stat .lbl{font-size:10px;color:var(--muted)}
    .profile-head{display:flex;align-items:center;gap:12px;margin-bottom:14px}
    .avatar{width:48px;height:48px;border-radius:50%;flex-shrink:0;
            background:linear-gradient(135deg,var(--accent),var(--accent2));
            display:flex;align-items:center;justify-content:center;font-size:20px}
    .profile-info .name{font-size:17px;font-weight:700}
    .profile-info .rank{font-size:11px;color:var(--muted);margin-top:2px}
    .tab-row{display:flex;gap:6px;margin-bottom:12px}
    .tab-btn{flex:1;padding:8px;border-radius:10px;border:none;cursor:pointer;
             background:var(--surface);color:var(--muted);font-size:12px;transition:.15s}
    .tab-btn.active{background:rgba(123,92,255,.25);color:var(--accent)}
    .pet-card{display:flex;align-items:center;gap:10px;padding:10px 0;
              border-bottom:1px solid rgba(255,255,255,.05)}
    .pet-card:last-child{border:none}
    .pet-icon{font-size:26px;width:34px;text-align:center;flex-shrink:0}
    .pet-info{flex:1}
    .pet-name{font-size:13px;font-weight:600}
    .pet-sub{font-size:11px;color:var(--muted);margin-top:2px}
    .fat-bar{height:4px;background:rgba(255,255,255,.1);border-radius:2px;margin:5px 0}
    .fat-fill{height:100%;border-radius:2px;transition:.3s}
    .top-row{display:flex;align-items:center;padding:8px 0;
             border-bottom:1px solid rgba(255,255,255,.05)}
    .top-row:last-child{border:none}
    .top-pos{font-size:16px;width:28px;text-align:center;flex-shrink:0}
    .top-name{font-size:13px;flex:1;padding:0 8px}
    .top-count{font-size:12px;color:var(--gold);font-weight:600}
    .inv-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px}
    .inv-item{background:var(--surface);border-radius:12px;padding:12px}
    .inv-item .iname{font-size:12px;font-weight:600;margin-bottom:4px}
    .inv-item .iqty{font-size:18px;font-weight:700;color:var(--accent)}
    .inv-item .idesc{font-size:10px;color:var(--muted);margin-top:3px}
    .shop-item{display:flex;align-items:center;gap:10px;padding:10px 0;
               border-bottom:1px solid rgba(255,255,255,.05)}
    .shop-item:last-child{border:none}
    .shop-icon{font-size:24px;width:32px;text-align:center;flex-shrink:0}
    .shop-info{flex:1}
    .shop-name{font-size:13px;font-weight:600}
    .shop-price{font-size:11px;color:var(--gold);margin-top:2px}
    .shop-desc{font-size:10px;color:var(--muted);margin-top:2px}
    .quest-item{padding:10px 0;border-bottom:1px solid rgba(255,255,255,.05)}
    .quest-item:last-child{border:none}
    .quest-title{font-size:13px;font-weight:600;margin-bottom:4px}
    .quest-reward{font-size:11px;color:var(--gold)}
    .quest-bar{height:5px;background:rgba(255,255,255,.1);border-radius:3px;margin:6px 0 3px}
    .quest-fill{height:100%;border-radius:3px;background:var(--accent);transition:.3s}
    .spin-list{display:flex;flex-direction:column;gap:8px;margin-bottom:12px}
    .spin-btn{display:flex;align-items:center;gap:10px;padding:12px;
              background:var(--surface);border-radius:12px;border:none;
              cursor:pointer;color:var(--text);text-align:left;width:100%;transition:.15s}
    .spin-btn:hover{background:rgba(123,92,255,.15)}
    .spin-result{background:var(--card);border-radius:14px;padding:14px;
                 border:2px solid var(--accent);margin-top:10px}
    .btn{padding:8px 14px;border-radius:10px;border:none;cursor:pointer;
         background:linear-gradient(135deg,var(--accent),var(--accent2));
         color:#fff;font-size:13px;font-weight:600;transition:.15s}
    .btn:disabled{opacity:.4;cursor:not-allowed}
    .btn-sm{padding:5px 10px;font-size:11px}
    .loader{text-align:center;color:var(--muted);padding:28px;font-size:13px}
    .err{background:rgba(248,113,113,.12);border:1px solid rgba(248,113,113,.3);
         border-radius:12px;padding:12px;color:var(--red);font-size:12px;margin:6px 0}
    .bal-row{display:flex;gap:8px;margin-bottom:10px}
    .bal{flex:1;background:var(--card);border-radius:12px;padding:8px;text-align:center}
    .bal .val{font-size:14px;font-weight:700}
    .bal .lbl{font-size:10px;color:var(--muted)}
    .food-list{display:flex;flex-direction:column;gap:5px;margin-top:8px}
    .food-opt{display:flex;align-items:center;gap:8px;padding:7px;
              background:var(--surface);border-radius:10px;cursor:pointer;transition:.15s}
    .food-opt:hover{background:rgba(123,92,255,.15)}
    .food-opt .fname{font-size:12px;flex:1}
    .food-opt .fqty{font-size:11px;color:var(--muted)}
    .food-opt .frest{font-size:11px;color:var(--green);font-weight:600}
    .login-overlay{position:fixed;inset:0;background:var(--bg);z-index:200;
                   display:flex;flex-direction:column;align-items:center;
                   justify-content:center;gap:20px;padding:28px;text-align:center}
    .login-overlay h1{font-size:26px;font-weight:800;
                      background:linear-gradient(135deg,var(--accent),var(--accent2));
                      -webkit-background-clip:text;-webkit-text-fill-color:transparent}
    .login-overlay p{color:var(--muted);font-size:13px;max-width:260px;line-height:1.5}
    .login-overlay.hidden{display:none}
    .toast{position:fixed;top:14px;left:50%;transform:translateX(-50%);
           padding:9px 18px;border-radius:99px;font-size:13px;font-weight:600;
           z-index:9999;opacity:0;transition:.25s;pointer-events:none}
    .toast.show{opacity:1}
  </style>
</head>
<body>
<div id="toast" class="toast"></div>

<div id="login-overlay" class="login-overlay hidden">
  <h1>🔮 Предвестник</h1>
  <p>Войдите через Telegram чтобы увидеть профиль, кормить питомцев и крутить гачу.</p>
  <div id="tg-login-widget"></div>
  <p style="font-size:10px;color:var(--muted)">Данные не хранятся без вашего разрешения.</p>
</div>

<!-- 1. Профиль -->
<div id="pg-profile" class="page active">
  <div id="profile-content" class="loader">Загрузка...</div>
</div>

<!-- 2. Зоопарк -->
<div id="pg-zoo" class="page">
  <div id="zoo-exp" class="card" style="display:none">
    <div class="card-title">⚔️ Активные экспедиции</div>
    <div id="zoo-exp-content"></div>
  </div>
  <div class="card">
    <div class="card-title">🐾 Питомцы</div>
    <div id="zoo-content" class="loader">Загрузка...</div>
  </div>
</div>

<!-- 3. Активность -->
<div id="pg-activity" class="page">
  <div class="tab-row">
    <button class="tab-btn active" onclick="switchActivity('quests',this)">📋 Квесты</button>
    <button class="tab-btn" onclick="switchActivity('gacha',this)">🎲 Гача</button>
    <button class="tab-btn" onclick="switchActivity('craft',this)">⚗️ Крафт</button>
  </div>
  <div id="act-quests"><div id="quests-content" class="loader">Загрузка...</div></div>
  <div id="act-gacha" style="display:none"><div id="gacha-content" class="loader">Загрузка...</div></div>
  <div id="act-craft" style="display:none"><div id="craft-content" class="loader">Загрузка...</div></div>
</div>

<!-- 4. Магазин -->
<div id="pg-shop" class="page">
  <div class="tab-row">
    <button class="tab-btn active" onclick="switchShop('buy',this)">🛒 Купить</button>
    <button class="tab-btn" onclick="switchShop('inv',this)">🎒 Инвентарь</button>
  </div>
  <div id="shop-bal" class="bal-row"></div>
  <div id="shop-buy"><div class="loader">Загрузка...</div></div>
  <div id="shop-inv" style="display:none"></div>
</div>

<!-- 5. Топ -->
<div id="pg-top" class="page">
  <div class="tab-row">
    <button class="tab-btn active" onclick="switchTop('local',this)">🏘 Чат</button>
    <button class="tab-btn" onclick="switchTop('global',this)">🌍 Глобальный</button>
  </div>
  <div id="top-content" class="loader">Загрузка...</div>
</div>

<nav class="nav">
  <div class="nav-btn active" onclick="switchPage('profile',this)"><span class="icon">👤</span>Профиль</div>
  <div class="nav-btn" onclick="switchPage('zoo',this)"><span class="icon">🐾</span>Зоопарк</div>
  <div class="nav-btn" onclick="switchPage('activity',this)"><span class="icon">🎮</span>Активность</div>
  <div class="nav-btn" onclick="switchPage('shop',this)"><span class="icon">🛒</span>Магазин</div>
  <div class="nav-btn" onclick="switchPage('top',this)"><span class="icon">🏆</span>Топ</div>
</nav>

<script>
const tg = window.Telegram?.WebApp;
if (tg) { tg.ready(); tg.expand(); }

const BASE = (window.location.origin + window.location.pathname).replace(/\/$/, '');
const INIT_DATA = tg?.initData || '';
const SESSION_KEY = 'pv_session';
const MEDALS = ['🥇','🥈','🥉'];
const PLACE = {active:'Активный', passive:'Пассивный', stash:'Запас'};
let _chatId = 0;
let _actTab = 'quests';

function getSession() { return localStorage.getItem(SESSION_KEY) || ''; }
function authHeaders() {
  const h = {'content-type': 'application/json'};
  if (INIT_DATA) h['x-init-data'] = INIT_DATA;
  const s = getSession(); if (s) h['x-session-token'] = s;
  return h;
}
function api(path, opts = {}) {
  return fetch(BASE + path, {...opts, headers: {...authHeaders(), ...(opts.headers||{})}})
    .then(r => {
      if (r.status === 401) {
        localStorage.removeItem(SESSION_KEY);
        document.getElementById('login-overlay').classList.remove('hidden');
        return Promise.reject('Требуется повторный вход.');
      }
      return r.ok ? r.json() : r.json().then(e => Promise.reject(e.detail || 'Ошибка'));
    });
}
function toast(msg, ok = true) {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.style.cssText = `background:${ok?'var(--green)':'var(--red)'};color:${ok?'#000':'#fff'}`;
  el.classList.add('show');
  setTimeout(() => el.classList.remove('show'), 2500);
}
function fmt(n) { return Number(n).toLocaleString('ru'); }
function fatColor(f) { return f < 40 ? 'var(--green)' : f < 70 ? 'var(--gold)' : 'var(--red)'; }
function el(id) { return document.getElementById(id); }

// ── Auth ──────────────────────────────────────────────────────────────────────
window.onTelegramWidgetAuth = function(user) {
  api('/auth/telegram-login', {method:'POST', body:JSON.stringify(user)})
    .then(d => {
      localStorage.setItem(SESSION_KEY, d.session_token);
      el('login-overlay').classList.add('hidden');
      loadProfile();
    })
    .catch(e => alert('Ошибка входа: ' + e));
};
if (!INIT_DATA && !getSession()) el('login-overlay').classList.remove('hidden');

// ── Navigation ────────────────────────────────────────────────────────────────
const _loaded = new Set();
function switchPage(name, btn) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
  el('pg-' + name).classList.add('active');
  btn.classList.add('active');
  if (!_loaded.has(name)) {
    _loaded.add(name);
    ({zoo:loadZoo, activity:loadActivity, shop:loadShop, top:loadTop}[name] || (()=>{}))();
  }
}

// ── Profile ───────────────────────────────────────────────────────────────────
function loadProfile() {
  el('profile-content').innerHTML = '<div class="loader">Загрузка...</div>';
  api('/profile/me')
    .then(d => {
      if (d.chats?.length) _chatId = d.chats[0].chat_tg_id;
      const pets = d.pets.filter(p => p.placement !== 'stash').slice(0, 4);
      const petsHtml = pets.length
        ? pets.map(p => `<div class="pet-card">
            <div class="pet-icon">🐾</div>
            <div class="pet-info">
              <div class="pet-name">${p.name||p.species_id}</div>
              <div class="pet-sub">Lv${p.pet_level} · ${PLACE[p.placement]||p.placement} · ${p.fatigue}% уст.</div>
              <div class="fat-bar"><div class="fat-fill" style="width:${p.fatigue}%;background:${fatColor(p.fatigue)}"></div></div>
            </div></div>`).join('')
        : '<div style="color:var(--muted);font-size:12px">Нет активных питомцев</div>';
      const chatsHtml = d.chats.map(c =>
        `<div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid rgba(255,255,255,.05)">
          <span style="font-size:12px">${c.chat_title||'Чат'}</span>
          <span style="font-size:11px;color:var(--muted)">Lv${c.user_level} · ${fmt(c.user_messages_count_all_time)} сообщ.</span>
        </div>`).join('');
      el('profile-content').innerHTML = `
        <div class="profile-head">
          <div class="avatar">🔮</div>
          <div class="profile-info"><div class="name">@${d.username||'Игрок'}</div><div class="rank">${d.rank}</div></div>
        </div>
        <div class="stat-grid">
          <div class="stat"><div class="icon">🪙</div><div class="val">${fmt(d.mora)}</div><div class="lbl">Мора</div></div>
          <div class="stat"><div class="icon">💎</div><div class="val">${d.diamonds.toFixed(1)}</div><div class="lbl">Алмазы</div></div>
          <div class="stat"><div class="icon">🔥</div><div class="val">${d.streak}</div><div class="lbl">Стрик</div></div>
          <div class="stat"><div class="icon">🏆</div><div class="val">${d.achievements}</div><div class="lbl">Ачивки</div></div>
        </div>
        <div class="card"><div class="card-title">🐾 Питомцы в питомнике</div>${petsHtml}</div>
        ${chatsHtml ? `<div class="card"><div class="card-title">💬 Активность</div>${chatsHtml}</div>` : ''}`;
    })
    .catch(e => { el('profile-content').innerHTML = `<div class="err">${typeof e==='string'?e:'Профиль не найден — напишите боту.'}</div>`; });
}
if (INIT_DATA || getSession()) loadProfile();
_loaded.add('profile');

// ── Zoo ───────────────────────────────────────────────────────────────────────
let _currentPetId = 0;
function loadZoo() {
  Promise.all([api('/zoo/'), api('/zoo/expeditions')])
    .then(([data, exps]) => {
      if (exps.length) {
        el('zoo-exp').style.display = 'block';
        el('zoo-exp-content').innerHTML = exps.map(e => {
          const diff = Math.max(0, Math.round((new Date(e.ends_at+'Z') - Date.now()) / 60000));
          return `<div class="pet-card">
            <div class="pet-icon">⚔️</div>
            <div class="pet-info">
              <div class="pet-name">${e.name}</div>
              <div class="pet-sub">${e.duration_hours}ч поход · ${Math.floor(diff/60)}ч ${diff%60}мин осталось</div>
            </div></div>`;
        }).join('');
      }
      const food = data.available_food;
      const foodHtml = Object.entries(food).map(([fid, f]) =>
        `<div class="food-opt" onclick="feedPet(_currentPetId,'${fid}',this)">
          <span class="fname">${f.name}</span>
          <span class="fqty">×${f.qty}</span>
          <span class="frest">−${f.restore} уст.</span>
        </div>`).join('') || '<div style="color:var(--muted);font-size:11px;padding:5px">Нет корма — купите в Магазине</div>';

      el('zoo-content').innerHTML = data.pets.length
        ? data.pets.map(p => `
          <div class="pet-card">
            <div class="pet-icon">🐾</div>
            <div class="pet-info">
              <div class="pet-name">${p.name||p.species_id} <span style="font-size:10px;color:var(--muted)">${p.rarity}</span></div>
              <div class="pet-sub">Lv${p.pet_level} · ${PLACE[p.placement]||p.placement}</div>
              <div class="fat-bar"><div class="fat-fill" style="width:${p.fatigue}%;background:${fatColor(p.fatigue)}"></div></div>
              <div style="font-size:10px;color:var(--muted);margin:3px 0">Усталость: ${p.fatigue}%</div>
              ${p.fatigue > 0
                ? `<button class="btn btn-sm" onclick="_currentPetId=${p.id};this.nextElementSibling.style.display=this.nextElementSibling.style.display==='none'?'flex':'none';this.nextElementSibling.style.flexDirection='column'">🍖 Покормить</button>
                   <div style="display:none" class="food-list">${foodHtml}</div>`
                : '<span style="color:var(--green);font-size:11px">✅ Бодрый</span>'}
            </div>
          </div>`).join('')
        : '<div style="color:var(--muted);font-size:13px">Питомцев нет — откройте яйцо в Активности!</div>';
    })
    .catch(e => { el('zoo-content').innerHTML = `<div class="err">${e}</div>`; });
}
function feedPet(petId, foodId, btn) {
  btn.style.opacity = '.5';
  api('/zoo/feed', {method:'POST', body:JSON.stringify({pet_id:petId, food_id:foodId})})
    .then(r => { toast(`✅ Усталость: ${r.fatigue_before}% → ${r.fatigue_after}%`); _loaded.delete('zoo'); loadZoo(); })
    .catch(e => { toast(e, false); btn.style.opacity = '1'; });
}

// ── Activity ──────────────────────────────────────────────────────────────────
function loadActivity() { switchActivity(_actTab, document.querySelector('#pg-activity .tab-btn')); }
function switchActivity(tab, btn) {
  _actTab = tab;
  document.querySelectorAll('#pg-activity .tab-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  ['quests','gacha','craft'].forEach(t => el('act-'+t).style.display = t===tab?'':'none');
  ({quests:loadQuests, gacha:loadGacha, craft:loadCraft}[tab])();
}

function loadQuests() {
  if (!_chatId) { el('quests-content').innerHTML = '<div class="err">Откройте Профиль сначала.</div>'; return; }
  api(`/quests/${_chatId}`)
    .then(qs => {
      el('quests-content').innerHTML = qs.length
        ? '<div class="card">' + qs.map(q => {
            const pct = Math.min(100, Math.round((q.progress||0) / (q.target||1) * 100));
            const rw = q.reward?.mora ? `+${fmt(q.reward.mora)} 🪙` : '';
            return `<div class="quest-item">
              <div class="quest-title">${q.completed?'✅':'🔲'} ${q.id}</div>
              ${rw ? `<div class="quest-reward">${rw}</div>` : ''}
              <div class="quest-bar"><div class="quest-fill" style="width:${pct}%"></div></div>
              <div style="font-size:10px;color:var(--muted)">${Math.round(q.progress||0)} / ${q.target||1}</div>
            </div>`;
          }).join('') + '</div>'
        : '<div class="loader">Нет квестов — напишите боту «бот задания».</div>';
    })
    .catch(e => { el('quests-content').innerHTML = `<div class="err">${e}</div>`; });
}

function loadGacha() {
  api('/gacha/')
    .then(d => {
      el('gacha-content').innerHTML =
        `<div class="bal-row"><div class="bal"><div class="val">🪙 ${fmt(d.mora)}</div><div class="lbl">Мора</div></div></div>
         <div class="card"><div class="card-title">Выберите крутку</div><div class="spin-list">` +
        d.spin_types.map(s => {
          const cost = s.cost_mora ? `${fmt(s.cost_mora)} 🪙` : `${s.cost_dia} 💎`;
          const tok = s.token_qty ? `<span style="color:var(--green);font-size:11px">🎟 ×${s.token_qty}</span>` : '';
          return `<button class="spin-btn" onclick="doSpin('${s.spin_type}',this)">
            <span style="font-size:22px">🎲</span>
            <span style="flex:1;font-size:13px;font-weight:600">${s.label}</span>
            ${tok}<span style="font-size:12px;color:var(--gold)">${cost}</span>
          </button>`;
        }).join('') +
        '</div></div><div id="spin-result"></div>';
    })
    .catch(e => { el('gacha-content').innerHTML = `<div class="err">${e}</div>`; });
}
function doSpin(spinType, btn) {
  btn.disabled = true;
  api('/gacha/spin', {method:'POST', body:JSON.stringify({spin_type:spinType})})
    .then(r => {
      const mora = r.mora ? `🪙 ${fmt(r.mora)}` : '';
      const dia = r.diamonds ? `💎 ${r.diamonds}` : '';
      const items = (r.items||[]).map(i=>`${i.name} ×${i.qty}`).join(', ');
      const dups = (r.dup_outcomes||[]).map(d=>`${d.species} дубликат`).join(', ');
      const got = [mora, dia, items, dups].filter(Boolean).join(' · ') || '—';
      el('spin-result').innerHTML =
        `<div class="spin-result"><div style="font-size:14px;font-weight:700;color:var(--accent);margin-bottom:6px">🎉 Результат!</div><div>${got}</div></div>`;
      loadGacha();
    })
    .catch(e => { toast(e, false); btn.disabled = false; });
}

function loadCraft() {
  api('/craft/')
    .then(recipes => {
      el('craft-content').innerHTML = recipes.length
        ? '<div class="card"><div class="card-title">Рецепты</div>' +
          recipes.map(r => {
            const ings = r.ingredients_status.map(i =>
              `<span style="color:${i.ok?'var(--green)':'var(--red)'};font-size:11px">${i.item_name}: ${i.have}/${i.needed}</span>`).join('  ');
            return `<div style="padding:10px 0;border-bottom:1px solid rgba(255,255,255,.05)">
              <div style="font-size:13px;font-weight:600;margin-bottom:4px">${r.name}</div>
              <div>${ings}</div>
              <button class="btn btn-sm" style="margin-top:8px" ${r.can_craft?'':'disabled'}
                      onclick="doCraft('${r.recipe_id}',this)">
                ${r.can_craft?'⚗️ Скрафтить':'🔒 Не хватает'}</button>
            </div>`;
          }).join('') + '</div>'
        : '<div class="loader">Рецептов нет.</div>';
    })
    .catch(e => { el('craft-content').innerHTML = `<div class="err">${e}</div>`; });
}
function doCraft(recipeId, btn) {
  btn.disabled = true;
  api(`/craft/${recipeId}`, {method:'POST'})
    .then(r => { toast(`✅ ${r.name} скрафтен!`); loadCraft(); })
    .catch(e => { toast(e, false); btn.disabled = false; });
}

// ── Shop ──────────────────────────────────────────────────────────────────────
function loadShop() { switchShop('buy', document.querySelector('#pg-shop .tab-btn')); }
function switchShop(tab, btn) {
  document.querySelectorAll('#pg-shop .tab-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  el('shop-buy').style.display = tab==='buy'?'':'none';
  el('shop-inv').style.display  = tab==='inv'?'':'none';
  tab === 'buy' ? loadShopCatalog() : loadInventory();
}
function loadShopCatalog() {
  api('/shop/')
    .then(d => {
      el('shop-bal').innerHTML =
        `<div class="bal"><div class="val">🪙 ${fmt(d.mora)}</div><div class="lbl">Мора</div></div>
         <div class="bal"><div class="val">💎 ${d.diamonds.toFixed(1)}</div><div class="lbl">Алмазы</div></div>`;
      const cats = {food:'🥩 Еда', egg:'🥚 Яйца', utility:'🛠 Утилиты', booster:'⚗️ Зелья'};
      const groups = {};
      d.items.forEach(it => (groups[it.category]=groups[it.category]||[]).push(it));
      el('shop-buy').innerHTML = Object.entries(groups).map(([cat, list]) =>
        `<div class="card"><div class="card-title">${cats[cat]||cat}</div>` +
        list.map(it => {
          const price = it.price_mora ? `${fmt(it.price_mora)} 🪙` : `${it.price_diamonds} 💎`;
          return `<div class="shop-item">
            <div class="shop-icon">${it.name.split(' ')[0]}</div>
            <div class="shop-info">
              <div class="shop-name">${it.name}</div>
              <div class="shop-price">${price}${it.discount_active?' 🐢':''}</div>
              <div class="shop-desc">${it.description||''}</div>
            </div>
            <button class="btn btn-sm" onclick="buyItem('${it.item_id}',this)">Купить</button>
          </div>`;
        }).join('') + '</div>').join('');
    })
    .catch(e => { el('shop-buy').innerHTML = `<div class="err">${e}</div>`; });
}
function buyItem(itemId, btn) {
  btn.disabled = true;
  api('/shop/buy', {method:'POST', body:JSON.stringify({item_id:itemId, quantity:1})})
    .then(r => { toast(`✅ Куплено: ${r.item_name}`); loadShopCatalog(); })
    .catch(e => { toast(e, false); btn.disabled = false; });
}
function loadInventory() {
  api('/inventory/')
    .then(items => {
      el('shop-inv').innerHTML = items.length
        ? '<div class="inv-grid">' + items.map(it =>
            `<div class="inv-item">
              <div class="iname">${it.name}</div>
              <div class="iqty">×${it.quantity}</div>
              <div class="idesc">${it.description||''}</div>
            </div>`).join('') + '</div>'
        : '<div class="loader">Инвентарь пуст.</div>';
    })
    .catch(e => { el('shop-inv').innerHTML = `<div class="err">${e}</div>`; });
}

// ── Top ───────────────────────────────────────────────────────────────────────
function loadTop() { switchTop('local', document.querySelector('#pg-top .tab-btn')); }
function switchTop(mode, btn) {
  document.querySelectorAll('#pg-top .tab-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  if (mode==='local' && !_chatId) {
    el('top-content').innerHTML = '<div class="err">Нужен профиль с чатом.</div>'; return;
  }
  el('top-content').innerHTML = '<div class="loader">Загрузка...</div>';
  api(mode==='global' ? '/top/global' : `/top/local/${_chatId}`)
    .then(rows => {
      el('top-content').innerHTML = rows.length
        ? '<div class="card">' + rows.slice(0,30).map((r,i) =>
            `<div class="top-row">
              <div class="top-pos">${MEDALS[i]||(i+1)+'.'}</div>
              <div class="top-name">${r.username}</div>
              <div class="top-count">${fmt(r.count)} 💬</div>
            </div>`).join('') + '</div>'
        : '<div class="loader">Данных пока нет.</div>';
    })
    .catch(e => { el('top-content').innerHTML = `<div class="err">${e}</div>`; });
}
</script>
</body>
</html>"""
