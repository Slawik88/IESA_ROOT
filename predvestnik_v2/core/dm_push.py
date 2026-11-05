"""Уведомления в личку с ботом: категории, лимиты и чистые правила (без базы и Telegram).

Как добавить новое уведомление:
1. Категория уже есть в CATEGORIES? Тогда пиши только сборщик события в services/dm_push_events.py.
   Новая категория: строка в CATEGORIES (live=True) и тема лички в TOPICS.
2. Сборщик ставит событие в очередь через services.dm_push.enqueue: у каждого события свой dedup_key
   (одно и то же событие не отправится дважды), текст по docs/PLAYER_COPY.md, кнопка — по желанию.
3. Согласие, лимит, тихие часы, дайджест и затухание делает services/dm_push.py: новому событию они достаются сами.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


@dataclass(frozen=True)
class Category:
    key: str
    label: str          # как называется в настройках
    hint: str           # одна строка под названием: когда придёт сообщение
    topic: str          # тема лички, куда уйдёт сообщение (ключ из TOPICS)
    live: bool = True   # False — зарезервирована: в настройках не показывается, событий пока нет


CATEGORIES: tuple[Category, ...] = (
    Category("pets", "🐾 Питомцы", "Напишу, когда питомец вернётся и добыча ждёт тебя.", "pets"),
    Category("quests", "📋 Задания", "Напишу, когда начнутся новые задания дня.", "quests"),
    Category("chests", "🎁 Сундуки", "Напишу, когда сундук будет готов.", "quests", live=False),
    Category("pass", "🏆 Пропуск", "Напишу, когда в Пропуске есть награда, которую можно забрать.", "quests"),
    Category("market", "📈 Биржа", "Напишу, когда твой ордер исполнен.", "market"),
    Category("season", "🏁 Сезон", "Напишу, когда сезон скоро закончится.", "news"),
    Category("events", "🎉 События", "Напишу о событиях и акциях.", "news", live=False),
    Category("vip_expiry", "⏳ VIP", "Напишу про поручение VIP и за 3 дня до конца срока.", "news"),
    Category("social", "💬 Люди", "Напишу о том, что случилось с тобой среди игроков.", "news", live=False),
)
BY_KEY: dict[str, Category] = {c.key: c for c in CATEGORIES}
LIVE_KEYS: tuple[str, ...] = tuple(c.key for c in CATEGORIES if c.live)

# Темы лички (Bot API 9.3+): куда раскладываются сообщения, если у игрока включены темы в чате с ботом.
TOPICS: dict[str, tuple[str, str]] = {   # ключ → (название темы, эмодзи-подпись)
    "quests": ("Задания", "📋"),
    "pets": ("Питомцы", "🐾"),
    "market": ("Биржа", "📈"),
    "news": ("Новости", "📰"),
}

# Лимиты. Всё, что не помещается, склеивается в один дайджест или ждёт следующего окна.
DAILY_CAP = 3                    # сообщений игроку за скользящие сутки (дайджест считается за одно)
EVENT_TTL = timedelta(hours=36)  # событие, которое не получилось доставить за это время, уже не нужно
UNANSWERED_LIMIT = 6             # столько сообщений подряд без отклика — и пауза до первого ответа игрока
DIGEST_MAX_LINES = 8             # строк в одном дайджесте; остальное уходит в хвост «и ещё N»
QUIET_START_HOUR = 22            # тихие часы по местному времени игрока: с 22:00 до 09:00
QUIET_END_HOUR = 9
DEFAULT_TZ_OFFSET = 3            # по умолчанию МСК; игрок меняет командой «бот уведомления пояс +5»
MIN_TZ, MAX_TZ = -12, 14
TOPIC_RETRY = timedelta(days=7)  # после неудачи с темой лички следующая попытка не раньше
SEND_BATCH = 200                 # игроков за один проход доставки


def local_hour(now: datetime, tz_offset: int) -> int:
    return (now.astimezone(timezone.utc) + timedelta(hours=int(tz_offset))).hour


def in_quiet_hours(now: datetime, tz_offset: int, quiet_enabled: bool = True) -> bool:
    """Тихие часы: окно через полночь (22:00–09:00 по умолчанию)."""
    if not quiet_enabled:
        return False
    hour = local_hour(now, tz_offset)
    return hour >= QUIET_START_HOUR or hour < QUIET_END_HOUR


def next_quiet_end(now: datetime, tz_offset: int) -> datetime:
    """Ближайшее 09:00 по местному времени игрока (в UTC)."""
    local = now.astimezone(timezone.utc) + timedelta(hours=int(tz_offset))
    end = local.replace(hour=QUIET_END_HOUR, minute=0, second=0, microsecond=0)
    if end <= local:
        end += timedelta(days=1)
    return end - timedelta(hours=int(tz_offset))


def merge_digest(rows: list[dict]) -> str:
    """Несколько событий — одно сообщение. Порядок как в очереди; хвост сворачивается в «и ещё N»."""
    lines = []
    for row in rows[:DIGEST_MAX_LINES]:
        text = str(row["text"]).strip().split("\n")[0]
        lines.append(f"• {text}")
    rest = len(rows) - DIGEST_MAX_LINES
    if rest > 0:
        lines.append(f"…и ещё {rest}")
    return "📬 <b>Пока тебя не было</b>\n\n" + "\n".join(lines)
