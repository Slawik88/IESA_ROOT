"""Policy for visual-only whole-app skin selection and VIP visibility."""
from __future__ import annotations

from core.economy_contract import IdempotencyConflict, InsufficientBalance
from core.global_skins_v1 import DEFAULT_SKIN_ID, SKINS, VERSION, is_known
from infrastructure.repositories.economy_ledger import apply_balance_change, find_reference_replay
from infrastructure.repositories import global_skins_v1 as repo
from services.vip import is_vip_active


class SkinConflict(RuntimeError):
    pass


def _item(skin_id: str, *, owned: bool, selected: bool, active: bool) -> dict:
    definition = SKINS[skin_id]
    return {
        "id": skin_id,
        "name": definition["name"],
        "description": definition["description"],
        "css_class": definition["css_class"],
        "asset": definition["asset"],
        "lineup": definition.get("lineup"),
        "price_zarniki": definition.get("price_zarniki"),
        "vip_required": bool(definition.get("vip_required")),
        "owned": owned,
        "selected": selected,
        "active": active,
    }


async def state(db, user_id: int) -> dict:
    await repo.ensure_tables(db)
    owned = await repo.owned_ids(db, int(user_id))
    available = {DEFAULT_SKIN_ID, *(skin_id for skin_id in owned if is_known(skin_id))}
    saved = await repo.saved_selection(db, int(user_id)) or DEFAULT_SKIN_ID
    if saved not in available:
        saved = DEFAULT_SKIN_ID
        await repo.set_selection(db, int(user_id), saved)
    vip_active = await is_vip_active(db, int(user_id))
    saved_definition = SKINS[saved]
    active = saved if saved == DEFAULT_SKIN_ID or not saved_definition.get("vip_required") or vip_active else DEFAULT_SKIN_ID
    return {
        "version": VERSION,
        "vip_active": vip_active,
        "selected_skin_id": saved,
        "active_skin_id": active,
        "items": [
            _item(
                skin_id,
                owned=skin_id in available,
                selected=skin_id == saved,
                active=skin_id == active,
            )
            for skin_id in SKINS
        ],
    }


async def select(db, user_id: int, skin_id: str) -> dict:
    await repo.ensure_tables(db)
    skin_id = str(skin_id or "").strip()
    if not is_known(skin_id):
        raise SkinConflict("Неизвестный скин приложения.")
    if skin_id != DEFAULT_SKIN_ID and skin_id not in await repo.owned_ids(db, int(user_id)):
        raise SkinConflict("Этот скин приложения не принадлежит игроку.")
    await repo.set_selection(db, int(user_id), skin_id)
    return await state(db, int(user_id))


async def buy(db, user_id: int, skin_id: str, *, idempotency_key: str) -> tuple[str, dict]:
    """Buy and save-select a shop skin with one authoritative Zarniki mutation."""
    definition = SKINS.get(str(skin_id or "").strip())
    price = int((definition or {}).get("price_zarniki") or 0)
    if not definition or not price:
        raise SkinConflict("Этот фон приложения не продаётся.")
    await repo.ensure_tables(db)
    mutation = None
    try:
        async with db.connection.transaction():
            await db.execute(
                "INSERT INTO users(user_tg_id) VALUES (?) ON CONFLICT DO NOTHING",
                (int(user_id),),
            )
            async with db.execute(
                "SELECT 1 FROM users WHERE user_tg_id=? FOR UPDATE", (int(user_id),)
            ) as cursor:
                await cursor.fetchone()
            mutation = await find_reference_replay(
                db,
                int(user_id),
                reason_code="global_skin_purchase",
                idempotency_key=idempotency_key,
                source_type="global_skins_v1",
                reference_type="global_skin",
                reference_id=skin_id,
            )
            if mutation is None:
                if skin_id in await repo.owned_ids(db, int(user_id)):
                    raise SkinConflict("Этот фон приложения уже принадлежит игроку.")
                mutation = await apply_balance_change(
                    db,
                    int(user_id),
                    {"zarniki": -price},
                    reason_code="global_skin_purchase",
                    idempotency_key=idempotency_key,
                    source_type="global_skins_v1",
                    reference_type="global_skin",
                    reference_id=skin_id,
                    metadata={"skin_id": skin_id, "price_zarniki": price},
                    note=skin_id,
                )
                await repo.grant(db, int(user_id), skin_id, source="purchase")
            await repo.set_selection(db, int(user_id), skin_id)
    except InsufficientBalance as exc:
        raise SkinConflict(f"Нужно {price}✨ для покупки этого фона.") from exc
    except IdempotencyConflict as exc:
        raise SkinConflict("Этот запрос уже использован для другой покупки.") from exc
    result = await state(db, int(user_id))
    message = (
        f"Куплено и выбрано: {definition['name']} · {price}✨"
        if mutation and mutation.applied
        else f"Покупка уже обработана: {definition['name']}."
    )
    return message, result
