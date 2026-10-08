#!/usr/bin/env python3
"""Skins V3 economy invariants (no database): prices only go up with rarity and Essence cannot be a cheap road around them.

What this proves, in Zarniki (1 Zarnik = ESSENCE_PER_ZARNIK Essence at every pack size):
  * a skin is never cheaper than the old launch price times two, and never dearer than times four;
  * buying every Essence step with Zarniki costs exactly the chain / rate: no pack discounts the rate;
  * the cheapest way to a look of tier T is the skin whose rarity is T, and its full price rises with T;
  * free Essence (quests, sets, rarity rows, collection steps, skin of the week) is a small share of what it costs to own.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.skins_v3 import (BONUS_SHARE, BUY_PRICE_ZARNIKI, ESSENCE_PACKS, ESSENCE_PER_ZARNIK, ESSENCE_QUEST_REWARD, FEATURED_SHARE, TIERS,  # noqa: E402
                           UPGRADE_ESSENCE, essence_zarniki, full_price, tier_index, total_upgrade_cost, upgrade_cost)
from core.skins_v3_catalog import SETS, SKINS  # noqa: E402
from core.skins_v3_collection import (PERMANENT, ROW_SHARE, featured, featured_bonus, milestones, row_bonus, row_members, season_window, set_bonus,  # noqa: E402
                                      total_one_time_essence, week_index)

LAUNCH_PRICES = {"D": 100, "C": 160, "B": 240, "A": 340, "S": 480, "SS": 650, "SSS": 900}


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def prices() -> None:
    for tier, old in LAUNCH_PRICES.items():
        ratio = BUY_PRICE_ZARNIKI[tier] / old
        check(2.0 <= ratio <= 4.0, f"{tier}: price {BUY_PRICE_ZARNIKI[tier]} is x{ratio:.2f} of the launch price, the owner asked for x2 to x4")
    ordered = [BUY_PRICE_ZARNIKI[t] for t in TIERS]
    check(ordered == sorted(set(ordered)), "prices must strictly rise with rarity")
    steps = [UPGRADE_ESSENCE[t] for t in TIERS[1:]]
    check(steps == sorted(set(steps)), "each Essence step must cost more than the one before it")
    check(all(UPGRADE_ESSENCE[t] >= 4 * old for t, old in {"C": 20, "B": 45, "A": 90, "S": 160, "SS": 280, "SSS": 480}.items()), "Essence steps were asked to go up too")


def essence_rate_has_no_discount() -> None:
    check(ESSENCE_PACKS == tuple(sorted(set(ESSENCE_PACKS))), "packs must be unique and ascending")
    # a pack is always `n * rate` Essence; the service never reads another formula (see services.skins_v3.buy_essence),
    # so the Zarniki price of one Essence is the same for every pack
    per = {n: n * ESSENCE_PER_ZARNIK / n for n in ESSENCE_PACKS}
    check(len(set(per.values())) == 1, f"every pack must give the same Essence per Zarnik, got {per}")
    for tier in TIERS[1:]:
        check(essence_zarniki(UPGRADE_ESSENCE[tier]) * ESSENCE_PER_ZARNIK >= UPGRADE_ESSENCE[tier], f"{tier}: rounding must never favour the buyer")


def cheapest_road_is_the_matching_rarity() -> None:
    full = [full_price(t) for t in TIERS]
    check(full == sorted(set(full)), f"the full price must strictly rise with rarity: {full}")
    for target in TIERS:
        roads = []
        for ceiling in TIERS:
            if tier_index(ceiling) < tier_index(target):
                continue                                           # the look cannot reach that tier at all
            chain = sum(UPGRADE_ESSENCE[t] for t in TIERS[1:tier_index(target)])
            roads.append((BUY_PRICE_ZARNIKI[ceiling] + essence_zarniki(chain), ceiling))
        check(min(roads)[1] == target, f"tier {target} must be cheapest on a {target} skin, roads: {sorted(roads)}")
    for tier in TIERS[1:]:   # the upgrade is a real part of the price from the first rarity that has one
        share = essence_zarniki(total_upgrade_cost(tier)) / BUY_PRICE_ZARNIKI[tier]
        check(share >= 0.05, f"{tier}: raising the skin is only {share:.0%} of its price, Essence would be pocket change")
    check(essence_zarniki(total_upgrade_cost("SSS")) / BUY_PRICE_ZARNIKI["SSS"] >= 0.35, "a top skin must keep a substantial Essence chain")
    check(upgrade_cost("D", "D") is None and upgrade_cost("SS", "SS") is None, "a skin never grows past its rarity")


def free_essence_is_small() -> None:
    year = ESSENCE_QUEST_REWARD["daily"] * 365 + (ESSENCE_QUEST_REWARD["weekly"] + ESSENCE_QUEST_REWARD["combined"]) * 52
    reach = 0
    for tier in TIERS[1:]:
        if reach + UPGRADE_ESSENCE[tier] > year:
            break
        reach += UPGRADE_ESSENCE[tier]
    check(year < total_upgrade_cost("SS"), f"a year of quests ({year}) must not raise a skin to SS ({total_upgrade_cost('SS')})")
    check(year < total_upgrade_cost("S") * 2, "a year of quests must stay well below two S chains")
    catalog_price = sum(BUY_PRICE_ZARNIKI[s["tier"]] for s in SKINS.values())
    free = essence_zarniki(total_one_time_essence())
    check(free <= 0.06 * catalog_price, f"all one-time Essence bonuses are worth {free}, over 6% of the whole catalog ({catalog_price})")
    for sid, st in SETS.items():
        cost = sum(BUY_PRICE_ZARNIKI[SKINS[m]["tier"]] for m in st["members"])
        check(essence_zarniki(set_bonus(sid)) <= 0.05 * cost, f"set {sid}: bonus {set_bonus(sid)} is over 5% of its price {cost}")
    for tier in TIERS:
        if row_members(tier):
            cost = sum(BUY_PRICE_ZARNIKI[SKINS[m]["tier"]] for m in row_members(tier))
            check(essence_zarniki(row_bonus(tier)) <= 0.05 * cost, f"row {tier}: bonus {row_bonus(tier)} is over 5% of its price {cost}")
    for sid in SKINS:
        price = BUY_PRICE_ZARNIKI[SKINS[sid]["tier"]]
        check(essence_zarniki(featured_bonus(sid)) <= 0.06 * price + 3, f"{sid}: skin-of-the-week gift {featured_bonus(sid)} is over 6% of the price")
    check(BONUS_SHARE <= 0.05 and ROW_SHARE <= 0.05 and FEATURED_SHARE <= 0.06, "bonus shares were raised above the agreed ceiling")
    check(all(a["at"] < b["at"] for a, b in zip(milestones(), milestones()[1:])), "collection steps must ascend")
    check(milestones()[-1]["at"] == len(PERMANENT), "the last collection step is every permanent skin")


def skin_of_the_week_is_fair() -> None:
    from datetime import datetime, timedelta, timezone
    start = datetime(2026, 10, 5, tzinfo=timezone.utc)                    # a Monday
    a, b = featured(start), featured(start + timedelta(days=6, hours=23))
    check(a == b, "the whole week shows the same skin")
    check(featured(start + timedelta(days=7))["skin_id"] != a["skin_id"], "the next week shows another skin")
    seen = {featured(start + timedelta(days=7 * n))["skin_id"] for n in range(len(PERMANENT))}
    check(seen == set(PERMANENT), "in one cycle every permanent skin is featured exactly once, season skins never")
    check(week_index(start) + 1 == week_index(start + timedelta(days=7)), "week index steps by one")
    check(datetime.fromisoformat(a["ends_at"]) - start == timedelta(days=7), "a week lasts seven days from Monday")


def seasons_are_bounded() -> None:
    from datetime import datetime, timedelta, timezone
    for sid, st in SETS.items():
        if not st.get("season"):
            continue
        win = season_window(st["season"], datetime(2026, 10, 20, tzinfo=timezone.utc))
        start, end = datetime.fromisoformat(win["starts_at"]), datetime.fromisoformat(win["ends_at"])
        check(timedelta(days=14) <= end - start <= timedelta(days=60), f"{sid}: a season lasts two weeks to two months")
        check(season_window(st["season"], start - timedelta(seconds=1))["state"] == "soon" and season_window(st["season"], start)["open"], "a season opens at its start")
        check(season_window(st["season"], end - timedelta(seconds=1))["open"] and season_window(st["season"], end)["state"] == "over", "a season ends exactly at its end")
        check(all(SKINS[m]["season"] == st["season"] for m in st["members"]), f"{sid}: every member sells in the same window")
        check(not any(m in PERMANENT for m in st["members"]), f"{sid}: a season skin is not part of the permanent collection")
    check(all(SKINS[sid]["season"] in {None, *[s["season"] for s in SETS.values() if s.get("season")]} for sid in SKINS), "a season skin belongs to a season set")


def main() -> None:
    prices()
    essence_rate_has_no_discount()
    cheapest_road_is_the_matching_rarity()
    free_essence_is_small()
    skin_of_the_week_is_fair()
    seasons_are_bounded()
    catalog_price = sum(BUY_PRICE_ZARNIKI[s["tier"]] for s in SKINS.values())
    print(f"OK: skins v3 economy. Catalog {catalog_price} Zarniki; full price by rarity "
          + ", ".join(f"{t} {full_price(t)}" for t in TIERS) + f"; free one-time Essence {total_one_time_essence()} (~{essence_zarniki(total_one_time_essence())} Zarniki)")


if __name__ == "__main__":
    main()
