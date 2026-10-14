"""Server-authoritative mixed chest purchase, delivery and reveal."""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
import secrets
from uuid import uuid4

from core.chests_v1 import (
    CATALOG_VERSION, FOODS, KEY_OFFERS, KEY_OFFERS_FLAG, KEY_TIER_NAMES, KEY_TIERS,
    PAID_KEY_DAILY_LIMIT, PAID_KEY_PRICE_ZARNIKI,
    PET_SPECIES, POLICY_VERSION, STAR_WEIGHTS, VIP_COSMETIC_POOL, KeyGrant,
    catalog_digest, canonical_snapshot_fingerprint, key_tier as checked_key_tier, public_reward_rows,
    roll_outcome, tier_for_source, tier_star_odds, validate_key_grant,
)
from core.cosmetics import COSMETICS
from core.economy_contract import InsufficientBalance
from infrastructure.repositories import economy_ledger, system_flags
from infrastructure.repositories import chests_v1 as repo
from infrastructure.repositories import skins_v3 as essence_repo
from services import vip


class ChestKeyConflict(ValueError):
    """A source identity was replayed with different immutable facts."""


@dataclass(frozen=True, slots=True)
class KeyGrantReceipt:
    grant_id: str
    applied: bool
    amount: int
    balance_before: int
    balance_after: int


def _action_id(value: object) -> str:
    normalized = str(value or "").strip()
    if not normalized or len(normalized) > 96 or any(ord(char) < 32 for char in normalized):
        raise ValueError("action_id обязателен и должен быть безопасным идентификатором.")
    return normalized


def _same_facts(row: dict, grant: KeyGrant, user_id: int, snapshot_hash: str) -> bool:
    return (
        int(row["user_id"]) == int(user_id)
        and int(row["amount"]) == grant.amount
        and str(row["policy_version"]) == POLICY_VERSION
        and str(row["source_snapshot_hash"]) == snapshot_hash
    )


async def grant_quest_completion_key(
    db, *, user_id: int, reward_kind: str, reward_id: str,
) -> KeyGrantReceipt:
    async with db.connection.transaction():
        await repo.lock_user(db, int(user_id))
        return await grant_quest_completion_key_in_transaction(
            db, user_id=int(user_id), reward_kind=reward_kind, reward_id=reward_id,
        )


