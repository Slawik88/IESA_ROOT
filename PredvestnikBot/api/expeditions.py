"""
api/expeditions.py — unified expedition operations.

All functions are async; the mini app wraps them with async_to_sync.
"""
import random
from datetime import datetime, timedelta, timezone
import logging
_log = logging.getLogger(__name__)


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
        add_mora, add_pet_fatigue, add_to_family_wallet,
        get_active_expedition, get_family_wallet, get_mora, get_pet,
        is_user_single, start_expedition as _db_start_expedition,
    )
    from config import EXPEDITION_OPTIONS

    opt = EXPEDITION_OPTIONS.get(option_key)
    if not opt:
        raise ValueError("Неизвестный тип экспедиции")

    # Pet checks
    pet = await get_pet(uid, chat_id)
    if not pet:
        raise ValueError("У тебя нет питомца")

    from config import PET_FATIGUE_MAX
    fatigue = pet.get("fatigue") or 0
    if fatigue >= PET_FATIGUE_MAX:
        raise ValueError(f"Питомец слишком устал ({PET_FATIGUE_MAX}/{PET_FATIGUE_MAX}). Покорми его!")

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
        except Exception as _e:
            _log.debug("%s", _e)
    active = await get_active_expedition(uid, chat_id)
    if active:
        raise ValueError("Питомец уже в экспедиции")

    # Block if partner already has an active expedition (couple shares ONE expedition slot)
    from database.db import get_marriage
    marriage = await get_marriage(uid, chat_id)
    if marriage:
        partner_id = marriage["partner_id"]
        partner_active = await get_active_expedition(partner_id, chat_id)
        if partner_active:
            raise ValueError("Питомец вашей пары уже в экспедиции")

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
                cursor = await db.execute(
                    "UPDATE family_wallet SET balance=balance-? WHERE chat_id=0 AND user_id=? AND balance>=?",
                    (cost, uid, cost),
                )
                if cursor.rowcount == 0:
                    fam_bal2 = await get_family_wallet(chat_id, uid)
                    raise ValueError(f"Недостаточно Моры в семейном кошельке ({fam_bal2}/{cost} 🪙)")
                await db.commit()
        else:
            from database.postgres import connect as postgres_connect
            async with postgres_connect() as db:
                cursor = await db.execute(
                    "UPDATE users SET balance=balance-? WHERE user_id=? AND COALESCE(balance,0)>=?",
                    (cost, uid, cost),
                )
                if cursor.rowcount == 0:
                    mora_row = await get_mora(uid, chat_id)
                    bal = mora_row["balance"] if mora_row else 0
                    raise ValueError(f"Недостаточно Моры ({bal}/{cost} 🪙)")
                await db.commit()

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

    # Log expedition cost
    if cost > 0:
        try:
            from api.economy import log_wallet_tx
            await log_wallet_tx(uid, chat_id, "expense", cost, "expedition",
                                f"Экспедиция {opt['hours']}ч")
        except Exception as _e:
            _log.debug("%s", _e)
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
        logging.getLogger(__name__).warning("quest_tick failed uid=%s chat=%s", uid, chat_id, exc_info=True)

    # Return current balance after cost deduction
    from database.db import get_mora as _get_mora, get_family_wallet as _get_fam_wal
    new_balance = None
    new_family_balance = None
    try:
        if wallet_type == "family":
            new_family_balance = await _get_fam_wal(chat_id, uid)
        else:
            _m = await _get_mora(uid, chat_id)
            new_balance = _m["balance"] if _m else 0
    except Exception as _e:
        _log.debug("%s", _e)
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
        "new_balance": new_balance,
        "new_family_balance": new_family_balance,
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
    # Talent: expedition_haste reduces cooldown by N minutes
    try:
        from database.db import get_talent_effect as _gte
        _cd_red = await _gte(uid, "expedition_cd_minutes")
        if _cd_red > 0:
            end_at -= timedelta(minutes=_cd_red)
    except Exception as _e:
        _log.debug("%s", _e)
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

    # Log reward
    try:
        from api.economy import log_wallet_tx
        await log_wallet_tx(uid, chat_id, "income", net_reward, "expedition",
                            f"Награда экспедиции ({reward_gross}🪙 - {exped_tax}🪙 налог)")
    except Exception as _e:
        _log.debug("%s", _e)
    # Block 4: Add season XP for expedition completion
    season_level_up = False
    season_new_level = 0
    try:
        from database.db import add_season_xp
        season_result = await add_season_xp(uid, 8)  # +8 season XP
        season_level_up = season_result.get("level_up", False)
        season_new_level = season_result.get("new_level", 0)
    except Exception:
        pass  # Безопасно игнорируем ошибки season XP

    return {
        "ok":           True,
        "reward_gross": reward_gross,
        "reward":       net_reward,
        "tax":          exped_tax,
        "new_balance":  new_balance,
        "season_level_up": season_level_up,
        "season_new_level": season_new_level,
    }


