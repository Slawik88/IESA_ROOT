#!/usr/bin/env python3
"""Negative contract tests for the local preprod database boundary."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from infrastructure.preprod import (
    assert_preprod_environment,
    is_preprod_browser_test_user,
    require_preprod_user,
    direct_stars_cosmetics_allowed,
    stars_invoice_issuance_allowed,
)


BASE = {
    "PREDVESTNIK_ENV": "preprod",
    "DATABASE_URL": "postgresql://predvestnik_preprod@127.0.0.1:55432/predvestnik_preprod",
    "PREPROD_ALLOWED_TG_IDS": "101, 202",
}


def rejected(change: dict[str, str]) -> None:
    env = {**BASE, **change}
    try:
        assert_preprod_environment(env)
    except RuntimeError:
        return
    raise AssertionError(f"unsafe preprod environment was accepted: {change!r}")


assert_preprod_environment(BASE)
rejected({"DATABASE_URL": "postgresql://user:secret@db.example.com/predvestnik_preprod"})
rejected({"DATABASE_URL": "postgresql://user:secret@127.0.0.1/production"})
rejected({"PREDVESTNIK_DATABASE_URL": "postgresql://user:secret@db.example.com/production"})
rejected({"PREPROD_ALLOWED_TG_IDS": ""})
rejected({"DATABASE_URL": "sqlite:///tmp/test.db"})
assert require_preprod_user(101, BASE)
assert not require_preprod_user(303, BASE)
assert require_preprod_user(303, {"PREDVESTNIK_ENV": "production"})
assert is_preprod_browser_test_user(990_000_001, BASE)
assert not is_preprod_browser_test_user(990_000_001, {"PREDVESTNIK_ENV": "production"})
assert not is_preprod_browser_test_user(101, BASE)
assert not stars_invoice_issuance_allowed(BASE)
assert not stars_invoice_issuance_allowed({"PREDVESTNIK_ENV": "production"})
assert not direct_stars_cosmetics_allowed({"PREDVESTNIK_ENV": "production"})
assert not direct_stars_cosmetics_allowed({
    "PREDVESTNIK_ENV": "production", "STARS_REFUND_RAIL_V1": "1",
    "STARS_DIRECT_ENTITLEMENTS_V1": "1",
})
print("OK: preprod DB isolation and Telegram allowlist fail closed")
