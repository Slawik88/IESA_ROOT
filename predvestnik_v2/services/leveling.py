# services/leveling.py — прогрессия уровня аккаунта.
#
# Уровень аккаунта ГЛОБАЛЬНЫЙ (users.account_xp / users.account_level):
# экспоненциальная кривая XP_req(L→L+1) = ACC_XP_BASE × ACC_XP_GROWTH^(L−1).
# Per-chat user_xp/user_level в user_chat_stats продолжают копиться как
# счётчики активности (топы, админка), но игровой уровень читается ТОЛЬКО отсюда.
import aiosqlite

from core.constants import ACC_XP_BASE, ACC_XP_GROWTH, ACC_LEVEL_CAP
from infrastructure.repositories import chat as chat_repo
from infrastructure.repositories import users as users_repo


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


async def process_message_xp(
    db: aiosqlite.Connection,
    user_id: int,
    chat_id: int,
    timezone_offset: str = "+3 hours",
) -> tuple[bool, int, int]:
    """Record a message without turning chat volume into power or currency.

    The function name is retained for callers during migration. Existing account
    XP/level remain readable legacy history; neither is mutated here.
    """
    stats = await chat_repo.increment_stats_and_get_xp(db, user_id, chat_id, timezone_offset)
    msg_count = stats.get("user_messages_count_all_time", 0)
    acc = await users_repo.get_account_progress(db, user_id)
    return False, calculate_account_level(acc.get("account_xp", 0)), msg_count
