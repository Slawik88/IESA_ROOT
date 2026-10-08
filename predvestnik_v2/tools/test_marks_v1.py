#!/usr/bin/env python3
"""Marks rules (no database): who can wear what, the order, and that nobody can award themselves a mark."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.marks_v1 import EARNED_RULES, GRANTABLE, HERO_LIMIT, KINDS, MARKS, TONES, compose, earned_state, ordered, staff_mark  # noqa: E402
from core.skins_v3_catalog import SEASONS  # noqa: E402


def check(cond: bool, message: str) -> None:
    if not cond:
        raise AssertionError(message)


def catalog() -> None:
    check(all(m["kind"] in KINDS and m["tone"] in TONES and m["glyph"] and m["title"] and m["desc"] and m["how"] for m in MARKS.values()), "every mark is complete")
    check(len({m["weight"] for m in MARKS.values()}) == len(MARKS), "weights are unique, so the order never depends on dict order")
    check(set(EARNED_RULES) == {k for k, m in MARKS.items() if m["kind"] == "earned"}, "every earned mark has a rule and only earned marks do")
    check(set(GRANTABLE) == {k for k, m in MARKS.items() if m["kind"] == "granted"}, "hand-given marks are exactly the granted kind")
    check(min(MARKS[k]["weight"] for k, m in MARKS.items() if m["kind"] == "staff") > max(m["weight"] for m in MARKS.values() if m["kind"] != "staff"), "staff always come first")
    for rule in EARNED_RULES.values():
        if rule[0].startswith("season:"):
            check(rule[0].split(":", 1)[1] in SEASONS, f"{rule[0]} must be a real season")


def staff() -> None:
    check([staff_mark(r) for r in (0, 1, 2, 3, 9)] == [None, "helper", "senior_helper", "developer", "developer"], "global rank decides the staff mark")
    check(staff_mark(0, is_developer=True) == "developer", "the developer id wins whatever the stored rank")


def composition() -> None:
    facts = {"streak": 31, "joined_days": 400, "messages": 50, "owned_permanent": 12, "maxed": 1, "seasons": {"halloween"}}
    got = [m["id"] for m in compose(global_rank=1, is_developer=False, granted_ids=["tester", "founder"], facts=facts)]
    check(got == ["helper", "founder", "tester", "collector", "streak30", "veteran", "halloween"], got)
    check([m["id"] for m in compose(global_rank=0, is_developer=False, granted_ids=[], facts={})] == [], "a new player wears nothing")
    check([m["id"] for m in compose(global_rank=0, is_developer=False, granted_ids=["developer", "helper", "veteran", "nonsense"], facts={})] == [],
          "staff and earned ids in the granted table are ignored: nobody can be given them by hand or by a bad row")
    check(ordered(["tester", "tester", "gone", "founder"]) == ordered(["founder", "tester"]), "unique, unknown ids skipped, heaviest first")
    check(HERO_LIMIT == 3, "the hero shows three marks")


def progress() -> None:
    state = {s["id"]: s for s in earned_state({"streak": 12, "owned_permanent": 99, "seasons": {"new_year"}})}
    check(state["streak30"] == {"id": "streak30", "done": False, "have": 12, "need": 30}, "progress below the need")
    check(state["collector"]["done"] and state["collector"]["have"] == 10, "progress never exceeds the need")
    check(state["new_year"]["done"] and not state["halloween"]["done"], "a season mark needs a skin of that season")
    check(not any(s["done"] for s in earned_state({})), "no facts, no earned marks")


def main() -> None:
    catalog()
    staff()
    composition()
    progress()
    print(f"OK: marks v1 rules. {len(MARKS)} marks: " + ", ".join(f"{k}={sum(1 for m in MARKS.values() if m['kind'] == k)}" for k in KINDS))


if __name__ == "__main__":
    main()
