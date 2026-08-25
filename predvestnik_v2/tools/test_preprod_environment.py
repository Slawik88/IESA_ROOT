#!/usr/bin/env python3
"""Negative contract tests for the local preprod database boundary."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from infrastructure.preprod import (
    assert_preprod_environment,
    require_preprod_user,
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
assert not stars_invoice_issuance_allowed(BASE)
assert stars_invoice_issuance_allowed({"PREDVESTNIK_ENV": "production"})
print("OK: preprod DB isolation and Telegram allowlist fail closed")
