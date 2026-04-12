"""
services/achievements.py — Сервисный слой системы достижений.

Независим от aiogram и Django. Работает напрямую с БД через asyncpg.
Единственный источник истины для всех ачивок.

Архитектура:
  - ACHIEVEMENTS — полный реестр всех достижений (ID, тип, порог, награда).
  - check_and_grant(user_id, chat_id, action_type, value) — проверить и выдать.
  - get_user_achievements(user_id, chat_id) — прогресс для мини-апп (только чтение).
  - get_leaderboard(chat_id) — топ по количеству достижений.
  - get_user_badge_keys(user_id, chat_id) — список ключей бейджей (для профиля).

Выдача атомарна: INSERT ON CONFLICT DO NOTHING → если вставка прошла — выплата.
Нет catch-up, нет бесконечных тиров, нет side-effects при чтении.
"""
from __future__ import annotations

import logging
from database.db import postgres_connect

_log = logging.getLogger(__name__)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Реестр достижений
#  Каждое: key, title, emoji, description, mora, xp, type, threshold
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ACHIEVEMENTS: list[dict] = [
    # ── Сообщения в чате ─────────────────────────────────────────────────────
    {"key": "chat_100",    "title": "Активист",             "emoji": "🗣",  "description": "Отправить 100 сообщений",        "mora": 30,   "xp": 50,   "type": "messages",       "threshold": 100},
    {"key": "chat_500",    "title": "Оратор",               "emoji": "📢",  "description": "Отправить 500 сообщений",        "mora": 60,   "xp": 100,  "type": "messages",       "threshold": 500},
    {"key": "chat_1000",   "title": "Болтун",               "emoji": "💬",  "description": "Отправить 1 000 сообщений",      "mora": 150,  "xp": 200,  "type": "messages",       "threshold": 1000},
    {"key": "chat_5000",   "title": "Трибун",               "emoji": "📣",  "description": "Отправить 5 000 сообщений",      "mora": 500,  "xp": 500,  "type": "messages",       "threshold": 5000},
    {"key": "chat_10000",  "title": "Легенда Чата",         "emoji": "🏆",  "description": "Отправить 10 000 сообщений",     "mora": 1000, "xp": 1000, "type": "messages",       "threshold": 10000},
    {"key": "chat_25000",  "title": "Неудержимый",          "emoji": "🌪",  "description": "Отправить 25 000 сообщений",     "mora": 2000, "xp": 2000, "type": "messages",       "threshold": 25000},
    {"key": "chat_50000",  "title": "Голос Эпохи",          "emoji": "👑",  "description": "Отправить 50 000 сообщений",     "mora": 5000, "xp": 5000, "type": "messages",       "threshold": 50000},
    {"key": "chat_100k",   "title": "Вечный Голос",         "emoji": "🌊",  "description": "Отправить 100 000 сообщений",    "mora": 10000,"xp": 8000, "type": "messages",       "threshold": 100000},
    {"key": "chat_250k",   "title": "Бессмертный Оратор",   "emoji": "🔱",  "description": "Отправить 250 000 сообщений",    "mora": 25000,"xp": 20000,"type": "messages",       "threshold": 250000},
    # ── Уровень ──────────────────────────────────────────────────────────────
    {"key": "level_5",     "title": "Первые шаги",          "emoji": "🌿",  "description": "Достичь 5 уровня",               "mora": 15,   "xp": 0,    "type": "level",          "threshold": 5},
    {"key": "level_10",    "title": "Новичок",              "emoji": "🌱",  "description": "Достичь 10 уровня",              "mora": 30,   "xp": 0,    "type": "level",          "threshold": 10},
    {"key": "level_25",    "title": "Опытный",              "emoji": "⭐",  "description": "Достичь 25 уровня",              "mora": 100,  "xp": 0,    "type": "level",          "threshold": 25},
    {"key": "level_50",    "title": "Ветеран",              "emoji": "💫",  "description": "Достичь 50 уровня",              "mora": 300,  "xp": 0,    "type": "level",          "threshold": 50},
    {"key": "level_100",   "title": "Легенда",              "emoji": "🏅",  "description": "Достичь 100 уровня",             "mora": 1000, "xp": 0,    "type": "level",          "threshold": 100},
    {"key": "level_200",   "title": "Бессмертный",          "emoji": "🌌",  "description": "Достичь 200 уровня",             "mora": 3000, "xp": 0,    "type": "level",          "threshold": 200},
    {"key": "level_300",   "title": "Архонт",               "emoji": "🏰",  "description": "Достичь 300 уровня",             "mora": 8000, "xp": 0,    "type": "level",          "threshold": 300},
    {"key": "level_500",   "title": "Вечный Предвестник",   "emoji": "👁️",  "description": "Достичь 500 уровня",             "mora": 20000,"xp": 0,    "type": "level",          "threshold": 500},
    # ── Гача ─────────────────────────────────────────────────────────────────
    {"key": "gacha_10",    "title": "Молящийся",            "emoji": "🙏",  "description": "Сделать 10 круток гачи",         "mora": 50,   "xp": 50,   "type": "gacha_rolls",    "threshold": 10},
    {"key": "gacha_50",    "title": "Охотник за удачей",    "emoji": "🎰",  "description": "Сделать 50 круток гачи",         "mora": 100,  "xp": 100,  "type": "gacha_rolls",    "threshold": 50},
    {"key": "gacha_100",   "title": "Одержимый",            "emoji": "😈",  "description": "Сделать 100 круток гачи",        "mora": 200,  "xp": 200,  "type": "gacha_rolls",    "threshold": 100},
    {"key": "gacha_500",   "title": "Завсегдатай Гачи",     "emoji": "🌀",  "description": "Сделать 500 круток гачи",        "mora": 500,  "xp": 500,  "type": "gacha_rolls",    "threshold": 500},
    {"key": "gacha_1000",  "title": "Избранный Гачи",       "emoji": "✨",  "description": "Сделать 1 000 круток гачи",      "mora": 1500, "xp": 1000, "type": "gacha_rolls",    "threshold": 1000},
    {"key": "gacha_2500",  "title": "Поглощённый Пустотой", "emoji": "🌌",  "description": "Сделать 2 500 круток гачи",      "mora": 5000, "xp": 3000, "type": "gacha_rolls",    "threshold": 2500},
    {"key": "gacha_5000",  "title": "Сам Пустота",          "emoji": "♾️",  "description": "Сделать 5 000 круток гачи",      "mora": 20000,"xp": 10000,"type": "gacha_rolls",    "threshold": 5000},
    # ── Урон по боссу ────────────────────────────────────────────────────────
    {"key": "boss_1k",     "title": "Воитель",              "emoji": "⚔️",  "description": "Нанести 1 000 урона боссам",     "mora": 50,   "xp": 50,   "type": "boss_damage",    "threshold": 1000},
    {"key": "boss_10k",    "title": "Истребитель",          "emoji": "🗡",  "description": "Нанести 10 000 урона боссам",    "mora": 150,  "xp": 150,  "type": "boss_damage",    "threshold": 10000},
    {"key": "boss_50k",    "title": "Герой Мира",           "emoji": "🦸",  "description": "Нанести 50 000 урона боссам",    "mora": 500,  "xp": 500,  "type": "boss_damage",    "threshold": 50000},
    {"key": "boss_200k",   "title": "Истребитель Богов",    "emoji": "⚡",  "description": "Нанести 200 000 урона боссам",   "mora": 2000, "xp": 1500, "type": "boss_damage",    "threshold": 200000},
    {"key": "boss_500k",   "title": "Титан",                "emoji": "🔱",  "description": "Нанести 500 000 урона боссам",   "mora": 5000, "xp": 3000, "type": "boss_damage",    "threshold": 500000},
    {"key": "boss_1m",     "title": "Разрушитель Миров",    "emoji": "💥",  "description": "Нанести 1 000 000 урона боссам", "mora": 8000, "xp": 5000, "type": "boss_damage",    "threshold": 1000000},
    {"key": "boss_3m",     "title": "Первичная Сила",       "emoji": "🌀",  "description": "Нанести 3 000 000 урона боссам", "mora": 20000,"xp": 12000,"type": "boss_damage",    "threshold": 3000000},
    # ── Стрик чекина ─────────────────────────────────────────────────────────
    {"key": "streak_7",    "title": "Пунктуальный",         "emoji": "📅",  "description": "Чекин 7 дней подряд",            "mora": 50,   "xp": 50,   "type": "checkin_streak", "threshold": 7},
    {"key": "streak_20",   "title": "Дисциплинированный",   "emoji": "🎯",  "description": "Чекин 20 дней подряд",           "mora": 200,  "xp": 200,  "type": "checkin_streak", "threshold": 20},
    {"key": "streak_50",   "title": "Постоянный",           "emoji": "🔥",  "description": "Чекин 50 дней подряд",           "mora": 500,  "xp": 500,  "type": "checkin_streak", "threshold": 50},
    {"key": "streak_100",  "title": "Легенда Дисциплины",   "emoji": "💎",  "description": "Чекин 100 дней подряд",          "mora": 2000, "xp": 1500, "type": "checkin_streak", "threshold": 100},
    {"key": "streak_200",  "title": "Несгибаемый",          "emoji": "🔩",  "description": "Чекин 200 дней подряд",          "mora": 5000, "xp": 3000, "type": "checkin_streak", "threshold": 200},
    {"key": "streak_365",  "title": "Хранитель Года",       "emoji": "🎖️",  "description": "Чекин 365 дней подряд",          "mora": 20000,"xp": 10000,"type": "checkin_streak", "threshold": 365},
    # ── Монетка ──────────────────────────────────────────────────────────────
    {"key": "coin_10",     "title": "Пробующий",            "emoji": "🪙",  "description": "Сыграть в монетку 10 раз",       "mora": 30,   "xp": 30,   "type": "coinflip",       "threshold": 10},
    {"key": "coin_50",     "title": "Азартный",             "emoji": "🎲",  "description": "Сыграть в монетку 50 раз",       "mora": 100,  "xp": 100,  "type": "coinflip",       "threshold": 50},
    {"key": "coin_100",    "title": "Картёжник",            "emoji": "🃏",  "description": "Сыграть в монетку 100 раз",      "mora": 200,  "xp": 200,  "type": "coinflip",       "threshold": 100},
    {"key": "coin_500",    "title": "Король Казино",        "emoji": "♠️",  "description": "Сыграть в монетку 500 раз",      "mora": 800,  "xp": 500,  "type": "coinflip",       "threshold": 500},
    {"key": "coin_1000",   "title": "Хозяин Монеты",        "emoji": "🌕",  "description": "Сыграть в монетку 1 000 раз",    "mora": 2000, "xp": 1200, "type": "coinflip",       "threshold": 1000},
    {"key": "coin_2500",   "title": "Вечный Игрок",         "emoji": "⏳",  "description": "Сыграть в монетку 2 500 раз",    "mora": 8000, "xp": 4000, "type": "coinflip",       "threshold": 2500},
    # ── Рулетка ──────────────────────────────────────────────────────────────
    {"key": "roulette_10", "title": "Рискующий",            "emoji": "🎡",  "description": "Сыграть 10 раз в рулетку",       "mora": 50,   "xp": 50,   "type": "roulette",       "threshold": 10},
    {"key": "roulette_50", "title": "Крупье",               "emoji": "🎰",  "description": "Сыграть 50 раз в рулетку",       "mora": 200,  "xp": 200,  "type": "roulette",       "threshold": 50},
    {"key": "roulette_100","title": "Игрок",                "emoji": "🎲",  "description": "Сыграть 100 раз в рулетку",      "mora": 500,  "xp": 400,  "type": "roulette",       "threshold": 100},
    {"key": "roulette_200","title": "Мастер рулетки",       "emoji": "♠️",  "description": "Сыграть 200 раз в рулетку",      "mora": 1200, "xp": 800,  "type": "roulette",       "threshold": 200},
    {"key": "roulette_500","title": "Рулеточный Бог",       "emoji": "👑",  "description": "Сыграть 500 раз в рулетку",      "mora": 3000, "xp": 2000, "type": "roulette",       "threshold": 500},
    {"key": "roulette_1000","title":"Мастер Удачи",         "emoji": "🎰",  "description": "Сыграть 1 000 раз в рулетку",    "mora": 5000, "xp": 3000, "type": "roulette",       "threshold": 1000},
    # ── Репутация ────────────────────────────────────────────────────────────
    {"key": "rep_10",      "title": "Добросердечный",       "emoji": "💚",  "description": "Дать репутацию 10 игрокам",       "mora": 50,   "xp": 50,   "type": "rep_given",      "threshold": 10},
    {"key": "rep_50",      "title": "Меценат",              "emoji": "💛",  "description": "Дать репутацию 50 игрокам",       "mora": 150,  "xp": 150,  "type": "rep_given",      "threshold": 50},
    {"key": "rep_100",     "title": "Народный Герой",       "emoji": "🫂",  "description": "Дать репутацию 100 игрокам",      "mora": 400,  "xp": 300,  "type": "rep_given",      "threshold": 100},
    {"key": "rep_250",     "title": "Столп Общества",       "emoji": "🏛️",  "description": "Дать репутацию 250 игрокам",      "mora": 1000, "xp": 700,  "type": "rep_given",      "threshold": 250},
    {"key": "rep_500",     "title": "Живой Орден",          "emoji": "⚜️",  "description": "Дать репутацию 500 игрокам",      "mora": 4000, "xp": 2500, "type": "rep_given",      "threshold": 500},
    # ── Отношения / питомец ──────────────────────────────────────────────────
    {"key": "married",     "title": "Влюблённый",           "emoji": "💍",  "description": "Вступить в брак",                "mora": 100,  "xp": 100,  "type": "married",        "threshold": 1},
    {"key": "has_pet",     "title": "Хозяин Питомца",       "emoji": "🐾",  "description": "Завести питомца",                "mora": 100,  "xp": 100,  "type": "has_pet",        "threshold": 1},
    # ── Экспедиции ───────────────────────────────────────────────────────────
    {"key": "exped_5",     "title": "Первопроходец",        "emoji": "🗺",  "description": "Отправить 5 экспедиций",          "mora": 50,   "xp": 50,   "type": "expeditions",    "threshold": 5},
    {"key": "exped_20",    "title": "Следопыт",             "emoji": "🧭",  "description": "Отправить 20 экспедиций",         "mora": 150,  "xp": 150,  "type": "expeditions",    "threshold": 20},
    {"key": "exped_50",    "title": "Исследователь Мира",   "emoji": "🌐",  "description": "Отправить 50 экспедиций",         "mora": 500,  "xp": 400,  "type": "expeditions",    "threshold": 50},
    {"key": "exped_100",   "title": "Странник",             "emoji": "🚀",  "description": "Отправить 100 экспедиций",        "mora": 1500, "xp": 1000, "type": "expeditions",    "threshold": 100},
    {"key": "exped_200",   "title": "Мастер Странствий",    "emoji": "🌍",  "description": "Отправить 200 экспедиций",        "mora": 3000, "xp": 2000, "type": "expeditions",    "threshold": 200},
    {"key": "exped_500",   "title": "Властелин Путей",      "emoji": "🗺️",  "description": "Отправить 500 экспедиций",        "mora": 10000,"xp": 6000, "type": "expeditions",    "threshold": 500},
    # ── Торговля / аукцион ───────────────────────────────────────────────────
    {"key": "sell_1",      "title": "Торговец",             "emoji": "🏪",  "description": "Выставить первый лот на аукцион", "mora": 50,   "xp": 50,   "type": "auction_sell",   "threshold": 1},
    {"key": "sell_10",     "title": "Барыга",               "emoji": "📦",  "description": "Продать 10 лотов на аукционе",    "mora": 300,  "xp": 200,  "type": "auction_sell",   "threshold": 10},
    {"key": "sell_50",     "title": "Оптовик",              "emoji": "📦",  "description": "Продать 50 лотов на аукционе",    "mora": 1000, "xp": 600,  "type": "auction_sell",   "threshold": 50},
    {"key": "sell_100",    "title": "Торговый Барон",       "emoji": "💼",  "description": "Продать 100 лотов на аукционе",   "mora": 3000, "xp": 1800, "type": "auction_sell",   "threshold": 100},
    {"key": "win_1",       "title": "Победитель торгов",    "emoji": "🔨",  "description": "Выиграть аукцион",                "mora": 100,  "xp": 100,  "type": "auction_win",    "threshold": 1},
    {"key": "win_10",      "title": "Коллекционер",         "emoji": "🎁",  "description": "Выиграть 10 аукционов",           "mora": 400,  "xp": 300,  "type": "auction_win",    "threshold": 10},
    {"key": "win_25",      "title": "Мастер Торгов",        "emoji": "🔨",  "description": "Выиграть 25 аукционов",           "mora": 800,  "xp": 500,  "type": "auction_win",    "threshold": 25},
    {"key": "win_50",      "title": "Легенда Аукциона",     "emoji": "🏆",  "description": "Выиграть 50 аукционов",           "mora": 2500, "xp": 1500, "type": "auction_win",    "threshold": 50},
    # ── Шпионаж ──────────────────────────────────────────────────────────────
    {"key": "spy_1",       "title": "Первая Разведка",      "emoji": "🕵️", "description": "Провести первую шпионскую миссию", "mora": 50,   "xp": 50,   "type": "spy_missions",   "threshold": 1},
    {"key": "spy_10",      "title": "Агент 007",            "emoji": "🔍",  "description": "Провести 10 шпионских миссий",    "mora": 200,  "xp": 200,  "type": "spy_missions",   "threshold": 10},
    {"key": "spy_25",      "title": "Мастер Теней",         "emoji": "🦇",  "description": "Провести 25 шпионских миссий",    "mora": 500,  "xp": 400,  "type": "spy_missions",   "threshold": 25},
    {"key": "spy_50",      "title": "Призрак",              "emoji": "👻",  "description": "Провести 50 шпионских миссий",    "mora": 1000, "xp": 800,  "type": "spy_missions",   "threshold": 50},
    {"key": "spy_100",     "title": "Архитектор Теней",     "emoji": "🌑",  "description": "Провести 100 шпионских миссий",   "mora": 3000, "xp": 2000, "type": "spy_missions",   "threshold": 100},
    # ── Банковские вклады ────────────────────────────────────────────────────
    {"key": "deposit_1",   "title": "Вкладчик",             "emoji": "🏧",  "description": "Открыть первый банковский вклад", "mora": 30,   "xp": 30,   "type": "deposits",       "threshold": 1},
    {"key": "deposit_10",  "title": "Инвестор",             "emoji": "📊",  "description": "Открыть 10 банковских вкладов",   "mora": 250,  "xp": 200,  "type": "deposits",       "threshold": 10},
    {"key": "deposit_25",  "title": "Опытный Вкладчик",     "emoji": "🏧",  "description": "Открыть 25 банковских вкладов",   "mora": 600,  "xp": 400,  "type": "deposits",       "threshold": 25},
    {"key": "deposit_50",  "title": "Банкир",               "emoji": "🏦",  "description": "Открыть 50 банковских вкладов",   "mora": 2000, "xp": 1200, "type": "deposits",       "threshold": 50},
    # ── Облигации ────────────────────────────────────────────────────────────
    {"key": "bonds_1",     "title": "Брокер",               "emoji": "📈",  "description": "Первая сделка с облигациями",      "mora": 50,   "xp": 50,   "type": "bond_trades",    "threshold": 1},
    {"key": "bonds_20",    "title": "Волк с Уолл-Стрит",    "emoji": "🐺",  "description": "20 сделок с облигациями",          "mora": 500,  "xp": 400,  "type": "bond_trades",    "threshold": 20},
    {"key": "bonds_50",    "title": "Финансист",            "emoji": "💼",  "description": "50 сделок с облигациями",          "mora": 1000, "xp": 800,  "type": "bond_trades",    "threshold": 50},
    {"key": "bonds_100",   "title": "Инвестиционный Гуру",  "emoji": "📊",  "description": "100 сделок с облигациями",         "mora": 2500, "xp": 1500, "type": "bond_trades",    "threshold": 100},
    {"key": "bonds_250",   "title": "Магнат Биржи",         "emoji": "🏦",  "description": "250 сделок с облигациями",         "mora": 6000, "xp": 3000, "type": "bond_trades",    "threshold": 250},
    {"key": "bonds_500",   "title": "Волшебник Биржи",      "emoji": "🧙",  "description": "500 сделок с облигациями",         "mora": 12000,"xp": 7000, "type": "bond_trades",    "threshold": 500},
    # ── Переводы ─────────────────────────────────────────────────────────────
    {"key": "transfer_1",  "title": "Щедрый",               "emoji": "💸",  "description": "Перевести мору другому игроку",   "mora": 20,   "xp": 20,   "type": "transfers",      "threshold": 1},
    {"key": "transfer_25", "title": "Филантроп",             "emoji": "🤝",  "description": "Совершить 25 переводов моры",     "mora": 300,  "xp": 250,  "type": "transfers",      "threshold": 25},
    {"key": "transfer_100","title": "Щедрый Архонт",         "emoji": "✨",  "description": "Совершить 100 переводов моры",    "mora": 1000, "xp": 700,  "type": "transfers",      "threshold": 100},
    {"key": "transfer_500","title": "Поток Моры",            "emoji": "🌊",  "description": "Совершить 500 переводов моры",    "mora": 6000, "xp": 4000, "type": "transfers",      "threshold": 500},
    # ── Сундуки ──────────────────────────────────────────────────────────────
    {"key": "chest_5",     "title": "Охотник за Сундуками",  "emoji": "🧳",  "description": "Открыть 5 сундуков",              "mora": 50,   "xp": 50,   "type": "chests",         "threshold": 5},
    {"key": "chest_25",    "title": "Кладоискатель",         "emoji": "🏴‍☠️","description": "Открыть 25 сундуков",             "mora": 200,  "xp": 200,  "type": "chests",         "threshold": 25},
    {"key": "chest_100",   "title": "Мастер Клада",          "emoji": "💎",  "description": "Открыть 100 сундуков",            "mora": 800,  "xp": 600,  "type": "chests",         "threshold": 100},
    {"key": "chest_500",   "title": "Охотник за Реликвиями", "emoji": "🗝️",  "description": "Открыть 500 сундуков",            "mora": 3000, "xp": 2000, "type": "chests",         "threshold": 500},
]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Индексы и метаданные (строятся при импорте модуля)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# {key → dict} — используется для отображения бейджей в профиле и поиска по ключу
ACH_BY_KEY: dict[str, dict] = {a["key"]: a for a in ACHIEVEMENTS}

