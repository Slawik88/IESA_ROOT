"""
api/expeditions.py — unified expedition operations.

All functions are async; the mini app wraps them with async_to_sync.
"""
import random
from datetime import datetime, timedelta, timezone


async def start_expedition(uid: int, chat_id: int, option_key: str,
                           wallet_type: str = "personal") -> dict:
    """
    Start a pet expedition.

    1. Validates pet exists and has fatigue < 100
    2. Validates pet is not currently walking
    3. Validates no active expedition
    4. Deducts cost from wallet
    5. Creates expedition record
    6. Adds +20 fatigue to pet
    7. Ticks quest

    wallet_type: "personal" | "family"
    Raises ValueError on error.
    Returns {ok, option, duration_h, reward_min, reward_max, cost, quest_done, quest_xp, quest_mora}
    """
    from database.db import (
        add_mora, add_pet_fatigue, add_to_family_wallet, deduct_mora,
        get_active_expedition, get_family_wallet, get_mora, get_pet,
        is_user_single, start_expedition as _db_start_expedition,
    )

    try:
        from config import EXPEDITION_OPTIONS
    except Exception:
        EXPEDITION_OPTIONS = {
            "short":  {"hours": 2, "cost": 0,  "reward_min": 10, "reward_max": 15,  "label": "2ч (бесплатно)"},
            "medium": {"hours": 4, "cost": 5,  "reward_min": 30, "reward_max": 35,  "label": "4ч (5 🪙)"},
            "long":   {"hours": 8, "cost": 10, "reward_min": 45, "reward_max": 50,  "label": "8ч (10 🪙)"},
        }

    opt = EXPEDITION_OPTIONS.get(option_key)
    if not opt:
        raise ValueError("Неизвестный тип экспедиции")

    # Pet checks
    pet = await get_pet(uid, chat_id)
    if not pet:
        raise ValueError("У тебя нет питомца")

    fatigue = pet.get("fatigue") or 0
    if fatigue >= 100:
        raise ValueError("Питомец слишком устал (100/100). Покорми его!")

    walk_end = pet.get("walk_end_at")
    if walk_end:
        try:
            if not hasattr(walk_end, "tzinfo"):
                walk_end = datetime.fromisoformat(str(walk_end).replace("Z", "+00:00"))
            if walk_end.tzinfo is None:
                walk_end = walk_end.replace(tzinfo=timezone.utc)
            if walk_end > datetime.now(timezone.utc):
                mins = int((walk_end - datetime.now(timezone.utc)).total_seconds() / 60) + 1
                raise ValueError(f"Питомец ещё на прогулке! Осталось {mins} мин.")
        except ValueError:
            raise
        except Exception:
            pass

    active = await get_active_expedition(uid, chat_id)
    if active:
        raise ValueError("Питомец уже в экспедиции")

    # Cost handling
    cost = opt["cost"]
    if cost > 0:
        if wallet_type == "family":
            single = await is_user_single(uid, chat_id)
            if single:
                raise ValueError("Нет семейного кошелька")
            fam_bal = await get_family_wallet(chat_id, uid)
            if fam_bal < cost:
                raise ValueError(f"Недостаточно Моры в семейном кошельке ({fam_bal}/{cost} 🪙)")
            # Deduct from family wallet using add_to_family_wallet with negative value
            from database.postgres import connect as postgres_connect
            async with postgres_connect() as db:
                await db.execute(
                    "UPDATE family_wallet SET balance=balance-? WHERE chat_id=? AND user_id=? AND balance>=?",
                    (cost, chat_id, uid, cost),
                )
                await db.commit()
        else:
            ok, _ = await deduct_mora(uid, chat_id, cost)
            if not ok:
                mora_row = await get_mora(uid, chat_id)
                bal = mora_row["balance"] if mora_row else 0
                raise ValueError(f"Недостаточно Моры ({bal}/{cost} 🪙)")

    # Start expedition
    ok = await _db_start_expedition(uid, chat_id, opt["hours"], opt["reward_min"], opt["reward_max"])
    if not ok:
        # Refund on failure
        if cost > 0:
            if wallet_type == "family":
                await add_to_family_wallet(chat_id, uid, cost)
            else:
                await add_mora(uid, chat_id, cost)
        raise ValueError("Не удалось начать экспедицию")

    await add_pet_fatigue(uid, chat_id, 20)

    # Quest tick
    quest_done = quest_xp = quest_mora = 0
    try:
        from utils.helpers import bot_today
        from database.db import (
            add_xp_in_chat, get_user_quest, mark_quest_rewarded, quest_tick,
        )
        today = bot_today()
        quest = await get_user_quest(uid, chat_id, today)
        if quest.get("type") == "expedition":
            _new_p, _goal, just_done = await quest_tick(uid, chat_id, today, quest["type"], quest["goal"])
            if just_done:
                quest_mora = quest.get("mora", 5)
                quest_xp   = quest.get("xp", 10)
                await add_xp_in_chat(uid, chat_id, quest_xp)
                await add_mora(uid, chat_id, quest_mora)
                await mark_quest_rewarded(uid, chat_id, today)
                quest_done = 1
    except Exception:
        pass

    return {
        "ok":          True,
        "option":      option_key,
        "duration_h":  opt["hours"],
        "reward_min":  opt["reward_min"],
        "reward_max":  opt["reward_max"],
        "cost":        cost,
        "quest_done":  bool(quest_done),
        "quest_xp":    int(quest_xp),
        "quest_mora":  int(quest_mora),
    }


