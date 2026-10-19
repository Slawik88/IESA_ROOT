"""Shared local-chat rank and permission registry; no adapters or I/O."""
from dataclasses import dataclass

RANKS: tuple[tuple[str, str], ...] = (
    ("👤", "Участник"),
    ("✨", "Активист"),
    ("🧭", "Наставник"),
    ("🔰", "Младший модератор"),
    ("🛡", "Модератор"),
    ("⚔️", "Старший модератор"),
    ("👮", "Администратор"),
    ("🏛", "Управляющий"),
    ("🤝", "Совладелец"),
    ("👑", "Владелец"),
)
OWNER = 9
DEV_LEVEL = 100

def rank_name(rank: int) -> str:
    if rank >= DEV_LEVEL:
        return "🛠 Разработчик бота"
    icon, name = RANKS[max(0, min(rank, OWNER))]
    return f"{icon} {name}"


def find_rank(text: str) -> int | None:
    """«5», «модератор», «мл модератор», «ст. модератор» -> номер ранга."""
    t = text.strip().lower().replace("ё", "е").replace(".", " ")
    t = " ".join(t.split())
    if t.isdecimal():
        n = int(t)
        return n if 0 <= n <= OWNER else None
    t = t.replace("мл ", "младший ").replace("ст ", "старший ")
    for i, (_, name) in enumerate(RANKS):
        if name.lower() == t:
            return i
    return None


@dataclass(frozen=True)
class Action:
    key: str
    label: str
    default: int


# Всё, что в чате можно ограничить рангом. Владелец меняет пороги командой «бот права».
ACTIONS: tuple[Action, ...] = (
    Action("lists", "Смотреть списки санкций", 3),
    Action("warn", "Выдавать варны", 3),
    Action("unwarn", "Снимать варны", 4),
    Action("warn_limit", "Менять лимит варнов", 6),
    Action("mute", "Мут", 4),
    Action("unmute", "Снимать мут", 4),
    Action("kick", "Кик", 5),
    Action("ban", "Бан", 6),
    Action("unban", "Снимать бан", 6),
    Action("shield", "Защита от чистки", 5),
    Action("immune", "Иммунитет", 7),
    Action("close_chat", "Закрывать и открывать чат", 6),
    Action("write_closed", "Писать в закрытый чат", 4),
    Action("purge", "Проводить чистку", 7),
    Action("purge_write", "Писать во время чистки", 4),
    Action("set_rank", "Выдавать ранги", 7),
    Action("admin_chat", "Привязывать админ-чат", 8),
    Action("settings", "Настройки чата", 8),
    Action("rights", "Менять права рангов", OWNER),
    Action("pinged", "Получать пинги в админ-сообщениях", 4),
)
ACTION_BY_KEY = {a.key: a for a in ACTIONS}