async def grant_quest_completion_key_in_transaction(
    db, *, user_id: int, reward_kind: str, reward_id: str,
) -> KeyGrantReceipt:
    """Typed adapter: only a daily/weekly quest-set receipt can mint a key."""
    await repo.assert_delivery_ready(db)
    if reward_kind not in {"daily", "weekly"}:
        raise ValueError("Only daily or weekly quest completion can grant a key.")
    receipt = await repo.quest_reward_receipt(
        db, user_id=int(user_id), reward_id=str(reward_id),
    )
    expected_prefix = f"{reward_kind}:"
    if not receipt or not str(reward_id).startswith(expected_prefix):
        raise ValueError("A typed quest reward receipt is required before granting its key.")
    if str(receipt.get("reward_kind") or "") != reward_kind:
        raise ValueError("Quest reward kind does not match its durable receipt.")
    required = ("quest_policy_version", "reward_policy_version", "amount_mora")
    if any(receipt.get(field) is None for field in required):
        raise ValueError("Legacy or incomplete quest receipts cannot mint chest keys.")
    metadata = receipt.get("metadata_json") or {}
    if isinstance(metadata, str):
        import json
        metadata = json.loads(metadata)
    expected_operation = (
        str(receipt.get("reason_code")) == "quest_reward"
        and str(receipt.get("source_type")) == "quest"
        and str(receipt.get("reference_type")) == "quest_reward"
        and str(receipt.get("reference_id")) == str(reward_id)
        and str(metadata.get("reward_kind")) == reward_kind
        and str(metadata.get("reward_id")) == str(reward_id)
        and str(metadata.get("policy_version")) == str(receipt["reward_policy_version"])
        and int(metadata.get("amount_mora", -1)) == int(receipt["amount_mora"])
        and int(receipt.get("ledger_amount", -1)) == int(receipt["amount_mora"])
    )
    if not expected_operation:
        raise ValueError("Quest receipt does not match its canonical economic operation.")
    grant = KeyGrant(
        source_kind=f"quest_{reward_kind}_set_complete",
        source_event_id=str(reward_id), amount=1,
        source_snapshot={
            "quest_policy_version": str(receipt["quest_policy_version"]),
            "reward_policy_version": str(receipt["reward_policy_version"]),
            "reward_id": str(reward_id), "reward_kind": reward_kind,
            "amount_mora": int(receipt["amount_mora"]), "amount_keys": 1,
        },
    )
    grant = validate_key_grant(grant)
    snapshot_hash = canonical_snapshot_fingerprint(grant.source_snapshot)
    replay = await repo.find_grant(
        db, user_id=int(user_id), source_kind=grant.source_kind,
        source_event_id=grant.source_event_id,
    )
    if replay:
        if not _same_facts(replay, grant, int(user_id), snapshot_hash):
            raise ChestKeyConflict("Chest-key source identity is bound to different facts.")
        total = await repo.grant_total(
            db, user_id=int(user_id), source_kind=grant.source_kind,
            source_event_id=grant.source_event_id)
        return KeyGrantReceipt(
            grant_id=str(replay["id"]), applied=False, amount=total,
            balance_before=int(replay["balance_before"]),
            balance_after=int(replay["balance_before"]) + total,
        )
    account = await repo.lock_account(db, int(user_id))
    before = int(account["balance"])
    grant_id = uuid4().hex
    after = await repo.apply_grant(
        db, grant_id=grant_id, user_id=int(user_id), source_kind=grant.source_kind,
        source_event_id=grant.source_event_id, amount=grant.amount,
        policy_version=POLICY_VERSION, source_snapshot=dict(grant.source_snapshot),
        source_snapshot_hash=snapshot_hash, balance_before=before,
        account_epoch=int(account["account_epoch"]),
    )
    after = await repo.apply_bonus_grants(
        db, user_id=int(user_id), source_kind=grant.source_kind,
        source_event_id=grant.source_event_id, policy_version=POLICY_VERSION,
        source_snapshot=dict(grant.source_snapshot), source_snapshot_hash=snapshot_hash,
        balance_before=after, account_epoch=int(account["account_epoch"]),
    )
    return KeyGrantReceipt(
        grant_id=grant_id, applied=True, amount=after - before,
        balance_before=before, balance_after=after,
    )


async def overview(db, *, user_id: int) -> dict:
    await repo.assert_delivery_ready(db)
    pending = await repo.latest_unrevealed_open(db, user_id=int(user_id))
    latest = await repo.latest_revealed_open(db, user_id=int(user_id))
    paid_today = await repo.paid_purchases_today(db, user_id=int(user_id))
    tiers_on = await offers_enabled(db)
    return {
        "policy_version": POLICY_VERSION,
        "catalog_version": CATALOG_VERSION,
        "catalog_digest": catalog_digest(),
        "key_balance": await repo.get_balance(db, int(user_id)),
        "key_balances": {str(tier): count for tier, count in (await repo.tier_balances(db, int(user_id))).items()},
        "key_tiers": [{"tier": tier, "name": KEY_TIER_NAMES[tier], "star_odds": tier_star_odds(tier)}
                      for tier in KEY_TIERS],
        "tiers_enabled": tiers_on,
        "offers": await _offers_public(db, int(user_id)) if tiers_on else [],
        "locked_paid_keys": 0,
        "pending_open": _prepared(pending) if pending else None,
        "last_result": _revealed(latest) if latest else None,
        "funding": {
            "free_key": True, "paid": not tiers_on, "price_zarniki": PAID_KEY_PRICE_ZARNIKI,
            "daily_limit": PAID_KEY_DAILY_LIMIT, "purchased_today": paid_today,
            "remaining_today": max(0, PAID_KEY_DAILY_LIMIT - paid_today), "day_boundary": "UTC",
        },
        "star_odds": [
            {"stars": stars, "basis_points": weight, "percent": weight / 100}
            for stars, weight in STAR_WEIGHTS.items()
        ],
        "rewards": public_reward_rows(),
        "inventory": await repo.inventory_summary(db, user_id=int(user_id)),
        "message": ("Ключ уровня N открывает тот же сундук, но звёзды ниже N становятся N. "
                    "Сервер фиксирует одну награду до раскрытия." if tiers_on else
                    "Бесплатный и купленный ключи имеют одинаковые шансы. Сервер фиксирует одну награду до раскрытия."),
        "surplus_policy": "Лишние карты сохраняются. Обмен и компенсация появятся только после отдельного предрелизного решения.",
    }


