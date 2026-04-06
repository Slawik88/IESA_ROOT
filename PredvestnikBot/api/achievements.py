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
    {"key": "chat_25000",  "title": "Неудержимый",      "emoji": "🌪",  "description": "Отправить 25 000 сообщений",        "mora": 2000, "xp": 2000, "type": "messages",       "threshold": 25000},
    {"key": "chat_50000",  "title": "Голос Эпохи",      "emoji": "👑",  "description": "Отправить 50 000 сообщений",        "mora": 5000, "xp": 5000, "type": "messages",       "threshold": 50000},
    # ─── Гача ─────────────────────────────────────────────────────────
    {"key": "gacha_10",    "title": "Молящийся",        "emoji": "🙏",  "description": "Сделать 10 круток гачи",            "mora": 50,   "xp": 50,   "type": "gacha_rolls",    "threshold": 10},
    {"key": "gacha_50",    "title": "Охотник за удачей","emoji": "🎰",  "description": "Сделать 50 круток гачи",            "mora": 100,  "xp": 100,  "type": "gacha_rolls",    "threshold": 50},
    {"key": "gacha_100",   "title": "Одержимый",        "emoji": "😈",  "description": "Сделать 100 круток гачи",           "mora": 200,  "xp": 200,  "type": "gacha_rolls",    "threshold": 100},
    {"key": "gacha_500",   "title": "Завсегдатай Гачи", "emoji": "🌀",  "description": "Сделать 500 круток гачи",           "mora": 500,  "xp": 500,  "type": "gacha_rolls",    "threshold": 500},
    {"key": "gacha_1000",  "title": "Избранный Гачи",   "emoji": "✨",  "description": "Сделать 1 000 круток гачи",         "mora": 1500, "xp": 1000, "type": "gacha_rolls",    "threshold": 1000},
    # ─── Урон по боссу (суммарно) ─────────────────────────────────────
    {"key": "boss_1k",     "title": "Воитель",          "emoji": "⚔️",  "description": "Нанести 1 000 урона боссам",        "mora": 50,   "xp": 50,   "type": "boss_damage",    "threshold": 1000},
    {"key": "boss_10k",    "title": "Истребитель",       "emoji": "🗡",  "description": "Нанести 10 000 урона боссам",       "mora": 150,  "xp": 150,  "type": "boss_damage",    "threshold": 10000},
    {"key": "boss_50k",    "title": "Герой Мира",        "emoji": "🦸",  "description": "Нанести 50 000 урона боссам",       "mora": 500,  "xp": 500,  "type": "boss_damage",    "threshold": 50000},
    {"key": "boss_200k",   "title": "Истребитель Богов", "emoji": "⚡",  "description": "Нанести 200 000 урона боссам",      "mora": 2000, "xp": 1500, "type": "boss_damage",    "threshold": 200000},
    {"key": "boss_500k",   "title": "Титан",            "emoji": "🔱",  "description": "Нанести 500 000 урона боссам",      "mora": 5000, "xp": 3000, "type": "boss_damage",    "threshold": 500000},
    # ─── Стрик чекина ─────────────────────────────────────────────────
    {"key": "streak_7",    "title": "Пунктуальный",     "emoji": "📅",  "description": "Чекин 7 дней подряд",               "mora": 50,   "xp": 50,   "type": "checkin_streak", "threshold": 7},
    {"key": "streak_20",   "title": "Дисциплинированный","emoji": "🎯", "description": "Чекин 20 дней подряд",              "mora": 200,  "xp": 200,  "type": "checkin_streak", "threshold": 20},
    {"key": "streak_50",   "title": "Постоянный",        "emoji": "🔥", "description": "Чекин 50 дней подряд",              "mora": 500,  "xp": 500,  "type": "checkin_streak", "threshold": 50},
    {"key": "streak_100",  "title": "Легенда Дисциплины","emoji": "💎", "description": "Чекин 100 дней подряд",             "mora": 2000, "xp": 1500, "type": "checkin_streak", "threshold": 100},
    # ─── Уровень ──────────────────────────────────────────────────────
    {"key": "level_5",     "title": "Первые шаги",      "emoji": "🌿",  "description": "Достичь 5 уровня",                  "mora": 15,   "xp": 0,    "type": "level",          "threshold": 5},
    {"key": "level_10",    "title": "Новичок",          "emoji": "🌱",  "description": "Достичь 10 уровня",                 "mora": 30,   "xp": 0,    "type": "level",          "threshold": 10},
    {"key": "level_25",    "title": "Опытный",          "emoji": "⭐",  "description": "Достичь 25 уровня",                 "mora": 100,  "xp": 0,    "type": "level",          "threshold": 25},
    {"key": "level_50",    "title": "Ветеран",          "emoji": "💫",  "description": "Достичь 50 уровня",                 "mora": 300,  "xp": 0,    "type": "level",          "threshold": 50},
    {"key": "level_100",   "title": "Легенда",          "emoji": "🏅",  "description": "Достичь 100 уровня",                "mora": 1000, "xp": 0,    "type": "level",          "threshold": 100},
    {"key": "level_200",   "title": "Бессмертный",      "emoji": "🌌",  "description": "Достичь 200 уровня",                "mora": 3000, "xp": 0,    "type": "level",          "threshold": 200},
    # ─── Монетка/казино ────────────────────────────────────────────────
    {"key": "coin_10",     "title": "Пробующий",        "emoji": "🪙",  "description": "Сыграть в монетку 10 раз",          "mora": 30,   "xp": 30,   "type": "coinflip",       "threshold": 10},
    {"key": "coin_50",     "title": "Азартный",         "emoji": "🎲",  "description": "Сыграть в монетку 50 раз",          "mora": 100,  "xp": 100,  "type": "coinflip",       "threshold": 50},
    {"key": "coin_100",    "title": "Картёжник",        "emoji": "🃏",  "description": "Сыграть в монетку 100 раз",         "mora": 200,  "xp": 200,  "type": "coinflip",       "threshold": 100},
    {"key": "coin_500",    "title": "Король Казино",    "emoji": "♠️",  "description": "Сыграть в монетку 500 раз",         "mora": 800,  "xp": 500,  "type": "coinflip",       "threshold": 500},
    # ─── Репутация ────────────────────────────────────────────────────
    {"key": "rep_10",      "title": "Добросердечный",   "emoji": "💚",  "description": "Дать репутацию 10 игрокам",          "mora": 50,   "xp": 50,   "type": "rep_given",      "threshold": 10},
    {"key": "rep_50",      "title": "Меценат",          "emoji": "💛",  "description": "Дать репутацию 50 игрокам",          "mora": 150,  "xp": 150,  "type": "rep_given",      "threshold": 50},
    {"key": "rep_100",     "title": "Народный Герой",   "emoji": "🫂",  "description": "Дать репутацию 100 игрокам",         "mora": 400,  "xp": 300,  "type": "rep_given",      "threshold": 100},
    # ─── Отношения / питомец ──────────────────────────────────────────
    {"key": "married",     "title": "Влюблённый",       "emoji": "💍",  "description": "Вступить в брак",                   "mora": 100,  "xp": 100,  "type": "married",        "threshold": 1},
    {"key": "has_pet",     "title": "Хозяин Питомца",   "emoji": "🐾",  "description": "Завести питомца",                   "mora": 100,  "xp": 100,  "type": "has_pet",        "threshold": 1},
    # ─── Экспедиции ────────────────────────────────────────────────────
    {"key": "exped_5",     "title": "Первопроходец",    "emoji": "🗺",  "description": "Отправить 5 экспедиций",             "mora": 50,   "xp": 50,   "type": "expeditions",    "threshold": 5},
    {"key": "exped_20",    "title": "Следопыт",         "emoji": "🧭",  "description": "Отправить 20 экспедиций",            "mora": 150,  "xp": 150,  "type": "expeditions",    "threshold": 20},
    {"key": "exped_50",    "title": "Исследователь Мира","emoji": "🌐", "description": "Отправить 50 экспедиций",            "mora": 500,  "xp": 400,  "type": "expeditions",    "threshold": 50},
    {"key": "exped_100",   "title": "Вечный Странник",  "emoji": "🚀",  "description": "Отправить 100 экспедиций",           "mora": 1500, "xp": 1000, "type": "expeditions",    "threshold": 100},
    # ─── Богатство ────────────────────────────────────────────────────
    {"key": "mora_1k",     "title": "Накопитель",       "emoji": "💰",  "description": "Накопить 1 000 моры",                "mora": 50,   "xp": 50,   "type": "mora_balance",   "threshold": 1000},
    {"key": "mora_5k",     "title": "Богатей",          "emoji": "💎",  "description": "Накопить 5 000 моры",                "mora": 100,  "xp": 100,  "type": "mora_balance",   "threshold": 5000},
    {"key": "mora_10k",    "title": "Магнат",           "emoji": "🏦",  "description": "Накопить 10 000 моры",               "mora": 200,  "xp": 200,  "type": "mora_balance",   "threshold": 10000},
    {"key": "mora_50k",    "title": "Олигарх",          "emoji": "🤑",  "description": "Накопить 50 000 моры",               "mora": 1000, "xp": 500,  "type": "mora_balance",   "threshold": 50000},
    {"key": "mora_100k",   "title": "Казначей Мира",    "emoji": "👸",  "description": "Накопить 100 000 моры",              "mora": 3000, "xp": 1500, "type": "mora_balance",   "threshold": 100000},
    # ─── Торговля / аукцион ───────────────────────────────────────────
    {"key": "first_sell",  "title": "Торговец",         "emoji": "🏪",  "description": "Выставить первый лот на аукцион",    "mora": 50,   "xp": 50,   "type": "auction_sell",   "threshold": 1},
    {"key": "first_win",   "title": "Победитель торгов","emoji": "🔨",  "description": "Выиграть аукцион",                   "mora": 100,  "xp": 100,  "type": "auction_win",    "threshold": 1},
    {"key": "sell_10",     "title": "Барыга",           "emoji": "📦",  "description": "Продать 10 лотов на аукционе",       "mora": 300,  "xp": 200,  "type": "auction_sell",   "threshold": 10},
    {"key": "win_10",      "title": "Коллекционер",     "emoji": "🎁",  "description": "Выиграть 10 аукционов",              "mora": 400,  "xp": 300,  "type": "auction_win",    "threshold": 10},
    # ─── Казино: рулетка ──────────────────────────────────────────────
    {"key": "roulette_10", "title": "Рискующий",        "emoji": "🎡",  "description": "Сыграть 10 раз в рулетку",           "mora": 50,   "xp": 50,   "type": "roulette",       "threshold": 10},
    {"key": "roulette_50", "title": "Крупье",           "emoji": "🎰",  "description": "Сыграть 50 раз в рулетку",           "mora": 200,  "xp": 200,  "type": "roulette",       "threshold": 50},
    # ─── Шпионаж ──────────────────────────────────────────────────────
    {"key": "spy_1",       "title": "Первая Разведка",  "emoji": "🕵️", "description": "Провести первую шпионскую миссию",   "mora": 50,   "xp": 50,   "type": "spy_missions",   "threshold": 1},
    {"key": "spy_10",      "title": "Агент 007",        "emoji": "🔍",  "description": "Провести 10 шпионских миссий",       "mora": 200,  "xp": 200,  "type": "spy_missions",   "threshold": 10},
    {"key": "spy_25",      "title": "Мастер Теней",     "emoji": "🦇",  "description": "Провести 25 шпионских миссий",       "mora": 500,  "xp": 400,  "type": "spy_missions",   "threshold": 25},
    # ─── Банковские вклады ────────────────────────────────────────────
    {"key": "deposit_1",   "title": "Вкладчик",         "emoji": "🏧",  "description": "Открыть первый банковский вклад",    "mora": 30,   "xp": 30,   "type": "deposits",       "threshold": 1},
    {"key": "deposit_10",  "title": "Инвестор",         "emoji": "📊",  "description": "Открыть 10 банковских вкладов",      "mora": 250,  "xp": 200,  "type": "deposits",       "threshold": 10},
    # ─── Облигации / акции ────────────────────────────────────────────
    {"key": "bonds_1",     "title": "Брокер",           "emoji": "📈",  "description": "Совершить первую покупку облигаций", "mora": 50,   "xp": 50,   "type": "bond_trades",    "threshold": 1},
    {"key": "bonds_20",    "title": "Волк с Уолл-Стрит","emoji": "🐺",  "description": "Совершить 20 сделок с облигациями",  "mora": 500,  "xp": 400,  "type": "bond_trades",    "threshold": 20},
    # ─── Переводы ─────────────────────────────────────────────────────
    {"key": "transfer_1",  "title": "Щедрый",           "emoji": "💸",  "description": "Перевести мору другому игроку",      "mora": 20,   "xp": 20,   "type": "transfers",      "threshold": 1},
    {"key": "transfer_25", "title": "Филантроп",        "emoji": "🤝",  "description": "Совершить 25 переводов моры",        "mora": 300,  "xp": 250,  "type": "transfers",      "threshold": 25},
    # ─── Сундуки ──────────────────────────────────────────────────────
    {"key": "chest_5",     "title": "Охотник за Сундуками","emoji":"🧳","description": "Открыть 5 сундуков",                "mora": 50,   "xp": 50,   "type": "chests",         "threshold": 5},
    {"key": "chest_25",    "title": "Кладоискатель",    "emoji": "🏴‍☠️","description": "Открыть 25 сундуков",               "mora": 200,  "xp": 200,  "type": "chests",         "threshold": 25},
    {"key": "chest_100",   "title": "Мастер Клада",     "emoji": "💎",  "description": "Открыть 100 сундуков",               "mora": 800,  "xp": 600,  "type": "chests",         "threshold": 100},
    # ─── Общий total_earned ───────────────────────────────────────────
    {"key": "earned_10k",  "title": "Трудяга",          "emoji": "⛏",  "description": "Заработать 10 000 моры за всё время", "mora": 100,  "xp": 100,  "type": "total_earned",   "threshold": 10000},
    {"key": "earned_50k",  "title": "Золотая Жила",     "emoji": "⚗️",  "description": "Заработать 50 000 моры за всё время", "mora": 500,  "xp": 400,  "type": "total_earned",   "threshold": 50000},
    {"key": "earned_250k", "title": "Легенда Экономики","emoji": "🏛",  "description": "Заработать 250 000 моры за всё время","mora": 3000, "xp": 2000, "type": "total_earned",   "threshold": 250000},
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

