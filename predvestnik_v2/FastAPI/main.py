"""FastAPI/main.py — Predvestnik Mini App entry point.
Adapter layer: registers routers, serves HTML shell.
No business logic here.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from dotenv import load_dotenv

load_dotenv()

from infrastructure.database import create_pool
from FastAPI.routers import profile, top, inventory, shop


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_pool()   # idempotent — no-op if bot already initialised the pool
    yield


app = FastAPI(title="Predvestnik Mini App", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(profile.router)
app.include_router(top.router)
app.include_router(inventory.router)
app.include_router(shop.router)


# ── Health / legacy ────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    return {"status": "ok"}


# Keep old /profile/{user_id} and /api/top/global endpoints for backward compat
@app.get("/profile/{user_id}")
async def legacy_profile(user_id: int):
    from infrastructure.database import get_pool
    from infrastructure.pg_adapter import PGAdapter
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
    from infrastructure.database import get_pool
    from infrastructure.pg_adapter import PGAdapter
    async with get_pool().acquire() as conn:
        db = PGAdapter(conn)
        async with db.execute(
            "SELECT * FROM exchange_events WHERE status = 'active' LIMIT 1"
        ) as c:
            active = await c.fetchone()
        async with db.execute(
            "SELECT * FROM exchange_events WHERE status = 'scheduled' ORDER BY starts_at LIMIT 1"
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
    return HTMLResponse(_HTML)


_HTML = """<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0,viewport-fit=cover"/>
  <title>Предвестник</title>
  <script src="https://telegram.org/js/telegram-web-app.js"></script>
  <style>
    :root {
      --bg:#0d0d1a; --surface:#151528; --card:#1e1e38;
      --accent:#7b5cff; --accent2:#c084fc;
      --text:#e2e2f0; --muted:#8888aa;
      --gold:#f5c542; --green:#4ade80; --red:#f87171;
    }
    *{margin:0;padding:0;box-sizing:border-box}
    body{background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
         min-height:100vh;padding-bottom:80px}
    /* Nav */
    .nav{position:fixed;bottom:0;left:0;right:0;background:var(--surface);
         border-top:1px solid rgba(255,255,255,.07);display:flex;z-index:100}
    .nav-btn{flex:1;padding:10px 4px;text-align:center;cursor:pointer;
             font-size:11px;color:var(--muted);transition:.2s}
    .nav-btn.active{color:var(--accent)}
    .nav-btn .icon{font-size:22px;display:block;margin-bottom:2px}
    /* Pages */
    .page{display:none;padding:12px}
    .page.active{display:block}
    /* Cards */
    .card{background:var(--card);border-radius:16px;padding:16px;margin-bottom:12px;
          border:1px solid rgba(123,92,255,.12)}
    .card-title{font-size:11px;text-transform:uppercase;letter-spacing:1px;color:var(--muted);margin-bottom:10px}
    /* Stat grid */
    .stat-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px}
    .stat{background:var(--surface);border-radius:12px;padding:12px;text-align:center}
    .stat .icon{font-size:20px}
    .stat .val{font-size:18px;font-weight:700;margin:2px 0}
    .stat .lbl{font-size:11px;color:var(--muted)}
    /* Profile header */
    .profile-head{display:flex;align-items:center;gap:14px;margin-bottom:16px}
    .avatar{width:54px;height:54px;border-radius:50%;
            background:linear-gradient(135deg,var(--accent),var(--accent2));
            display:flex;align-items:center;justify-content:center;font-size:22px;flex-shrink:0}
    .profile-info .name{font-size:18px;font-weight:700}
    .profile-info .rank{font-size:12px;color:var(--muted);margin-top:2px}
    /* Pet card */
    .pet{display:flex;align-items:center;gap:10px;padding:8px 0;
         border-bottom:1px solid rgba(255,255,255,.05)}
    .pet:last-child{border:none}
    .pet-icon{font-size:26px;width:36px;text-align:center}
    .pet-info .pet-name{font-size:14px;font-weight:600}
    .pet-info .pet-sub{font-size:11px;color:var(--muted);margin-top:1px}
    .pet-badge{margin-left:auto;font-size:11px;padding:2px 8px;border-radius:99px;background:rgba(123,92,255,.2);color:var(--accent)}
    /* Top */
    .top-row{display:flex;align-items:center;padding:9px 0;border-bottom:1px solid rgba(255,255,255,.05)}
    .top-row:last-child{border:none}
    .top-pos{font-size:18px;width:32px;text-align:center;flex-shrink:0}
    .top-name{font-size:14px;flex:1;padding:0 8px}
    .top-count{font-size:13px;color:var(--gold);font-weight:600}
    /* Tab buttons */
    .tab-row{display:flex;gap:6px;margin-bottom:12px}
    .tab-btn{flex:1;padding:8px;border-radius:10px;border:none;cursor:pointer;
             background:var(--surface);color:var(--muted);font-size:12px;transition:.2s}
    .tab-btn.active{background:rgba(123,92,255,.25);color:var(--accent)}
    /* Inventory */
    .inv-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px}
    .inv-item{background:var(--surface);border-radius:12px;padding:12px}
    .inv-item .item-name{font-size:13px;font-weight:600;margin-bottom:4px}
    .inv-item .item-qty{font-size:20px;font-weight:700;color:var(--accent)}
    .inv-item .item-desc{font-size:11px;color:var(--muted);margin-top:4px}
    /* Shop */
    .shop-item{display:flex;align-items:center;gap:12px;padding:12px 0;
               border-bottom:1px solid rgba(255,255,255,.05)}
    .shop-item:last-child{border:none}
    .shop-icon{font-size:28px;width:36px;text-align:center;flex-shrink:0}
    .shop-info{flex:1}
    .shop-name{font-size:14px;font-weight:600}
    .shop-price{font-size:12px;color:var(--gold);margin-top:2px}
    .shop-desc{font-size:11px;color:var(--muted);margin-top:2px}
    .btn-buy{padding:8px 14px;border-radius:10px;border:none;cursor:pointer;
             background:linear-gradient(135deg,var(--accent),var(--accent2));
             color:#fff;font-size:13px;font-weight:600;flex-shrink:0}
    .btn-buy:disabled{opacity:.4;cursor:not-allowed}
    /* Loader / error */
    .loader{text-align:center;color:var(--muted);padding:32px;font-size:14px}
    .err{background:rgba(248,113,113,.12);border:1px solid rgba(248,113,113,.3);
         border-radius:12px;padding:14px;color:var(--red);font-size:13px;margin:8px 0}
    /* Balance bar */
    .balance-bar{display:flex;gap:8px;margin-bottom:12px}
    .bal{flex:1;background:var(--card);border-radius:12px;padding:10px;text-align:center}
    .bal .val{font-size:16px;font-weight:700}
    .bal .lbl{font-size:11px;color:var(--muted)}
    /* Toast */
    .toast{position:fixed;top:16px;left:50%;transform:translateX(-50%);
           background:var(--green);color:#000;padding:10px 20px;border-radius:99px;
           font-size:14px;font-weight:600;z-index:9999;opacity:0;transition:.3s;pointer-events:none}
    .toast.show{opacity:1}
  </style>
</head>
<body>
<div id="toast" class="toast"></div>

<!-- Profile -->
<div id="pg-profile" class="page active">
  <div id="profile-content" class="loader">Загрузка...</div>
</div>

<!-- Top -->
<div id="pg-top" class="page">
  <div class="tab-row">
    <button class="tab-btn active" onclick="loadTop('day',this)">Сегодня</button>
    <button class="tab-btn" onclick="loadTop('week',this)">Неделя</button>
    <button class="tab-btn" onclick="loadTop('all_time',this)">Всё время</button>
  </div>
  <div id="top-content" class="loader">Загрузка...</div>
</div>

<!-- Inventory -->
<div id="pg-inventory" class="page">
  <div id="inv-content" class="loader">Загрузка...</div>
</div>

<!-- Shop -->
<div id="pg-shop" class="page">
  <div id="shop-balance" class="balance-bar"></div>
  <div id="shop-content" class="loader">Загрузка...</div>
</div>

<!-- Nav -->
<nav class="nav">
  <div class="nav-btn active" onclick="switchPage('profile',this)">
    <span class="icon">👤</span>Профиль
  </div>
  <div class="nav-btn" onclick="switchPage('top',this)">
    <span class="icon">🏆</span>Топ
  </div>
  <div class="nav-btn" onclick="switchPage('inventory',this)">
    <span class="icon">🎒</span>Инвентарь
  </div>
  <div class="nav-btn" onclick="switchPage('shop',this)">
    <span class="icon">🛒</span>Магазин
  </div>
</nav>

<script>
const tg = window.Telegram?.WebApp;
if (tg) { tg.ready(); tg.expand(); }

// Base URL — works at both / and /predvestnik/
const BASE = (window.location.origin + window.location.pathname).replace(/\/$/, '');
const INIT_DATA = tg?.initData || '';
let _topChatId = 0;  // will be set from profile data

const MEDALS = ['🥇','🥈','🥉'];
const RARITY_COLOR = {common:'#aaa',rare:'#4a9eff',epic:'#c084fc',legendary:'#f5c542'};
const PLACE_LABEL  = {active:'Активный',passive:'Пассивный',stash:'Запас'};

function api(path, opts={}) {
  return fetch(BASE + path, {
    ...opts,
    headers: { 'x-init-data': INIT_DATA, 'content-type':'application/json', ...(opts.headers||{}) }
  }).then(r => r.ok ? r.json() : r.json().then(e => Promise.reject(e.detail || 'Ошибка')));
}

function toast(msg, ok=true) {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.style.background = ok ? 'var(--green)' : 'var(--red)';
  el.style.color = ok ? '#000' : '#fff';
  el.classList.add('show');
  setTimeout(() => el.classList.remove('show'), 2500);
}

function fmt(n) { return Number(n).toLocaleString('ru'); }

// ── Navigation ────────────────────────────────────────────────────────────────
const _loaded = new Set();
function switchPage(name, btn) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
  document.getElementById('pg-' + name).classList.add('active');
  btn.classList.add('active');
  if (!_loaded.has(name)) {
    _loaded.add(name);
    ({ top: () => loadTop('day'), inventory: loadInventory, shop: loadShop }[name] || (() => {}))();
  }
}