def _row_tier(row: dict) -> int:
    kind = row.get("key_source_kind")
    return tier_for_source(str(kind)) if kind else 1


def _prepared(row: dict) -> dict:
    return {
        "open_id": str(row["id"]),
        "key_tier": _row_tier(row),
        "catalog_version": str(row["catalog_version"]),
        "catalog_digest": str(row["catalog_digest"]),
        "key_balance": int(row["key_balance_after"]),
        "sealed": not bool(row.get("revealed")),
    }


def _revealed(row: dict) -> dict:
    return {
        "open_id": str(row["id"]), "catalog_version": str(row["catalog_version"]),
        "catalog_digest": str(row["catalog_digest"]), "stars": int(row["stars"]),
        "key_tier": _row_tier(row), "reward": _reward_public(row),
        "key_balance": int(row["key_balance_after"]), "revealed": True,
    }


def _reward_public(row: dict) -> dict:
    kind = str(row["reward_kind"])
    ref = str(row.get("reward_ref") or "") or None
    labels = {"mora": "Мора", "diamonds": "Алмазы", "zarniki": "Зарники",
              "food": "Еда", "pet_card": "Карты питомца", "joker": "Джокер",
              "vip_days": "VIP", "vip_cosmetic": "VIP-образ"}
    icon = {"mora": "🪙", "diamonds": "💎", "zarniki": "✨", "food": "🍲",
            "pet_card": "🐾", "joker": "🃏", "vip_days": "👑", "vip_cosmetic": "🎨"}.get(kind, "🎁")
    name = labels.get(kind, kind)
    if kind == "food" and ref in FOODS:
        name, icon = str(FOODS[ref]["name"]), str(FOODS[ref]["icon"])
    elif kind == "pet_card" and ref in PET_SPECIES:
        name, icon = str(PET_SPECIES[ref]["name"]), str(PET_SPECIES[ref]["icon"])
    elif kind == "joker" and ref:
        name = f"Джокер · {ref}"
    elif kind == "vip_cosmetic" and ref in COSMETICS:
        name = str(COSMETICS[ref].get("name") or "VIP-образ")
    return {"kind": kind, "ref": ref, "amount": int(row["reward_amount"]),
            "rarity": row.get("reward_rarity"), "name": name, "icon": icon}