async def claim_expedition(uid: int, chat_id: int) -> dict:
    """
    Collect a completed expedition reward.

    Tax by duration: short (≤2h) = 0%, medium (≤4h) = 6.5%, long = 7%.
    Raises ValueError on error.
    Returns {ok, reward_gross, reward, tax, new_balance}
    """
    from database.db import add_mora, add_to_treasury, finish_expedition, get_active_expedition

    active = await get_active_expedition(uid, chat_id)
    if not active:
        raise ValueError("Нет активной экспедиции")

    started_at = active["started_at"]
    duration_h = active["duration_h"]
    reward_min = active["reward_min"]
    reward_max = active["reward_max"]

    if isinstance(started_at, str):
        started_at = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)

    now    = datetime.now(timezone.utc)
    end_at = started_at + timedelta(hours=duration_h)
    if now < end_at:
        secs_left = int((end_at - now).total_seconds())
        h_left = secs_left // 3600
        m_left = (secs_left % 3600) // 60
        raise ValueError(f"Экспедиция ещё не завершена. Осталось: {h_left}ч {m_left}мин")

    reward_gross = random.randint(reward_min, reward_max)

    # Tax by duration
    if duration_h <= 2:
        exped_tax = 0
    elif duration_h <= 4:
        exped_tax = max(0, int(reward_gross * 0.065))
    else:
        exped_tax = max(0, int(reward_gross * 0.07))
    net_reward = reward_gross - exped_tax

    await finish_expedition(uid, chat_id)
    new_balance = await add_mora(uid, chat_id, net_reward)
    if exped_tax > 0:
        await add_to_treasury(chat_id, exped_tax, "expedition", uid)

    return {
        "ok":           True,
        "reward_gross": reward_gross,
        "reward":       net_reward,
        "tax":          exped_tax,
        "new_balance":  new_balance,
    }


