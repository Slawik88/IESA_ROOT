"""Immutable direct-Stars supporter cosmetics; never gameplay power."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Final


POLICY_VERSION: Final = "supporter-cosmetics-v1-2026-08-28"
OFFERS: Final[tuple[dict, ...]] = (
    {"id": "quiet_bell", "cosmetic_id": "supporter_quiet_bell", "stars": 50,
     "icon": "🔔", "name": "Тихий звон", "description": "Постоянная профильная печать ранней поддержки."},
    {"id": "archive_witness", "cosmetic_id": "supporter_archive_witness", "stars": 100,
     "icon": "▥", "name": "Свидетель Архива", "description": "Постоянная печать хранителя историй Предвестника."},
    {"id": "rift_patron", "cosmetic_id": "supporter_rift_patron", "stars": 200,
     "icon": "✦", "name": "Покровитель Разлома", "description": "Постоянная светящаяся профильная печать с безопасным статичным эффектом."},
)
OFFER_BY_ID: Final = {item["id"]: item for item in OFFERS}
DEFINITION_DIGEST: Final = hashlib.sha256(json.dumps(
    {"policy_version": POLICY_VERSION, "offers": OFFERS},
    ensure_ascii=False, sort_keys=True, separators=(",", ":"),
).encode("utf-8")).hexdigest()
OFFER_DIGEST_BY_ID: Final = {
    item["id"]: hashlib.sha256(json.dumps(item, ensure_ascii=False, sort_keys=True,
                                           separators=(",", ":")).encode()).hexdigest()
    for item in OFFERS
}
_PAYLOAD = re.compile(r"^cosmetic:v1:(?P<order>[a-f0-9]{32})$")


@dataclass(frozen=True, slots=True)
class CosmeticInvoice:
    order_id: str


def invoice_payload(order_id: str) -> str:
    value = str(order_id).lower()
    if not re.fullmatch(r"[a-f0-9]{32}", value):
        raise ValueError("invalid_order_id")
    return f"cosmetic:v1:{value}"


def parse_invoice_payload(payload: object) -> CosmeticInvoice | None:
    if not isinstance(payload, str):
        return None
    match = _PAYLOAD.fullmatch(payload)
    return CosmeticInvoice(match["order"]) if match else None


def public_offers(owned_ids: set[str]) -> list[dict]:
    return [{**item, "owned": item["cosmetic_id"] in owned_ids,
             "currency": "XTR", "permanent": True,
             "ownership_terms": "Бессрочно, пока покупка не возвращена или не отозвана.",
             "combat_power": False,
             "progression": False, "tradeable": False} for item in OFFERS]


def validate_definition() -> None:
    ids = [item["id"] for item in OFFERS]
    cosmetics = [item["cosmetic_id"] for item in OFFERS]
    if len(ids) != len(set(ids)) or len(cosmetics) != len(set(cosmetics)):
        raise RuntimeError("Supporter cosmetic ids must be unique")
    if any(not isinstance(item["stars"], int) or item["stars"] <= 0 for item in OFFERS):
        raise RuntimeError("Supporter cosmetic Stars prices must be positive integers")


validate_definition()
