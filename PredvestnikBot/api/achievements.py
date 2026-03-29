# api/achievements.py — Система достижений/титулов
# Использует таблицу user_badges (user_id, chat_id, badge_key, obtained_at)
# Счётчики хранятся в user_mora (expeditions_sent, chests_opened, casino_wins,
#   roulette_losses, total_gacha_rolls, total_coinflip, rep_given_count)
# Уровень/сообщения — из user_mora (level, message_count)
# Брак — из marriages; питомец — из pets; чекин — из daily_checkin
# Босс-урон — SUM из boss_damage_log

from __future__ import annotations
import asyncio
import logging
from typing import Optional
from database.db import postgres_connect

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Определения достижений
# Поля: key, title, emoji, description, mora_reward, xp_reward
#   ach_type: тип события, threshold: значение для разблокировки
# ---------------------------------------------------------------------------
ACHIEVEMENTS: list[dict] = [
    # ─── Сообщения в чате ─────────────────────────────────────────────
    {"key": "chat_100",    "title": "Активист",        "emoji": "🗣",  "description": "Отправить 100 сообщений в чате",    "mora": 30,   "xp": 50,   "type": "messages",       "threshold": 100},
    {"key": "chat_500",    "title": "Оратор",           "emoji": "📢",  "description": "Отправить 500 сообщений в чате",    "mora": 60,   "xp": 100,  "type": "messages",       "threshold": 500},
    {"key": "chat_1000",   "title": "Болтун",           "emoji": "💬",  "description": "Отправить 1000 сообщений в чате",   "mora": 150,  "xp": 200,  "type": "messages",       "threshold": 1000},
    {"key": "chat_5000",   "title": "Трибун",           "emoji": "📣",  "description": "Отправить 5000 сообщений в чате",   "mora": 500,  "xp": 500,  "type": "messages",       "threshold": 5000},
    {"key": "chat_10000",  "title": "Легенда Чата",     "emoji": "🏆",  "description": "Отправить 10 000 сообщений в чате", "mora": 1000, "xp": 1000, "type": "messages",       "threshold": 10000},
    # ─── Гача ─────────────────────────────────────────────────────────
    {"key": "gacha_10",    "title": "Молящийся",        "emoji": "🙏",  "description": "Сделать 10 круток гачи",            "mora": 50,   "xp": 50,   "type": "gacha_rolls",    "threshold": 10},
    {"key": "gacha_50",    "title": "Охотник за удачей","emoji": "🎰",  "description": "Сделать 50 круток гачи",            "mora": 100,  "xp": 100,  "type": "gacha_rolls",    "threshold": 50},
    {"key": "gacha_100",   "title": "Одержимый",        "emoji": "😈",  "description": "Сделать 100 круток гачи",           "mora": 200,  "xp": 200,  "type": "gacha_rolls",    "threshold": 100},
    {"key": "gacha_500",   "title": "Завсегдатай Гачи", "emoji": "🌀",  "description": "Сделать 500 круток гачи",           "mora": 500,  "xp": 500,  "type": "gacha_rolls",    "threshold": 500},
    # ─── Урон по боссу (суммарно) ─────────────────────────────────────
    {"key": "boss_1k",     "title": "Воитель",          "emoji": "⚔️",  "description": "Нанести 1 000 урона боссам",        "mora": 50,   "xp": 50,   "type": "boss_damage",    "threshold": 1000},
    {"key": "boss_10k",    "title": "Истребитель",       "emoji": "🗡",  "description": "Нанести 10 000 урона боссам",       "mora": 150,  "xp": 150,  "type": "boss_damage",    "threshold": 10000},
    {"key": "boss_50k",    "title": "Герой Мира",        "emoji": "🦸",  "description": "Нанести 50 000 урона боссам",       "mora": 500,  "xp": 500,  "type": "boss_damage",    "threshold": 50000},
    # ─── Стрик чекина ─────────────────────────────────────────────────
    {"key": "streak_7",    "title": "Пунктуальный",     "emoji": "📅",  "description": "Чекин 7 дней подряд",               "mora": 50,   "xp": 50,   "type": "checkin_streak", "threshold": 7},
    {"key": "streak_20",   "title": "Дисциплинированный","emoji": "🎯", "description": "Чекин 20 дней подряд",              "mora": 200,  "xp": 200,  "type": "checkin_streak", "threshold": 20},
    {"key": "streak_50",   "title": "Постоянный",        "emoji": "🔥", "description": "Чекин 50 дней подряд",              "mora": 500,  "xp": 500,  "type": "checkin_streak", "threshold": 50},
    # ─── Уровень ──────────────────────────────────────────────────────
    {"key": "level_10",    "title": "Новичок",          "emoji": "🌱",  "description": "Достичь 10 уровня",                 "mora": 30,   "xp": 0,    "type": "level",          "threshold": 10},
    {"key": "level_25",    "title": "Опытный",          "emoji": "⭐",  "description": "Достичь 25 уровня",                 "mora": 100,  "xp": 0,    "type": "level",          "threshold": 25},
    {"key": "level_50",    "title": "Ветеран",          "emoji": "💫",  "description": "Достичь 50 уровня",                 "mora": 300,  "xp": 0,    "type": "level",          "threshold": 50},
    {"key": "level_100",   "title": "Легенда",          "emoji": "🏅",  "description": "Достичь 100 уровня",                "mora": 1000, "xp": 0,    "type": "level",          "threshold": 100},
    # ─── Монетка/казино ────────────────────────────────────────────────
    {"key": "coin_10",     "title": "Пробующий",        "emoji": "🪙",  "description": "Сыграть в монетку 10 раз",          "mora": 30,   "xp": 30,   "type": "coinflip",       "threshold": 10},
    {"key": "coin_50",     "title": "Азартный",         "emoji": "🎲",  "description": "Сыграть в монетку 50 раз",          "mora": 100,  "xp": 100,  "type": "coinflip",       "threshold": 50},
    {"key": "coin_100",    "title": "Картёжник",        "emoji": "🃏",  "description": "Сыграть в монетку 100 раз",         "mora": 200,  "xp": 200,  "type": "coinflip",       "threshold": 100},
    # ─── Репутация ────────────────────────────────────────────────────
    {"key": "rep_10",      "title": "Добросердечный",   "emoji": "💚",  "description": "👍 Добавить репутацию 10 игрокам",  "mora": 50,   "xp": 50,   "type": "rep_given",      "threshold": 10},
    {"key": "rep_50",      "title": "Меценат",          "emoji": "💛",  "description": "👍 Добавить репутацию 50 игрокам",  "mora": 150,  "xp": 150,  "type": "rep_given",      "threshold": 50},
    # ─── Отношения / питомец ──────────────────────────────────────────
    {"key": "married",     "title": "Влюблённый",       "emoji": "💍",  "description": "Вступить в брак",                   "mora": 100,  "xp": 100,  "type": "married",        "threshold": 1},
    {"key": "has_pet",     "title": "Хозяин Питомца",   "emoji": "🐾",  "description": "Завести питомца",                   "mora": 100,  "xp": 100,  "type": "has_pet",        "threshold": 1},
    # ─── Экспедиции ────────────────────────────────────────────────────
    {"key": "exped_5",     "title": "Первопроходец",    "emoji": "🗺",  "description": "Отправить 5 экспедиций",             "mora": 50,   "xp": 50,   "type": "expeditions",    "threshold": 5},
    {"key": "exped_20",    "title": "Следопыт",         "emoji": "🧭",  "description": "Отправить 20 экспедиций",            "mora": 150,  "xp": 150,  "type": "expeditions",    "threshold": 20},
    # ─── Богатство ────────────────────────────────────────────────────
    {"key": "mora_1k",     "title": "Накопитель",       "emoji": "💰",  "description": "Накопить 1 000 моры",                "mora": 50,   "xp": 50,   "type": "mora_balance",   "threshold": 1000},
    {"key": "mora_5k",     "title": "Богатей",          "emoji": "💎",  "description": "Накопить 5 000 моры",                "mora": 100,  "xp": 100,  "type": "mora_balance",   "threshold": 5000},
    {"key": "mora_10k",    "title": "Магнат",           "emoji": "🏦",  "description": "Накопить 10 000 моры",               "mora": 200,  "xp": 200,  "type": "mora_balance",   "threshold": 10000},
    # ─── Торговля / аукцион ───────────────────────────────────────────
    {"key": "first_sell",  "title": "Торговец",         "emoji": "🏪",  "description": "Выставить первый лот на аукцион",    "mora": 50,   "xp": 50,   "type": "auction_sell",   "threshold": 1},
    {"key": "first_win",   "title": "Победитель торгов","emoji": "🔨",  "description": "Выиграть аукцион",                   "mora": 100,  "xp": 100,  "type": "auction_win",    "threshold": 1},
]