// ── Profile ───────────────────────────────────────────────────────────────────
api('/profile/me')
  .then(d => {
    if (d.chats?.length) _topChatId = d.chats[0].chat_tg_id;
    const rarity_icon = {common:'⬜',rare:'🟦',epic:'🟣',legendary:'🟡'};
    const pets_html = d.pets.length
      ? d.pets.map(p => `
        <div class="pet">
          <div class="pet-icon">🐾</div>
          <div class="pet-info">
            <div class="pet-name">${p.name || p.species_id}</div>
            <div class="pet-sub">${p.rarity} · усталость ${p.fatigue}%</div>
          </div>
          <div class="pet-badge">Lv${p.pet_level} ${PLACE_LABEL[p.placement]||p.placement}</div>
        </div>`).join('')
      : '<div style="color:var(--muted);font-size:13px">Питомцев нет — отправьте их в питомник!</div>';

    const chats_html = d.chats.length
      ? d.chats.map(c => `
        <div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid rgba(255,255,255,.05)">
          <span style="font-size:13px">${c.chat_title||'Чат '+c.chat_tg_id}</span>
          <span style="font-size:12px;color:var(--muted)">Lv${c.user_level} · ${fmt(c.user_messages_count_all_time)} сообщ.</span>
        </div>`).join('')
      : '<div style="color:var(--muted);font-size:13px">Нет активных чатов.</div>';

    document.getElementById('profile-content').innerHTML = `
      <div class="profile-head">
        <div class="avatar">🔮</div>
        <div class="profile-info">
          <div class="name">@${d.username || 'Игрок'}</div>
          <div class="rank">${d.rank}</div>
        </div>
      </div>
      <div class="stat-grid" style="margin-bottom:12px">
        <div class="stat"><div class="icon">🪙</div><div class="val">${fmt(d.mora)}</div><div class="lbl">Мора</div></div>
        <div class="stat"><div class="icon">💎</div><div class="val">${d.diamonds.toFixed(1)}</div><div class="lbl">Алмазы</div></div>
        <div class="stat"><div class="icon">🔥</div><div class="val">${d.streak}</div><div class="lbl">Стрик</div></div>
        <div class="stat"><div class="icon">🏆</div><div class="val">${d.achievements}</div><div class="lbl">Достижений</div></div>
      </div>
      <div class="card"><div class="card-title">🐾 Питомники</div>${pets_html}</div>
      <div class="card"><div class="card-title">💬 Активность в чатах</div>${chats_html}</div>`;
  })
  .catch(e => {
    document.getElementById('profile-content').innerHTML =
      `<div class="err">${typeof e==='string'?e:'Не удалось загрузить профиль. Напишите боту чтобы создать аккаунт.'}</div>`;
  });
