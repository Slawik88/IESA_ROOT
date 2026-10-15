"""Gifts by tier and the gift shelf (ECO-04 PR-C), dark behind the ``gifts_v2`` flag.

Send follows the shop's Polish template, in one transaction:
lock sender -> replay -> action id owner -> flag -> catalogue -> recipient (partner, not self)
-> UTC day from one CLOCK_TIMESTAMP -> limits (5 a day, 3 a day to one recipient)
-> shortages (nothing debited) -> ledger debit -> append-only receipt.
The recipient's notification runs after commit and never undoes the gift.
First release: the recipient is the sender's marriage partner (as the old partner gifts).
"""
from __future__ import annotations

from datetime import datetime, time, timedelta
import html
import json
import math
import os
from uuid import uuid4

from loguru import logger

from core import gifts_v2 as policy
from core.economy_contract import IdempotencyConflict, InsufficientBalance
from infrastructure.repositories import economy_ledger, system_flags
from infrastructure.repositories import gifts_v2 as repo
from infrastructure.repositories import public_profiles_v1 as public_profiles
from infrastructure.repositories import shop_v1 as shop_repo


CLOSED = "Подарки пока закрыты"
NOT_MARRIED = "Подарки пока можно дарить только супругу."
SELF = "Себе дарить нельзя."
# Gifts are sent from the shop's «Подарки» tab: with shop_v1 off there is nowhere to send from.
SHOP_CLOSED = "Подарки дарятся через магазин, а он пока закрыт."
SHOP_FLAG = "shop_v1"
_ICONS = {"mora": "🪙", "diamonds": "💎", "zarniki": "✨"}


class GiftsClosed(LookupError):
    """The gifts flag is off: the screen and every new gift answer 404."""


class GiftConflict(ValueError):
    """The request is well-formed but refused by the catalogue, the limits or durable state."""


def _action_id(value: object) -> str:
    normalized = str(value or "").strip()
    if not normalized or len(normalized) > 96 or any(ord(char) < 32 for char in normalized):
        raise GiftConflict("action_id обязателен и должен быть безопасным идентификатором.")
    return normalized


async def enabled(db) -> bool:
    return await system_flags.is_enabled(db, policy.FLAG)


async def can_send_now(db) -> bool:
    """Sending needs both flags: gifts_v2 (the feature) and shop_v1 (the tab it is sent from). The shelf needs only gifts_v2."""
    return await enabled(db) and await system_flags.is_enabled(db, SHOP_FLAG)


async def ensure_ready(db) -> None:
    await public_profiles.ensure_tables(db)
    await repo.ensure_tables(db)


async def balances(db, user_id: int) -> dict[str, float]:
    from infrastructure.repositories import economy as economy_repo
    balance = await economy_repo.get_balance(db, int(user_id))
    return {"mora": float(balance["user_balance_mora"] or 0),
            "diamonds": float(balance["user_balance_diamonds"] or 0),
            "zarniki": float(balance.get("user_balance_zarniki") or 0)}


def missing(cost: dict, have: dict) -> dict[str, int]:
    """Whole units still needed per currency; a fractional gap rounds up, never to 0."""
    return {currency: math.ceil(float(amount) - have[currency])
            for currency, amount in cost.items() if have[currency] < float(amount)}


def missing_text(gaps: dict[str, int]) -> str:
    return "Не хватает: " + ", ".join(f"{amount} {_ICONS[currency]}" for currency, amount in gaps.items()) + "."


def _number(value: float) -> float | int:
    return int(value) if float(value).is_integer() else float(value)


def _resets_in(day, now: datetime) -> int:
    return max(0, math.ceil((datetime.combine(day + timedelta(days=1), time.min) - now.replace(tzinfo=None)).total_seconds()))


def _when(value) -> str:
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


async def _people(db, user_ids) -> dict[int, dict]:
    """Opaque references and public names only: Telegram ids never leave the server."""
    ids = [int(u) for u in user_ids if u is not None]
    found = await public_profiles.player_projection(db, user_ids=ids) if ids else {}
    return {uid: {"name": row["display_name"], "ref": row["profile_ref"]} for uid, row in found.items()}