async def purchase_key(
    db, *, user_id: int, action_id: str, requested_catalog_version: str,
    requested_catalog_digest: str,
) -> dict:
    """Buy one traceable entitlement. Retries never debit or consume quota twice."""
    await repo.assert_delivery_ready(db)
    action_id = _action_id(action_id)
    request_hash = canonical_snapshot_fingerprint({
        "catalog_version": str(requested_catalog_version),
        "catalog_digest": str(requested_catalog_digest), "price_zarniki": PAID_KEY_PRICE_ZARNIKI,
    })
    async with db.connection.transaction():
        await repo.lock_user(db, int(user_id))
        replay = await repo.find_purchase(db, user_id=int(user_id), action_id=action_id)
        if replay:
            if str(replay["request_hash"]) != request_hash:
                raise ChestKeyConflict("action_id уже использован для другой покупки.")
            return {"purchase_id": str(replay["id"]), "applied": False,
                    "key_balance": int(replay["balance_after"]), "price_zarniki": int(replay["price_zarniki"])}
        if await offers_enabled(db):
            raise ChestKeyConflict("Ключ за 10 ✨ заменён Серебряным ключом. Обнови экран.")
        if (str(requested_catalog_version) != CATALOG_VERSION
                or str(requested_catalog_digest) != catalog_digest()):
            raise ChestKeyConflict("Каталог изменился. Обнови экран перед покупкой.")
        if await repo.paid_purchases_today(db, user_id=int(user_id)) >= PAID_KEY_DAILY_LIMIT:
            raise ChestKeyConflict("Сегодня уже куплены два ключа. Новый лимит откроется в 00:00 UTC.")
        account = await repo.lock_account(db, int(user_id))
        purchase_id = uuid4().hex
        mutation = await economy_ledger.apply_balance_change(
            db, int(user_id), {"zarniki": -PAID_KEY_PRICE_ZARNIKI},
            reason_code="chest_key_purchase", idempotency_key=f"chest-key:{purchase_id}",
            source_type="chest_v1", reference_type="chest_key_purchase", reference_id=purchase_id,
            metadata={"policy_version": POLICY_VERSION, "catalog_version": CATALOG_VERSION,
                      "catalog_digest": catalog_digest(), "price_zarniki": PAID_KEY_PRICE_ZARNIKI},
            note="Покупка ключа сундука",
        )
        await repo.create_purchase(
            db, purchase_id=purchase_id, user_id=int(user_id), action_id=action_id,
            request_hash=request_hash, catalog_version=CATALOG_VERSION, catalog_digest=catalog_digest(),
            price_zarniki=PAID_KEY_PRICE_ZARNIKI, economy_operation_id=str(mutation.operation_id),
        )
        snapshot = {"purchase_id": purchase_id, "catalog_version": CATALOG_VERSION,
                    "catalog_digest": catalog_digest(), "price_zarniki": PAID_KEY_PRICE_ZARNIKI}
        grant_id = uuid4().hex
        after = await repo.apply_grant(
            db, grant_id=grant_id, user_id=int(user_id), source_kind="zarniki_purchase",
            source_event_id=purchase_id, amount=1, policy_version=POLICY_VERSION,
            source_snapshot=snapshot, source_snapshot_hash=canonical_snapshot_fingerprint(snapshot),
            balance_before=int(account["balance"]), account_epoch=int(account["account_epoch"]),
        )
        return {"purchase_id": purchase_id, "applied": True, "key_balance": after,
                "price_zarniki": PAID_KEY_PRICE_ZARNIKI}