# {type → [dict, ...]} — отсортировано по threshold (для check_and_grant)
ACH_BY_TYPE: dict[str, list[dict]] = {}
for _a in ACHIEVEMENTS:
    ACH_BY_TYPE.setdefault(_a["type"], []).append(_a)
for _lst in ACH_BY_TYPE.values():
    _lst.sort(key=lambda x: x["threshold"])

# Типы с булевым значением (есть/нет), без прогресс-бара
BOOL_TYPES: frozenset[str] = frozenset({"married", "has_pet"})

# Метаданные категорий для UI мини-аппа
TYPE_META: dict[str, dict] = {
    "messages":       {"label": "Сообщения",          "emoji": "🗣",  "order": 1},
    "level":          {"label": "Уровень",             "emoji": "⭐",  "order": 2},
    "gacha_rolls":    {"label": "Крутки гачи",         "emoji": "🎰",  "order": 3},
    "coinflip":       {"label": "Монетка",             "emoji": "🪙",  "order": 4},
    "roulette":       {"label": "Рулетка",             "emoji": "🎡",  "order": 5},
    "boss_damage":    {"label": "Урон боссам",         "emoji": "⚔️",  "order": 6},
    "checkin_streak": {"label": "Стрик чекина",        "emoji": "📅",  "order": 7},
    "expeditions":    {"label": "Экспедиции",          "emoji": "🗺",  "order": 8},
    "chests":         {"label": "Сундуки",             "emoji": "🧳",  "order": 9},
    "rep_given":      {"label": "Репутация",           "emoji": "💚",  "order": 10},
    "married":        {"label": "Брак",                "emoji": "💍",  "order": 11},
    "has_pet":        {"label": "Питомец",             "emoji": "🐾",  "order": 12},
    "transfers":      {"label": "Переводы",            "emoji": "💸",  "order": 13},
    "deposits":       {"label": "Вклады",              "emoji": "🏧",  "order": 14},
    "bond_trades":    {"label": "Облигации",           "emoji": "📈",  "order": 15},
    "auction_sell":   {"label": "Продажи (аукцион)",   "emoji": "🏪",  "order": 16},
    "auction_win":    {"label": "Покупки (аукцион)",   "emoji": "🔨",  "order": 17},
    "spy_missions":   {"label": "Шпионаж",             "emoji": "🕵️",  "order": 18},
}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Внутренние хелперы
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def _try_insert_badge(user_id: int, chat_id: int, badge_key: str) -> bool:
    """Атомарно вставить бейдж.
    Возвращает True если бейдж только что создан (INSERT),
    False если уже существовал (ON CONFLICT DO NOTHING).
    """
    async with postgres_connect() as db:
        result = await db.execute(
            """INSERT INTO user_badges (user_id, chat_id, badge_key, obtained_at)
               VALUES ($1, $2, $3, NOW())
               ON CONFLICT (user_id, chat_id, badge_key) DO NOTHING""",
            user_id, chat_id, badge_key,
        )
        # asyncpg: result — строка вида "INSERT 0 1" или "INSERT 0 0"
        return result.endswith(" 1")


