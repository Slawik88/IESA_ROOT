"""Canonical formatting and granting of Battle Pass item rewards.

Kept separate from the season service so these entitlement rules can be tested
without importing database adapters or web/bot layers.
"""
from core.cosmetics import COSMETICS
from core.registry import ITEMS_REGISTRY
from core.themes import THEMES


def reward_item_name(item_id: str) -> str:
    cosmetic = COSMETICS.get(item_id)
    return (cosmetic or ITEMS_REGISTRY.get(item_id, {})).get("name", item_id)


def normalize_configured_reward_items(items) -> list[list]:
    """Validate admin-configured reward items and return JSON-safe pairs."""
    if not isinstance(items, (list, tuple)):
        raise ValueError("items должен быть списком пар [item_id, qty]")
    normalized: list[list] = []
    for raw in items:
        if not isinstance(raw, (list, tuple)) or len(raw) != 2:
            raise ValueError("каждый item должен быть парой [item_id, qty]")
        item_id, raw_qty = raw
        if not isinstance(item_id, str) or not item_id:
            raise ValueError("item_id должен быть непустой строкой")
        if item_id not in ITEMS_REGISTRY and item_id not in COSMETICS:
            raise ValueError(f"неизвестный item '{item_id}'")
        try:
            qty = int(raw_qty)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"qty для '{item_id}' должен быть целым числом") from exc
        if qty <= 0:
            raise ValueError(f"qty для '{item_id}' должен быть больше нуля")
        if item_id in COSMETICS and qty != 1:
            raise ValueError(f"косметика '{item_id}' должна иметь qty=1")
        normalized.append([item_id, qty])
    return normalized


def reward_short_text(reward: dict) -> str:
    """Compact, registry-resolved reward description."""
    parts = []
    if reward.get("mora"):
        parts.append(f"+{int(reward['mora'])}🪙")
    if reward.get("diamonds"):
        parts.append(f"+{int(reward['diamonds'])}💎")
    for item_id, qty in reward.get("items", ()):
        parts.append(f"+{1 if item_id in COSMETICS else qty} {reward_item_name(item_id)}")
    if reward.get("theme"):
        parts.append(f"🎨 {THEMES.get(reward['theme'], {}).get('name', reward['theme'])}")
    return ", ".join(parts) if parts else "—"


def reward_cosmetics_error(items: tuple) -> str | None:
    """Reject cosmetic rewards that cannot become durable entitlements."""
    for raw in items:
        if not isinstance(raw, (list, tuple)) or len(raw) != 2:
            return "Некорректное описание предмета в награде. Награда не списана."
        item_id, qty = raw
        if not str(item_id).startswith("cos_"):
            continue
        if item_id not in COSMETICS:
            return f"Косметика «{item_id}» больше не определена в реестре. Награда не списана."
        try:
            cosmetic_qty = int(qty)
        except (TypeError, ValueError):
            cosmetic_qty = 0
        if cosmetic_qty != 1:
            return f"Косметика «{item_id}» должна выдаваться как одно право владения, не в количестве {qty}."
    return None


async def grant_reward_items(db, user_id: int, items: tuple) -> None:
    """Grant BP items in their canonical storage inside the caller transaction.

    Cosmetics are unique entitlements in ``user_cosmetics``. Storing them in
    stackable ``inventory`` makes the reward invisible to the fitting room.
    """
    for item_id, qty in items:
        if item_id in COSMETICS:
            await db.execute(
                "INSERT INTO user_cosmetics (user_id, cosmetic_id) VALUES (?, ?) "
                "ON CONFLICT (user_id, cosmetic_id) DO NOTHING",
                (user_id, item_id),
            )
        else:
            await db.execute(
                "INSERT INTO inventory (user_id, item_id, quantity) VALUES (?, ?, ?) "
                "ON CONFLICT(user_id, item_id) DO UPDATE SET quantity = inventory.quantity + ?",
                (user_id, item_id, qty, qty),
            )
