import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from dotenv import load_dotenv

load_dotenv()

from infrastructure.database import create_pool, get_pool
from infrastructure.pg_adapter import PGAdapter


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_pool(os.getenv("DATABASE_URL", ""))
    yield


app = FastAPI(title="Predvestnik API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Mini App HTML ──────────────────────────────────────────────────────────────

_MINI_APP_HTML = """<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover"/>
  <title>Предвестник V2</title>
  <script src="https://telegram.org/js/telegram-web-app.js"></script>
  <style>
    :root {
      --bg: #0d0d1a;
      --surface: #151528;
      --card: #1e1e38;
      --accent: #7b5cff;
      --accent2: #c084fc;
      --text: #e2e2f0;
      --muted: #8888aa;
      --gold: #f5c542;
      --green: #4ade80;
    }
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      min-height: 100vh;
      padding: 16px;
      padding-bottom: 32px;
    }
    .header {
      text-align: center;
      padding: 24px 0 16px;
    }
    .header h1 {
      font-size: 26px;
      font-weight: 800;
      background: linear-gradient(135deg, var(--accent), var(--accent2));
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      letter-spacing: 0.5px;
    }
    .header p { color: var(--muted); font-size: 13px; margin-top: 4px; }
    .card {
      background: var(--card);
      border-radius: 16px;
      padding: 16px;
      margin-bottom: 12px;
      border: 1px solid rgba(123,92,255,0.15);
    }
    .card h2 { font-size: 14px; color: var(--muted); text-transform: uppercase; letter-spacing: 1px; margin-bottom: 12px; }
    .stat-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
    .stat {
      background: var(--surface);
      border-radius: 12px;
      padding: 12px;
      text-align: center;
    }
    .stat .icon { font-size: 22px; margin-bottom: 4px; }
    .stat .val { font-size: 18px; font-weight: 700; color: var(--text); }
    .stat .lbl { font-size: 11px; color: var(--muted); margin-top: 2px; }
    .row { display: flex; justify-content: space-between; align-items: center; padding: 8px 0; border-bottom: 1px solid rgba(255,255,255,0.05); }
    .row:last-child { border-bottom: none; }
    .row .name { font-size: 14px; color: var(--text); }
    .row .val  { font-size: 14px; font-weight: 700; color: var(--gold); }
    .event-badge {
      display: inline-block;
      padding: 3px 10px;
      border-radius: 99px;
      font-size: 12px;
      font-weight: 600;
    }
    .event-badge.active { background: rgba(74,222,128,0.2); color: var(--green); }
    .event-badge.soon   { background: rgba(245,197,66,0.2);  color: var(--gold); }
    .event-badge.idle   { background: rgba(136,136,170,0.2); color: var(--muted); }
    .profile-box { display: flex; align-items: center; gap: 12px; }
    .avatar {
      width: 54px; height: 54px; border-radius: 50%;
      background: linear-gradient(135deg, var(--accent), var(--accent2));
      display: flex; align-items: center; justify-content: center;
      font-size: 22px;
    }
    .profile-info .uname { font-size: 17px; font-weight: 700; }
    .profile-info .rank  { font-size: 12px; color: var(--muted); margin-top: 2px; }
    .btn {
      display: block; width: 100%; padding: 14px;
      background: linear-gradient(135deg, var(--accent), var(--accent2));
      border: none; border-radius: 14px; color: #fff;
      font-size: 15px; font-weight: 700; cursor: pointer; margin-top: 12px;
      text-align: center; text-decoration: none;
    }
    .loader { text-align: center; color: var(--muted); padding: 24px; font-size: 14px; }
    .error-box { background: rgba(239,68,68,0.15); border: 1px solid rgba(239,68,68,0.3);
                 border-radius: 12px; padding: 14px; color: #f87171; font-size: 13px; }
  </style>
</head>
<body>
<div class="header">
  <h1>🔮 Предвестник V2</h1>
  <p id="tg-name">Telegram-игра с питомцами и экономикой</p>
</div>

<div id="profile-card" class="card" style="display:none">
  <h2>Мой профиль</h2>
  <div id="profile-content" class="loader">Загрузка...</div>
</div>

<div id="events-card" class="card">
  <h2>Активные ивенты</h2>
  <div id="events-content" class="loader">Загрузка...</div>
</div>

<div id="top-card" class="card">
  <h2>Топ игроков (сообщения за всё время)</h2>
  <div id="top-content" class="loader">Загрузка...</div>
</div>

<a class="btn" href="https://t.me/predvestnik_v2_bot" target="_blank">🤖 Открыть бота</a>

<script>
const tg = window.Telegram.WebApp;
tg.ready();
tg.expand();

const BASE = window.location.origin;

// Show user name from Telegram
if (tg.initDataUnsafe?.user) {
  const u = tg.initDataUnsafe.user;
  document.getElementById('tg-name').textContent = `Привет, ${u.first_name}!`;

  document.getElementById('profile-card').style.display = 'block';
  fetch(`${BASE}/profile/${u.id}`)
    .then(r => r.ok ? r.json() : null)
    .then(data => {
      if (!data) { document.getElementById('profile-content').innerHTML = '<i>Профиль не найден — сначала напишите боту</i>'; return; }
      const u2 = data.user;
      const mora = Math.floor(u2.user_balance_mora || 0).toLocaleString('ru');
      const dia  = parseFloat(u2.user_balance_diamonds || 0).toFixed(1);
      document.getElementById('profile-content').innerHTML = `
        <div class="profile-box" style="margin-bottom:14px">
          <div class="avatar">🔮</div>
          <div class="profile-info">
            <div class="uname">@${u2.user_tg_username || u.first_name}</div>
            <div class="rank">${data.global_rank_name}</div>
          </div>
        </div>
        <div class="stat-grid">
          <div class="stat"><div class="icon">🪙</div><div class="val">${mora}</div><div class="lbl">Мора</div></div>
          <div class="stat"><div class="icon">💎</div><div class="val">${dia}</div><div class="lbl">Алмазы</div></div>
          <div class="stat"><div class="icon">🔥</div><div class="val">${data.streak}</div><div class="lbl">Стрик</div></div>
          <div class="stat"><div class="icon">🏆</div><div class="val">${data.achievements_count}</div><div class="lbl">Достижений</div></div>
        </div>`;
    })
    .catch(() => { document.getElementById('profile-content').innerHTML = '<i>Ошибка загрузки</i>'; });
}

// Events
fetch(`${BASE}/api/events`)
  .then(r => r.json())
  .then(ev => {
    let html = '';
    if (ev.exchange?.active) {
      html += `<div class="row"><span class="name">💱 Обмен Моры→Алмазы</span><span class="event-badge active">ИДЁТ</span></div>`;
      html += `<div class="row"><span class="name" style="color:var(--muted);font-size:12px">Заканчивается: ${ev.exchange.ends_at||'—'}</span></div>`;
    } else if (ev.exchange?.scheduled) {
      html += `<div class="row"><span class="name">💱 Обмен Моры→Алмазы</span><span class="event-badge soon">СКОРО</span></div>`;
      html += `<div class="row"><span class="name" style="color:var(--muted);font-size:12px">Начало: ${ev.exchange.starts_at||'—'}</span></div>`;
    } else {
      html += `<div class="row"><span class="name">💱 Обмен Моры→Алмазы</span><span class="event-badge idle">нет данных</span></div>`;
    }
    html += `<div class="row"><span class="name">📦 Сундуки</span><span class="event-badge active">Случайные</span></div>`;
    html += `<div class="row"><span class="name">🌑 Культ Бездны</span><span class="event-badge idle">23:00–01:00 UTC</span></div>`;
    document.getElementById('events-content').innerHTML = html || '<i>Нет активных ивентов</i>';
  })
  .catch(() => { document.getElementById('events-content').innerHTML = '<i>Ошибка загрузки</i>'; });

// Top players (global all-time)
fetch(`${BASE}/api/top/global`)
  .then(r => r.json())
  .then(rows => {
    if (!rows.length) { document.getElementById('top-content').innerHTML = '<i>Данных пока нет</i>'; return; }
    const medals = ['🥇','🥈','🥉'];
    let html = rows.slice(0,10).map((r,i) => {
      const name = r.user_tg_username || `ID${r.user_tg_id}`;
      const medal = medals[i] || `${i+1}.`;
      return `<div class="row"><span class="name">${medal} ${name}</span><span class="val">${(r.value||0).toLocaleString('ru')} 💬</span></div>`;
    }).join('');
    document.getElementById('top-content').innerHTML = html;
  })
  .catch(() => { document.getElementById('top-content').innerHTML = '<i>Ошибка загрузки</i>'; });
</script>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse)
async def mini_app_root():
    return HTMLResponse(content=_MINI_APP_HTML)


# ── REST API ───────────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.get("/api/events")
async def api_events():
    """Returns current exchange event status and next schedule."""
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

    result: dict = {"exchange": {}}
    if active:
        a = dict(active)
        result["exchange"] = {
            "active": True,
            "ends_at": str(a.get("ends_at", ""))[:16],
            "event_id": a.get("id"),
        }
    elif scheduled:
        s = dict(scheduled)
        result["exchange"] = {
            "active": False,
            "scheduled": True,
            "starts_at": str(s.get("starts_at", ""))[:16],
            "ends_at": str(s.get("ends_at", ""))[:16],
        }
    else:
        result["exchange"] = {"active": False, "scheduled": False}

    return result


@app.get("/api/top/global")
async def api_top_global(limit: int = 10):
    """Global all-time top by messages."""
    limit = min(limit, 50)
    async with get_pool().acquire() as conn:
        db = PGAdapter(conn)
        async with db.execute(
            "SELECT s.user_tg_id, u.user_tg_username, "
            "SUM(s.user_messages_count_all_time) AS value "
            "FROM user_chat_stats s "
            "LEFT JOIN users u ON s.user_tg_id = u.user_tg_id "
            "GROUP BY s.user_tg_id, u.user_tg_username "
            "HAVING SUM(s.user_messages_count_all_time) > 0 "
            "ORDER BY value DESC LIMIT ?",
            (limit,),
        ) as c:
            rows = [dict(r) for r in await c.fetchall()]
    return rows


@app.get("/api/top/{chat_id}")
async def api_top_chat(chat_id: int, period: str = "all_time", limit: int = 10):
    """Local chat top. period: all_time | day | week."""
    limit = min(limit, 50)
    async with get_pool().acquire() as conn:
        db = PGAdapter(conn)

        if period == "all_time":
            async with db.execute(
                "SELECT s.user_tg_id, u.user_tg_username, "
                "s.user_messages_count_all_time AS value "
                "FROM user_chat_stats s "
                "LEFT JOIN users u ON s.user_tg_id = u.user_tg_id "
                "WHERE s.chat_tg_id = ? AND s.is_left = FALSE "
                "AND s.user_messages_count_all_time > 0 "
                "ORDER BY value DESC LIMIT ?",
                (chat_id, limit),
            ) as c:
                rows = [dict(r) for r in await c.fetchall()]
        else:
            now = datetime.now(timezone.utc)
            today = now.strftime("%Y-%m-%d")
            if period == "day":
                date_start = today
            elif period == "week":
                date_start = (now - timedelta(days=6)).strftime("%Y-%m-%d")
            else:
                date_start = today

            async with db.execute(
                "SELECT d.user_id AS user_tg_id, u.user_tg_username, "
                "SUM(d.message_count) AS value "
                "FROM daily_user_stats d "
                "LEFT JOIN users u ON d.user_id = u.user_tg_id "
                "WHERE d.chat_id = ? AND d.date >= ? AND d.date <= ? "
                "GROUP BY d.user_id, u.user_tg_username "
                "HAVING SUM(d.message_count) > 0 "
                "ORDER BY value DESC LIMIT ?",
                (chat_id, date_start, today, limit),
            ) as c:
                rows = [dict(r) for r in await c.fetchall()]

    return rows


@app.get("/api/users")
async def get_users():
    async with get_pool().acquire() as conn:
        db = PGAdapter(conn)
        async with db.execute(
            "SELECT user_tg_id, user_tg_username FROM users LIMIT 20"
        ) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]


@app.get("/profile/{user_id}")
async def get_profile(user_id: int):
    async with get_pool().acquire() as conn:
        db = PGAdapter(conn)

        async with db.execute(
            "SELECT user_tg_id, user_tg_username, global_rank, "
            "user_balance_mora, user_balance_diamonds "
            "FROM users WHERE user_tg_id = ?",
            (user_id,),
        ) as cur:
            user_row = await cur.fetchone()

        if user_row is None:
            raise HTTPException(status_code=404, detail="Пользователь не найден")

        user = dict(user_row)

        async with db.execute(
            "SELECT ucs.chat_tg_id, ucs.local_rank, ucs.user_level, ucs.user_xp, "
            "ucs.user_messages_count_per_day, ucs.user_messages_count_per_week, "
            "ucs.user_messages_count_all_time, ucs.warnings, ucs.is_immune, ucs.immune_until, "
            "ucs.joined_at, ucs.is_left, cs.chat_title "
            "FROM user_chat_stats ucs "
            "LEFT JOIN chat_settings cs ON cs.chat_id = ucs.chat_tg_id "
            "WHERE ucs.user_tg_id = ? AND ucs.is_left = FALSE",
            (user_id,),
        ) as cur:
            chats = [dict(r) for r in await cur.fetchall()]

        async with db.execute(
            "SELECT chat_id, user1_id, user1_name, user2_id, user2_name, "
            "marriage_date, family_balance "
            "FROM marriages WHERE user1_id = ? OR user2_id = ?",
            (user_id, user_id),
        ) as cur:
            marriages_raw = [dict(r) for r in await cur.fetchall()]

        marriages = []
        for m in marriages_raw:
            partner_id   = m["user2_id"]   if m["user1_id"] == user_id else m["user1_id"]
            partner_name = m["user2_name"] if m["user1_id"] == user_id else m["user1_name"]
            marriages.append({
                "chat_id":        m["chat_id"],
                "partner_id":     partner_id,
                "partner_name":   partner_name,
                "marriage_date":  str(m["marriage_date"]) if m["marriage_date"] else None,
                "family_balance": m["family_balance"],
            })

        async with db.execute(
            "SELECT item_id, quantity FROM inventory WHERE user_id = ? AND quantity > 0",
            (user_id,),
        ) as cur:
            inventory = [dict(r) for r in await cur.fetchall()]

        async with db.execute(
            "SELECT id, name, species_id, rarity, placement, fatigue "
            "FROM pets WHERE owner_id = ?",
            (user_id,),
        ) as cur:
            pets = [dict(r) for r in await cur.fetchall()]

        async with db.execute(
            "SELECT streak, last_login FROM daily_login "
            "WHERE user_id = ? ORDER BY streak DESC LIMIT 1",
            (user_id,),
        ) as cur:
            streak_row = await cur.fetchone()
        streak = dict(streak_row) if streak_row else {"streak": 0, "last_login": None}

        async with db.execute(
            "SELECT COUNT(*) FROM achievements WHERE user_id = ? AND progress >= 1",
            (user_id,),
        ) as cur:
            achievements_count = (await cur.fetchone())[0]

    _GLOBAL_RANK_NAMES = {
        0: "👤 Пользователь",
        1: "⭐ Почётный участник",
        2: "🛡 Модератор",
        3: "🌌 Главный разработчик",
    }
    global_rank_id = user.get("global_rank", 0)
    global_rank_name = _GLOBAL_RANK_NAMES.get(global_rank_id, f"Ранг {global_rank_id}")

    return {
        "user":               user,
        "chats":              chats,
        "marriages":          marriages,
        "inventory":          inventory,
        "pets":               pets,
        "streak":             streak["streak"],
        "achievements_count": achievements_count,
        "global_rank_name":   global_rank_name,
        "balance_diamonds":   float(user.get("user_balance_diamonds", 0)),
    }