async def refund_unused_purchase(
    db, *, user_id: int, purchase_id: str, action_id: str,
    reason: str = "delivery_failure",
) -> dict:
    """Server/support-only refund. A spent or already refunded key is immutable."""
    await repo.assert_delivery_ready(db)
    action_id = _action_id(action_id)
    purchase_id = _action_id(purchase_id)
    if reason not in {"delivery_failure", "owner_approved_support"}:
        raise ValueError("Некорректная причина возврата.")
    request_hash = canonical_snapshot_fingerprint({"purchase_id": purchase_id, "reason": reason})
    async with db.connection.transaction():
        await repo.lock_user(db, int(user_id))
        replay = await repo.find_refund(db, user_id=int(user_id), action_id=action_id)
        if replay:
            if str(replay["request_hash"]) != request_hash:
                raise ChestKeyConflict("action_id уже использован для другого возврата.")
            return {"refund_id": str(replay["id"]), "applied": False,
                    "amount_zarniki": int(replay["amount_zarniki"]),
                    "key_balance": int(replay["balance_after"])}
        purchase = await repo.refundable_purchase(
            db, user_id=int(user_id), purchase_id=purchase_id,
        )
        if not purchase:
            raise ChestKeyConflict("Покупка не найдена, ключ уже использован или возврат выполнен.")
        account = await repo.lock_account(db, int(user_id))
        if int(purchase["grant_account_epoch"]) != int(account["account_epoch"]):
            raise ChestKeyConflict("Ключ относится к завершённому игровому аккаунту.")
        refund_id = uuid4().hex
        amount = int(purchase["price_zarniki"])
        mutation = await economy_ledger.apply_balance_change(
            db, int(user_id), {"zarniki": amount}, reason_code="chest_key_refund",
            idempotency_key=f"chest-key-refund:{refund_id}", source_type="chest_v1",
            reference_type="chest_key_purchase", reference_id=purchase_id,
            metadata={"policy_version": POLICY_VERSION, "purchase_id": purchase_id,
                      "refund_id": refund_id, "reason": reason, "amount_zarniki": amount},
            note="Возврат неиспользованного ключа сундука",
        )
        after = await repo.apply_refund(
            db, refund_id=refund_id, user_id=int(user_id), purchase_id=purchase_id,
            action_id=action_id, request_hash=request_hash, amount_zarniki=amount,
            economy_operation_id=str(mutation.operation_id), reason=reason,
            grant_id=str(purchase["grant_id"]), balance_before=int(account["balance"]),
        )
        return {"refund_id": refund_id, "applied": True,
                "amount_zarniki": amount, "key_balance": after}


async def offers_enabled(db) -> bool:
    """Tiered key offers share the pet level-up switch: no paid tiers before cards have a sink."""
    return await system_flags.is_enabled(db, KEY_OFFERS_FLAG)


_PRICE_NAMES = {"mora": "Моры", "diamonds": "💎", "zarniki": "✨", "essence": "Эссенции"}


async def _offers_public(db, user_id: int) -> list[dict]:
    day, week = await repo.offer_window(db)
    legacy_today = await repo.legacy_purchases_on(db, user_id=int(user_id), day=day)
    rows = []
    for offer_id, offer in KEY_OFFERS.items():
        used = await repo.offer_purchases_in_window(
            db, user_id=int(user_id), offer_id=offer_id, window=str(offer["window"]), day=day, week=week)
        if offer_id == "silver_zarniki":
            used += legacy_today
        rows.append({"offer_id": offer_id, "key_tier": int(offer["tier"]),
                     "name": KEY_TIER_NAMES[int(offer["tier"])], "price": dict(offer["price"]),
                     "limit": int(offer["limit"]), "window": str(offer["window"]), "used": used,
                     "remaining": max(0, int(offer["limit"]) - used), "day_boundary": "UTC"})
    return rows


async def _shortages(db, user_id: int, price: dict) -> list[str]:
    from infrastructure.repositories import economy as economy_repo
    balance = await economy_repo.get_balance(db, int(user_id))
    have = {"mora": float(balance["user_balance_mora"] or 0),
            "diamonds": float(balance["user_balance_diamonds"] or 0),
            "zarniki": float(balance.get("user_balance_zarniki") or 0),
            "essence": float(await essence_repo.essence_balance(db, int(user_id)))}
    return [f"{math.ceil(amount - have[currency])} {_PRICE_NAMES[currency]}"
            for currency, amount in price.items() if have[currency] < amount]


def _stored_price(value) -> dict[str, int]:
    if isinstance(value, str):
        value = json.loads(value)
    return {str(k): int(v) for k, v in dict(value or {}).items()}


