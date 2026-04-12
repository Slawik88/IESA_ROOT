"""
api/achievements.py — Интеграционный слой достижений для Telegram-бота.

Тонкая обёртка над services/achievements.py:
  - Реэкспортирует все публичные имена (обратная совместимость для всех call-sites).
  - Добавляет единственную aiogram-зависимость: уведомление в чат при получении ачивки.

Вся бизнес-логика, данные и работа с БД — в services/achievements.py.
Mini App API (Django) может импортировать напрямую из services.
"""
from __future__ import annotations

import logging

# ── Реэкспорт из сервисного слоя (полная обратная совместимость) ──────────────
from services.achievements import (           # noqa: F401 — публичные имена
    ACHIEVEMENTS,
    ACH_BY_KEY,
    ACH_BY_TYPE,
    BOOL_TYPES,
    TYPE_META,
    check_and_grant,
    get_user_achievements,
    get_leaderboard,
    get_user_badge_keys,
)

_log = logging.getLogger(__name__)


# ── Обёртки с обратной совместимостью (старые имена → новые) ──────────────────
# Все 21+ call-site вызывают check_and_award(uid, cid, type, value, bot, username).
# Мы сохраняем эту сигнатуру, делегируя логику в сервис и добавляя уведомление.

async def check_and_award(
    user_id: int,
    chat_id: int,
    ach_type: str,
    value: int | float,
    bot=None,
    username: str = "",
) -> list[dict]:
    """Проверить и выдать достижения + отправить уведомление в чат.

    Это единственное место с зависимостью от aiogram (bot.send_message).
    Вся бизнес-логика — в services.achievements.check_and_grant().
    Безопасна для fire-and-forget: никогда не пробрасывает исключений.
    """
    try:
        newly_awarded = await check_and_grant(user_id, chat_id, ach_type, value)
    except Exception as e:
        _log.warning("check_and_award ошибка uid=%s type=%s: %s", user_id, ach_type, e)
        return []

    if newly_awarded:
        await _notify_achievements(bot, user_id, chat_id, newly_awarded, username)

    return newly_awarded


async def get_all_achievements_with_status(user_id: int, chat_id: int) -> dict:
    """Обёртка над get_user_achievements() для совместимости с miniapp_views."""
    return await get_user_achievements(user_id, chat_id)


async def get_global_achievements_leaderboard(chat_id: int, limit: int = 20) -> list[dict]:
    """Обёртка над get_leaderboard() для совместимости с miniapp_views."""
    return await get_leaderboard(chat_id, limit)


# ── Уведомление в Telegram-чат (единственная aiogram-зависимость) ────────────

async def _notify_achievements(
    bot,
    user_id: int,
    chat_id: int,
    newly_awarded: list[dict],
    username: str,
) -> None:
    """Отправить красивое уведомление о новых достижениях в чат."""
    if not bot:
        try:
            from utils.bot_instance import get_bot
            bot = get_bot()
        except Exception:
            return
    if not bot:
        return
    try:
        lines = "\n".join(
            f"{a['emoji']} <b>{a['title']}</b> — {a['description']}"
            f"  <i>(+{a['mora']} 🪙{(' / +' + str(a['xp']) + ' XP') if a.get('xp') else ''})</i>"
            for a in newly_awarded
        )
        name = username or "Предвестник"
        n = len(newly_awarded)
        header = "достижения" if n > 1 else "достижение"
        await bot.send_message(
            chat_id,
            f"🏆 <b>{name}</b> получил {header}!\n\n{lines}",
            parse_mode="HTML",
        )
    except Exception as e:
        _log.debug("Уведомление о достижениях не отправлено: %s", e)