async def get_expedition_status(uid: int, chat_id: int) -> dict:
    """Full expedition page payload: pet, active expedition, balance, options.

    Returns the same shape the miniapp_expeditions GET view expects.
    """
    from database.db import get_active_expedition, get_mora, get_pet
    from config import EXPEDITION_OPTIONS

    pet_row = await get_pet(uid, chat_id)
    pet = None
    if pet_row:
        pet = {
            "type": pet_row.get("pet_type"),
            "name": pet_row.get("name") or "безымянный",
            "fatigue": pet_row.get("fatigue") or 0,
            "color": pet_row.get("color_name"),
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
            except Exception as _e:
                _log.debug("%s", _e)
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

    # Family wallet balance (0 if user is single)
    family_balance = 0
    partner_expedition = None
    try:
        from database.db import get_family_wallet, is_user_single, get_marriage, get_active_expedition as _get_exp
        if not await is_user_single(uid, chat_id):
            family_balance = await get_family_wallet(chat_id, uid)
            marriage = await get_marriage(uid, chat_id)
            if marriage:
                partner_id = marriage["partner_id"]
                partner_active = await _get_exp(partner_id, chat_id)
                if partner_active:
                    p_started = partner_active["started_at"]
                    p_duration_h = partner_active["duration_h"]
                    if isinstance(p_started, str):
                        p_started = datetime.fromisoformat(p_started.replace("Z", "+00:00"))
                    if p_started.tzinfo is None:
                        p_started = p_started.replace(tzinfo=timezone.utc)
                    p_end = p_started + timedelta(hours=p_duration_h)
                    p_done = datetime.now(timezone.utc) >= p_end
                    p_secs = max(0, (p_end - datetime.now(timezone.utc)).total_seconds())
                    partner_expedition = {
                        "duration_h": p_duration_h,
                        "reward_min": partner_active["reward_min"],
                        "reward_max": partner_active["reward_max"],
                        "done": p_done,
                        "time_left_h": int(p_secs // 3600),
                        "time_left_m": int((p_secs % 3600) // 60),
                    }
    except Exception as _e:
        _log.debug("%s", _e)
    return {
        "ok": True,
        "pet": pet,
        "expedition": expedition,
        "partner_expedition": partner_expedition,
        "balance": balance,
        "family_balance": family_balance,
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


async def boost_expedition(uid: int, chat_id: int, item_id: int) -> dict:
    """Apply an expedition boost coupon. Returns {ok, new_end_at, saved_minutes}."""
    from database.postgres import connect as postgres_connect
    from shared_prices import ITEM_METADATA

    # Look up active expedition globally (any chat), so mini-app chat context doesn't matter
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT * FROM pet_expeditions WHERE user_id=? AND finished=0",
            (uid,),
        ) as c:
            active = await c.fetchone()
    if not active:
        raise ValueError("Нет активной экспедиции")
    expedition_chat_id = active["chat_id"]

    async with postgres_connect() as db:
        async with db.execute(
            "SELECT id, item_key, COALESCE(stack_count, 1) FROM gacha_inventory "
            "WHERE id=? AND user_id=?",
            (item_id, uid),
        ) as c:
            item_row = await c.fetchone()
        if not item_row:
            raise ValueError("Предмет не найден")

        iid, item_key, stack_count = item_row[0], item_row[1], item_row[2]
        if not item_key.startswith("exp_boost_"):
            raise ValueError("Этот предмет нельзя использовать как ускорение")

        meta = ITEM_METADATA.get(item_key, {})
        started_at = active["started_at"]
        duration_h = active["duration_h"]
        if isinstance(started_at, str):
            started_at = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=timezone.utc)

        end_at = started_at + timedelta(hours=duration_h)
        now = datetime.now(timezone.utc)
        remaining_secs = max(0, (end_at - now).total_seconds())
        if remaining_secs == 0:
            raise ValueError("Экспедиция уже завершена — забери награду!")

        boost_pct = meta.get("boost_pct")
        boost_minutes = meta.get("boost_minutes")
        if boost_pct:
            saved_secs = remaining_secs * boost_pct
        elif boost_minutes:
            saved_secs = boost_minutes * 60
        else:
            raise ValueError("Некорректный купон ускорения")

        saved_secs = min(saved_secs, remaining_secs)
        new_started_at = started_at - timedelta(seconds=saved_secs)
        saved_minutes = int(saved_secs / 60)

        await db.execute(
            "UPDATE pet_expeditions SET started_at=? WHERE user_id=? AND chat_id=? AND finished=0",
            (new_started_at, uid, expedition_chat_id),
        )
        if stack_count <= 1:
            await db.execute("DELETE FROM gacha_inventory WHERE id=?", (iid,))
        else:
            await db.execute(
                "UPDATE gacha_inventory SET stack_count = stack_count - 1 WHERE id=?", (iid,)
            )
        await db.commit()
        new_end_at = (new_started_at + timedelta(hours=duration_h)).isoformat()

    return {"ok": True, "new_end_at": new_end_at, "saved_minutes": saved_minutes}


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