async def buy_offer(
    db, *, user_id: int, offer_id: str, action_id: str, requested_catalog_version: str,
    requested_catalog_digest: str,
) -> dict:
    """Buy one tiered key: limit, all-currency debit and the key grant commit together."""
    await repo.assert_delivery_ready(db)
    action_id = _action_id(action_id)
    offer_id = str(offer_id or "").strip()
    if offer_id not in KEY_OFFERS:
        raise ChestKeyConflict("Такого ключа в продаже нет.")
    offer = KEY_OFFERS[offer_id]
    tier, price = int(offer["tier"]), {k: int(v) for k, v in dict(offer["price"]).items()}
    request_hash = canonical_snapshot_fingerprint({
        "offer_id": offer_id, "catalog_version": str(requested_catalog_version),
        "catalog_digest": str(requested_catalog_digest), "price": price,
    })
    await essence_repo.ensure_tables(db)
    async with db.connection.transaction():
        await repo.lock_user(db, int(user_id))
        replay = await repo.find_offer_purchase(db, user_id=int(user_id), action_id=action_id)
        if replay:
            if str(replay["request_hash"]) != request_hash:
                raise ChestKeyConflict("action_id уже использован для другой покупки.")
            return {"purchase_id": str(replay["id"]), "applied": False, "offer_id": offer_id,
                    "key_tier": tier, "key_balance": int(replay["balance_after"]), "price": _stored_price(replay["price"])}
        if not await offers_enabled(db):
            raise ChestKeyConflict("Ключи по звёздам пока недоступны.")
        if (str(requested_catalog_version) != CATALOG_VERSION
                or str(requested_catalog_digest) != catalog_digest()):
            raise ChestKeyConflict("Каталог изменился. Обнови экран перед покупкой.")
        day, week = await repo.offer_window(db)
        used = await repo.offer_purchases_in_window(
            db, user_id=int(user_id), offer_id=offer_id, window=str(offer["window"]), day=day, week=week)
        if offer_id == "silver_zarniki":  # PAID_KEY_DAILY_LIMIT also counts legacy 10 ✨ keys of the day
            used += await repo.legacy_purchases_on(db, user_id=int(user_id), day=day)
        if used >= int(offer["limit"]):
            period = "сегодня" if offer["window"] == "day" else "на этой неделе"
            raise ChestKeyConflict(f"Лимит {period} исчерпан: {offer['limit']} из {offer['limit']}.")
        account = await repo.lock_account(db, int(user_id))
        missing = await _shortages(db, int(user_id), price)
        if missing:
            raise ChestKeyConflict("Не хватает: " + ", ".join(missing) + ".")
        purchase_id = uuid4().hex
        metadata = {"policy_version": POLICY_VERSION, "catalog_version": CATALOG_VERSION,
                    "catalog_digest": catalog_digest(), "offer_id": offer_id, "key_tier": tier, "price": price}
        ledger_price = {k: -v for k, v in price.items() if k != "essence"}
        try:
            mutation = await economy_ledger.apply_balance_change(
                db, int(user_id), ledger_price, reason_code=f"chest_key_offer_{offer_id}",
                idempotency_key=f"chest-offer:{purchase_id}", source_type="chest_v1",
                reference_type="chest_key_offer", reference_id=purchase_id, metadata=metadata,
                note=f"Покупка ключа: {KEY_TIER_NAMES[tier]}",
            )
        except InsufficientBalance as exc:
            raise ChestKeyConflict("Не хватает валюты для покупки.") from exc
        essence = price.get("essence", 0)
        if essence:
            try:
                await essence_repo.essence_apply(
                    db, int(user_id), -essence, reason=f"chest_key_offer_{offer_id}",
                    reference=purchase_id, idempotency_key=f"chest-offer:{purchase_id}",
                )
            except ValueError as exc:
                raise ChestKeyConflict(f"Не хватает: {essence} Эссенции.") from exc
        snapshot = {"purchase_id": purchase_id, "offer_id": offer_id, "key_tier": tier, "price": price,
                    "catalog_version": CATALOG_VERSION, "catalog_digest": catalog_digest()}
        grant_id = uuid4().hex
        after = await repo.apply_grant(
            db, grant_id=grant_id, user_id=int(user_id), source_kind=f"offer_{offer_id}",
            source_event_id=purchase_id, amount=1, policy_version=POLICY_VERSION,
            source_snapshot=snapshot, source_snapshot_hash=canonical_snapshot_fingerprint(snapshot),
            balance_before=int(account["balance"]), account_epoch=int(account["account_epoch"]),
        )
        await repo.create_offer_purchase(
            db, purchase_id=purchase_id, user_id=int(user_id), action_id=action_id, offer_id=offer_id,
            key_tier=tier, request_hash=request_hash, catalog_version=CATALOG_VERSION,
            catalog_digest=catalog_digest(), price=price, economy_operation_id=str(mutation.operation_id),
            essence_spent=essence, grant_id=grant_id, day=day, week=week,
        )
        return {"purchase_id": purchase_id, "applied": True, "offer_id": offer_id,
                "key_tier": tier, "key_balance": after, "price": price}


