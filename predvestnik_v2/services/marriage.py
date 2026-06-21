# services/marriage.py
# Business rules for marriage proposals. No platform dependencies.
import aiosqlite

from infrastructure.repositories.marriages import get_user_marriage


async def check_marriage_proposal(
    db: aiosqlite.Connection,
    initiator_id: int,
    target_id: int,
    is_target_bot: bool,
) -> tuple[bool, str]:
    """Return (allowed, error_message)."""
    if initiator_id == target_id:
        return False, "🤡 <b>Ошибка:</b> Нельзя заключить брак с самим собой!"
    if is_target_bot:
        return False, "🤖 <b>Ошибка:</b> Боты созданы для работы, а не для любви."
    if await get_user_marriage(db, initiator_id):
        return False, "💔 <b>Ошибка:</b> Вы уже состоите в браке!"
    if await get_user_marriage(db, target_id):
        return False, "💔 <b>Ошибка:</b> Этот пользователь уже состоит в браке!"
    return True, ""


# ── Годовщины брака (Implementation Block 14) ────────────────────────────────
# Вехи: 100 дней, затем каждый год (365, 730, ...). Празднуется один раз
# (маркер marriages.last_anniversary хранит дни последней отпразднованной вехи).
_ANNIVERSARY_MILESTONES: list[int] = [100] + [365 * y for y in range(1, 60)]


def anniversary_due(days: int, last_celebrated: int) -> int | None:
    """Наивысшая достигнутая веха (в днях), если она новее last_celebrated, иначе None."""
    reached = [m for m in _ANNIVERSARY_MILESTONES if m <= days]
    if not reached:
        return None
    top = max(reached)
    return top if top > last_celebrated else None


def _years_word(y: int) -> str:
    if y % 10 == 1 and y % 100 != 11:
        return "год"
    if 2 <= y % 10 <= 4 and not 12 <= y % 100 <= 14:
        return "года"
    return "лет"


def anniversary_reward(milestone: int) -> tuple[int, int, str]:
    """(mora, diamonds, label) за веху. Награда — каждому супругу."""
    if milestone < 365:
        return 500, 2, "100 дней вместе 💞"
    years = milestone // 365
    return 1500 * years, 5 * years, f"{years} {_years_word(years)} вместе 💞"
