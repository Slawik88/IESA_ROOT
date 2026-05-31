import json
from datetime import datetime
from services.formatting import parse_dt

import aiosqlite

from infrastructure.repositories import promocodes as promo_repo
from infrastructure.repositories.economy import add_balance
from core.registry import ITEMS_REGISTRY


class PromoError(Exception):
    pass


async def activate_promocode(
    db: aiosqlite.Connection,
    user_id: int,
    code: str,
    chat_id: int | None = None,
) -> dict:
    """
    Validate and apply a promo code for user_id.
    Returns dict with reward details on success.
    Raises PromoError with a user-friendly message on failure.
    """
    code = code.strip().upper()
    promo = await promo_repo.get_promocode(db, code)
    if not promo:
        raise PromoError("❌ Промокод не найден. Проверьте правильность написания.")

    if not promo["is_active"]:
        raise PromoError("❌ Этот промокод деактивирован.")

    now = datetime.now()

    if promo["valid_from"]:
        try:
            vf = parse_dt(promo["valid_from"])
        except ValueError:
            vf = datetime.strptime(promo["valid_from"], "%Y-%m-%d")
        if now < vf:
            raise PromoError(
                f"⏳ Промокод ещё не активен.\n"
                f"Начинает действовать: <b>{vf.strftime('%d.%m.%Y %H:%M')}</b>"
            )

    if promo["valid_until"]:
        try:
            vu = parse_dt(promo["valid_until"])
        except ValueError:
            vu = datetime.strptime(promo["valid_until"], "%Y-%m-%d")
        if now > vu:
            raise PromoError(
                f"⌛ Срок действия промокода истёк: <b>{vu.strftime('%d.%m.%Y')}</b>"
            )

    max_act = promo["max_activations"]
    if max_act > 0 and promo["activations_count"] >= max_act:
        raise PromoError("❌ Лимит активаций исчерпан. Промокод больше не действует.")

    # Check user whitelist (if set)
    allowed_users_raw = promo.get("allowed_users_json") or "[]"
    try:
        allowed_users: list[int] = json.loads(allowed_users_raw)
    except (json.JSONDecodeError, TypeError):
        allowed_users = []
    if allowed_users and user_id not in allowed_users:
        raise PromoError("🔒 Этот промокод предназначен для конкретных пользователей.")

    # Check chat whitelist (if set)
    allowed_chats_raw = promo.get("allowed_chats_json") or "[]"
    try:
        allowed_chats: list[int] = json.loads(allowed_chats_raw)
    except (json.JSONDecodeError, TypeError):
        allowed_chats = []
    if allowed_chats:
        if chat_id is None or chat_id not in allowed_chats:
            raise PromoError(
                "🔒 Этот промокод действует только в определённых чатах.\n"
                "<i>Попробуй активировать его в нужном чате.</i>"
            )

    if await promo_repo.has_user_redeemed(db, code, user_id):
        raise PromoError("⚠️ Вы уже активировали этот промокод ранее.")

    mora = float(promo["reward_mora"] or 0)
    diamonds = float(promo["reward_diamonds"] or 0)
    dark_mora = float(promo.get("reward_dark_mora") or 0)

    try:
        items: dict[str, int] = json.loads(promo["reward_items_json"] or "{}")
    except (json.JSONDecodeError, TypeError):
        items = {}

    # Apply all rewards atomically — single commit at the end via redeem_promocode
    if mora > 0 or diamonds > 0:
        await add_balance(
            db, user_id, mora, diamonds,
            commit=False, source="promocode", chat_id=chat_id, note=f"Promo:{code}"
        )

    if dark_mora > 0:
        from infrastructure.repositories.dark_mora import add_dark_mora
        await add_dark_mora(db, user_id, dark_mora, source="promocode", note=f"Promo:{code}")

    for item_id, qty in items.items():
        if qty > 0:
            await db.execute(
                "INSERT INTO inventory (user_id, item_id, quantity) VALUES (?, ?, ?) "
                "ON CONFLICT(user_id, item_id) DO UPDATE SET quantity = quantity + ?",
                (user_id, item_id, qty, qty),
            )

    await promo_repo.redeem_promocode(db, code, user_id, chat_id)

    return {
        "code": code,
        "description": promo.get("description", ""),
        "mora": mora,
        "diamonds": diamonds,
        "dark_mora": dark_mora,
        "items": items,
    }


def format_reward_text(reward: dict) -> str:
    """Build a human-readable reward summary line."""
    parts = []
    if reward["mora"] > 0:
        parts.append(f"🪙 <b>+{reward['mora']:,.0f}</b> Моры")
    if reward["diamonds"] > 0:
        parts.append(f"💎 <b>+{reward['diamonds']:,.1f}</b> Алмазов")
    if reward.get("dark_mora", 0) > 0:
        parts.append(f"🌑 <b>+{reward['dark_mora']:,.0f}</b> Тёмной Моры")
    for item_id, qty in reward.get("items", {}).items():
        item_name = ITEMS_REGISTRY.get(item_id, {}).get("name", item_id)
        parts.append(f"📦 <b>{item_name}</b> ×{qty}")
    return "\n".join(f"├ {p}" if i < len(parts) - 1 else f"└ {p}" for i, p in enumerate(parts)) if parts else "└ <i>Нет наград</i>"
