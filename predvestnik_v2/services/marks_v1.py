"""Player marks: composition for the profile hero, public card, lists and the «all marks» sheet; hand-given marks for the console.

Rules live in core/marks_v1.py. Staff marks come from the global rank, granted marks from the table, earned marks from the player's own
facts (streak, joined date, messages, collection, season skins), so a mark can never be forged or go stale.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

from core.marks_v1 import GRANTABLE, MARKS, compose, earned_state, ordered, public, staff_mark
from core.skins_v3_catalog import SKINS
from core.skins_v3_collection import PERMANENT
from infrastructure.repositories import marks_v1 as repo
from infrastructure.repositories import skins_v3 as skins_repo


class MarkConflict(RuntimeError):
    """A request that cannot be applied; the message is shown to the admin."""


def developer_id() -> int:
    return int(os.getenv("DEVELOPER_ID", "0") or 0)


def _joined_days(joined) -> int:
    if not joined:
        return 0
    try:
        moment = joined if isinstance(joined, datetime) else datetime.fromisoformat(str(joined).replace("Z", "+00:00"))
    except ValueError:
        return 0
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return max(0, (datetime.now(timezone.utc) - moment).days)


async def facts_for(db, user_id: int, *, streak=0, joined=None, messages=0) -> dict:
    """The numbers earned marks are computed from. The caller passes what the profile already loaded; skins are read here."""
    await skins_repo.ensure_tables(db)
    owned = await skins_repo.owned(db, user_id)
    maxed = sum(1 for sid, tier in owned.items() if sid in SKINS and SKINS[sid]["tier"] != "D" and tier == SKINS[sid]["tier"])
    seasons = {SKINS[sid]["season"] for sid in owned if sid in SKINS and SKINS[sid].get("season")}
    return {"streak": int(streak or 0), "joined_days": _joined_days(joined), "messages": int(messages or 0),
            "owned_permanent": sum(1 for sid in owned if sid in PERMANENT), "maxed": maxed, "seasons": seasons}


async def marks_for(db, user_id: int, *, global_rank: int, streak=0, joined=None, messages=0) -> list[dict]:
    """The marks a player wears, heaviest first. Never raises: a broken lookup must not take the profile down."""
    try:
        await repo.ensure_tables(db)
        facts = await facts_for(db, user_id, streak=streak, joined=joined, messages=messages)
        return compose(global_rank=global_rank, is_developer=bool(developer_id()) and int(user_id) == developer_id(),
                       granted_ids=await repo.granted(db, user_id), facts=facts)
    except Exception:
        return []


async def sheet(db, user_id: int, *, global_rank: int, streak=0, joined=None, messages=0) -> dict:
    """Own «all marks» view: worn marks and the earned ones still ahead, with progress."""
    await repo.ensure_tables(db)
    facts = await facts_for(db, user_id, streak=streak, joined=joined, messages=messages)
    worn = compose(global_rank=global_rank, is_developer=bool(developer_id()) and int(user_id) == developer_id(),
                   granted_ids=await repo.granted(db, user_id), facts=facts)
    ahead = [{**public(s["id"]), "how": MARKS[s["id"]]["how"], "have": s["have"], "need": s["need"]}
             for s in sorted(earned_state(facts), key=lambda s: -MARKS[s["id"]]["weight"]) if not s["done"]]
    return {"marks": worn, "ahead": ahead, "special": "Метки хелперов и разработчиков идут вместе с рангом, а особые метки выдают разработчики."}


async def top_mark_batch(db, user_ids: list[int]) -> dict[int, dict]:
    """One compact mark per player for list rows: staff and hand-given marks only (earned ones would cost a query per player)."""
    ids = [int(u) for u in dict.fromkeys(user_ids or [])]
    if not ids:
        return {}
    try:
        await repo.ensure_tables(db)
        marks = ",".join("?" for _ in ids)
        async with db.execute(f"SELECT user_tg_id, COALESCE(global_rank, 0) FROM users WHERE user_tg_id IN ({marks})", tuple(ids)) as c:
            ranks = {int(r[0]): int(r[1]) for r in await c.fetchall()}
        given = await repo.granted_batch(db, ids)
        dev = developer_id()
        out = {}
        for uid in ids:
            found: list[str] = []
            staff = staff_mark(ranks.get(uid, 0), is_developer=bool(dev) and uid == dev)
            if staff:
                found.append(staff)
            found.extend(m for m in given.get(uid, []) if m in MARKS and MARKS[m]["kind"] == "granted")
            top = ordered(found)
            if top:
                out[uid] = {"id": top[0]["id"], "title": top[0]["title"], "glyph": top[0]["glyph"], "tone": top[0]["tone"]}
        return out
    except Exception:
        return {}


async def grant(db, user_id: int, mark_id: str, actor_id: int, reason: str) -> str:
    """Give a hand-given mark. Returns the mark title; raises MarkConflict with a message for the admin."""
    if mark_id not in GRANTABLE:
        kind = MARKS.get(mark_id, {}).get("kind")
        raise MarkConflict("Эта метка идёт вместе с рангом и не выдаётся вручную." if kind == "staff"
                           else "Эта метка считается сама по данным игрока." if kind == "earned" else "Такой метки нет.")
    reason = (reason or "").strip()[:200]
    if not reason:
        raise MarkConflict("Укажите причину: она попадёт в журнал.")
    async with db.execute("SELECT 1 FROM users WHERE user_tg_id=?", (int(user_id),)) as c:
        if not await c.fetchone():
            raise MarkConflict("Такого игрока нет.")
    await repo.ensure_tables(db)
    if not await repo.grant(db, user_id, mark_id, actor_id, reason):
        raise MarkConflict("Эта метка у игрока уже есть.")
    return MARKS[mark_id]["title"]


async def revoke(db, user_id: int, mark_id: str, actor_id: int, reason: str) -> str:
    if mark_id not in GRANTABLE:
        raise MarkConflict("Снять можно только метку, выданную вручную.")
    reason = (reason or "").strip()[:200]
    if not reason:
        raise MarkConflict("Укажите причину: она попадёт в журнал.")
    await repo.ensure_tables(db)
    if not await repo.revoke(db, user_id, mark_id, actor_id, reason):
        raise MarkConflict("У игрока нет такой метки.")
    return MARKS[mark_id]["title"]


async def admin_view(db, user_id: int) -> dict:
    await repo.ensure_tables(db)
    return {"given": [public(m) for m in await repo.granted(db, user_id) if m in MARKS], "history": await repo.history(db, user_id),
            "grantable": [{"id": m, "title": MARKS[m]["title"], "glyph": MARKS[m]["glyph"], "desc": MARKS[m]["desc"]} for m in GRANTABLE]}
