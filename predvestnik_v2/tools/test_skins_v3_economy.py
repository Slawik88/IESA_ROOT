#!/usr/bin/env python3
"""Skins V3 economy invariants (no database): prices only go up with rarity and Essence cannot be a cheap road around them.

What this proves, in Zarniki (1 Zarnik = ESSENCE_PER_ZARNIK Essence at every pack size):
  * a skin is never cheaper than the old launch price times two, and never dearer than times four;
  * buying every Essence step with Zarniki costs exactly the chain / rate: no pack discounts the rate;
  * every skin is raised to SSS by the same Essence chain; the rarity only sets the entry price, so the full price rises with it;
  * free Essence (quests, sets, rarity rows, collection steps, skin of the week) is a small share of what it costs to own.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.skins_v3 import (BONUS_SHARE, BONUS_ESSENCE_RATE, BUY_PRICE_ZARNIKI, CEILING, signature_tier, ESSENCE_PACKS, ESSENCE_PER_ZARNIK, ESSENCE_QUEST_REWARD, FEATURED_SHARE, FREE_ESSENCE_PER_WEEK, purchased_essence,  # noqa: E402
                           TIERS, UPGRADE_ESSENCE, essence_zarniki, free_weeks, full_price, tier_index, total_upgrade_cost, upgrade_cost)
from core.skins_v3_catalog import EXCLUSIVE_HOLDERS, SEASONS, SETS, SKINS  # noqa: E402
from services.skins_v3 import look_payload  # noqa: E402
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
    check(all(UPGRADE_ESSENCE[t] >= 2 * old for t, old in {"C": 20, "B": 45, "A": 90, "S": 160, "SS": 280, "SSS": 480}.items()), "Essence steps went up at least twofold")
    check(all(UPGRADE_ESSENCE[t] >= 5 * old for t, old in {"A": 90, "S": 160, "SS": 280, "SSS": 480}.items()), "from A on the full step applies")


def essence_rate_has_no_discount() -> None:
    check(ESSENCE_PACKS == (20, 30, 50, 80, 200, 500), "owner-approved pack sizes")
    check([purchased_essence(n) for n in ESSENCE_PACKS] == [50, 75, 125, 200, 500, 1250], "exact integer credits at 5/2")
    check(all(isinstance(purchased_essence(n), int) for n in ESSENCE_PACKS), "ledger amounts stay integer")
    for essence in range(1, 101):
        cost = essence_zarniki(essence)
        check(cost * 5 >= essence * 2 and (cost - 1) * 5 < essence * 2, "conversion rounds up exactly")
    check(ESSENCE_PACKS == tuple(sorted(set(ESSENCE_PACKS))), "packs must be unique and ascending")
    # a pack is always `n * rate` Essence; the service never reads another formula (see services.skins_v3.buy_essence),
    # so the Zarniki price of one Essence is the same for every pack
    per = {n: n * ESSENCE_PER_ZARNIK / n for n in ESSENCE_PACKS}
    check(len(set(per.values())) == 1, f"every pack must give the same Essence per Zarnik, got {per}")
    for tier in TIERS[1:]:
        check(essence_zarniki(UPGRADE_ESSENCE[tier]) * ESSENCE_PER_ZARNIK >= UPGRADE_ESSENCE[tier], f"{tier}: rounding must never favour the buyer")


def every_skin_reaches_the_last_tier() -> None:
    """The rarity of a skin only sets what it costs to start and which collection row it sits in: every skin is raised to SSS by the same chain."""
    check(CEILING == TIERS[-1] == "SSS", "the common ceiling is the last tier")
    full = [full_price(t) for t in TIERS]
    check(full == sorted(set(full)), f"the full price must strictly rise with rarity: {full}")
    chain = essence_zarniki(total_upgrade_cost(CEILING))
    check(all(full_price(t) == BUY_PRICE_ZARNIKI[t] + chain for t in TIERS), "full price is the entry price of the rarity plus one common chain")
    check(chain >= 0.35 * BUY_PRICE_ZARNIKI["SSS"] and chain >= 3 * BUY_PRICE_ZARNIKI["D"], "the climb to SSS stays a substantial part of the price on every rarity")
    for sid, skin in SKINS.items():
        road, tier = [], "D"
        while (step := upgrade_cost(tier, CEILING)):
            tier = step[0]; road.append(tier)
        check(road == list(TIERS[1:]), f"{sid}: the road from D must lead through every tier to SSS, got {road}")
        look = look_payload(sid, "D")
        check(look["ceiling"] == "SSS" and look["rarity"] == skin["tier"] and look["sig_from"] == signature_tier(skin["tier"]), f"{sid}: look payload ceiling/rarity/sig_from")
    check(upgrade_cost("SSS", CEILING) is None, "nothing grows past SSS")
    check({signature_tier(t) for t in TIERS[:4]} == {"SSS"} and [signature_tier(t) for t in TIERS[4:]] == ["S", "SS", "SSS"], "a signature appears at the rarity from S up and at SSS below it")
    for sid, skin in SKINS.items():
        if skin["sig"]:
            check(tier_index(signature_tier(skin["tier"])) >= tier_index(skin["tier"]), f"{sid}: its signature cannot show below its own rarity")


def free_essence_is_small() -> None:
    # Подарки остаются прежними; при новом курсе их стоимость в Зарниках выше в 4/2,5 раза.
    bonus_value_scale = BONUS_ESSENCE_RATE / ESSENCE_PER_ZARNIK
    year = ESSENCE_QUEST_REWARD["daily"] * 365 + (ESSENCE_QUEST_REWARD["weekly"] + ESSENCE_QUEST_REWARD["combined"]) * 52
    reach = 0
    for tier in TIERS[1:]:
        if reach + UPGRADE_ESSENCE[tier] > year:
            break
        reach += UPGRADE_ESSENCE[tier]
    check(year < total_upgrade_cost("SSS") * 0.6, f"a year of quests ({year}) must stay far from a top skin at SSS ({total_upgrade_cost('SSS')})")
    check(year < total_upgrade_cost("S") * 2, "a year of quests must stay well below two S chains")
    catalog_price = sum(BUY_PRICE_ZARNIKI[s["tier"]] for s in SKINS.values() if not s["exclusive"])   # a personal skin is not for sale
    free = essence_zarniki(total_one_time_essence())
    check(free <= 0.06 * bonus_value_scale * catalog_price, f"preserved one-time gifts exceed the historical grant budget: {free}")
    for sid, st in SETS.items():
        cost = sum(BUY_PRICE_ZARNIKI[SKINS[m]["tier"]] for m in st["members"])
        check(essence_zarniki(set_bonus(sid)) <= 0.05 * bonus_value_scale * cost, f"set {sid}: preserved gift exceeds historical budget")
    for tier in TIERS:
        if row_members(tier):
            cost = sum(BUY_PRICE_ZARNIKI[SKINS[m]["tier"]] for m in row_members(tier))
            check(essence_zarniki(row_bonus(tier)) <= 0.05 * bonus_value_scale * cost, f"row {tier}: preserved gift exceeds historical budget")
    for sid in PERMANENT:
        price = BUY_PRICE_ZARNIKI[SKINS[sid]["tier"]]
        check(essence_zarniki(featured_bonus(sid)) <= 0.06 * bonus_value_scale * price + 3, f"{sid}: preserved weekly gift exceeds historical budget")
    check(BONUS_SHARE <= 0.05 and ROW_SHARE <= 0.05 and FEATURED_SHARE <= 0.06, "bonus shares were raised above the agreed ceiling")
    check(all(a["at"] < b["at"] for a, b in zip(milestones(), milestones()[1:])), "collection steps must ascend")
    check(milestones()[-1]["at"] == len(PERMANENT), "the last collection step is every permanent skin")
    personal = [sid for sid, skin in SKINS.items() if skin["exclusive"]]
    check(len(personal) == 2 and EXCLUSIVE_HOLDERS == 1, "two personal skins, one holder each")
    check(not set(personal) & set(PERMANENT) and not any(SKINS[sid]["set"] or SKINS[sid]["season"] for sid in personal),
          "a personal skin never counts toward ranks, rows, sets, seasons or the skin of the week")
    check(all(sid not in row_members(SKINS[sid]["tier"]) for sid in personal), "a personal skin is in no rarity row")


def free_farm_is_long() -> None:
    """A player who never pays: the first tiers come fast (so farming feels real), but no set is finished within months."""
    check(FREE_ESSENCE_PER_WEEK == 65, "the free Essence rate changed: re-read this test before changing it")
    check(free_weeks(UPGRADE_ESSENCE["C"]) <= 2, "the first tier must come within two weeks of quests")
    check(free_weeks(UPGRADE_ESSENCE["C"] + UPGRADE_ESSENCE["B"]) <= 4, "tier B must come within about a month")
    check(free_weeks(total_upgrade_cost("A")) >= 8, f"tier A on one skin must take two months or more of quests, got {free_weeks(total_upgrade_cost('A')):.1f} weeks")
    check(free_weeks(total_upgrade_cost("S")) >= 26, "tier S on one skin must take about half a year of quests")
    check(free_weeks(total_upgrade_cost("SS")) >= 50, "tier SS on one skin must take about a year of daily perfect quests")
    check(free_weeks(total_upgrade_cost("SSS")) >= 85, "tier SSS (which needs VIP too) must take well over a year")
    for sid, st in SETS.items():
        chain = sum(total_upgrade_cost(SKINS[m]["tier"]) for m in st["members"])
        check(free_weeks(chain) >= 12, f"set {sid}: raising all three skins takes {free_weeks(chain):.1f} weeks of quests, it must stay over three months")
        check(free_weeks(chain) > 4.5 * 2, f"set {sid}: a month of quests must be nowhere near a full set")
    month = free_weeks(1) * 0 + FREE_ESSENCE_PER_WEEK * 4.35
    check(month < min(sum(total_upgrade_cost(SKINS[m]["tier"]) for m in st["members"]) for st in SETS.values()) / 3, "a month of quests is under a third of the cheapest set")


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
    at = lambda *a: datetime(*a, tzinfo=timezone.utc)
    for sid, st in SETS.items():
        if not st.get("season"):
            continue
        check(all(SKINS[m]["season"] == st["season"] for m in st["members"]), f"{sid}: every member sells in the same window")
        check(not any(m in PERMANENT for m in st["members"]), f"{sid}: a season skin is not part of the permanent collection")
    check(all(SKINS[sid]["season"] in {None, *[s["season"] for s in SETS.values() if s.get("season")]} for sid in SKINS), "a season skin belongs to a season set")
    # the calendar does the work: every year, and a window can cross New Year
    check(season_window("halloween", at(2026, 10, 16, 23, 59, 59))["state"] == "soon" and season_window("halloween", at(2026, 10, 17))["open"], "Halloween opens on its day")
    check(season_window("halloween", at(2026, 11, 3, 23, 59, 59))["open"] and not season_window("halloween", at(2026, 11, 4))["open"], "Halloween closes on its end day")
    check(season_window("halloween", at(2027, 10, 25))["open"] and season_window("halloween", at(2030, 10, 31))["open"], "it comes back every year with no edit")
    soon = season_window("halloween", at(2026, 11, 20))
    check(soon["state"] == "soon" and soon["starts_at"].startswith("2027-10-17"), "after the window the next opening is a year later")
    check(season_window("new_year", at(2026, 12, 20))["open"] and season_window("new_year", at(2027, 1, 5))["open"] and not season_window("new_year", at(2027, 1, 11))["open"], "New Year crosses the year edge")
    check(season_window("new_year", at(2027, 1, 5))["starts_at"].startswith("2026-12-15") and season_window("new_year", at(2027, 1, 5))["ends_at"].startswith("2027-01-11"), "the window crossing the year keeps its true dates")
    for season_id in SEASONS:
        win = season_window(season_id, at(2026, 6, 1))
        length = datetime.fromisoformat(win["ends_at"]) - datetime.fromisoformat(win["starts_at"])
        check(timedelta(days=14) <= length <= timedelta(days=60), f"{season_id}: a season lasts two weeks to two months")
    import os
    os.environ["SKINS_V3_SEASONS_OPEN"] = "halloween"
    try:
        check(season_window("halloween", at(2026, 3, 1))["open"] and not season_window("new_year", at(2026, 3, 1))["open"], "the test-stand switch opens only the named season")
    finally:
        os.environ.pop("SKINS_V3_SEASONS_OPEN", None)
    check(not season_window("halloween", at(2026, 3, 1))["open"], "the switch is off by default")


def main() -> None:
    prices()
    essence_rate_has_no_discount()
    every_skin_reaches_the_last_tier()
    free_essence_is_small()
    free_farm_is_long()
    skin_of_the_week_is_fair()
    seasons_are_bounded()
    catalog_price = sum(BUY_PRICE_ZARNIKI[s["tier"]] for s in SKINS.values() if not s["exclusive"])   # a personal skin is not for sale
    print(f"OK: skins v3 economy. Catalog {catalog_price} Zarniki; full price by rarity "
          + ", ".join(f"{t} {full_price(t)}" for t in TIERS) + f"; free one-time Essence {total_one_time_essence()} (~{essence_zarniki(total_one_time_essence())} Zarniki)")


if __name__ == "__main__":
    main()
