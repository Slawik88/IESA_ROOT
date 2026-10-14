"""Shop screen (ECO-04 PR-B): one catalogue view and one buy entry point behind the ``shop_v1`` flag.

Polish (Шлифовка) is the shop's own purchase and follows the chest offer template:
lock -> replay -> flag -> catalog -> window -> limit -> shortages -> ledger debit ->
Essence credit -> append-only receipt, all in one transaction. Keys are sold by
``chests_v1.buy_offer`` and exchanges by ``zarniki_exchange_v1.exchange`` unchanged:
the shop only maps its item id onto them and keeps one action id from being reused
across the three stores.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta
import json
import math
from uuid import uuid4

from core import shop_v1 as policy
from core.chests_v1 import (
    CATALOG_VERSION as CHEST_CATALOG_VERSION, KEY_TIER_NAMES, ChestPolicyError,
    canonical_snapshot_fingerprint, catalog_digest as chest_catalog_digest, tier_star_odds,
)
from core.economy_contract import IdempotencyConflict, InsufficientBalance
from core.zarniki_exchange_v1 import DAILY_ZARNIKI_CAP, ZarnikiExchangePolicyError
from infrastructure.repositories import economy_ledger, system_flags
from infrastructure.repositories import chests_v1 as chests_repo
from infrastructure.repositories import shop_v1 as repo
from infrastructure.repositories import skins_v3 as essence_repo
from infrastructure.repositories import zarniki_exchange_v1 as exchange_repo
from services import chests_v1, zarniki_exchange_v1


CLOSED = "Магазин пока закрыт"
CHESTS_FLAG = "content_chests_v1"
_ICONS = {"mora": "🪙", "diamonds": "💎", "zarniki": "✨", "essence": "🔮"}
_KINDS = {"keys": "key", "essence": "polish", "exchange": "exchange"}


class ShopClosed(LookupError):
    """The shop flag is off: the screen and every purchase answer 404."""


class ShopConflict(ValueError):
    """The purchase is well-formed but refused by the catalogue or durable state."""


def _action_id(value: object) -> str:
    normalized = str(value or "").strip()
    if not normalized or len(normalized) > 96 or any(ord(char) < 32 for char in normalized):
        raise ShopConflict("action_id обязателен и должен быть безопасным идентификатором.")
    return normalized


async def enabled(db) -> bool:
    return await system_flags.is_enabled(db, policy.FLAG)


async def keys_enabled(db) -> bool:
    """Keys follow the chest screen: tiered offers (pets_level_up_v1) and the chests themselves."""
    return await chests_v1.offers_enabled(db) and await system_flags.is_enabled(db, CHESTS_FLAG)


async def ensure_ready(db) -> None:
    await repo.ensure_tables(db)
    await essence_repo.ensure_tables(db)
    await exchange_repo.ensure_tables(db)


async def _balances(db, user_id: int) -> dict[str, float]:
    from infrastructure.repositories import economy as economy_repo
    balance = await economy_repo.get_balance(db, int(user_id))
    return {"mora": float(balance["user_balance_mora"] or 0),
            "diamonds": float(balance["user_balance_diamonds"] or 0),
            "zarniki": float(balance.get("user_balance_zarniki") or 0),
            "essence": float(await essence_repo.essence_balance(db, int(user_id)))}


def missing(cost: dict, have: dict) -> dict[str, int]:
    """Whole units still needed per currency; a fractional gap rounds up, never to 0."""
    return {currency: math.ceil(float(amount) - have[currency])
            for currency, amount in cost.items() if have[currency] < float(amount)}


def missing_text(gaps: dict[str, int]) -> str:
    return "Не хватает: " + ", ".join(f"{amount} {_ICONS[currency]}" for currency, amount in gaps.items()) + "."


def _resets_in(period: str, day, week, now: datetime) -> int:
    start = day + timedelta(days=1) if period == "day" else week + timedelta(days=7)
    return max(0, math.ceil((datetime.combine(start, time.min) - now.replace(tzinfo=None)).total_seconds()))


def _number(value: float) -> float | int:
    return int(value) if float(value).is_integer() else float(value)


async def overview(db, *, user_id: int) -> dict:
    if not await enabled(db):
        raise ShopClosed(CLOSED)
    await ensure_ready(db)
    user_id = int(user_id)
    day, week, now = await repo.window(db)
    have = await _balances(db, user_id)
    keys_on = await keys_enabled(db)
    offers = {row["offer_id"]: row for row in await chests_v1._offers_public(db, user_id)} if keys_on else {}
    polish_used = await repo.purchases_in_week(db, user_id=user_id, item_id=policy.POLISH_ITEM, week=week)
    exchange_used = await exchange_repo.usage_today(db, user_id)
    exchange_left = max(0, DAILY_ZARNIKI_CAP - exchange_used)
    sections = {section: [] for section, _name in policy.SECTIONS}
    for row in policy.items():
        item = {key: value for key, value in row.items() if key not in {"offer_id", "target"}}
        limit = dict(row["limit"])
        if row["section"] == "keys":
            used = int(offers.get(str(row["offer_id"]), {}).get("used", 0))
            top = tier_star_odds(int(row["tier"]))[0]
            item["odds"] = {"stars": int(top["stars"]), "percent": top["percent"]}
            reason = None if keys_on else "Ключи по звёздам пока недоступны."
        elif row["section"] == "essence":
            used, reason = polish_used, None
        else:
            used, reason = exchange_used, None
        limit.update(used=used, left=max(0, int(limit["max"]) - used),
                     resets_in_seconds=_resets_in(str(limit["period"]), day, week, now))
        gaps = missing(dict(row["cost"]), have)
        item.update(limit=limit, missing=gaps, affordable=not gaps,
                    available=reason is None and limit["left"] > 0, unavailable_reason=reason)
        if row["section"] == "exchange":
            item["max_amount"] = max(0, min(exchange_left, math.floor(have["zarniki"])))
        sections[str(row["section"])].append(item)
    pass_on = await system_flags.is_enabled(db, "season_pass_v1")
    links = [link for link in policy.links() if not link["flag"] or (link["flag"] == "season_pass_v1" and pass_on)]
    tiers = await chests_repo.tier_balances(db, user_id)
    return {
        "shop_version": policy.SHOP_VERSION, "catalog_version": policy.SHOP_VERSION,
        "catalog_digest": policy.catalog_digest(), "day_boundary": "UTC",
        "balances": {**{currency: _number(amount) for currency, amount in have.items()},
                     "keys": {str(tier): int(count) for tier, count in tiers.items()}},
        "keys_enabled": keys_on,
        "key_odds": [{"tier": tier, "name": KEY_TIER_NAMES[tier], "stars": tier,
                      "percent": tier_star_odds(tier)[0]["percent"]} for tier in (4, 6)],
        "exchange": {"daily_cap": DAILY_ZARNIKI_CAP, "used_today": exchange_used, "left": exchange_left},
        "sections": [{"id": section, "name": name, "items": sections[section]} for section, name in policy.SECTIONS],
        "links": [{key: value for key, value in link.items() if key != "flag"} for link in links],
    }


def _receipt(row: dict, *, applied: bool) -> dict:
    def _json(value):
        return json.loads(value) if isinstance(value, str) else dict(value or {})
    return {"purchase_id": str(row["id"]), "applied": applied, "item_id": str(row["item_id"]),
            "price": {k: int(v) for k, v in _json(row["price"]).items()},
            "gives": {k: int(v) for k, v in _json(row["gives"]).items()},
            "shop_version": str(row["shop_version"]), "economy_operation_id": str(row["economy_operation_id"]),
            "purchased_on": str(row["purchased_on"]), "purchased_week": str(row["purchased_week"])}


async def buy_polish(
    db, *, user_id: int, action_id: str, requested_catalog_version: str, requested_catalog_digest: str,
) -> dict:
    """600 Mora + 1 Diamond -> 60 Essence: limit, both debits, the credit and the receipt commit together."""
    action_id = _action_id(action_id)
    user_id = int(user_id)
    price = {k: int(v) for k, v in dict(policy.POLISH["price"]).items()}
    gives = {"essence": int(policy.POLISH["essence"])}
    # The hash leaves the catalogue digest out: a retry after a deploy that changed other prices still finds its receipt.
    request_hash = canonical_snapshot_fingerprint({"item_id": policy.POLISH_ITEM, "price": price})
    await essence_repo.ensure_tables(db)
    await repo.ensure_tables(db)
    async with db.connection.transaction():
        await repo.lock_user(db, user_id)
        replay = await repo.find_purchase(db, user_id=user_id, action_id=action_id)
        if replay:
            if str(replay["request_hash"]) != request_hash:
                raise ShopConflict("action_id уже использован для другой покупки.")
            return _receipt(replay, applied=False)
        if not await enabled(db):
            raise ShopClosed(CLOSED)
        if (str(requested_catalog_version) != policy.SHOP_VERSION
                or str(requested_catalog_digest) != policy.catalog_digest()):
            raise ShopConflict("Каталог магазина изменился. Обнови экран перед покупкой.")
        day, week, _now = await repo.window(db)
        limit = int(policy.POLISH["limit"])
        if await repo.purchases_in_week(db, user_id=user_id, item_id=policy.POLISH_ITEM, week=week) >= limit:
            raise ShopConflict(f"Лимит на этой неделе исчерпан: {limit} из {limit}.")
        gaps = missing(price, await _balances(db, user_id))
        if gaps:
            raise ShopConflict(missing_text(gaps))
        purchase_id = uuid4().hex
        idempotency_key = f"shop-polish:{purchase_id}"
        try:
            mutation = await economy_ledger.apply_balance_change(
                db, user_id, {k: -v for k, v in price.items()}, reason_code=policy.POLISH_REASON_CODE,
                idempotency_key=idempotency_key, source_type="shop_v1", reference_type="shop_purchase",
                reference_id=purchase_id,
                metadata={"shop_version": policy.SHOP_VERSION, "catalog_digest": policy.catalog_digest(),
                          "item_id": policy.POLISH_ITEM, "price": price, "gives": gives},
                note=f"Шлифовка: +{gives['essence']} Эссенции",
            )
        except InsufficientBalance as exc:
            raise ShopConflict("Не хватает валюты для покупки.") from exc
        await essence_repo.essence_apply(
            db, user_id, gives["essence"], reason=policy.POLISH_REASON_CODE, reference=purchase_id,
            idempotency_key=idempotency_key,
        )
        await repo.create_purchase(
            db, purchase_id=purchase_id, user_id=user_id, action_id=action_id, item_id=policy.POLISH_ITEM,
            request_hash=request_hash, shop_version=policy.SHOP_VERSION, catalog_digest=policy.catalog_digest(),
            price=price, gives=gives, economy_operation_id=str(mutation.operation_id), day=day, week=week,
        )
        row = await repo.find_purchase(db, user_id=user_id, action_id=action_id)
        if not row:
            raise RuntimeError("Shop receipt was not persisted.")
        return _receipt(row, applied=True)


async def buy(
    db, *, user_id: int, item_id: str, action_id: str, catalog_version: str, catalog_digest: str,
    amount: int | None = None,
) -> dict:
    """Dispatch one purchase by item kind. One action id belongs to one store and one item."""
    action_id = _action_id(action_id)
    user_id = int(user_id)
    try:
        item = policy.item(item_id)
    except policy.ShopPolicyError as exc:
        raise ShopConflict(str(exc)) from exc
    kind = _KINDS[str(item["section"])]
    if kind == "exchange":
        if isinstance(amount, bool) or not isinstance(amount, int) or not 1 <= amount <= DAILY_ZARNIKI_CAP:
            raise ShopConflict(f"Сумма обмена — целое число Зарников от 1 до {DAILY_ZARNIKI_CAP}.")
    elif amount not in (None, 1):
        raise ShopConflict("Этот товар покупается по одному.")
    await ensure_ready(db)
    async with db.connection.transaction():
        await repo.lock_user(db, user_id)
        owner = await repo.action_owner(db, user_id=user_id, action_id=action_id)
        if owner is not None and owner != kind:
            raise ShopConflict("action_id уже использован для другой покупки.")
        if owner is None:  # a replay is answered by its own store, even after the flag or catalogue changed
            if not await enabled(db):
                raise ShopClosed(CLOSED)
            if str(catalog_version) != policy.SHOP_VERSION or str(catalog_digest) != policy.catalog_digest():
                raise ShopConflict("Каталог магазина изменился. Обнови экран перед покупкой.")
            if kind == "key" and not await keys_enabled(db):
                raise ShopConflict("Ключи по звёздам пока недоступны.")
        try:
            if kind == "polish":
                receipt = await buy_polish(db, user_id=user_id, action_id=action_id,
                                           requested_catalog_version=catalog_version,
                                           requested_catalog_digest=catalog_digest)
            elif kind == "key":
                receipt = await chests_v1.buy_offer(
                    db, user_id=user_id, offer_id=str(item["offer_id"]), action_id=action_id,
                    requested_catalog_version=CHEST_CATALOG_VERSION, requested_catalog_digest=chest_catalog_digest(),
                )
            else:
                receipt = await zarniki_exchange_v1.exchange(
                    db, user_id=user_id, zarniki=int(amount), target=str(item["target"]), action_id=action_id,
                )
        except (ShopClosed, ShopConflict):
            raise
        except IdempotencyConflict as exc:  # the ledger's own message is English and internal
            raise ShopConflict("action_id уже использован для другой покупки.") from exc
        except (chests_v1.ChestKeyConflict, ChestPolicyError, ZarnikiExchangePolicyError,
                InsufficientBalance) as exc:
            raise ShopConflict(str(exc)) from exc
    return {"ok": True, "item_id": str(item["id"]), "mode": str(item["mode"]), "section": str(item["section"]),
            "receipt": receipt, "balances": await _balances(db, user_id)}
