"""Private menu snapshots: presentation only, never a second path to game actions."""

from __future__ import annotations

from core import widget_cards as rules
from core import widgets
from infrastructure.repositories import widget_cards as repo


async def available(db, user_id: int) -> bool:
    from services import global_moderation
    from services.widgets import switched_off

    async with db.execute(
        "SELECT user_tg_id FROM users WHERE user_tg_id = ? AND deleted_at IS NULL",
        (user_id,),
    ) as cursor:
        exists = await cursor.fetchone()
    return bool(
        exists
        and not await global_moderation.is_blocked(db, user_id)
        and not await switched_off(db)
    )


async def enabled(db, user_id: int) -> bool:
    return await available(db, user_id) and await repo.enabled(db, user_id)


async def answer(db, query, bot_id: int) -> str:
    parts = query.data.split(":")
    if (
        not query.in_own_dm
        or query.type.type != "data"
        or len(query.data.encode("utf-8")) > widgets.MAX_QUERY_BYTES
        or len(parts) != 5
        or parts[:2] != ["card", "p"]
        or any(
            not value.isascii() or not value.isdigit() or len(value) > 10
            for value in parts[3:]
        )
    ):
        return widgets.error("Открой меню заново командой в личке с ботом.")
    row = await repo.get(db, bot_id, query.chat.id, query.message_id)
    if (
        not row
        or row["token"] != parts[2]
        or row["owner_id"] != query.sender.id
        or not await available(db, query.sender.id)
    ):
        return widgets.error("Это меню больше недоступно. Открой его заново.")
    await repo.acknowledge(db, row["token"], int(parts[4]))
    return widgets.encode(rules.snapshot(row, int(parts[3])))
