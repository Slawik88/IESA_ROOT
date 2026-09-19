"""Application layer for direct-Stars supporter cosmetics."""
from __future__ import annotations

from core.supporter_cosmetics_v1 import OFFER_BY_ID, invoice_payload, public_offers
from infrastructure.repositories import reconstruction as lock_repo
from infrastructure.repositories import supporter_cosmetics_v1 as repo


async def overview(db, user_id: int) -> dict:
    entitlements = await repo.active_entitlements(db, int(user_id))
    owned = {row["cosmetic_id"] for row in entitlements}
    active = None
    async with db.execute(
        "SELECT active_entitlement_id,revision FROM supporter_profile_v1 WHERE user_id=?",
        (int(user_id),),
    ) as cursor:
        profile = await cursor.fetchone()
    if profile and profile[0]:
        active = next((row for row in entitlements if row["entitlement_id"] == profile[0]), None)
    return {
        "offers": public_offers(owned),
        "entitlements": [{"entitlement_id": row["entitlement_id"],
                           "cosmetic_id": row["cosmetic_id"]} for row in entitlements],
        "active_cosmetic_id": active["cosmetic_id"] if active else None,
        "revision": int(profile[1]) if profile else 0,
        "stars_only": True, "permanent": True, "combat_power": False,
        "progression": False, "tradeable": False,
    }


async def create_order(db, *, payer_user_id: int, beneficiary_user_id: int,
                       offer_id: str, request_id: str) -> tuple[dict, bool]:
    if int(payer_user_id) != int(beneficiary_user_id):
        raise ValueError("gifting_not_enabled")
    async with db.connection.transaction():
        await lock_repo.lock_user(db, int(payer_user_id))
        replay = await repo.get_order_by_request(db, payer_user_id, request_id)
        if replay:
            expected = OFFER_BY_ID.get(offer_id)
            if (not expected or int(replay["beneficiary_user_id"]) != int(beneficiary_user_id)
                    or replay["offer_id"] != offer_id):
                raise RuntimeError("order_request_conflict")
            return replay, False
        owned = {row["cosmetic_id"] for row in await repo.active_entitlements(db, beneficiary_user_id)}
        offer = OFFER_BY_ID.get(offer_id)
        if not offer:
            raise ValueError("unknown_offer")
        if offer["cosmetic_id"] in owned:
            raise ValueError("already_owned")
        pending = await repo.get_order_by_cosmetic(db, beneficiary_user_id, offer["cosmetic_id"])
        if pending:
            # A lost Mini App response must not make a paid-capable invoice
            # inaccessible. The same frozen order/payload remains the only one.
            return pending, False
        return await repo.create_order(
            db, payer_user_id=payer_user_id, beneficiary_user_id=beneficiary_user_id,
            offer_id=offer_id, request_id=request_id, payload_builder=invoice_payload,
        )


async def validate_precheckout(db, *, payer_user_id: int, payload: str,
                               currency: str, amount: int, query_id: str) -> dict:
    from core.supporter_cosmetics_v1 import parse_invoice_payload
    parsed = parse_invoice_payload(payload)
    if not parsed:
        raise ValueError("invalid_payload")
    row = await repo.get_order(db, parsed.order_id)
    if not row:
        raise ValueError("unknown_order")
    repo.validate_order(row, payer_user_id=payer_user_id, currency=currency, amount=amount)
    async with db.connection.transaction():
        await lock_repo.lock_user(db, int(payer_user_id))
        return await repo.claim_precheckout(db, order_id=parsed.order_id, query_id=str(query_id))


async def grant_paid(db, *, payer_user_id: int, payload: str, currency: str,
                     amount: int, charge_id: str) -> tuple[dict, bool]:
    from core.supporter_cosmetics_v1 import parse_invoice_payload
    parsed = parse_invoice_payload(payload)
    if not parsed or not charge_id:
        raise ValueError("invalid_payment")
    # Commit Telegram's paid fact before projecting the entitlement. A later
    # projection failure must not erase evidence that real Stars were charged.
    async with db.connection.transaction():
        await repo.record_charge(
            db, charge_id=charge_id, order_id=parsed.order_id,
            payer_user_id=payer_user_id, payload=payload,
            currency=currency, amount=amount,
        )
    try:
        async with db.connection.transaction():
            await lock_repo.lock_user(db, int(payer_user_id))
            order, applied = await repo.grant_paid(
                db, order_id=parsed.order_id, payer_user_id=payer_user_id,
                charge_id=charge_id, currency=currency, amount=amount,
            )
            await repo.set_charge_status(db, charge_id, "entitled")
            return order, applied
    except Exception:
        async with db.connection.transaction():
            await repo.link_failed_projection(
                db, order_id=parsed.order_id, charge_id=charge_id,
            )
            await repo.set_charge_status(db, charge_id, "review")
        raise


async def select(db, *, user_id: int, cosmetic_id: str | None,
                 expected_revision: int) -> dict:
    async with db.connection.transaction():
        await lock_repo.lock_user(db, int(user_id))
        entitlements = await repo.active_entitlements(db, int(user_id))
        selected = None
        if cosmetic_id is not None:
            selected = next((row for row in entitlements if row["cosmetic_id"] == cosmetic_id), None)
            if not selected:
                raise ValueError("not_owned")
        async with db.execute(
            "INSERT INTO supporter_profile_v1(user_id,active_entitlement_id,revision) VALUES (?,?,1) "
            "ON CONFLICT(user_id) DO UPDATE SET active_entitlement_id=excluded.active_entitlement_id,"
            "revision=supporter_profile_v1.revision+1,updated_at=NOW() "
            "WHERE supporter_profile_v1.revision=? RETURNING revision",
            (int(user_id), selected["entitlement_id"] if selected else None, int(expected_revision)),
        ) as cursor:
            if not await cursor.fetchone():
                raise RuntimeError("revision_conflict")
    return await overview(db, int(user_id))


async def active_public(db, user_id: int) -> dict | None:
    view = await overview(db, user_id)
    cosmetic_id = view["active_cosmetic_id"]
    offer = next((item for item in OFFER_BY_ID.values() if item["cosmetic_id"] == cosmetic_id), None)
    return ({"id": cosmetic_id, "icon": offer["icon"], "name": offer["name"]}
            if offer else None)
