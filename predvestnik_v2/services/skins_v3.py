"""Skins V3 service: catalog state, buying, equipping, tier upgrades and Essence.

Zarniki always move through the shared economy ledger; Essence moves through its own ledger
(infrastructure/repositories/skins_v3.py). Every mutation takes the user row lock and is safe to repeat.
"""
from __future__ import annotations

from core.appearance_v3 import cap_tier
from core.economy_contract import IdempotencyConflict, InsufficientBalance
from core.skins_v3 import (BUY_PRICE_ZARNIKI, ESSENCE_PACKS, ESSENCE_PER_ZARNIK, ESSENCE_QUEST_REWARD, TIERS,
                           UPGRADE_ESSENCE, next_tier, tier_index, total_upgrade_cost, upgrade_cost)
from core.skins_v3_catalog import SKINS
from infrastructure.repositories import economy_ledger
from infrastructure.repositories import skins_v3 as repo
from services.vip import is_vip_active

VERSION = "skins-v3-2026-10"


class SkinConflict(RuntimeError):
    """A request that cannot be applied; the message is shown to the player."""


def look_payload(skin_id: str, tier: str, *, compact: bool = False) -> dict:
    """What a client needs to draw a skin at a tier. Compact form is used for rows in lists."""
    skin = SKINS[skin_id]
    look = {"id": skin_id, "name": skin["name"], "tier": tier, "ceiling": skin["tier"], "pal": list(skin["pal"]),
            "kinds": dict(skin["kinds"]), "sig": skin["sig"], "title": skin["items"]["title"]}
    if not compact:
        look["items"] = dict(skin["items"])
        look["tokens"] = dict(skin["tokens"])
    return look


def _item(skin_id: str, owned_tier: str | None, equipped: str | None, vip: bool) -> dict:
    skin = SKINS[skin_id]
    nxt = upgrade_cost(owned_tier, skin["tier"]) if owned_tier else None
    shown = cap_tier(owned_tier, vip) if owned_tier else "D"
    return {
        **look_payload(skin_id, shown), "blurb": skin["blurb"], "price_zarniki": BUY_PRICE_ZARNIKI[skin["tier"]],
        "owned": owned_tier is not None, "level": owned_tier, "shown_tier": shown, "equipped": skin_id == equipped,
        "next": {"tier": nxt[0], "essence": nxt[1], "needs_vip": nxt[0] == "SSS" and not vip} if nxt else None,
        "maxed": owned_tier is not None and nxt is None, "total_upgrade_essence": total_upgrade_cost(skin["tier"]),
    }


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
        "items": [_item(sid, owned.get(sid), wearing, vip) for sid in SKINS],
    }


async def own_look(db, user_id: int) -> dict | None:
    """The look the owner wears, in the same shape the public view uses (always visible to the owner)."""
    worn = (await repo.equipped_batch(db, [user_id])).get(int(user_id))
    if not worn or worn[0] not in SKINS:
        return None
    return look_payload(worn[0], cap_tier(worn[1], await is_vip_active(db, user_id)))


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
    try:
        async with db.connection.transaction():
            await _lock_user(db, user_id)
            replay = await economy_ledger.find_reference_replay(
                db, int(user_id), reason_code="skin_v3_purchase", idempotency_key=idempotency_key,
                source_type="skins_v3", reference_type="skin_v3", reference_id=skin_id)
            if replay is None:
                if skin_id in await repo.owned(db, user_id):
                    raise SkinConflict("Этот скин уже у вас.")
                await economy_ledger.apply_balance_change(
                    db, int(user_id), {"zarniki": -price}, reason_code="skin_v3_purchase", idempotency_key=idempotency_key,
                    source_type="skins_v3", reference_type="skin_v3", reference_id=skin_id,
                    metadata={"skin_id": skin_id, "ceiling": skin["tier"], "price_zarniki": price}, note=skin_id)
                await repo.grant(db, user_id, skin_id)
            await repo.set_equipped(db, user_id, skin_id)
    except InsufficientBalance as exc:
        raise SkinConflict(f"Нужно {price}✨ для этого скина.") from exc
    except IdempotencyConflict as exc:
        raise SkinConflict("Этот запрос уже использован для другой покупки.") from exc
    return f"Скин «{skin['name']}» ваш. Он начинает с тира D и растёт за Эссенцию.", await state(db, user_id)


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
        if applied:
            await repo.set_tier(db, user_id, skin_id, target)
    return f"«{skin['name']}» теперь тир {target}.", await state(db, user_id)


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
