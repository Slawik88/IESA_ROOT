"""Pure contract checks for the first modular home projection."""
from services.hub_v1 import build_hub_view


view = build_hub_view(
    identity={"user_tg_id": 7, "user_tg_username": "mira", "account_xp": 100},
    family={"id": 3, "partner_id": 8, "partner_name": "kai", "family_balance": 12},
    clan={"clan_id": 4, "name": "North", "tag": "N", "role": "fighter"},
    active_pet={"id": 5, "name": "Лис", "species_id": "fox", "fatigue": 9},
    transactions=({"id": 1, "source": "legacy"},),
)
assert view["identity"]["level"] >= 1
assert view["modules"]["family"]["bank_status"] == "active_receipted"
assert view["modules"]["clan"]["one_clan_only"] is True
assert view["modules"]["pets"]["name"] == "Лис"
assert view["economy_status"] == "family_wallet_active_receipted"

empty = build_hub_view(
    identity={"user_tg_id": 8, "user_tg_username": None, "account_xp": -1},
    family=None, clan=None, active_pet=None, transactions=(),
)
assert empty["identity"]["account_xp"] == 0
assert empty["modules"]["family"] is None
assert empty["modules"]["clan"] is None
print("hub_v1: read-only contract OK")