def _entry(row: dict, people: dict[int, dict], *, me: int) -> dict:
    meta = policy.GIFTS.get(str(row["gift_id"]), {})
    tier = int(row["tier"])
    price = json.loads(row["price"]) if isinstance(row["price"], str) else dict(row["price"] or {})
    out = {
        "id": str(row["id"]), "gift_id": str(row["gift_id"]), "name": meta.get("name", str(row["gift_id"])),
        "icon": meta.get("icon", "🎁"), "tier": tier, "tier_name": policy.TIERS.get(tier, ""),
        "note": row.get("note"), "created_at": _when(row["created_at"]),
        "from": people.get(int(row["sender_id"])), "to": people.get(int(row["receiver_id"])),
        "pinned": bool(row.get("pinned")),
    }
    if int(row["sender_id"]) == int(me):
        out["price"] = {k: int(v) for k, v in price.items()}
    return out


def _receipt(row: dict, *, applied: bool) -> dict:
    price = json.loads(row["price"]) if isinstance(row["price"], str) else dict(row["price"] or {})
    return {"send_id": str(row["id"]), "applied": applied, "gift_id": str(row["gift_id"]), "tier": int(row["tier"]),
            "note": row.get("note"), "price": {k: int(v) for k, v in price.items()},
            "gifts_version": str(row["gifts_version"]), "economy_operation_id": str(row["economy_operation_id"]),
            "sent_on": str(row["sent_on"]), "created_at": _when(row["created_at"])}


async def _recipient(db, *, sender_id: int, to_ref: str | None, lock: bool) -> dict:
    """First release: the partner only. A reference to oneself is refused before the marriage check."""
    if to_ref:
        target = await public_profiles.resolve_reference(db, profile_ref=str(to_ref))
        if target is None:
            raise GiftConflict("Игрок не найден.")
        if int(target) == int(sender_id):
            raise GiftConflict(SELF)
    marriage = await repo.partner_of(db, sender_id, lock=lock)
    if not marriage:
        raise GiftConflict(NOT_MARRIED)
    if to_ref and int(target) != marriage["partner_id"]:
        raise GiftConflict(NOT_MARRIED)
    if marriage["partner_id"] == int(sender_id):
        raise GiftConflict(SELF)
    return marriage


