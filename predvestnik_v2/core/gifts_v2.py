"""Gifts by tier (ECO-04 PR-C). Pure rules: no clock, no database.

Four tiers, three gifts each, numbers from the owner's catalogue
(pipeline/tasks/ECO-04-PR-B-shop/shop_catalog.json). A gift is a keepsake on the
recipient's shelf: no power, no XP, no currency for the recipient. First release:
the recipient is the sender's marriage partner (as the old partner gifts).
"""
from __future__ import annotations

import unicodedata
from typing import Final

from core.chests_v1 import canonical_snapshot_fingerprint


GIFTS_VERSION: Final = "gifts-v2-2026-10-14"
FLAG: Final = "gifts_v2"
REASON_CODE: Final = "gift_send_v2"
CURRENCIES: Final = ("mora", "diamonds", "zarniki")

# TIERS and NOTE_MAX are mirrored by named CHECKs in infrastructure/repositories/gifts_v2.py
# (gift_sends_v2_tier_range, gift_sends_v2_note_length). ensure_tables never alters an existing table:
# changing the tier count or NOTE_MAX needs an explicit ALTER TABLE migration of those constraints.
TIERS: Final = {1: "Знак", 2: "Тёплый", 3: "Редкий", 4: "Легендарный"}
TOP_TIER: Final = 4
# Display order inside each tier is the order here.
GIFTS: Final = {
    "gift_card": {"tier": 1, "name": "Открытка", "icon": "💌", "price": {"mora": 150}},
    "gift_rose": {"tier": 1, "name": "Роза", "icon": "🌹", "price": {"mora": 300}},
    "gift_choco": {"tier": 1, "name": "Шоколад", "icon": "🍫", "price": {"mora": 450}},
    "gift_bear": {"tier": 2, "name": "Мишка", "icon": "🧸", "price": {"mora": 800}},
    "gift_bouquet": {"tier": 2, "name": "Букет", "icon": "💐", "price": {"mora": 1500}},
    "gift_inspiration": {"tier": 2, "name": "Вдохновение", "icon": "✨", "price": {"mora": 2000}},
    "gift_candy": {"tier": 3, "name": "Конфеты", "icon": "🍬", "price": {"diamonds": 2}},
    "gift_star": {"tier": 3, "name": "Звезда", "icon": "🌠", "price": {"diamonds": 4}},
    "gift_ring": {"tier": 3, "name": "Кольцо", "icon": "💍", "price": {"diamonds": 6}},
    "gift_crown": {"tier": 4, "name": "Корона", "icon": "👑", "price": {"zarniki": 800}},
    "gift_castle": {"tier": 4, "name": "Замок", "icon": "🏰", "price": {"zarniki": 1500}},
    "gift_constellation": {"tier": 4, "name": "Созвездие", "icon": "🪐", "price": {"zarniki": 3000}},
}

DAILY_SEND_LIMIT: Final = 5          # gifts per UTC day per sender
DAILY_PER_RECIPIENT_LIMIT: Final = 3  # gifts per UTC day from one sender to one recipient
NOTE_MAX: Final = 60
PIN_MAX: Final = 3

# Bidirectional overrides and isolates can make a note read differently from what was typed.
_BIDI_CONTROLS: Final = frozenset(chr(c) for c in (*range(0x202A, 0x202F), *range(0x2066, 0x206A)))


class GiftPolicyError(ValueError):
    """The request does not name a gift or carries a note that cannot be stored."""


def gift(gift_id: object) -> dict[str, object]:
    normalized = str(gift_id or "").strip()
    row = GIFTS.get(normalized)
    if row is None:
        raise GiftPolicyError("Такого подарка нет.")
    return {"id": normalized, "tier": int(row["tier"]), "tier_name": TIERS[int(row["tier"])],
            "name": str(row["name"]), "icon": str(row["icon"]),
            "cost": {str(k): int(v) for k, v in dict(row["price"]).items()}}


def gifts() -> list[dict[str, object]]:
    return [gift(gift_id) for gift_id in GIFTS]


def irreversible(cost: dict) -> bool:
    """Paid with ✨ or 💎: the confirm sheet says «Это необратимо»."""
    return "zarniki" in cost or "diamonds" in cost


def normalize_note(raw: object) -> str | None:
    """Strip; empty -> None; at most NOTE_MAX characters; no control, line-separator or bidi characters."""
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise GiftPolicyError("Записка должна быть текстом.")
    note = raw.strip()
    if not note:
        return None
    if len(note) > NOTE_MAX:
        raise GiftPolicyError(f"Записка — не больше {NOTE_MAX} символов.")
    for char in note:
        if unicodedata.category(char) in {"Cc", "Cs", "Co", "Cn", "Zl", "Zp"} or char in _BIDI_CONTROLS:
            raise GiftPolicyError("В записке есть служебные символы. Оставь обычный текст и эмодзи.")
    return note


def request_hash(gift_id: str, note: str | None) -> str:
    """What one action id means: this gift with this note. Prices and the catalogue digest stay out,
    so a retry after a deploy that changed prices still finds its receipt."""
    return canonical_snapshot_fingerprint({"kind": "gift_v2", "gift_id": str(gift_id), "note": note or ""})


def catalog_payload() -> dict[str, object]:
    return {
        "gifts_version": GIFTS_VERSION, "tiers": {str(k): v for k, v in TIERS.items()}, "gifts": gifts(),
        "daily_send_limit": DAILY_SEND_LIMIT, "daily_per_recipient_limit": DAILY_PER_RECIPIENT_LIMIT,
        "note_max": NOTE_MAX, "pin_max": PIN_MAX,
    }


def catalog_digest() -> str:
    return canonical_snapshot_fingerprint(catalog_payload())
