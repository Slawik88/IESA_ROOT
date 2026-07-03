# services/leveling.py — прогрессия уровня аккаунта (R0, GDD_REBUILD_PLAN.md).
#
# Уровень аккаунта ГЛОБАЛЬНЫЙ (users.account_xp / users.account_level):
# экспоненциальная кривая XP_req(L→L+1) = ACC_XP_BASE × ACC_XP_GROWTH^(L−1).
# Per-chat user_xp/user_level в user_chat_stats продолжают копиться как
# счётчики активности (топы, админка), но игровой уровень читается ТОЛЬКО отсюда.
import aiosqlite
from datetime import datetime, timedelta, timezone

from core.constants import (
    XP_PER_MESSAGE, XP_DAILY_SOFT_STEPS,
    ACC_XP_BASE, ACC_XP_GROWTH, ACC_LEVEL_CAP,
    ACC_LEVEL_REWARD_MORA_PER_LVL, ACC_LEVEL_REWARD_DIAMONDS,
    ACC_LEVEL_REWARD_DIAMONDS_MILESTONE,
)
from infrastructure.repositories import chat as chat_repo
from infrastructure.repositories import economy as eco_repo
from infrastructure.repositories import users as users_repo
from infrastructure.repositories import zoo as zoo_repo


# ── Кривая уровней ────────────────────────────────────────────────────────────

def xp_for_level(level: int) -> int:
    """Кумулятивный XP, необходимый для ДОСТИЖЕНИЯ уровня level (уровень 1 = 0 XP).
    C(L) = BASE × (GROWTH^(L−1) − 1) / (GROWTH − 1)."""
    if level <= 1:
        return 0
    return int(round(ACC_XP_BASE * (ACC_XP_GROWTH ** (level - 1) - 1) / (ACC_XP_GROWTH - 1)))


def calculate_account_level(xp: int) -> int:
    """Уровень аккаунта по накопленному XP (обратная функция кумулятива).
    Линейный подъём по уровням: кривая монотонна, ACC_LEVEL_CAP ограничивает цикл."""
    xp = max(0, int(xp or 0))
    level = 1
    while level < ACC_LEVEL_CAP and xp >= xp_for_level(level + 1):
        level += 1
    return level


def account_progress(xp: int) -> dict:
    """Прогресс внутри текущего уровня: {level, xp_into, xp_need}.
    xp_need = 0 на капе (бар в UI показывается заполненным)."""
    level = calculate_account_level(xp)
    floor = xp_for_level(level)
    need = 0 if level >= ACC_LEVEL_CAP else xp_for_level(level + 1) - floor
    return {"level": level, "xp_into": max(0, int(xp or 0) - floor), "xp_need": need}


def _daily_xp_multiplier(msgs_today: int) -> float:
    """Софт-кап XP за сообщения: полный XP до 100-го сообщения дня, дальше ступени.
    msgs_today — номер ТЕКУЩЕГО сообщения (счётчик уже инкрементирован)."""
    for threshold, mult in XP_DAILY_SOFT_STEPS:
        if msgs_today <= threshold:
            return mult
    return XP_DAILY_SOFT_STEPS[-1][1]


def _level_up_rewards(from_level: int, to_level: int) -> tuple[float, float]:
    """Суммарная награда (мора, алмазы) за все уровни (from_level; to_level]."""
    mora = diamonds = 0.0
    for lvl in range(from_level + 1, to_level + 1):
        mora += ACC_LEVEL_REWARD_MORA_PER_LVL * lvl
        diamonds += ACC_LEVEL_REWARD_DIAMONDS
        if lvl % 5 == 0:
            diamonds += ACC_LEVEL_REWARD_DIAMONDS_MILESTONE
    return mora, diamonds


def _is_weekend_in_tz(timezone_offset: str) -> bool:
    """Returns True if 'now' is Saturday or Sunday in the chat's timezone.
    Parses '+3 hours' / '-5 hours' style strings."""
    try:
        parts = timezone_offset.strip().split()
        hours = int(parts[0])
    except (ValueError, IndexError):
        hours = 0
    now = datetime.now(timezone.utc) + timedelta(hours=hours)
    return now.weekday() >= 5


async def process_message_xp(
    db: aiosqlite.Connection,
    user_id: int,
    chat_id: int,
    timezone_offset: str = "+3 hours",
) -> tuple[bool, int]:
    """Начислить XP за одно сообщение: per-chat счётчик (топы) + XP аккаунта.

    Аккаунт получает: base×софт-кап + бонус Конспекта + бонус Совы.
    Per-chat user_xp получает те же слагаемые БЕЗ софт-капа (это счётчик
    активности, а не прогрессия — резать его незачем).
    Возвращает (был ли левел-ап аккаунта, текущий уровень аккаунта)."""
    stats = await chat_repo.increment_stats_and_get_xp(db, user_id, chat_id, timezone_offset)

    msg_count = stats.get("user_messages_count_all_time", 0)
    msgs_today = stats.get("user_messages_count_per_day", 1)

    account_gain = int(round(XP_PER_MESSAGE * _daily_xp_multiplier(msgs_today)))

    # study_notes: +50% XP if buff active
    try:
        async with db.execute(
            "SELECT expires_at, value FROM player_buffs "
            "WHERE user_id = ? AND buff_type = 'study_xp' AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)",
            (user_id,),
        ) as _sb:
            _sbrow = await _sb.fetchone()
        if _sbrow:
            study_bonus = int(round(XP_PER_MESSAGE * float(_sbrow["value"] or 0.5)))
            if study_bonus > 0:
                await chat_repo.add_xp(db, user_id, chat_id, study_bonus)
                account_gain += study_bonus
    except Exception:
        pass

    # Block 12: бонус Совы масштабируется по слоту (passive → bonus_xp ×0.5,
    # weekend_double off; trigger_every_n_msg структурное — не масштабируется).
    # R0-фикс: msg_count теперь реально возвращается из RETURNING (раньше всегда
    # был 0 → «каждое N-е сообщение» срабатывало на каждом).
    owl = await zoo_repo.get_species_bonus(db, user_id, "owl")
    if owl:
        every_n = owl.get("trigger_every_n_msg", 1)
        if every_n > 0 and msg_count % every_n == 0:
            bonus = owl.get("bonus_xp", 0.0)
            if owl.get("weekend_double") and _is_weekend_in_tz(timezone_offset):
                bonus *= 2.0
            bonus_int = int(round(bonus))
            if bonus_int > 0:
                await chat_repo.add_xp(db, user_id, chat_id, bonus_int)
                account_gain += bonus_int

    acc = await users_repo.add_account_xp(db, user_id, account_gain)
    old_lvl = int(acc.get("account_level") or 1)
    new_lvl = calculate_account_level(acc.get("account_xp", 0))

    if new_lvl > old_lvl:
        await users_repo.set_account_level(db, user_id, new_lvl)
        mora, diamonds = _level_up_rewards(old_lvl, new_lvl)
        await eco_repo.add_balance(
            db, user_id, mora=mora, diamonds=diamonds,
            source="level_up", note=f"Уровень аккаунта {new_lvl}",
        )
        return True, new_lvl

    return False, new_lvl