async def prepare_free_open(
    db, *, user_id: int, action_id: str, requested_catalog_version: str,
    requested_catalog_digest: str, key_tier: int = 1,
) -> dict:
    """Consume one key of ``key_tier`` and persist one sealed outcome in the same transaction."""
    await repo.assert_delivery_ready(db)
    action_id = _action_id(action_id)
    key_tier = checked_key_tier(key_tier)
    requested_catalog_version = str(requested_catalog_version or "").strip()
    requested_catalog_digest = str(requested_catalog_digest or "").strip()
    request = {
        "funding": "free_key", "catalog_version": requested_catalog_version,
        "catalog_digest": requested_catalog_digest,
    }
    if key_tier != 1:  # tier-1 requests keep their pre-tier hash, so old retries still replay
        request["key_tier"] = key_tier
    request_hash = canonical_snapshot_fingerprint(request)
    async with db.connection.transaction():
        await repo.lock_user(db, int(user_id))
        replay = await repo.find_open_by_action(db, user_id=int(user_id), action_id=action_id)
        if replay:
            if str(replay["request_hash"]) != request_hash:
                raise ChestKeyConflict("action_id уже использован для другого открытия.")
            return _prepared(replay)
        if (requested_catalog_version != CATALOG_VERSION
                or requested_catalog_digest != catalog_digest()):
            raise ChestKeyConflict("Каталог сундука изменился. Обнови экран перед открытием.")
        account = await repo.lock_account(db, int(user_id))
        before = int(account["balance"])
        if before < 1:
            raise ChestKeyConflict("Нужен один ключ от сундука.")
        if (await repo.tier_balances(db, int(user_id)))[key_tier] < 1:
            raise ChestKeyConflict("Нет ключа этого уровня.")
        grant = await repo.next_unspent_grant(
            db, user_id=int(user_id), account_epoch=int(account["account_epoch"]), key_tier=key_tier,
        )
        if not grant:
            raise ChestKeyConflict("Нет ключа этого уровня.")
        vip_ids: tuple[str, ...] = ()
        if await vip.is_vip_active(db, int(user_id)):
            vip_ids = tuple(await repo.vip_cosmetic_candidates(
                db, user_id=int(user_id), allowed_ids=VIP_COSMETIC_POOL,
            ))
        outcome = roll_outcome(secrets.randbelow, vip_cosmetic_ids=vip_ids, tier=key_tier)
        open_id = uuid4().hex
        await repo.create_open(
            db, open_id=open_id, user_id=int(user_id), action_id=action_id,
            request_hash=request_hash, catalog_version=CATALOG_VERSION,
            catalog_digest=catalog_digest(), roll=outcome.roll, stars=outcome.stars,
            reward_kind=outcome.reward_kind, reward_amount=outcome.amount,
            reward_ref=outcome.reward_ref, reward_rarity=outcome.rarity,
            key_balance_before=before, account_epoch=int(account["account_epoch"]),
            grant_id=str(grant["id"]),
        )
        row = await repo.find_open_by_action(db, user_id=int(user_id), action_id=action_id)
        if not row:
            raise RuntimeError("Chest open receipt was not persisted.")
        return _prepared(row)


