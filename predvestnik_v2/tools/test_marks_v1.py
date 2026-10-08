#!/usr/bin/env python3
"""Marks rules (no database): who can wear what, the order, that earned marks are retroactive by design, and that nobody can award themselves a mark."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.marks_v1 import EARNED_RULES, GRANTABLE, KINDS, MARKS, PLAYER_NAME, TONES, compose, earned_state, ordered, staff_hint  # noqa: E402
from core.skins_v3_catalog import SEASONS  # noqa: E402


def check(cond: bool, message: str) -> None:
    if not cond:
        raise AssertionError(message)


def catalog() -> None:
    check(all(m["kind"] in KINDS and m["tone"] in TONES and m["glyph"] and m["title"] and m["desc"] and m["how"] for m in MARKS.values()), "every mark is complete")
    check(len({m["weight"] for m in MARKS.values()}) == len(MARKS), "weights are unique, so the order never depends on dict order")
    check(set(EARNED_RULES) == {k for k, m in MARKS.items() if m["kind"] == "earned"}, "every earned mark has a rule and only earned marks do")
    check(set(GRANTABLE) == {k for k, m in MARKS.items() if m["kind"] in ("staff", "granted")}, "the console gives staff and special marks, never earned ones")
    check(PLAYER_NAME == "Регалии" and PLAYER_NAME.lower() not in ("титул", "статус", "метки"), "players see the marks under their own name")
    check(min(MARKS[k]["weight"] for k, m in MARKS.items() if m["kind"] == "staff") > max(m["weight"] for m in MARKS.values() if m["kind"] != "staff"), "staff always come first")
    for rule in EARNED_RULES.values():
        if rule[0].startswith("season:"):
            check(rule[0].split(":", 1)[1] in SEASONS, f"{rule[0]} must be a real season")


def staff() -> None:
    check([staff_hint(r) for r in (0, 1, 2, 3, 9)] == [None, "helper", "senior_helper", "developer", "developer"], "the rank only suggests a badge to the console")
    check(not any("автомат" in MARKS[k]["how"].lower() for k, m in MARKS.items() if m["kind"] == "staff"), "staff marks are never described as automatic")


def composition() -> None:
    facts = {"streak": 31, "joined_days": 400, "messages": 50, "owned_permanent": 12, "maxed": 1, "seasons": {"halloween"}}
    got = [m["id"] for m in compose(held_ids=["tester", "founder", "helper"], facts=facts)]
    check(got == ["helper", "founder", "tester", "collector", "streak30", "veteran", "halloween"], got)
    check([m["id"] for m in compose(held_ids=[], facts={})] == [], "a new player wears nothing, whatever the bot rank")
    check([m["id"] for m in compose(held_ids=["streak30", "nonsense"], facts={"streak": 3})] == ["streak30"],
          "an earned mark that was awarded stays when the streak later breaks (sticky); unknown ids are skipped")
    check(ordered(["tester", "tester", "gone", "founder"]) == ordered(["founder", "tester"]), "unique, unknown ids skipped, heaviest first")


def progress() -> None:
    state = {s["id"]: s for s in earned_state({"streak": 12, "owned_permanent": 99, "seasons": {"new_year"}})}
    check(state["streak30"] == {"id": "streak30", "done": False, "have": 12, "need": 30}, "progress below the need")
    check(state["collector"]["done"] and state["collector"]["have"] == 10, "progress never exceeds the need")
    check(state["new_year"]["done"] and not state["halloween"]["done"], "a season mark needs a skin of that season")
    check(not any(s["done"] for s in earned_state({})), "no facts, no earned marks")
    check(next(s for s in earned_state({"streak": 45}) if s["id"] == "streak30")["done"], "a best streak above the need is enough: nobody farms it again")


def main() -> None:
    catalog()
    staff()
    composition()
    progress()
    print(f"OK: marks v1 rules. {len(MARKS)} marks: " + ", ".join(f"{k}={sum(1 for m in MARKS.values() if m['kind'] == k)}" for k in KINDS))


if __name__ == "__main__":
    main()