async def _pay_reward(user_id: int, chat_id: int, mora: int, xp: int) -> None:
    """Выплатить награду за достижение. Ошибки логируются, не пробрасываются."""
    if mora > 0:
        try:
            from database.db import add_mora as _add_mora
            # update_earned=False → награды за ачивки не раздувают total_earned
            await _add_mora(user_id, 0, mora, update_earned=False)
        except Exception as e:
            _log.warning("Выплата моры за ачивку не удалась uid=%s: %s", user_id, e)

    if xp > 0:
        try:
            from database.db import add_xp_in_chat as _add_xp
            await _add_xp(user_id, chat_id, xp)
        except Exception as e:
            _log.warning("Выплата XP за ачивку не удалась uid=%s: %s", user_id, e)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Публичный API — Выдача достижений
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def check_and_grant(
    user_id: int,
    chat_id: int,
    action_type: str,
    value: int | float,
) -> list[dict]:
    """Проверить и выдать достижения по типу действия.

    Аргументы:
        user_id:     Telegram ID пользователя
        chat_id:     ID чата
        action_type: тип действия (ключ из TYPE_META, например "messages")
        value:       текущее значение счётчика (сообщений, уровня и т.д.)

    Возвращает список только что выданных достижений (пустой, если ни одного).
    Идемпотентно: повторный вызов с тем же value безопасен (INSERT ON CONFLICT).
    Никогда не пробрасывает исключений наружу — безопасно для fire-and-forget.
    """
    candidates = ACH_BY_TYPE.get(action_type, [])
    if not candidates:
        return []

    newly_awarded: list[dict] = []
    for ach in candidates:
        if value < ach["threshold"]:
            break  # список отсортирован → дальше только выше
        try:
            is_new = await _try_insert_badge(user_id, chat_id, ach["key"])
            if not is_new:
                continue
            await _pay_reward(user_id, chat_id, ach["mora"], ach.get("xp", 0))
            newly_awarded.append(ach)
        except Exception as e:
            _log.warning("check_and_grant ошибка uid=%s key=%s: %s", user_id, ach["key"], e)

    return newly_awarded


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Публичный API — Чтение (только для Mini App / REST, БД не изменяется)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def _fetch_earned(db, user_id: int, chat_id: int) -> dict[str, str]:
    """Получить все выданные бейджи {badge_key: obtained_at} из user_badges."""
    rows = await db.fetch(
        "SELECT badge_key, obtained_at FROM user_badges WHERE user_id=$1 AND chat_id=$2",
        user_id, chat_id,
    )
    return {r["badge_key"]: str(r.get("obtained_at", "")) for r in rows}


