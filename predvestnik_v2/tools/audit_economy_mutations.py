#!/usr/bin/env python3
"""Fail when a new direct users.user_balance_* writer bypasses the ledger.

Known legacy writers are reported but allowed while they are migrated in waves.
The important guard is that the debt can only shrink: a new unclassified writer
causes a non-zero exit code in local/CI checks.
"""
from __future__ import annotations

from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
SCAN_ROOTS = ("FastAPI", "bot", "infrastructure", "services")
WRITE_RE = re.compile(
    r"UPDATE\s+users(?:\s+[a-z][a-z0-9_]*)?\s+SET\b.{0,700}?"
    r"(?:user_balance_|\{(?:assignments|[a-z_]*col)\})",
    re.IGNORECASE | re.DOTALL,
)

CANONICAL_WRITERS = {
    "infrastructure/repositories/economy_ledger.py",
}

# Every file here is migration debt, not an endorsed alternative architecture.
LEGACY_WRITERS = {
    "FastAPI/routers/battle.py",
    "FastAPI/routers/dev_console/player.py",
    "FastAPI/routers/dev_console/vip.py",
    "FastAPI/routers/showcase.py",
    "infrastructure/repositories/clans.py",
    "infrastructure/repositories/crypto.py",
    "infrastructure/repositories/dark_mora.py",
    "infrastructure/repositories/economy.py",
    "infrastructure/repositories/marriages.py",
    "infrastructure/repositories/raids.py",
    "infrastructure/repositories/relics.py",
    "infrastructure/repositories/shadow_gates.py",
    "infrastructure/repositories/shadow_merchant.py",
    "infrastructure/repositories/zoo.py",
    "services/cosmetics.py",
    "services/dark_market.py",
    "services/scheduler.py",
}

EXCEPTION_WRITERS = {
    # Account erasure intentionally zeroes all state and is not gameplay economy.
    "services/account_deletion.py",
    # Idempotent startup migrations/refunds execute before gameplay is available.
    "bot/core/database.py",
}


def _discover():
    matches = []
    for root_name in SCAN_ROOTS:
        for path in sorted((ROOT / root_name).rglob("*.py")):
            relative = path.relative_to(ROOT).as_posix()
            text = path.read_text(encoding="utf-8")
            for match in WRITE_RE.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                matches.append((relative, line))
    return matches


def main() -> int:
    matches = _discover()
    files = {path for path, _ in matches}
    known = CANONICAL_WRITERS | LEGACY_WRITERS | EXCEPTION_WRITERS
    unknown = sorted(files - known)

    groups = (
        ("canonical", CANONICAL_WRITERS),
        ("legacy", LEGACY_WRITERS),
        ("exception", EXCEPTION_WRITERS),
    )
    print(f"direct balance SQL audit: {len(matches)} writes in {len(files)} files")
    for label, allowed in groups:
        present = sorted(files & allowed)
        print(f"  {label}: {len(present)} files")
        if label == "legacy":
            for path in present:
                lines = ", ".join(str(line) for found, line in matches if found == path)
                print(f"    - {path}:{lines}")

    if unknown:
        print("  UNKNOWN LEDGER BYPASS:")
        for path in unknown:
            lines = ", ".join(str(line) for found, line in matches if found == path)
            print(f"    - {path}:{lines}")
        return 1
    print("  guard: OK (no new unclassified balance writers)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