_loaded.add('profile');

// ── Top ───────────────────────────────────────────────────────────────────────
let _topPeriod = 'day';
function loadTop(period, btn) {
  _topPeriod = period;
  if (btn) {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
  }
  const chatId = _topChatId;
  if (!chatId) {
    document.getElementById('top-content').innerHTML =
      '<div class="err">Откройте профиль сначала — нужен ID чата.</div>';
    return;
  }
  document.getElementById('top-content').innerHTML = '<div class="loader">Загрузка...</div>';
  api(`/top/${chatId}?period=${period}`)
    .then(rows => {
      if (!rows.length) {
        document.getElementById('top-content').innerHTML = '<div class="loader">Данных пока нет.</div>';
        return;
      }
      document.getElementById('top-content').innerHTML =
        '<div class="card">' +
        rows.slice(0,30).map((r,i) => `
          <div class="top-row">
            <div class="top-pos">${MEDALS[i]||String(i+1)+'.'}</div>
            <div class="top-name">${r.username}</div>
            <div class="top-count">${fmt(r.count)} 💬</div>
          </div>`).join('') +
        '</div>';
    })
    .catch(e => {
      document.getElementById('top-content').innerHTML = `<div class="err">${e}</div>`;
    });
}

// ── Inventory ─────────────────────────────────────────────────────────────────
function loadInventory() {
  api('/inventory/')
    .then(items => {
      if (!items.length) {
        document.getElementById('inv-content').innerHTML =
          '<div class="loader">Инвентарь пуст.</div>';
        return;
      }
      document.getElementById('inv-content').innerHTML =
        '<div class="inv-grid">' +
        items.map(it => `
          <div class="inv-item">
            <div class="item-name">${it.name}</div>
            <div class="item-qty">×${it.quantity}</div>
            <div class="item-desc">${it.description||''}</div>
          </div>`).join('') +
        '</div>';
    })
    .catch(e => {
      document.getElementById('inv-content').innerHTML = `<div class="err">${e}</div>`;
    });
}