async def send(
    db, *, sender_id: int, gift_id: str, action_id: str, catalog_version: str, catalog_digest: str,
    note: object = None, to_ref: str | None = None,
) -> dict:
    """Debit the sender and put the gift on the partner's shelf, exactly once per action id."""
    action_id = _action_id(action_id)
    sender_id = int(sender_id)
    try:
        item = policy.gift(gift_id)
        clean_note = policy.normalize_note(note)
    except policy.GiftPolicyError as exc:
        raise GiftConflict(str(exc)) from exc
    price = dict(item["cost"])
    request_hash = policy.request_hash(str(item["id"]), clean_note)
    await ensure_ready(db)
    async with db.connection.transaction():
        await repo.lock_user(db, sender_id)
        replay = await repo.find_send(db, sender_id=sender_id, action_id=action_id)
        if replay:  # answered before the flag and catalogue: a retry after either changed still gets its receipt
            if str(replay["request_hash"]) != request_hash:
                raise GiftConflict("action_id уже использован для другого подарка.")
            return {**_receipt(replay, applied=False), "receiver_id": int(replay["receiver_id"])}
        owner = await shop_repo.action_owner(db, user_id=sender_id, action_id=action_id)
        if owner is not None:
            raise GiftConflict("action_id уже использован для другой покупки.")
        if not await enabled(db):
            raise GiftsClosed(CLOSED)
        if not await system_flags.is_enabled(db, SHOP_FLAG):
            raise GiftConflict(SHOP_CLOSED)
        if str(catalog_version) != policy.GIFTS_VERSION or str(catalog_digest) != policy.catalog_digest():
            raise GiftConflict("Каталог подарков изменился. Обнови экран перед покупкой.")
        marriage = await _recipient(db, sender_id=sender_id, to_ref=to_ref, lock=True)
        receiver_id = marriage["partner_id"]
        day, _week, _now = await repo.window(db)
        if await repo.sent_today(db, sender_id=sender_id, day=day) >= policy.DAILY_SEND_LIMIT:
            raise GiftConflict(f"Не больше {policy.DAILY_SEND_LIMIT} подарков в сутки.")
        if await repo.sent_today(db, sender_id=sender_id, day=day, receiver_id=receiver_id) >= policy.DAILY_PER_RECIPIENT_LIMIT:
            raise GiftConflict(f"Не больше {policy.DAILY_PER_RECIPIENT_LIMIT} подарков одному игроку в сутки.")
        gaps = missing(price, await balances(db, sender_id))
        if gaps:
            raise GiftConflict(missing_text(gaps))
        send_id = uuid4().hex
        digest = policy.catalog_digest()
        try:
            mutation = await economy_ledger.apply_balance_change(
                db, sender_id, {k: -v for k, v in price.items()}, reason_code=policy.REASON_CODE,
                idempotency_key=f"gift-v2:{send_id}", source_type="social", reference_type="gift_send_v2",
                reference_id=send_id, target_id=receiver_id,
                metadata={"gifts_version": policy.GIFTS_VERSION, "catalog_digest": digest, "gift_id": item["id"],
                          "tier": item["tier"], "price": price, "no_power": True},
                note=f"Подарок: {item['name']}",
            )
        except InsufficientBalance as exc:
            raise GiftConflict("Не хватает валюты для подарка.") from exc
        except IdempotencyConflict as exc:
            raise GiftConflict("action_id уже использован для другого подарка.") from exc
        await repo.create_send(
            db, send_id=send_id, sender_id=sender_id, receiver_id=receiver_id, action_id=action_id,
            gift_id=str(item["id"]), tier=int(item["tier"]), note=clean_note, request_hash=request_hash,
            gifts_version=policy.GIFTS_VERSION, catalog_digest=digest, price=price,
            marriage_id=marriage["marriage_id"], economy_operation_id=str(mutation.operation_id), day=day,
        )
        row = await repo.find_send(db, sender_id=sender_id, action_id=action_id)
        if not row:
            raise RuntimeError("Gift receipt was not persisted.")
        return {**_receipt(row, applied=True), "receiver_id": receiver_id}


async def overview(db, *, user_id: int) -> dict:
    """The Gifts tab of the shop and the own shelf in one read."""
    if not await enabled(db):
        raise GiftsClosed(CLOSED)
    await ensure_ready(db)
    user_id = int(user_id)
    day, _week, now = await repo.window(db)
    have = await balances(db, user_id)
    marriage = await repo.partner_of(db, user_id)
    partner_id = marriage["partner_id"] if marriage else None
    used = await repo.sent_today(db, sender_id=user_id, day=day)
    to_partner = await repo.sent_today(db, sender_id=user_id, day=day, receiver_id=partner_id) if partner_id else 0
    daily_left = max(0, policy.DAILY_SEND_LIMIT - used)
    recipient_left = max(0, policy.DAILY_PER_RECIPIENT_LIMIT - to_partner) if partner_id else 0
    shop_on = await system_flags.is_enabled(db, SHOP_FLAG)
    reason = (SHOP_CLOSED if not shop_on
              else NOT_MARRIED if not partner_id
              else f"Не больше {policy.DAILY_SEND_LIMIT} подарков в сутки." if not daily_left
              else f"Не больше {policy.DAILY_PER_RECIPIENT_LIMIT} подарков одному игроку в сутки." if not recipient_left
              else None)
    tiers = []
    for tier, name in policy.TIERS.items():
        rows = []
        for item in policy.gifts():
            if item["tier"] != tier:
                continue
            gaps = missing(item["cost"], have)
            rows.append({**item, "missing": gaps, "affordable": not gaps, "irreversible": policy.irreversible(item["cost"]),
                         "available": reason is None})
        tiers.append({"tier": tier, "name": name, "gifts": rows})
    people = await _people(db, [partner_id] if partner_id else [])
    return {
        "gifts_version": policy.GIFTS_VERSION, "catalog_version": policy.GIFTS_VERSION,
        "catalog_digest": policy.catalog_digest(), "day_boundary": "UTC",
        "balances": {currency: _number(amount) for currency, amount in have.items()},
        "recipient": people.get(partner_id) if partner_id else None,
        "limits": {"daily": {"max": policy.DAILY_SEND_LIMIT, "used": used, "left": daily_left},
                   "recipient": {"max": policy.DAILY_PER_RECIPIENT_LIMIT, "used": to_partner, "left": recipient_left},
                   "resets_in_seconds": _resets_in(day, now)},
        "can_send": reason is None, "unavailable_reason": reason, "note_max": policy.NOTE_MAX, "pin_max": policy.PIN_MAX,
        "tiers": tiers, "shelf": await shelf(db, user_id=user_id),
    }