async def reveal(db, *, user_id: int, open_id: str) -> dict:
    await repo.assert_delivery_ready(db)
    open_id = str(open_id or "").strip()
    if not open_id or len(open_id) > 96:
        raise ValueError("Некорректный идентификатор сундука.")
    async with db.connection.transaction():
        await repo.lock_user(db, int(user_id))
        row = await repo.get_open(db, user_id=int(user_id), open_id=open_id)
        if not row:
            raise ChestKeyConflict("Сундук не найден.")
        if bool(row.get("revealed")):
            return _revealed(row)
        kind, amount = str(row["reward_kind"]), int(row["reward_amount"])
        ref = str(row.get("reward_ref") or "") or None
        metadata = {"policy_version": POLICY_VERSION, "catalog_version": str(row["catalog_version"]),
                    "catalog_digest": str(row["catalog_digest"]), "roll": int(row["roll"]),
                    "stars": int(row["stars"]), "reward_kind": kind,
                    "reward_ref": ref, "reward_amount": amount, "key_tier": _row_tier(row)}
        if kind in {"mora", "diamonds", "zarniki"}:
            mutation = await economy_ledger.apply_balance_change(
                db, int(user_id), {kind: amount}, reason_code="chest_v1_reward",
                idempotency_key=f"chest-v1:{open_id}:reward", source_type="chest_v1",
                reference_type="chest_open", reference_id=open_id, metadata=metadata,
                note="Сундук: раскрытая серверная награда",
            )
            await repo.record_currency_or_vip_delivery(
                db, user_id=int(user_id), open_id=open_id, reward_kind=kind,
                reward_ref=ref, reward_amount=amount, operation_id=str(mutation.operation_id),
            )
        else:
            operation_id = uuid4().hex
            await repo.create_item_operation(
                db, operation_id=operation_id, user_id=int(user_id), open_id=open_id, metadata=metadata,
            )
            if kind == "vip_days":
                await vip.grant_vip_days(db, int(user_id), "silver", amount)
                await repo.record_currency_or_vip_delivery(
                    db, user_id=int(user_id), open_id=open_id, reward_kind=kind,
                    reward_ref=ref, reward_amount=amount, operation_id=operation_id,
                )
            else:
                await repo.deliver_inventory_reward(
                    db, user_id=int(user_id), open_id=open_id, reward_kind=kind,
                    reward_ref=ref, reward_amount=amount, operation_id=operation_id,
                    species=PET_SPECIES.get(ref) if ref else None,
                )
            class _Mutation:
                pass
            mutation = _Mutation()
            mutation.operation_id = operation_id
        inserted = await repo.reveal_open(
            db, user_id=int(user_id), open_id=open_id,
            economy_operation_id=str(mutation.operation_id),
        )
        if not inserted:
            raise RuntimeError("Chest reward was credited without its reveal receipt.")
        from services import quests_v1 as quests
        quest_sources = await quests.available_sources(db, user_id=int(user_id))
        vip_active = await vip.is_vip_active(db, int(user_id))
        await quests.record_metric(
            db, user_id=int(user_id), metric="chest_revealed", event_id=open_id,
            vip_active=vip_active, sources=quest_sources,
        )
        from services import achievements_v1 as achievements
        await achievements.record_terminal(
            db, user_id=int(user_id), metric="chest_revealed", source_event_id=open_id,
            source_snapshot={"open_id": open_id, "catalog_version": str(row["catalog_version"]),
                             "stars": int(row["stars"]), "reward_kind": kind},
        )
        revealed = await repo.get_open(db, user_id=int(user_id), open_id=open_id)
        if not revealed or not bool(revealed.get("revealed")):
            raise RuntimeError("Chest reveal receipt was not persisted.")
        return _revealed(revealed)
