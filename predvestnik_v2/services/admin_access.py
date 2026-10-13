"""Кто и где может действовать в админке (ADM-02): принципал, область, права ролей.

Принципал — это либо сотрудник (`kind="staff"`, глобальная роль `rank` ≥ 1, область — вся платформа),
либо владелец чатов (`kind="owner"`, `rank=0`, `chats` — свои чаты из БД). Владелец НЕ ранг: числовые проверки
сотрудников (`section()`, `_check`, `_guard_target`) его никогда не пропускают.

Права ролей 1–4 хранятся в `admin_role_grants` как порог «минимальная роль» на раздел или действие.
Менять можно только то, что перечислено в CONFIGURABLE, и только в пределах [FLOOR, CEILING]: всё остальное
закреплено в коде за разработчиком и создателем. Потолок применяется при ЧТЕНИИ, строка сверх него (ручной SQL,
старая версия) просто ужимается. Один порог на действие = монотонность: если роль может, то и все роли выше тоже.
"""
from __future__ import annotations

from fastapi import HTTPException

from bot.chat.global_ranks import CREATOR

STAFF, OWNER = "staff", "owner"

FLOOR = 2     # ниже «мл. хелпера» порог опустить нельзя (тестер — учётка для проверок)
CEILING = 5   # выше «разработчика» тоже нельзя: создатель не должен терять доступ

# Ключи: "section:<раздел>" и "action:<действие>". Остальное закреплено в коде.
CONFIGURABLE = frozenset({
    "section:people", "section:reports", "section:metrics", "section:journal", "section:health",
    "action:warn", "action:mute", "action:unmute", "action:unwarn_all", "action:kick", "action:ban", "action:unban",
    "action:block", "action:unblock", "action:close", "action:open", "action:warn_limit",
})

STATEMENTS = (
    """CREATE TABLE IF NOT EXISTS admin_role_grants (
        key        TEXT PRIMARY KEY,
        min_rank   INT    NOT NULL,
        updated_by BIGINT NOT NULL,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""",
)

_ready = False


def staff_principal(user_id: int, rank: int) -> dict:
    return {"id": int(user_id), "rank": int(rank), "kind": STAFF, "chats": None}


def owner_principal(user_id: int, chats) -> dict:
    return {"id": int(user_id), "rank": 0, "kind": OWNER, "chats": frozenset(int(c) for c in chats)}


def is_staff(principal: dict) -> bool:
    return principal.get("kind", STAFF) == STAFF and int(principal.get("rank", 0)) > 0


def require_staff(principal: dict) -> None:
    """Для маршрутов сотрудников: владелец чата сюда не проходит ни при каком ранге."""
    if not is_staff(principal):
        raise HTTPException(403, "Этот раздел доступен только персоналу бота.")


def require_chat(principal: dict, chat_id: int) -> None:
    """Область: сотрудник действует везде, владелец — только в своих чатах. Вызывается внутри исполнителей действий."""
    if is_staff(principal):
        return
    chats = principal.get("chats")
    if principal.get("kind") == OWNER and chats is not None and int(chat_id or 0) in chats:
        return
    raise HTTPException(403, "Этот чат вам недоступен.")


def effective_min(key: str, default: int, grants: dict[str, int] | None = None) -> int:
    """Минимальная роль на действие: порог из БД, ужатый до [FLOOR, CEILING]; не настраиваемое — как в коде."""
    if key not in CONFIGURABLE or not grants or key not in grants:
        return default
    return max(FLOOR, min(int(grants[key]), CEILING))


async def ensure_schema(db) -> None:
    global _ready
    for sql in STATEMENTS:
        await db.execute(sql)
    _ready = True


async def load_grants(db) -> dict[str, int]:
    if not _ready:
        await ensure_schema(db)
    async with db.execute("SELECT key, min_rank FROM admin_role_grants") as cur:
        return {str(r[0]): int(r[1]) for r in await cur.fetchall()}


async def set_grant(db, actor: dict, key: str, min_rank: int | None) -> None:
    """Изменить порог (None — вернуть значение по умолчанию). Только создатель; вне CONFIGURABLE и [FLOOR, CEILING] нельзя."""
    from services import admin_people
    if not is_staff(actor) or actor["rank"] < CREATOR:
        raise HTTPException(403, "Права ролей меняет только создатель.")
    if key not in CONFIGURABLE:
        raise HTTPException(400, "Это право закреплено в коде и не настраивается.")
    if min_rank is not None and not FLOOR <= int(min_rank) <= CEILING:
        raise HTTPException(400, f"Порог — от {FLOOR} до {CEILING}.")
    if not _ready:
        await ensure_schema(db)
    if min_rank is None:
        await db.execute("DELETE FROM admin_role_grants WHERE key = ?", (key,))
    else:
        await db.execute(
            "INSERT INTO admin_role_grants (key, min_rank, updated_by) VALUES (?, ?, ?) "
            "ON CONFLICT (key) DO UPDATE SET min_rank = EXCLUDED.min_rank, updated_by = EXCLUDED.updated_by, updated_at = NOW()",
            (key, int(min_rank), actor["id"]))
    await admin_people.audit(db, actor["id"], "grant", details={"key": key, "min_rank": min_rank})