async def _top_badge(db, user_id: int) -> dict | None:
    row = await repo.top_tier_latest(db, user_id, policy.TOP_TIER)
    if not row:
        return None
    meta = policy.GIFTS.get(str(row["gift_id"]), {})
    return {"icon": meta.get("icon", "🎁"), "name": meta.get("name", ""), "tier_name": policy.TIERS[policy.TOP_TIER]}


async def shelf(db, *, user_id: int) -> dict:
    """Own shelf: four tiers, one slot per catalogue gift (empty = silhouette), counters and the pinned showcase."""
    user_id = int(user_id)
    by_gift = {str(row["gift_id"]): row for row in await repo.received_by_gift(db, user_id)}
    tiers = []
    for tier, name in policy.TIERS.items():
        slots = [{"gift_id": item["id"], "name": item["name"], "icon": item["icon"],
                  "count": int(by_gift.get(item["id"], {}).get("n", 0) or 0)}
                 for item in policy.gifts() if item["tier"] == tier]
        tiers.append({"tier": tier, "name": name, "slots": slots})
    pins = await repo.pinned(db, user_id)
    people = await _people(db, {int(r["sender_id"]) for r in pins} | {user_id})
    return {"counts": await repo.counts(db, user_id), "tiers": tiers,
            "pinned": [_entry(row, people, me=user_id) for row in pins],
            "top_badge": await _top_badge(db, user_id)}


async def history(db, *, user_id: int, box: str, tier: int | None = None, gift_id: str | None = None,
                  limit: int = 50) -> dict:
    if not await enabled(db):
        raise GiftsClosed(CLOSED)
    if box not in {"received", "sent"}:
        raise GiftConflict("Список: received или sent.")
    if tier is not None and tier not in policy.TIERS:
        raise GiftConflict("Такого тира нет.")
    if gift_id is not None and gift_id not in policy.GIFTS:
        raise GiftConflict("Такого подарка нет.")
    await ensure_ready(db)
    rows = await repo.history(db, user_id=int(user_id), box=box, tier=tier, gift_id=gift_id,
                              limit=max(1, min(100, int(limit))))
    people = await _people(db, {int(r["sender_id"]) for r in rows} | {int(r["receiver_id"]) for r in rows})
    return {"box": box, "tier": tier, "items": [_entry(row, people, me=int(user_id)) for row in rows]}


async def set_pin(db, *, user_id: int, send_id: str, pinned: bool) -> dict:
    """Pin or unpin one received gift; at most PIN_MAX pinned. Only the recipient may pin."""
    if not await enabled(db):
        raise GiftsClosed(CLOSED)
    await ensure_ready(db)
    user_id = int(user_id)
    async with db.connection.transaction():
        await repo.lock_user(db, user_id)
        row = await repo.get_send(db, str(send_id))
        if not row or int(row["receiver_id"]) != user_id:
            raise GiftConflict("Закрепить можно только подарок, который получил ты.")
        current = {str(r["id"]) for r in await repo.pinned(db, user_id)}
        if pinned and str(send_id) not in current:
            if len(current) >= policy.PIN_MAX:
                raise GiftConflict(f"На витрине не больше {policy.PIN_MAX} подарков. Сними один, чтобы закрепить этот.")
            await repo.pin(db, user_id=user_id, send_id=str(send_id))
        elif not pinned:
            await repo.unpin(db, user_id=user_id, send_id=str(send_id))
    return {"ok": True, "shelf": await shelf(db, user_id=user_id)}


