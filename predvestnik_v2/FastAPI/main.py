import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from dotenv import load_dotenv

load_dotenv()

from infrastructure.database import create_pool, get_pool
from infrastructure.pg_adapter import PGAdapter


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_pool(os.getenv("DATABASE_URL", ""))
    yield


app = FastAPI(title="Predvestnik API", lifespan=lifespan)


@app.get("/")
async def root():
    return {"status": "ok"}


@app.get("/users")
async def get_users():
    async with get_pool().acquire() as conn:
        db = PGAdapter(conn)
        async with db.execute("SELECT user_tg_id, user_tg_username FROM users LIMIT 20") as cur:
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
            "SELECT streak, last_login FROM daily_login WHERE user_id = ? ORDER BY streak DESC LIMIT 1",
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