# Allowed counter columns (whitelist for safe f-string usage)
_COUNTER_COLS = frozenset({
    'expeditions_sent', 'chests_opened', 'casino_wins',
    'roulette_losses', 'total_gacha_rolls', 'total_coinflip',
    'rep_given_count', 'level', 'message_count',
})


async def _get_counter(db, user_id: int, chat_id: int, col: str) -> int:
    """Получить значение счётчика из user_mora."""
    if col not in _COUNTER_COLS:
        return 0
    row = await db.fetchone(
        f"SELECT {col} FROM user_mora WHERE user_id=? AND chat_id=?",
        (user_id, chat_id)
    )
    return int(row[col] or 0) if row else 0


async def _award(db, user_id: int, chat_id: int, ach: dict) -> bool:
    """Выдать достижение. Возвращает True если это новое достижение."""
    try:
        result = await db.execute(
            """INSERT INTO user_badges (user_id, chat_id, badge_key, obtained_at)
               VALUES (?, ?, ?, NOW()) ON CONFLICT DO NOTHING""",
            (user_id, chat_id, ach["key"])
        )
        if result.rowcount == 0:
            return False
    except Exception:
        return False

    # Применяем награду
    try:
        if ach["mora"] > 0:
            await db.execute(
                "UPDATE user_mora SET mora = mora + ? WHERE user_id=? AND chat_id=?",
                (ach["mora"], user_id, chat_id)
            )
        if ach.get("xp", 0) > 0:
            await db.execute(
                "UPDATE user_mora SET xp = xp + ? WHERE user_id=? AND chat_id=?",
                (ach["xp"], user_id, chat_id)
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
                (user_id, chat_id)
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
                (user_id, chat_id)
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