async def _fetch_counters(db, user_id: int, chat_id: int) -> dict[str, int]:
    """Собрать все счётчики прогресса из разных таблиц.
    При ошибке в одной таблице — логируем и продолжаем с нулём.
    """
    c: dict[str, int] = {}

    # user_mora: гача, монетка, репутация, экспедиции, сундуки
    try:
        row = await db.fetchrow(
            "SELECT COALESCE(total_gacha_rolls,0) gr,"
            "       COALESCE(total_coinflip,0)    cf,"
            "       COALESCE(rep_given_count,0)   rg,"
            "       COALESCE(expeditions_sent,0)  ex,"
            "       COALESCE(chests_opened,0)     ch"
            " FROM user_mora WHERE user_id=$1 AND chat_id=$2",
            user_id, chat_id,
        )
        if row:
            c["gacha_rolls"] = int(row["gr"])
            c["coinflip"]    = int(row["cf"])
            c["rep_given"]   = int(row["rg"])
            c["expeditions"] = int(row["ex"])
            c["chests"]      = int(row["ch"])
    except Exception as e:
        _log.warning("_fetch_counters user_mora uid=%s: %s", user_id, e)

    # user_stats: сообщения, уровень
    try:
        row = await db.fetchrow(
            "SELECT COALESCE(message_count,0) mc, COALESCE(level,1) lv"
            " FROM user_stats WHERE user_id=$1 AND chat_id=$2",
            user_id, chat_id,
        )
        if row:
            c["messages"] = int(row["mc"])
            c["level"]    = int(row["lv"])
    except Exception as e:
        _log.warning("_fetch_counters user_stats uid=%s: %s", user_id, e)

    # boss_damage — суммарный урон за все бои
    try:
        row = await db.fetchrow(
            "SELECT COALESCE(SUM(damage),0) total"
            " FROM boss_damage_log WHERE user_id=$1 AND chat_id=$2",
            user_id, chat_id,
        )
        c["boss_damage"] = int(row["total"]) if row else 0
    except Exception as e:
        _log.warning("_fetch_counters boss_damage uid=%s: %s", user_id, e)

    # checkin streak
    try:
        row = await db.fetchrow(
            "SELECT COALESCE(streak,0) s FROM daily_checkin WHERE user_id=$1 AND chat_id=$2",
            user_id, chat_id,
        )
        c["checkin_streak"] = int(row["s"]) if row else 0
    except Exception as e:
        _log.warning("_fetch_counters checkin uid=%s: %s", user_id, e)

    # married (глобально)
    try:
        row = await db.fetchrow(
            "SELECT COUNT(*) c FROM marriages_global WHERE user_id=$1",
            user_id,
        )
        c["married"] = 1 if row and int(row["c"]) > 0 else 0
    except Exception as e:
        _log.warning("_fetch_counters married uid=%s: %s", user_id, e)

    # has_pet (глобально)
    try:
        row = await db.fetchrow(
            "SELECT COUNT(*) c FROM pets_global WHERE user_id=$1",
            user_id,
        )
        c["has_pet"] = 1 if row and int(row["c"]) > 0 else 0
    except Exception as e:
        _log.warning("_fetch_counters pets uid=%s: %s", user_id, e)

    # auction_sell
    try:
        row = await db.fetchrow(
            "SELECT COUNT(*) c FROM auctions WHERE seller_id=$1 AND chat_id=$2",
            user_id, chat_id,
        )
        c["auction_sell"] = int(row["c"]) if row else 0
    except Exception as e:
        _log.warning("_fetch_counters auction_sell uid=%s: %s", user_id, e)

    # auction_win
    try:
        row = await db.fetchrow(
            "SELECT COUNT(*) c FROM auctions"
            " WHERE highest_bidder_id=$1 AND chat_id=$2 AND status='sold'",
            user_id, chat_id,
        )
        c["auction_win"] = int(row["c"]) if row else 0
    except Exception as e:
        _log.warning("_fetch_counters auction_win uid=%s: %s", user_id, e)

    # roulette
    try:
        row = await db.fetchrow(
            "SELECT COUNT(*) c FROM wallet_ledger"
            " WHERE user_id=$1 AND chat_id=$2 AND source='roulette'",
            user_id, chat_id,
        )
        c["roulette"] = int(row["c"]) if row else 0
    except Exception as e:
        _log.warning("_fetch_counters roulette uid=%s: %s", user_id, e)

    # spy_missions
    try:
        row = await db.fetchrow(
            "SELECT COUNT(*) c FROM espionage_log WHERE spy_id=$1 AND chat_id=$2",
            user_id, chat_id,
        )
        c["spy_missions"] = int(row["c"]) if row else 0
    except Exception as e:
        _log.warning("_fetch_counters spy uid=%s: %s", user_id, e)

    # deposits
    try:
        row = await db.fetchrow(
            "SELECT COUNT(*) c FROM bank_deposits WHERE user_id=$1 AND chat_id=$2",
            user_id, chat_id,
        )
        c["deposits"] = int(row["c"]) if row else 0
    except Exception as e:
        _log.warning("_fetch_counters deposits uid=%s: %s", user_id, e)

    # bond_trades
    try:
        row = await db.fetchrow(
            "SELECT COUNT(*) c FROM user_bond_lots WHERE user_id=$1 AND chat_id=$2",
            user_id, chat_id,
        )
        c["bond_trades"] = int(row["c"]) if row else 0
    except Exception as e:
        _log.warning("_fetch_counters bonds uid=%s: %s", user_id, e)

    # transfers
    try:
        row = await db.fetchrow(
            "SELECT COUNT(*) c FROM wallet_ledger"
            " WHERE user_id=$1 AND chat_id=$2 AND source='transfer_out'",
            user_id, chat_id,
        )
        c["transfers"] = int(row["c"]) if row else 0
    except Exception as e:
        _log.warning("_fetch_counters transfers uid=%s: %s", user_id, e)

    return c


