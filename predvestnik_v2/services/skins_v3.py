"""Skins V3 service: catalog state, buying, equipping, tier upgrades and Essence.

Zarniki always move through the shared economy ledger; Essence moves through its own ledger
(infrastructure/repositories/skins_v3.py). Every mutation takes the user row lock and is safe to repeat.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

from core.appearance_v3 import cap_tier
from core.economy_contract import IdempotencyConflict, InsufficientBalance
from core.skins_v3 import (BUY_PRICE_ZARNIKI, ESSENCE_PACKS, ESSENCE_PER_ZARNIK, ESSENCE_QUEST_REWARD, TIERS, UPGRADE_ESSENCE, full_price,
                           next_tier, tier_index, total_upgrade_cost, upgrade_cost)
from core.skins_v3_catalog import SETS, SKINS
from core.skins_v3_collection import (BASE_RANK, MAXED_BADGES, PERMANENT, SET_GLYPH, featured, maxed_badge, milestones, owned_permanent, rank_for, row_bonus,
                                      row_members, season_of, season_window, set_bonus)
from infrastructure.repositories import economy_ledger
from infrastructure.repositories import skins_v3 as repo
from services.vip import is_vip_active

VERSION = "skins-v3-2026-10"


def _now() -> datetime:
    return datetime.now(timezone.utc)


class SkinConflict(RuntimeError):
    """A request that cannot be applied; the message is shown to the player."""


def crest_for(skin_id: str, owned: dict) -> dict | None:
    """The set emblem a player shows while wearing a member of a set they completed."""
    set_id = SKINS[skin_id]["set"]
    if not set_id or not all(m in owned for m in SETS[set_id]["members"]):
        return None
    return {"id": set_id, "name": SETS[set_id]["name"], "glyph": SET_GLYPH.get(set_id, "◈")}


def look_payload(skin_id: str, tier: str, *, compact: bool = False, crest: dict | None = None) -> dict:
    """What a client needs to draw a skin at a tier. Compact form is used for rows in lists."""
    skin = SKINS[skin_id]
    look = {"id": skin_id, "name": skin["name"], "tier": tier, "ceiling": skin["tier"], "pal": list(skin["pal"]),
            "kinds": dict(skin["kinds"]), "sig": skin["sig"], "title": skin["items"]["title"]}
    if crest:
        look["crest"] = crest
    if not compact:
        look["items"] = dict(skin["items"])
        look["tokens"] = dict(skin["tokens"])
    return look


def _item(skin_id: str, owned_tier: str | None, equipped: str | None, vip: bool, owned: dict) -> dict:
    skin = SKINS[skin_id]
    season = season_of(skin_id, _now())
    nxt = upgrade_cost(owned_tier, skin["tier"]) if owned_tier else None
    shown = cap_tier(owned_tier, vip) if owned_tier else "D"
    return {
        **look_payload(skin_id, shown, crest=crest_for(skin_id, owned)), "blurb": skin["blurb"], "price_zarniki": BUY_PRICE_ZARNIKI[skin["tier"]],
        "set": skin["set"], "owned": owned_tier is not None, "level": owned_tier, "shown_tier": shown, "equipped": skin_id == equipped,
        "next": {"tier": nxt[0], "essence": nxt[1], "needs_vip": nxt[0] == "SSS" and not vip} if nxt else None,
        "maxed": owned_tier is not None and nxt is None, "total_upgrade_essence": total_upgrade_cost(skin["tier"]),
        "full_price_zarniki": full_price(skin["tier"]), "season": season, "buyable": season is None or season["open"],
    }


def _sets_state(owned: dict) -> list[dict]:
    return [{"id": sid, "name": st["name"], "blurb": st["blurb"], "glyph": SET_GLYPH.get(sid, "◈"), "members": list(st["members"]),
             "bonus_essence": set_bonus(sid), "have": sum(1 for m in st["members"] if m in owned),
             "missing": [m for m in st["members"] if m not in owned], "complete": all(m in owned for m in st["members"]),
             "season": season_window(st["season"], _now()) if st.get("season") else None}
            for sid, st in SETS.items()]


def _maxed_count(owned: dict) -> int:
    """Skins raised all the way to their ceiling. A D skin has no road to climb, so it never counts."""
    return sum(1 for sid, tier in owned.items() if sid in SKINS and SKINS[sid]["tier"] != "D" and tier == SKINS[sid]["tier"])


def collection_summary(owned: dict) -> dict:
    """Counts only (no skin ids): safe to show on a public profile."""
    maxed, have = _maxed_count(owned), owned_permanent(owned)
    return {"owned": have, "total": len(PERMANENT), "rank": rank_for(have), "maxed": maxed, "maxed_badge": maxed_badge(maxed),
            "sets_done": [{"id": sid, "name": st["name"], "glyph": SET_GLYPH.get(sid, "◈")} for sid, st in SETS.items() if all(m in owned for m in st["members"])]}


def _collection_state(owned: dict) -> dict:
    maxed, count = _maxed_count(owned), owned_permanent(owned)
    steps = [{**s, "done": count >= s["at"]} for s in milestones()]
    rows = []
    for rarity in TIERS:
        members = row_members(rarity)
        if members:
            have = sum(1 for m in members if m in owned)
            rows.append({"rarity": rarity, "have": have, "total": len(members), "bonus_essence": row_bonus(rarity), "done": have == len(members)})
    return {**collection_summary(owned), "base_rank": BASE_RANK, "milestones": steps, "next_milestone": next((s for s in steps if not s["done"]), None),
            "rows": rows, "maxed_badges": [{"at": at, "title": name, "done": maxed >= at} for at, name in MAXED_BADGES]}


async def _grant_bonus(db, user_id: int, amount: int, *, reason: str, reference: str, key: str) -> bool:
    applied, _ = await repo.essence_apply(db, user_id, amount, reason=reason, reference=reference, idempotency_key=key)
    return applied


async def _purchase_rewards(db, user_id: int, skin_id: str, owned: dict) -> list[dict]:
    """Everything a purchase can complete, each paid at most once per player: the set, the rarity row, collection steps, skin of the week."""
    events: list[dict] = []
    set_id = SKINS[skin_id]["set"]
    if set_id and all(m in owned for m in SETS[set_id]["members"]):
        amount = set_bonus(set_id)
        if await _grant_bonus(db, user_id, amount, reason="set_bonus", reference=set_id, key=f"skin-v3:set:{set_id}"):
            events.append({"kind": "set", "id": set_id, "name": SETS[set_id]["name"], "glyph": SET_GLYPH.get(set_id, "◈"), "essence": amount})
    rarity = SKINS[skin_id]["tier"]
    if all(m in owned for m in row_members(rarity)):
        amount = row_bonus(rarity)
        if await _grant_bonus(db, user_id, amount, reason="row_bonus", reference=rarity, key=f"skin-v3:row:{rarity}"):
            events.append({"kind": "row", "rarity": rarity, "essence": amount})
    for step in milestones():
        if owned_permanent(owned) >= step["at"] and await _grant_bonus(db, user_id, step["essence"], reason="milestone_bonus", reference=step["id"], key=f"skin-v3:{step['id']}"):
            events.append({"kind": "rank", "rank": step["rank"], "at": step["at"], "essence": step["essence"]})
    week = featured()
    if week["skin_id"] == skin_id and await _grant_bonus(db, user_id, week["bonus_essence"], reason="featured_bonus", reference=skin_id,
                                                         key=f"skin-v3:featured:{skin_id}:{week['week']}"):
        events.append({"kind": "featured", "skin_id": skin_id, "essence": week["bonus_essence"]})
    return events


def _event_text(events: list[dict]) -> str:
    parts = []
    for e in events:
        if e["kind"] == "set":
            parts.append(f"Сет «{e['name']}» собран: +{e['essence']} Эссенции и знак сета.")
        elif e["kind"] == "row":
            parts.append(f"Редкость {e['rarity']} собрана целиком: +{e['essence']} Эссенции.")
        elif e["kind"] == "rank":
            parts.append(f"Новый ранг «{e['rank']}»: +{e['essence']} Эссенции.")
        elif e["kind"] == "featured":
            parts.append(f"Образ недели: +{e['essence']} Эссенции в подарок.")
    return (" " + " ".join(parts)) if parts else ""


async def _zarniki(db, user_id: int) -> int:
    async with db.execute("SELECT COALESCE(user_balance_zarniki,0) FROM users WHERE user_tg_id=?", (int(user_id),)) as c:
        row = await c.fetchone()
    return int(row[0]) if row else 0


async def state(db, user_id: int) -> dict:
    owned = await repo.owned(db, user_id)
    wearing = await repo.equipped(db, user_id)
    if wearing not in owned:
        wearing = None
    vip = await is_vip_active(db, user_id)
    return {
        "version": VERSION, "equipped": wearing, "vip": vip, "zarniki": await _zarniki(db, user_id),
        "essence": {"balance": await repo.essence_balance(db, user_id), "per_zarnik": ESSENCE_PER_ZARNIK,
                    "packs": [{"zarniki": n, "essence": n * ESSENCE_PER_ZARNIK} for n in ESSENCE_PACKS],
                    "quest_reward": dict(ESSENCE_QUEST_REWARD), "costs": dict(UPGRADE_ESSENCE)},
        "items": [_item(sid, owned.get(sid), wearing, vip, owned) for sid in SKINS], "sets": _sets_state(owned),
        "collection": _collection_state(owned), "featured": {**featured(), "owned": featured()["skin_id"] in owned},
        "share_url": f"https://t.me/{os.getenv('BOT_USERNAME', 'IIIPredvestnikIIIBot').strip().lstrip('@')}?startapp=looks",
    }


async def own_look(db, user_id: int) -> dict | None:
    """The look the owner wears, in the same shape the public view uses (always visible to the owner)."""
    worn = (await repo.equipped_batch(db, [user_id])).get(int(user_id))
    if not worn or worn[0] not in SKINS:
        return None
    return look_payload(worn[0], cap_tier(worn[1], await is_vip_active(db, user_id)), crest=crest_for(worn[0], await repo.owned(db, user_id)))


async def _lock_user(db, user_id: int) -> None:
    await db.execute("INSERT INTO users(user_tg_id) VALUES (?) ON CONFLICT DO NOTHING", (int(user_id),))
    async with db.execute("SELECT 1 FROM users WHERE user_tg_id=? FOR UPDATE", (int(user_id),)) as c:
        await c.fetchone()


async def buy(db, user_id: int, skin_id: str, *, idempotency_key: str) -> tuple[str, dict]:
    skin = SKINS.get(str(skin_id or ""))
    if not skin:
        raise SkinConflict("Такого скина нет.")
    price = BUY_PRICE_ZARNIKI[skin["tier"]]
    await economy_ledger.ensure_tables(db)
    await repo.ensure_tables(db)
    events: list[dict] = []
    try:
        async with db.connection.transaction():
            await _lock_user(db, user_id)
            replay = await economy_ledger.find_reference_replay(
                db, int(user_id), reason_code="skin_v3_purchase", idempotency_key=idempotency_key,
                source_type="skins_v3", reference_type="skin_v3", reference_id=skin_id)
            if replay is None:
                if skin_id in await repo.owned(db, user_id):
                    raise SkinConflict("Этот скин уже у вас.")
                season = season_of(skin_id, _now())      # checked here, so a retry of a purchase made in time is still a replay
                if season and not season["open"]:
                    raise SkinConflict(f"Сезон «{season['name']}» ещё не начался." if season["state"] == "soon" else f"Сезон «{season['name']}» закончился: этот образ больше нельзя купить.")
                await economy_ledger.apply_balance_change(
                    db, int(user_id), {"zarniki": -price}, reason_code="skin_v3_purchase", idempotency_key=idempotency_key,
                    source_type="skins_v3", reference_type="skin_v3", reference_id=skin_id,
                    metadata={"skin_id": skin_id, "ceiling": skin["tier"], "price_zarniki": price}, note=skin_id)
                await repo.grant(db, user_id, skin_id)
                events = await _purchase_rewards(db, user_id, skin_id, await repo.owned(db, user_id))
            await repo.set_equipped(db, user_id, skin_id)
    except InsufficientBalance as exc:
        raise SkinConflict(f"Нужно {price}✨ для этого скина.") from exc
    except IdempotencyConflict as exc:
        raise SkinConflict("Этот запрос уже использован для другой покупки.") from exc
    result = await state(db, user_id)
    result["events"] = events
    return f"Скин «{skin['name']}» ваш. Он начинает с тира D и растёт за Эссенцию.{_event_text(events)}", result


async def equip(db, user_id: int, skin_id: str | None) -> dict:
    await repo.ensure_tables(db)
    async with db.connection.transaction():
        await _lock_user(db, user_id)
        if skin_id is not None:
            if skin_id not in SKINS:
                raise SkinConflict("Такого скина нет.")
            if skin_id not in await repo.owned(db, user_id):
                raise SkinConflict("Этот скин ещё не куплен.")
        await repo.set_equipped(db, user_id, skin_id)
    return await state(db, user_id)


async def upgrade(db, user_id: int, skin_id: str, *, idempotency_key: str) -> tuple[str, dict]:
    skin = SKINS.get(str(skin_id or ""))
    if not skin:
        raise SkinConflict("Такого скина нет.")
    await repo.ensure_tables(db)
    async with db.connection.transaction():
        await _lock_user(db, user_id)
        key = f"skin-v3:upgrade:{idempotency_key}"
        async with db.execute("SELECT 1 FROM skins_v3_essence_ledger WHERE user_id=? AND idempotency_key=?", (int(user_id), key)) as c:
            if await c.fetchone():
                return f"«{skin['name']}» уже улучшен этим запросом.", await state(db, user_id)   # safe retry
        current = await repo.owned_tier_locked(db, user_id, skin_id)
        if current is None:
            raise SkinConflict("Сначала купите этот скин.")
        step = upgrade_cost(current, skin["tier"])
        if step is None:
            raise SkinConflict("Скин уже на своём максимальном тире.")
        target, cost = step
        if target == "SSS" and not await is_vip_active(db, user_id):
            raise SkinConflict("Последний тир SSS открывается только с активным VIP.")
        try:
            applied, _ = await repo.essence_apply(db, user_id, -cost, reason="skin_upgrade", reference=f"{skin_id}:{target}", idempotency_key=key)
        except ValueError as exc:
            raise SkinConflict(f"Нужно {cost} Эссенции для тира {target}.") from exc
        events: list[dict] = []
        if applied:
            before = _maxed_count(await repo.owned(db, user_id))
            await repo.set_tier(db, user_id, skin_id, target)
            owned_now = await repo.owned(db, user_id)
            events.append({"kind": "tier", "skin_id": skin_id, "name": skin["name"], "tier": target, "maxed": target == skin["tier"], "sig": bool(skin["sig"]) and target == skin["tier"]})
            after = _maxed_count(owned_now)
            if after > before and maxed_badge(after) != maxed_badge(before):
                events.append({"kind": "badge", "title": maxed_badge(after), "maxed": after})
    result = await state(db, user_id)
    result["events"] = events
    return f"«{skin['name']}» теперь тир {target}.", result


async def buy_essence(db, user_id: int, zarniki: int, *, idempotency_key: str) -> tuple[str, dict]:
    if int(zarniki) not in ESSENCE_PACKS:
        raise SkinConflict("Такого набора Эссенции нет.")
    amount = int(zarniki) * ESSENCE_PER_ZARNIK
    await economy_ledger.ensure_tables(db)
    await repo.ensure_tables(db)
    try:
        async with db.connection.transaction():
            await _lock_user(db, user_id)
            key = f"skin-v3:essence:{idempotency_key}"
            async with db.execute("SELECT 1 FROM skins_v3_essence_ledger WHERE user_id=? AND idempotency_key=?", (int(user_id), key)) as c:
                replay = await c.fetchone()
            if not replay:
                await economy_ledger.apply_balance_change(
                    db, int(user_id), {"zarniki": -int(zarniki)}, reason_code="skin_essence_purchase", idempotency_key=key,
                    source_type="skins_v3", reference_type="skin_essence", reference_id=str(zarniki),
                    metadata={"essence": amount}, note="essence")
                await repo.essence_apply(db, user_id, amount, reason="essence_purchase", reference=f"{zarniki}z", idempotency_key=key)
    except InsufficientBalance as exc:
        raise SkinConflict(f"Нужно {int(zarniki)}✨ для этого набора.") from exc
    except IdempotencyConflict as exc:
        raise SkinConflict("Этот запрос уже использован для другой покупки.") from exc
    return f"Получено {amount} Эссенции.", await state(db, user_id)


async def grant_essence_in_transaction(db, user_id: int, amount: int, *, reason: str, reference: str) -> int:
    """For callers that already hold a transaction (quest rewards). Idempotent per (reason, reference)."""
    await repo.ensure_tables(db)
    applied, _ = await repo.essence_apply(db, user_id, int(amount), reason=reason, reference=reference, idempotency_key=f"{reason}:{reference}")
    return int(amount) if applied else 0


__all__ = ["SkinConflict", "state", "buy", "equip", "upgrade", "buy_essence", "own_look", "look_payload", "grant_essence_in_transaction", "TIERS", "next_tier", "tier_index"]
