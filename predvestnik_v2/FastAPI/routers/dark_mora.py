"""FastAPI/routers/dark_mora.py — контрабанда и ритуал Тёмной Моры."""
import random
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.constants import (
    DARK_MORA_CONTRABANDA_MIN_STAKE, DARK_MORA_CONTRABANDA_MAX_STAKE,
    DARK_MORA_CONTRABANDA_SUCCESS_CHANCE, DARK_MORA_CONTRABANDA_FAIL_CHANCE,
    DARK_MORA_CONTRABANDA_MORA_PER_DARK, DARK_MORA_CONTRABANDA_COOLDOWN_DAYS,
    DARK_MORA_CONTRABANDA_CATCH_PENALTY_DAYS,
    DARK_MORA_CULT_STREAK_MIN, DARK_MORA_CULT_LEVEL_MIN, DARK_MORA_CULT_PETS_MIN,
    DARK_MORA_CULT_COOLDOWN_DAYS, DARK_MORA_CULT_REWARD_MIN, DARK_MORA_CULT_REWARD_MAX,
    DARK_MORA_CULT_HOUR_START, DARK_MORA_CULT_HOUR_END,
)
from FastAPI.deps import get_db, require_tg_user
from infrastructure.repositories import economy as eco_repo

router = APIRouter(prefix="/dark-mora", tags=["dark-mora"])


class ContrabandaRequest(BaseModel):
    stake: float


@router.post("/contrabanda")
async def contrabanda(body: ContrabandaRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    stake = body.stake
    if not (DARK_MORA_CONTRABANDA_MIN_STAKE <= stake <= DARK_MORA_CONTRABANDA_MAX_STAKE):
        raise HTTPException(400, f"Ставка: {int(DARK_MORA_CONTRABANDA_MIN_STAKE)}–{int(DARK_MORA_CONTRABANDA_MAX_STAKE)} 🪙.")

    # Check cooldown
    now = datetime.now(timezone.utc)
    async with db.execute(
        "SELECT contrabanda_banned_until, contrabanda_last_at FROM users WHERE user_tg_id = ?",
        (user["id"],),
    ) as c:
        row = await c.fetchone()

    if row:
        if row["contrabanda_banned_until"] and str(row["contrabanda_banned_until"]) > str(now)[:19]:
            raise HTTPException(400, "Вы пойманы! Подождите окончания штрафа.")
        if row["contrabanda_last_at"]:
            cd_end = datetime.fromisoformat(str(row["contrabanda_last_at"])) + timedelta(days=DARK_MORA_CONTRABANDA_COOLDOWN_DAYS)
            if cd_end.replace(tzinfo=timezone.utc) > now:
                days_left = (cd_end.replace(tzinfo=timezone.utc) - now).days + 1
                raise HTTPException(400, f"Кулдаун: ещё {days_left} д.")

    bal = await eco_repo.get_balance(db, user["id"])
    if bal["user_balance_mora"] < stake:
        raise HTTPException(400, "Недостаточно Моры.")

    r = random.random()
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")

    if r < DARK_MORA_CONTRABANDA_SUCCESS_CHANCE:
        dark_earned = int(stake / DARK_MORA_CONTRABANDA_MORA_PER_DARK)
        await eco_repo.add_balance(db, user["id"], mora=-stake, commit=False, source="contrabanda")
        await db.execute("UPDATE users SET dark_mora = COALESCE(dark_mora,0) + ?, contrabanda_last_at = ? WHERE user_tg_id = ?",
                         (dark_earned, now_str, user["id"]))
        await db.commit()
        return {"success": True, "result_text": f"✅ Успех! +{dark_earned} 🌑 Тёмной Моры"}

    elif r < DARK_MORA_CONTRABANDA_SUCCESS_CHANCE + DARK_MORA_CONTRABANDA_FAIL_CHANCE:
        lost = stake / 2
        await eco_repo.add_balance(db, user["id"], mora=-lost, commit=False, source="contrabanda_fail")
        await db.execute("UPDATE users SET contrabanda_last_at = ? WHERE user_tg_id = ?", (now_str, user["id"]))
        await db.commit()
        return {"success": False, "result_text": f"❌ Провал. Потеряно {int(lost)} 🪙"}

    else:
        ban_until = (now + timedelta(days=DARK_MORA_CONTRABANDA_CATCH_PENALTY_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
        await eco_repo.add_balance(db, user["id"], mora=-stake, commit=False, source="contrabanda_caught")
        await db.execute("UPDATE users SET contrabanda_banned_until = ?, contrabanda_last_at = ? WHERE user_tg_id = ?",
                         (ban_until, now_str, user["id"]))
        await db.commit()
        return {"success": False, "result_text": f"🚔 Поймали! Штраф {DARK_MORA_CONTRABANDA_CATCH_PENALTY_DAYS} дней. Потеряно {int(stake)} 🪙"}


@router.post("/ritual")
async def ritual(db=Depends(get_db), user=Depends(require_tg_user)):
    now = datetime.now(timezone.utc)
    hour = now.hour
    valid_hours = list(range(DARK_MORA_CULT_HOUR_START, 24)) + list(range(0, DARK_MORA_CULT_HOUR_END + 1))
    if hour not in valid_hours:
        raise HTTPException(400, f"Ритуал доступен только с {DARK_MORA_CULT_HOUR_START}:00 до {DARK_MORA_CULT_HOUR_END}:00 UTC.")

    async with db.execute("SELECT user_level FROM user_chat_stats WHERE user_tg_id = ? ORDER BY user_level DESC LIMIT 1", (user["id"],)) as c:
        lvl_row = await c.fetchone()
    if not lvl_row or lvl_row[0] < DARK_MORA_CULT_LEVEL_MIN:
        raise HTTPException(400, f"Нужен уровень {DARK_MORA_CULT_LEVEL_MIN}+.")

    async with db.execute("SELECT MAX(streak) FROM daily_login WHERE user_id = ?", (user["id"],)) as c:
        s = await c.fetchone()
    if not s or (s[0] or 0) < DARK_MORA_CULT_STREAK_MIN:
        raise HTTPException(400, f"Нужен стрик {DARK_MORA_CULT_STREAK_MIN}+.")

    async with db.execute("SELECT COUNT(*) FROM pets WHERE owner_id = ? AND placement IN ('active','passive')", (user["id"],)) as c:
        pets = (await c.fetchone())[0]
    if pets < DARK_MORA_CULT_PETS_MIN:
        raise HTTPException(400, f"Нужно {DARK_MORA_CULT_PETS_MIN}+ питомца в питомнике.")

    async with db.execute("SELECT ritual_last_at FROM users WHERE user_tg_id = ?", (user["id"],)) as c:
        r = await c.fetchone()
    if r and r[0]:
        cd = datetime.fromisoformat(str(r[0])) + timedelta(days=DARK_MORA_CULT_COOLDOWN_DAYS)
        if cd.replace(tzinfo=timezone.utc) > now:
            raise HTTPException(400, f"Кулдаун: {(cd.replace(tzinfo=timezone.utc)-now).days}д. осталось.")

    reward = random.randint(DARK_MORA_CULT_REWARD_MIN, DARK_MORA_CULT_REWARD_MAX)
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")
    await db.execute("UPDATE users SET dark_mora = COALESCE(dark_mora,0) + ?, ritual_last_at = ? WHERE user_tg_id = ?",
                     (reward, now_str, user["id"]))
    await db.commit()
    return {"ok": True, "message": f"🌑 Ритуал совершён! +{reward} Тёмной Моры"}