async def get_expedition_status(uid: int, chat_id: int) -> dict:
    """Full expedition page payload: pet, active expedition, balance, options.

    Returns the same shape the miniapp_expeditions GET view expects.
    """
    from database.db import get_active_expedition, get_mora, get_pet

    try:
        from config import EXPEDITION_OPTIONS
    except Exception:
        EXPEDITION_OPTIONS = {
            "short":  {"hours": 2, "cost": 0,  "reward_min": 10, "reward_max": 15,  "label": "2ч (бесплатно)"},
            "medium": {"hours": 4, "cost": 5,  "reward_min": 30, "reward_max": 35,  "label": "4ч (5 🪙)"},
            "long":   {"hours": 8, "cost": 10, "reward_min": 45, "reward_max": 50,  "label": "8ч (10 🪙)"},
        }

    pet_row = await get_pet(uid, chat_id)
    pet = None
    if pet_row:
        pet = {
            "type": pet_row.get("pet_type"),
            "name": pet_row.get("name") or "безымянный",
            "fatigue": pet_row.get("fatigue") or 0,
        }
        walk_end = pet_row.get("walk_end_at")
        if walk_end:
            try:
                if not hasattr(walk_end, "tzinfo"):
                    walk_end = datetime.fromisoformat(str(walk_end).replace("Z", "+00:00"))
                if walk_end.tzinfo is None:
                    walk_end = walk_end.replace(tzinfo=timezone.utc)
                if walk_end > datetime.now(timezone.utc):
                    secs = (walk_end - datetime.now(timezone.utc)).total_seconds()
                    pet["walking"] = True
                    pet["walk_mins_left"] = int(secs / 60) + 1
            except Exception:
                pass

    active = await get_active_expedition(uid, chat_id)
    expedition = None
    if active:
        started_at = active["started_at"]
        duration_h = active["duration_h"]
        if isinstance(started_at, str):
            started_at = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        end_at = started_at + timedelta(hours=duration_h)
        done = now >= end_at
        secs_left = max(0, (end_at - now).total_seconds())
        expedition = {
            "started_at": started_at.isoformat(),
            "duration_h": duration_h,
            "reward_min": active["reward_min"],
            "reward_max": active["reward_max"],
            "done": done,
            "time_left_h": int(secs_left // 3600),
            "time_left_m": int((secs_left % 3600) // 60),
        }

    mora_row = await get_mora(uid, chat_id)
    balance = mora_row["balance"] if mora_row else 0

    return {
        "ok": True,
        "pet": pet,
        "expedition": expedition,
        "balance": balance,
        "options": {
            k: {
                "hours": v["hours"],
                "cost": v["cost"],
                "reward_min": v["reward_min"],
                "reward_max": v["reward_max"],
                "label": v["label"],
            }
            for k, v in EXPEDITION_OPTIONS.items()
        },
    }


async def get_status(uid: int, chat_id: int) -> dict:
    """Return current expedition status and pet info.

    Returns {active, started_at?, duration_h?, reward_min?, reward_max?,
             remaining_sec?, pet?}.
    """
    from database.db import get_active_expedition, get_pet

    active = await get_active_expedition(uid, chat_id)
    pet = await get_pet(uid, chat_id)

    pet_info = None
    if pet:
        walk_end = pet.get("walk_end_at")
        walking = False
        if walk_end:
            if isinstance(walk_end, str):
                walk_end = datetime.fromisoformat(walk_end.replace("Z", "+00:00"))
            if hasattr(walk_end, "tzinfo") and walk_end.tzinfo is None:
                walk_end = walk_end.replace(tzinfo=timezone.utc)
            walking = walk_end > datetime.now(timezone.utc)
        pet_info = {
            "pet_type": pet.get("pet_type"),
            "name": pet.get("name"),
            "fatigue": pet.get("fatigue") or 0,
            "walking": walking,
        }

    if not active:
        return {"ok": True, "active": False, "pet": pet_info}

    started_at = active["started_at"]
    duration_h = active["duration_h"]

    if isinstance(started_at, str):
        started_at = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)

    end_at = started_at + timedelta(hours=duration_h)
    now = datetime.now(timezone.utc)
    remaining = max(0, int((end_at - now).total_seconds()))

    return {
        "ok": True,
        "active": True,
        "started_at": started_at.isoformat(),
        "duration_h": duration_h,
        "reward_min": active["reward_min"],
        "reward_max": active["reward_max"],
        "remaining_sec": remaining,
        "pet": pet_info,
    }
