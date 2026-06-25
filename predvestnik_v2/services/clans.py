"""services/clans.py — бизнес-логика кланов (валидация + флоу + сообщения).

Единый источник правды для веб- и бот-адаптеров. Без импортов bot.*/FastAPI.*.
SQL — в infrastructure/repositories/clans.py.
"""
import re

from core.constants import (
    CLAN_CREATE_COST_MORA, CLAN_MAX_MEMBERS,
    CLAN_NAME_MIN, CLAN_NAME_MAX, CLAN_TAG_MIN, CLAN_TAG_MAX,
    CLAN_DESC_MAX, CLAN_EMBLEMS, CLAN_REQUEST_ITEM_CATEGORIES,
)
from core.registry import ITEMS_REGISTRY
from infrastructure.repositories import clans as repo


def allowed_request_items() -> list[dict]:
    """Предметы, которые можно просить на Доске (дешёвые расходники — корм/материалы)."""
    return [{"item_id": iid, "name": d.get("name", iid)}
            for iid, d in ITEMS_REGISTRY.items()
            if d.get("category") in CLAN_REQUEST_ITEM_CATEGORIES]


def _is_requestable(item_id: str) -> bool:
    d = ITEMS_REGISTRY.get(item_id)
    return bool(d) and d.get("category") in CLAN_REQUEST_ITEM_CATEGORIES

# Буквы/цифры/пробел и базовая пунктуация (рус/лат). Защита от мусора/инъекций в UI.
_NAME_RE = re.compile(r"^[\w \-!?'«»\".,]+$", re.UNICODE)
_TAG_RE = re.compile(r"^[A-Za-zА-Яа-яЁё0-9]+$", re.UNICODE)


async def get_overview(db, user_id: int) -> dict:
    """Полная картина для экрана кланов: мой клан (Штаб/здания/Доска) и топ кланов."""
    my = await repo.get_user_clan(db, user_id)
    if my:
        txp = my.get("total_xp", 0)
        my["members"] = await repo.get_members(db, my["clan_id"])
        my["level"] = repo.clan_level(txp)
        my["level_progress"] = repo.clan_level_progress(txp)
        my["buildings"] = repo.building_levels(txp)
        my["effective_max"] = repo.effective_max_members(txp)
        reqs = await repo.list_requests(db, my["clan_id"])
        is_leader = my.get("role") == "leader"
        for r in reqs:
            r["item_name"] = ITEMS_REGISTRY.get(r["item_id"], {}).get("name", r["item_id"])
            r["mine"] = (r["author_id"] == user_id)
            r["can_cancel"] = r["mine"] or is_leader
            r["remaining"] = max(0, int(r["qty_need"]) - int(r["qty_filled"]))
        my["requests"] = reqs
        my["request_qty_cap"] = repo.board_qty_cap(my["level"])
        my["request_active_cap"] = repo.board_active_cap(my["level"])
    top = await repo.list_top_clans(db)
    for t in top:
        t["level"] = repo.clan_level(t.get("total_xp", 0))
        t["effective_max"] = repo.effective_max_members(t.get("total_xp", 0))
    return {
        "my_clan": my,
        "top": top,
        "create_cost": CLAN_CREATE_COST_MORA,
        "max_members": CLAN_MAX_MEMBERS,
        "emblems": list(CLAN_EMBLEMS),
        "name_max": CLAN_NAME_MAX,
        "tag_max": CLAN_TAG_MAX,
        "request_items": allowed_request_items(),
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


# ── Доска Запросов ──────────────────────────────────────────────────────────────


async def request_create(db, user_id: int, item_id: str, qty) -> tuple[bool, str]:
    item_id = (item_id or "").strip()
    if not _is_requestable(item_id):
        return False, "Просить можно только корм и материалы."
    try:
        qty = int(qty)
    except (TypeError, ValueError):
        return False, "Некорректное количество."
    if qty < 1:
        return False, "Количество должно быть ≥ 1."
    my = await repo.get_user_clan(db, user_id)
    if not my:
        return False, "Ты не в клане."
    cap = repo.board_qty_cap(repo.clan_level(my.get("total_xp", 0)))
    if qty > cap:
        return False, f"Максимум {cap} шт. в одном запросе (зависит от уровня Доски)."
    return await repo.create_request(db, user_id, item_id, qty)


async def request_fill(db, user_id: int, request_id, qty) -> tuple[bool, str]:
    try:
        request_id, qty = int(request_id), int(qty)
    except (TypeError, ValueError):
        return False, "Некорректные данные."
    return await repo.fill_request(db, user_id, request_id, qty)


async def request_cancel(db, user_id: int, request_id) -> tuple[bool, str]:
    try:
        request_id = int(request_id)
    except (TypeError, ValueError):
        return False, "Некорректный запрос."
    return await repo.cancel_request(db, user_id, request_id)
