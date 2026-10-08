"""Каталог достижений чат-бота.

Каждое достижение — одна величина (сколько сообщений, дней, побед…) и лестница
порогов от 20 до 80 уровней. Пороги — «круглые» числа: 100, 120, 150, 200, 250…
Новое достижение = новая строка в ACHIEVEMENTS; источник величины — в achievements.py.
"""
from __future__ import annotations

from dataclasses import dataclass

# Мантиссы порогов внутри каждого десятка: частые (≈12 уровней на порядок) и редкие (7).
FINE = (1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 7, 8, 9)
NORMAL = (1, 1.5, 2, 3, 4, 5, 7)

MIN_LEVELS, MAX_LEVELS = 20, 80


def ladder(start: int, end: int, steps: tuple[float, ...] = FINE) -> tuple[int, ...]:
    """Круглые пороги от start до end включительно, без повторов."""
    out: set[int] = set()
    power = 1
    while power <= end:
        for m in steps:
            value = round(m * power)
            if start <= value <= end:
                out.add(value)
        power *= 10
    return tuple(sorted(out))


@dataclass(frozen=True)
class Achievement:
    id: str
    icon: str
    name: str
    group: str                  # когда пересчитывать: chat, warps, transfers, family, games
    measure: str                # что считаем, для карточки: «Сообщений во всех чатах»
    unit: tuple[str, str, str]  # 1 сообщение, 2 сообщения, 5 сообщений
    thresholds: tuple[int, ...]
    aliases: tuple[str, ...] = ()

    @property
    def max_level(self) -> int:
        return len(self.thresholds)


def plural(n: int, forms: tuple[str, str, str]) -> str:
    n = abs(int(n))
    if n % 10 == 1 and n % 100 != 11:
        return forms[0]
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return forms[1]
    return forms[2]


DAYS = ("день", "дня", "дней")
TIMES = ("раз", "раза", "раз")
GAMES = ("игра", "игры", "игр")
WINS = ("победа", "победы", "побед")

ACHIEVEMENTS: tuple[Achievement, ...] = (
    # ── Общение ──────────────────────────────────────────────────────────────
    Achievement("messages", "💬", "Болтун", "chat", "Сообщений во всех чатах",
                ("сообщение", "сообщения", "сообщений"), ladder(100, 1_000_000), ("сообщения", "болтун")),
    Achievement("active_days", "📅", "Завсегдатай", "chat", "Дней, когда вы писали в чат",
                DAYS, ladder(3, 3650), ("дни", "завсегдатай")),
    Achievement("best_day", "🏃", "Марафонец", "chat", "Больше всего сообщений за один день",
                ("сообщение", "сообщения", "сообщений"), ladder(50, 20_000), ("марафонец", "рекорд дня")),
    Achievement("chats", "🌐", "Душа компании", "chat", "Чатов, где вы писали",
                ("чат", "чата", "чатов"), ladder(2, 300), ("чаты", "душа компании")),
    Achievement("streak", "🔥", "Постоянство", "chat", "Лучший стрик: дней подряд с активностью",
                DAYS, ladder(3, 2000), ("стрик", "постоянство")),
    # ── Взаимодействия ───────────────────────────────────────────────────────
    Achievement("warps_sent", "🎭", "Заводила", "warps", "Варп-команд другим игрокам",
                TIMES, ladder(10, 200_000), ("варпы", "заводила")),
    Achievement("warps_received", "🫂", "Любимчик", "warps", "Варп-команд от других игроков",
                TIMES, ladder(10, 200_000), ("любимчик",)),
    Achievement("transfers", "🤝", "Щедрая душа", "transfers", "Переводов другим игрокам",
                ("перевод", "перевода", "переводов"), ladder(1, 20_000), ("переводы", "щедрая душа")),
    Achievement("mora_given", "🪙", "Меценат", "transfers", "Моры передано другим игрокам",
                ("мора", "моры", "моры"), ladder(1_000, 500_000_000, NORMAL), ("меценат",)),
    # ── Семья ────────────────────────────────────────────────────────────────
    Achievement("marriage_days", "💞", "Верность", "family", "Самый долгий брак",
                DAYS, ladder(7, 3650), ("брак", "верность")),
    # ── Игры ─────────────────────────────────────────────────────────────────
    Achievement("mafia_games", "🕵️", "Мафиози", "games", "Сыгранных партий Мафии",
                GAMES, ladder(1, 10_000), ("мафия", "мафиози")),
    Achievement("mafia_wins", "🌙", "Хозяин ночи", "games", "Побед в Мафии",
                WINS, ladder(1, 5_000), ("победы в мафии", "хозяин ночи")),
    Achievement("rhythm_runs", "🥁", "Чувство ритма", "games", "Завершённых забегов в Ритме",
                GAMES, ladder(1, 20_000), ("ритм", "чувство ритма")),
    Achievement("minesweeper_wins", "💣", "Сапёр", "games", "Побед в Сапёре",
                WINS, ladder(1, 20_000), ("сапер", "сапёр")),
    Achievement("quests", "📜", "Искатель", "games", "Выполненных квестов",
                ("квест", "квеста", "квестов"), ladder(1, 20_000), ("квесты", "искатель")),
)

BY_ID = {a.id: a for a in ACHIEVEMENTS}
GROUPS = tuple(dict.fromkeys(a.group for a in ACHIEVEMENTS))