async def get_user_achievements(user_id: int, chat_id: int) -> dict:
    """Вернуть полный прогресс достижений пользователя.

    ТОЛЬКО ЧТЕНИЕ — не изменяет БД, не выдаёт награды.
    Формат ответа совместим с REST API для Mini App.
    """
    earned: dict[str, str] = {}
    counters: dict[str, int] = {}

    try:
        async with postgres_connect() as db:
            earned   = await _fetch_earned(db, user_id, chat_id)
            counters = await _fetch_counters(db, user_id, chat_id)
    except Exception as e:
        _log.warning("get_user_achievements DB ошибка uid=%s: %s", user_id, e)

    categories: list[dict] = []
    total_unlocked = 0
    total_defined  = 0

    for ach_type, tiers in ACH_BY_TYPE.items():
        meta          = TYPE_META.get(ach_type, {"label": ach_type, "emoji": "🏅", "order": 99})
        current_value = counters.get(ach_type, 0)
        is_bool       = ach_type in BOOL_TYPES

        ranks: list[dict] = []
        unlocked_count = 0
        next_rank_idx: int | None = None

        for i, ach in enumerate(tiers):
            unlocked = ach["key"] in earned
            if unlocked:
                unlocked_count += 1
            elif next_rank_idx is None:
                next_rank_idx = i
            ranks.append({
                "rank":        i + 1,
                "key":         ach["key"],
                "title":       ach["title"],
                "emoji":       ach["emoji"],
                "description": ach["description"],
                "threshold":   ach["threshold"],
                "mora":        ach["mora"],
                "xp":          ach.get("xp", 0),
                "unlocked":    unlocked,
                "obtained_at": earned.get(ach["key"]),
            })

        # Прогресс до следующего ранга
        if is_bool:
            progress_pct = 100 if current_value >= 1 else 0
        elif next_rank_idx is None:
            progress_pct = 100  # все разблокированы
        else:
            prev_t   = ranks[next_rank_idx - 1]["threshold"] if next_rank_idx > 0 else 0
            next_t   = ranks[next_rank_idx]["threshold"]
            rng      = next_t - prev_t
            progress_pct = min(100, max(0, int((current_value - prev_t) / rng * 100))) if rng > 0 else 100

        next_rank = ranks[next_rank_idx] if next_rank_idx is not None else None

        total_unlocked += unlocked_count
        total_defined  += len(tiers)

        categories.append({
            "type":           ach_type,
            "label":          meta["label"],
            "emoji":          meta["emoji"],
            "order":          meta["order"],
            "current_value":  current_value,
            "current_rank":   unlocked_count,
            "total_defined":  len(tiers),
            "next_threshold": next_rank["threshold"] if next_rank else None,
            "next_title":     next_rank["title"]     if next_rank else None,
            "progress_pct":   progress_pct,
            "is_bool":        is_bool,
            "ranks":          ranks,
        })

    categories.sort(key=lambda x: x["order"])
    return {
        "categories":     categories,
        "total_unlocked": total_unlocked,
        "total_defined":  total_defined,
    }


