#!/usr/bin/env python3
"""Pure policy checks for the two immutable Weekly Case content packs."""
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from core.weekly_case_v1 import CASE_CATALOG, CONTENT_PACKS, case_token, case_view, definition_digest, finale_id, public_manifest

assert len(CASE_CATALOG) == 8
assert len(CONTENT_PACKS) == 2 and all(len(pack["case_ids"]) == 4 for pack in CONTENT_PACKS)
assert len({item["case_id"] for item in CASE_CATALOG}) == 8
assert len({item["policy_version"] for item in CASE_CATALOG}) == 8
assert len({definition_digest(item) for item in CASE_CATALOG}) == 8
assert all(len(case_token(item)) == 12 for item in CASE_CATALOG)
assert sum(int(item["target_days"]) for item in CASE_CATALOG) == 24
assert all(len(item["paths"]) == 2 and len(item["finales"]) == 3 for item in CASE_CATALOG)
assert finale_id({"mastery","tempo","discovery"}) == "many_voices"
assert finale_id({"mastery","discovery"}) == "careful_echo"
assert finale_id({"tempo"}) == "single_note"
assert public_manifest()["expires"] is False
assert public_manifest()["stars_can_buy_progress"] is False

first=CASE_CATALOG[0]
locked=case_view({"policy_version":first["policy_version"],"path_id":None,"progress_days":3},set())
assert not locked["completed"] and locked["finale"] is None
done=case_view({"policy_version":first["policy_version"],"path_id":"follow_bell","progress_days":3,"finale_id":"many_voices"},{"mastery","tempo","discovery"})
assert done["completed"] and done["next_case_available"]
try:
    case_view({"policy_version":"deleted-content","progress_days":0},set())
except ValueError:
    pass
else:
    raise AssertionError("unknown catalog content must fail closed")

print("OK: 8 immutable cases provide 24 non-expiring meaningful days without paid progress")