# быстрый dict для поиска по ключу
ACH_BY_KEY: dict[str, dict] = {a["key"]: a for a in ACHIEVEMENTS}

# поиск достижений по типу, отсортированных по threshold
ACH_BY_TYPE: dict[str, list[dict]] = {}
for _a in ACHIEVEMENTS:
    ACH_BY_TYPE.setdefault(_a["type"], []).append(_a)
for _lst in ACH_BY_TYPE.values():
    _lst.sort(key=lambda x: x["threshold"])


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------

async def _get_counter(db, user_id: int, chat_id: int, col: str) -> int:
    """Получить значение счётчика из user_mora."""
    row = await db.fetchrow(
        f"SELECT {col} FROM user_mora WHERE user_id=? AND chat_id=?",
        user_id, chat_id
    )
    return int(row[col] or 0) if row else 0


async def _award(db, user_id: int, chat_id: int, ach: dict) -> bool:
    """Выдать достижение. Возвращает True если это новое достижение."""
    try:
        result = await db.execute(
            """INSERT INTO user_badges (user_id, chat_id, badge_key, obtained_at)
               VALUES (?, ?, ?, NOW()) ON CONFLICT DO NOTHING""",
            user_id, chat_id, ach["key"]
        )
        # asyncpg возвращает 'INSERT 0 0' или 'INSERT 0 1'
        if hasattr(result, 'split'):
            rows_affected = int(result.split()[-1]) if result else 0
        else:
            rows_affected = 1  # psycopg2 compatible
        if rows_affected == 0:
            return False
    except Exception:
        return False

    # Применяем награду
    try:
        if ach["mora"] > 0:
            await db.execute(
                "UPDATE user_mora SET mora = mora + ? WHERE user_id=? AND chat_id=?",
                ach["mora"], user_id, chat_id
            )
        if ach.get("xp", 0) > 0:
            await db.execute(
                "UPDATE user_mora SET xp = xp + ? WHERE user_id=? AND chat_id=?",
                ach["xp"], user_id, chat_id
            )
    except Exception as e:
        logger.warning("Achievement reward failed for %s: %s", ach["key"], e)

    return True


