import os
from contextlib import asynccontextmanager

import aiosqlite
from fastapi import FastAPI, Depends, HTTPException
from dotenv import load_dotenv

load_dotenv()

DB_PATH = os.getenv("DB_PATH", "db.sqlite3")


# ── DB ────────────────────────────────────────────────────────────────────────

async def _open_db() -> aiosqlite.Connection:
    conn = await aiosqlite.connect(DB_PATH, timeout=20.0)
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA journal_mode=WAL")
    await conn.execute("PRAGMA synchronous=NORMAL")
    await conn.execute("PRAGMA foreign_keys=ON")
    await conn.commit()
    return conn


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.db = await _open_db()
    yield
    await app.state.db.close()


async def get_db() -> aiosqlite.Connection:
    return app.state.db


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(title="Predvestnik API", lifespan=lifespan)


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return {"status": "ok"}


@app.get("/users")
async def get_users(db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute("SELECT user_tg_id, user_tg_username FROM users LIMIT 20") as cur:
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


@app.get("/profile/{user_id}")
async def get_profile(user_id: int, db: aiosqlite.Connection = Depends(get_db)):
    # 1. Базовая инфа + баланс
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

    # 2. Активность и ранги по всем чатам (с названием чата)
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

    # 3. Браки (по всем чатам)
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
            "marriage_date":  m["marriage_date"],
            "family_balance": m["family_balance"],
        })

    # 4. Инвентарь
    async with db.execute(
        "SELECT item_id, quantity FROM inventory WHERE user_id = ? AND quantity > 0",
        (user_id,),
    ) as cur:
        inventory = [dict(r) for r in await cur.fetchall()]

    # 5. Питомцы
    async with db.execute(
        "SELECT id, name, species_id, rarity, placement, fatigue "
        "FROM pets WHERE owner_id = ?",
        (user_id,),
    ) as cur:
        pets = [dict(r) for r in await cur.fetchall()]

    # 6. Стрик (берём максимальный по всем чатам)
    async with db.execute(
        "SELECT streak, last_login FROM daily_login WHERE user_id = ? ORDER BY streak DESC LIMIT 1",
        (user_id,),
    ) as cur:
        streak_row = await cur.fetchone()
    streak = dict(streak_row) if streak_row else {"streak": 0, "last_login": None}

    # 7. Достижения
    async with db.execute(
        "SELECT COUNT(*) FROM achievements WHERE user_id = ? AND progress >= 1",
        (user_id,),
    ) as cur:
        achievements_count = (await cur.fetchone())[0]

    # 8. Global rank name
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
