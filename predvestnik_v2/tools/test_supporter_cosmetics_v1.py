"""Compact contract for direct-Stars supporter cosmetics."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.supporter_cosmetics_v1 import (
    DEFINITION_DIGEST, OFFERS, invoice_payload, parse_invoice_payload, public_offers,
)


def main() -> None:
    assert len(OFFERS) == 3 and len(DEFINITION_DIGEST) == 64
    assert all(item["stars"] > 0 for item in OFFERS)
    assert all(item["cosmetic_id"].startswith("supporter_") for item in OFFERS)
    order = "a" * 32
    assert parse_invoice_payload(invoice_payload(order)).order_id == order
    for malformed in (None, "", "cosmetic:v1:../x", "cosmetic:v2:" + order):
        assert parse_invoice_payload(malformed) is None
    view = public_offers({OFFERS[0]["cosmetic_id"]})
    assert view[0]["owned"] is True
    assert all(item["currency"] == "XTR" and item["permanent"] for item in view)
    assert all(not item["combat_power"] and not item["progression"] and not item["tradeable"] for item in view)
    print("OK: direct Stars cosmetics are immutable, explicit and non-economic")


if __name__ == "__main__":
    main()