async def check_and_award(
    user_id: int,
    chat_id: int,
    ach_type: str,
    value: int | float,
    bot=None,
    username: str = "",
) -> list[dict]:
    """
    Проверить и выдать все достижения типа ach_type где threshold <= value.
    Возвращает список только что выданных достижений.
    Безопасно вызывать fire-and-forget через asyncio.create_task().
    """
    candidates = ACH_BY_TYPE.get(ach_type, [])
    if not candidates:
        return []

    newly_awarded: list[dict] = []
    try:
        async with postgres_connect() as db:
            for ach in candidates:
                if value >= ach["threshold"]:
                    if await _award(db, user_id, chat_id, ach):
                        newly_awarded.append(ach)
    except Exception as e:
        logger.warning("check_and_award error (%s, %s, %s): %s", user_id, chat_id, ach_type, e)
        return []

    if newly_awarded and bot:
        try:
            lines = "\n".join(
                f"{a['emoji']} <b>{a['title']}</b> — {a['description']} (+{a['mora']} 🪙)"
                for a in newly_awarded
            )
            name = username or f"Предвестник"
            await bot.send_message(
                chat_id,
                f"🏆 <b>{name}</b> разблокировал достижение{'я' if len(newly_awarded) > 1 else ''}!\n\n{lines}",
                parse_mode="HTML",
            )
        except Exception as e:
            logger.debug("Achievement notify failed: %s", e)

    return newly_awarded


async def get_user_achievements(user_id: int, chat_id: int) -> list[dict]:
    """Вернуть список всех выданных достижений пользователя с деталями."""
    try:
        async with postgres_connect() as db:
            rows = await db.fetch(
                "SELECT badge_key, obtained_at FROM user_badges WHERE user_id=? AND chat_id=?",
                user_id, chat_id
            )
    except Exception:
        return []

    result = []
    for row in rows:
        key = row["badge_key"]
        if key in ACH_BY_KEY:
            ach = dict(ACH_BY_KEY[key])
            ach["obtained_at"] = str(row.get("obtained_at", ""))
            result.append(ach)
    result.sort(key=lambda x: x.get("obtained_at", ""), reverse=True)
    return result


async def get_all_achievements_with_status(user_id: int, chat_id: int) -> list[dict]:
    """
    Вернуть все 32 достижения с флагом unlocked=True/False.
    Используется для Mini App.
    """
    try:
        async with postgres_connect() as db:
            rows = await db.fetch(
                "SELECT badge_key, obtained_at FROM user_badges WHERE user_id=? AND chat_id=?",
                user_id, chat_id
            )
        earned = {row["badge_key"]: str(row.get("obtained_at", "")) for row in rows}
    except Exception:
        earned = {}

    result = []
    for ach in ACHIEVEMENTS:
        entry = dict(ach)
        entry["unlocked"] = ach["key"] in earned
        entry["obtained_at"] = earned.get(ach["key"], None)
        result.append(entry)
    return result
