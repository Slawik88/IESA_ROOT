"""FastAPI/routers/dark_mora.py — контрабанда, ритуал и Теневой Торговец."""
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
    DARK_MORA_SHADOW_MERCHANT_COOLDOWN_DAYS, DARK_MORA_SHADOW_MERCHANT_REWARD_MIN,
    DARK_MORA_SHADOW_MERCHANT_REWARD_MAX, DARK_MORA_SHADOW_MERCHANT_WINNERS,
)
from FastAPI.deps import get_db, require_tg_user, require_module
from infrastructure.repositories import economy as eco_repo
from infrastructure.repositories.dark_mora import (
    get_cooldown, set_cooldown, add_dark_mora, get_dark_mora_balance,
)

router = APIRouter(prefix="/dark-mora", tags=["dark-mora"], dependencies=[Depends(require_module("module_warps"))])


def _format_cooldown(dt: datetime) -> str:
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    diff = dt - now
    if diff.total_seconds() <= 0:
        return "уже доступно"
    days = diff.days
    hours, rem = divmod(diff.seconds, 3600)
    mins = rem // 60
    if days > 0:
        return f"{days}д {hours}ч"
    if hours > 0:
        return f"{hours}ч {mins}м"
    return f"{mins}м"


class ContrabandaRequest(BaseModel):
    stake: float


