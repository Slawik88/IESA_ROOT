"""services/clans.py — бизнес-логика кланов (валидация + флоу + сообщения).

Единый источник правды для веб- и бот-адаптеров. Без импортов bot.*/FastAPI.*.
SQL — в infrastructure/repositories/clans.py.
"""
import re

from core.constants import (
    CLAN_CREATE_COST_MORA, CLAN_MAX_MEMBERS,
    CLAN_NAME_MIN, CLAN_NAME_MAX, CLAN_TAG_MIN, CLAN_TAG_MAX,
    CLAN_DESC_MAX, CLAN_EMBLEMS,
)
from infrastructure.repositories import clans as repo

# Буквы/цифры/пробел и базовая пунктуация (рус/лат). Защита от мусора/инъекций в UI.
_NAME_RE = re.compile(r"^[\w \-!?'«»\".,]+$", re.UNICODE)
_TAG_RE = re.compile(r"^[A-Za-zА-Яа-яЁё0-9]+$", re.UNICODE)


async def get_overview(db, user_id: int) -> dict:
    """Полная картина для экрана кланов: мой клан (+состав) и топ кланов."""
    my = await repo.get_user_clan(db, user_id)
    if my:
        my["members"] = await repo.get_members(db, my["clan_id"])
    return {
        "my_clan": my,
        "top": await repo.list_top_clans(db),
        "create_cost": CLAN_CREATE_COST_MORA,
        "max_members": CLAN_MAX_MEMBERS,
        "emblems": list(CLAN_EMBLEMS),
        "name_max": CLAN_NAME_MAX,
        "tag_max": CLAN_TAG_MAX,
    }


async def create(db, user_id: int, name: str, tag: str,
                 desc: str = "", emblem: str = "") -> tuple[bool, str, int | None]:
    name = (name or "").strip()
    tag = (tag or "").strip().upper()
    desc = (desc or "").strip()[:CLAN_DESC_MAX]
    if not (CLAN_NAME_MIN <= len(name) <= CLAN_NAME_MAX):
        return False, f"Название клана: от {CLAN_NAME_MIN} до {CLAN_NAME_MAX} символов.", None
    if not _NAME_RE.match(name):
        return False, "В названии недопустимые символы.", None
    if not (CLAN_TAG_MIN <= len(tag) <= CLAN_TAG_MAX):
        return False, f"Тег: от {CLAN_TAG_MIN} до {CLAN_TAG_MAX} символов.", None
    if not _TAG_RE.match(tag):
        return False, "Тег — только буквы и цифры.", None
    if emblem not in CLAN_EMBLEMS:
        emblem = CLAN_EMBLEMS[0]
    return await repo.create_clan(db, user_id, name, tag, desc, emblem)


async def join(db, user_id: int, clan_id: int) -> tuple[bool, str]:
    try:
        clan_id = int(clan_id)
    except (TypeError, ValueError):
        return False, "Некорректный клан."
    return await repo.join_clan(db, user_id, clan_id)


async def leave(db, user_id: int) -> tuple[bool, str]:
    return await repo.leave_clan(db, user_id)
