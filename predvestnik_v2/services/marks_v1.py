"""Player marks («Регалии» for players): composition for the profile hero, public card, lists and the «all» sheet; hand-given marks for the console.

Rules live in core/marks_v1.py. Staff and special marks are only what the console gave. Earned marks are awarded by this module the first time the
player's own facts meet a rule (the best streak ever counts) and stay stored, so nothing is lost when a streak breaks and nothing is farmed twice.
Dynamic marks («Душа чата», «Личная жизнь?») are never stored: they are computed on every view from the last 30 / 60 days.
"""
from __future__ import annotations

from datetime import datetime, timezone

from core.marks_v1 import GRANTABLE, LIVE_WINDOWS, MARKS, PLAYER_NAME, compose, earned_state, live_state, ordered, public, staff_hint, stored
from core.skins_v3 import CEILING
from core.skins_v3_catalog import SKINS
from core.skins_v3_collection import PERMANENT
from infrastructure.repositories import marks_v1 as repo
from infrastructure.repositories import skins_v3 as skins_repo


class MarkConflict(RuntimeError):
    """A request that cannot be applied; the message is shown to the admin."""


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


def _recent_facts(windows: dict[int, int] | None) -> dict:
    return {f"messages_{days}d": int((windows or {}).get(days, 0)) for days in LIVE_WINDOWS}


async def facts_for(db, user_id: int, *, streak=0, joined=None) -> dict:
    """The numbers earned marks are computed from. The caller passes what the profile already loaded; skins and the streak history are read here.
    `streak` is the current one; the fact is the best known: the current, the one lost at the last break, or the legacy best."""
    await skins_repo.ensure_tables(db)
    owned = await skins_repo.owned(db, user_id)
    maxed = sum(1 for sid, tier in owned.items() if sid in SKINS and tier == CEILING)
    seasons = {SKINS[sid]["season"] for sid in owned if sid in SKINS and SKINS[sid].get("season")}
    best = max(int(streak or 0), await repo.best_streak_before(db, user_id))
    return {"streak": best, "joined_days": _joined_days(joined), **_recent_facts((await repo.messages_recent_batch(db, [user_id])).get(int(user_id))),
            "owned_permanent": sum(1 for sid in owned if sid in PERMANENT), "maxed": maxed, "seasons": seasons}


async def _worn(db, user_id: int, facts: dict) -> list[dict]:
    """Stored marks plus earned ones that the facts already satisfy; those are stored on the spot so they are kept for good."""
    held = await repo.held(db, user_id)
    for state in earned_state(facts):
        if state["done"] and state["id"] not in held:
            try:
                await repo.award(db, user_id, state["id"])
            except Exception:
                pass          # shown anyway through compose; the next view tries to store it again
    return compose(held_ids=held, facts=facts)


async def marks_for(db, user_id: int, *, streak=0, joined=None) -> list[dict]:
    """The marks a player wears, heaviest first. Never raises: a broken lookup must not take the profile down."""
    try:
        await repo.ensure_tables(db)
        return await _worn(db, user_id, await facts_for(db, user_id, streak=streak, joined=joined))
    except Exception:
        return []


async def sheet(db, user_id: int, *, streak=0, joined=None) -> dict:
    """Own «all» view: worn marks and the earned ones still ahead, with progress."""
    await repo.ensure_tables(db)
    facts = await facts_for(db, user_id, streak=streak, joined=joined)
    worn = await _worn(db, user_id, facts)
    ahead = [{**public(s["id"]), "how": MARKS[s["id"]]["how"], "have": s["have"], "need": s["need"]}
             for s in sorted(earned_state(facts) + live_state(facts), key=lambda s: -MARKS[s["id"]]["weight"]) if not s["done"]]
    return {"marks": worn, "ahead": ahead, "name": PLAYER_NAME,
            "special": "Заслуженные регалии приходят сами и остаются навсегда, даже за то, что вы сделали раньше. Динамическая держится, пока вы сохраняете темп. Особые выдают разработчики."}


async def top_mark_batch(db, user_ids: list[int]) -> dict[int, dict]:
    """One compact mark per player for list rows: the heaviest of the stored ones (staff, special, earned and already awarded) and the dynamic ones met right now."""
    ids = [int(u) for u in dict.fromkeys(user_ids or [])]
    if not ids:
        return {}
    try:
        await repo.ensure_tables(db)
        held = await repo.held_batch(db, ids)
        recent = await repo.messages_recent_batch(db, ids)
        out = {}
        for uid in ids:
            live = [s["id"] for s in live_state(_recent_facts(recent.get(uid))) if s["done"]]
            top = ordered([*stored(held.get(uid, [])), *live])
            if top:
                out[uid] = {"id": top[0]["id"], "title": top[0]["title"], "glyph": top[0]["glyph"], "tone": top[0]["tone"]}
        return out
    except Exception:
        return {}


async def grant(db, user_id: int, mark_id: str, actor_id: int, reason: str) -> str:
    """Give a hand-given mark. Returns the mark title; raises MarkConflict with a message for the admin."""
    if mark_id not in GRANTABLE:
        kind = MARKS.get(mark_id, {}).get("kind")
        raise MarkConflict({"earned": "Эту метку сервер выдаёт сам, когда игрок её заслужит, и она остаётся навсегда.",
                            "live": "Эта метка динамическая: сервер считает её сам по сообщениям за последние дни."}.get(kind, "Такой метки нет."))
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
    """What the console shows for a player: given marks, earned ones the server stored, the log, what can be given, and a hint for the bot rank."""
    await repo.ensure_tables(db)
    held = stored(await repo.held(db, user_id))
    async with db.execute("SELECT COALESCE(global_rank, 0) FROM users WHERE user_tg_id=?", (int(user_id),)) as c:
        row = await c.fetchone()
    rank = int(row[0]) if row else 0
    hint = staff_hint(rank)
    return {"given": [public(m) for m in held if MARKS[m]["kind"] != "earned"], "earned": [public(m) for m in held if MARKS[m]["kind"] == "earned"],
            "history": await repo.history(db, user_id), "rank": rank, "rank_hint": public(hint) if hint and hint not in held else None,
            "grantable": [{"id": m, "title": MARKS[m]["title"], "glyph": MARKS[m]["glyph"], "desc": MARKS[m]["desc"], "kind": MARKS[m]["kind"]} for m in GRANTABLE]}