async def public_view(db, *, target_id: int, viewer_id: int) -> dict | None:
    """Another player's card: pinned gifts (max 3) and the total only; the full shelf stays private.
    ``can_send``: the viewer may gift this player now (first release: their partner)."""
    if not await enabled(db):
        return None
    await ensure_ready(db)
    target_id, viewer_id = int(target_id), int(viewer_id)
    pins = (await repo.pinned(db, target_id))[:policy.PIN_MAX]
    sendable = viewer_id != target_id and await system_flags.is_enabled(db, SHOP_FLAG)
    marriage = await repo.partner_of(db, viewer_id) if sendable else None
    return {
        "total": (await repo.counts(db, target_id))["received"],
        "pinned": [{"gift_id": str(r["gift_id"]), "name": policy.GIFTS.get(str(r["gift_id"]), {}).get("name", ""),
                    "icon": policy.GIFTS.get(str(r["gift_id"]), {}).get("icon", "🎁"), "tier": int(r["tier"]),
                    "tier_name": policy.TIERS.get(int(r["tier"]), "")} for r in pins],
        "top_badge": await _top_badge(db, target_id),
        "can_send": bool(marriage and marriage["partner_id"] == target_id),
    }


async def _bot_dm(user_id: int, text: str) -> None:
    import httpx
    token = os.getenv("BOT_TOKEN", "")
    if not token:
        return
    async with httpx.AsyncClient(timeout=6) as client:
        await client.post(f"https://api.telegram.org/bot{token}/sendMessage",
                          json={"chat_id": int(user_id), "text": text, "parse_mode": "HTML"})


async def notify_recipient(db, *, sender_id: int, receipt: dict) -> None:
    """Bot message plus the in-app gift box (same payload as the old partner gift). Never raises:
    the gift is already committed and a lost notification must not look like a failed purchase.
    The sender is named by the public display name (@username or «Игрок XXXXX»), never by a Telegram id."""
    if not receipt.get("applied"):
        return
    receiver_id = int(receipt["receiver_id"])
    item = policy.GIFTS.get(str(receipt["gift_id"]), {})
    note = receipt.get("note")
    try:
        sender = (await _people(db, [int(sender_id)])).get(int(sender_id), {}).get("name") or "Супруг"
    except Exception:
        logger.exception("gifts_v2: sender name lookup failed")
        sender = "Супруг"
    try:
        from FastAPI.routers.marriage import _notify_partner_gift
        await _notify_partner_gift(db, int(sender_id), receiver_id, {
            "name": f"{item.get('icon', '🎁')} {item.get('name', 'Подарок')}",
            "msg": note or "Подарок уже на твоей полке в профиле.",
        }, from_name=sender)
    except Exception:
        logger.exception("gifts_v2: in-app notification failed")
    try:
        text = (f"🎁 {html.escape(sender)} дарит тебе «{html.escape(str(item.get('name', 'Подарок')))}» "
                f"{item.get('icon', '')} · {policy.TIERS.get(int(receipt['tier']), '')}.")
        if note:
            text += f"\nЗаписка: «{html.escape(note)}»"
        text += "\nПодарок уже на полке в профиле."
        await _bot_dm(receiver_id, text)
    except Exception:
        logger.exception("gifts_v2: bot notification failed")


async def notify_recipient_detached(*, sender_id: int, receipt: dict) -> None:
    """Background task after the response: its own pool connection (the request's one is already released), errors only logged."""
    try:
        from infrastructure.database import create_pool, get_pool
        from infrastructure.pg_adapter import PGAdapter
        await create_pool()
        async with get_pool().acquire() as connection:
            await notify_recipient(PGAdapter(connection), sender_id=int(sender_id), receipt=receipt)
    except Exception:
        logger.exception("gifts_v2: detached notification failed")