// ── Shop ──────────────────────────────────────────────────────────────────────
function loadShop() {
  api('/shop/')
    .then(data => {
      document.getElementById('shop-balance').innerHTML = `
        <div class="bal"><div class="val">🪙 ${fmt(data.mora)}</div><div class="lbl">Мора</div></div>
        <div class="bal"><div class="val">💎 ${data.diamonds.toFixed(1)}</div><div class="lbl">Алмазы</div></div>`;

      const items = data.items || [];
      if (!items.length) {
        document.getElementById('shop-content').innerHTML = '<div class="loader">Магазин пуст.</div>';
        return;
      }

      const groups = {};
      items.forEach(it => { (groups[it.category] = groups[it.category]||[]).push(it); });
      const CAT_NAMES = {food:'🥩 Еда и корм',egg:'🥚 Яйца',utility:'🛠 Утилиты',booster:'⚗️ Зелья'};

      let html = '';
      Object.entries(groups).forEach(([cat, list]) => {
        html += `<div class="card"><div class="card-title">${CAT_NAMES[cat]||cat}</div>`;
        list.forEach(it => {
          const price = it.price_mora
            ? `${fmt(it.price_mora)} 🪙`
            : `${it.price_diamonds} 💎`;
          const disc = it.discount_active ? ' <span style="color:var(--green);font-size:10px">скидка🐢</span>' : '';
          html += `
            <div class="shop-item">
              <div class="shop-icon">${it.name.split(' ')[0]}</div>
              <div class="shop-info">
                <div class="shop-name">${it.name}</div>
                <div class="shop-price">${price}${disc}</div>
                <div class="shop-desc">${it.description||''}</div>
              </div>
              <button class="btn-buy" onclick="buyItem('${it.item_id}','${it.name}',this)">Купить</button>
            </div>`;
        });
        html += '</div>';
      });
      document.getElementById('shop-content').innerHTML = html;
    })
    .catch(e => {
      document.getElementById('shop-content').innerHTML = `<div class="err">${e}</div>`;
    });
}

function buyItem(itemId, itemName, btn) {
  btn.disabled = true;
  api('/shop/buy', {
    method: 'POST',
    body: JSON.stringify({item_id: itemId, quantity: 1}),
  })
    .then(r => {
      toast(`✅ Куплено: ${r.item_name}`);
      loadShop();   // refresh balance
    })
    .catch(e => {
      toast(typeof e==='string' ? e : 'Ошибка покупки', false);
    })
    .finally(() => { btn.disabled = false; });
}
</script>
</body>
</html>"""