@router.post("/contrabanda")
async def contrabanda(body: ContrabandaRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    stake = round(body.stake)
    if not (DARK_MORA_CONTRABANDA_MIN_STAKE <= stake <= DARK_MORA_CONTRABANDA_MAX_STAKE):
        raise HTTPException(400, f"Ставка: {int(DARK_MORA_CONTRABANDA_MIN_STAKE)}–{int(DARK_MORA_CONTRABANDA_MAX_STAKE)} 🪙.")

    # Check cooldown — shared with the bot via dark_mora_cooldowns
    now = datetime.now(timezone.utc)
    cd = await get_cooldown(db, user["id"], "contrabanda")
    if cd:
        if cd.tzinfo is None:
            cd = cd.replace(tzinfo=timezone.utc)
        if cd > now:
            raise HTTPException(400, f"⏳ Следующая попытка через: {_format_cooldown(cd)}")

    # Deduct full stake upfront (atomic, prevents negative balance)
    ok, err = await eco_repo.spend_mora(db, user["id"], stake, source="contrabanda_stake", note="контрабанда")
    if not ok:
        raise HTTPException(400, err)

    r = random.random()

    if r < DARK_MORA_CONTRABANDA_SUCCESS_CHANCE:
        dark_earned = max(1, int(stake / DARK_MORA_CONTRABANDA_MORA_PER_DARK))
        cooldown_until = now + timedelta(days=DARK_MORA_CONTRABANDA_COOLDOWN_DAYS)
        await set_cooldown(db, user["id"], "contrabanda", cooldown_until)
        await add_dark_mora(db, user["id"], dark_earned, source="contrabanda", note=f"ставка {stake:.0f}")
        return {"success": True, "result_text": f"✅ Успех! +{dark_earned} 🌑 Тёмной Моры"}

    elif r < DARK_MORA_CONTRABANDA_SUCCESS_CHANCE + DARK_MORA_CONTRABANDA_FAIL_CHANCE:
        cooldown_until = now + timedelta(days=DARK_MORA_CONTRABANDA_COOLDOWN_DAYS)
        await set_cooldown(db, user["id"], "contrabanda", cooldown_until)
        refund = round(stake * 0.5)
        await eco_repo.add_balance(db, user["id"], mora=refund, source="contrabanda_refund", note="провал, возврат 50%")
        return {"success": False, "result_text": f"❌ Провал. Потеряно {int(stake - refund)} 🪙"}

    else:
        cooldown_until = now + timedelta(days=DARK_MORA_CONTRABANDA_CATCH_PENALTY_DAYS)
        await set_cooldown(db, user["id"], "contrabanda", cooldown_until)
        return {"success": False, "result_text": f"🚔 Поймали! Штраф {DARK_MORA_CONTRABANDA_CATCH_PENALTY_DAYS} дней. Потеряно {int(stake)} 🪙"}


@router.post("/ritual")
async def ritual(db=Depends(get_db), user=Depends(require_tg_user)):
    now = datetime.now(timezone.utc)
    hour = now.hour
    valid_hours = list(range(DARK_MORA_CULT_HOUR_START, 24)) + list(range(0, DARK_MORA_CULT_HOUR_END + 1))
    if hour not in valid_hours:
        raise HTTPException(400, f"Ритуал доступен только с {DARK_MORA_CULT_HOUR_START}:00 до {DARK_MORA_CULT_HOUR_END}:00 UTC.")

    # Cooldown — shared with the bot via dark_mora_cooldowns
    cd = await get_cooldown(db, user["id"], "ritual")
    if cd:
        if cd.tzinfo is None:
            cd = cd.replace(tzinfo=timezone.utc)
        if cd > now:
            raise HTTPException(400, f"Ритуал уже проводился. Следующий через: {_format_cooldown(cd)}")

    async with db.execute("SELECT MAX(streak) FROM daily_login WHERE user_id = ?", (user["id"],)) as c:
        s = await c.fetchone()
    if not s or (s[0] or 0) < DARK_MORA_CULT_STREAK_MIN:
        raise HTTPException(400, f"Нужен стрик {DARK_MORA_CULT_STREAK_MIN}+.")

    async with db.execute("SELECT MAX(user_level) FROM user_chat_stats WHERE user_tg_id = ?", (user["id"],)) as c:
        lvl_row = await c.fetchone()
    max_level = int(lvl_row[0]) if lvl_row and lvl_row[0] else 1
    if max_level < DARK_MORA_CULT_LEVEL_MIN:
        raise HTTPException(400, f"Нужен уровень {DARK_MORA_CULT_LEVEL_MIN}+.")

    async with db.execute("SELECT COUNT(*) FROM pets WHERE owner_id = ?", (user["id"],)) as c:
        pets = (await c.fetchone())[0]
    if pets < DARK_MORA_CULT_PETS_MIN:
        raise HTTPException(400, f"Нужно {DARK_MORA_CULT_PETS_MIN}+ питомца в питомнике.")

    reward = random.randint(DARK_MORA_CULT_REWARD_MIN, DARK_MORA_CULT_REWARD_MAX)
    cooldown_until = now + timedelta(days=DARK_MORA_CULT_COOLDOWN_DAYS)
    await set_cooldown(db, user["id"], "ritual", cooldown_until)
    await add_dark_mora(db, user["id"], reward, source="cult_ritual", note="Культ Бездны")

    new_balance = await get_dark_mora_balance(db, user["id"])
    return {"ok": True, "message": f"🌑 Ритуал совершён! +{reward} Тёмной Моры", "balance": new_balance}


@router.get("/merchant-status")
async def merchant_status(db=Depends(get_db), user=Depends(require_tg_user)):
    """Статус Теневого Торговца: когда последний/следующий ивент."""
    # Check last merchant event from DB (stored in a global event log)
    now = datetime.now(timezone.utc)
    last_event = None
    next_event = None
    active = False

    try:
        async with db.execute(
            "SELECT posted_at, expires_at FROM shadow_merchant_events "
            "ORDER BY posted_at DESC LIMIT 1"
        ) as c:
            row = await c.fetchone()
        if row and row[0]:
            posted = row[0]
            expires = row[1]
            if isinstance(posted, str):
                posted = datetime.fromisoformat(posted.replace(" ", "T"))
            if posted.tzinfo is None:
                posted = posted.replace(tzinfo=timezone.utc)
            if expires is not None:
                if isinstance(expires, str):
                    expires = datetime.fromisoformat(expires.replace(" ", "T"))
                if expires.tzinfo is None:
                    expires = expires.replace(tzinfo=timezone.utc)
                active = expires > now
            else:
                active = (now - posted).total_seconds() < 7200
            last_event = posted
            next_event = posted + timedelta(days=DARK_MORA_SHADOW_MERCHANT_COOLDOWN_DAYS)
    except Exception:
        pass

    # If no event data, show info about the mechanic
    return {
        "active":       active,
        "last_event":   last_event.isoformat() if last_event else None,
        "next_expected": next_event.isoformat() if next_event else None,
        "cooldown_days": DARK_MORA_SHADOW_MERCHANT_COOLDOWN_DAYS,
        "winners":       DARK_MORA_SHADOW_MERCHANT_WINNERS,
        "reward_min":    DARK_MORA_SHADOW_MERCHANT_REWARD_MIN,
        "reward_max":    DARK_MORA_SHADOW_MERCHANT_REWARD_MAX,
        "how_it_works": (
            f"Каждые {DARK_MORA_SHADOW_MERCHANT_COOLDOWN_DAYS} дня бот публикует зашифрованное "
            f"пророчество в чате. Первые {DARK_MORA_SHADOW_MERCHANT_WINNERS} игрока, "
            f"угадавшие ключевое слово, получают {DARK_MORA_SHADOW_MERCHANT_REWARD_MIN}–"
            f"{DARK_MORA_SHADOW_MERCHANT_REWARD_MAX} 🌑 Тёмной Моры."
        ),
    }