async def get_leaderboard(chat_id: int, limit: int = 20) -> list[dict]:
    """Топ пользователей по количеству достижений в чате."""
    try:
        async with postgres_connect() as db:
            rows = await db.fetch(
                """SELECT ub.user_id,
                          COUNT(ub.badge_key) AS badge_count,
                          u.full_name
                   FROM user_badges ub
                   LEFT JOIN users u ON u.user_id = ub.user_id
                   WHERE ub.chat_id = $1
                   GROUP BY ub.user_id, u.full_name
                   ORDER BY badge_count DESC
                   LIMIT $2""",
                chat_id, limit,
            )
        return [
            {
                "user_id":     r["user_id"],
                "full_name":   r["full_name"] or f"user_{r['user_id']}",
                "badge_count": int(r["badge_count"]),
            }
            for r in rows
        ]
    except Exception as e:
        _log.warning("get_leaderboard chat=%s: %s", chat_id, e)
        return []


async def get_user_badge_keys(user_id: int, chat_id: int) -> list[str]:
    """Вернуть список ключей бейджей пользователя (для отображения в профиле)."""
    try:
        async with postgres_connect() as db:
            rows = await db.fetch(
                "SELECT badge_key FROM user_badges WHERE user_id=$1 AND chat_id=$2"
                " ORDER BY obtained_at",
                user_id, chat_id,
            )
        return [r["badge_key"] for r in rows]
    except Exception as e:
        _log.warning("get_user_badge_keys uid=%s: %s", user_id, e)
        return []
