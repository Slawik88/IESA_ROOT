#!/usr/bin/env python3
"""Ten-year player economy simulator (ECO-04), expectation model, one step per week.

Reads the live chest tables from ``core.chests_v1`` and applies the proposed
changes on top (key tiers, loot scale after ECO-02, pet level-ups paid with
cards + Mora + Essence, Mora/Diamond/Essence shop).  Nothing here touches a
database; every number that is an assumption is in ``P`` or ``PROFILES``.

    PYTHONPATH=. python3 tools/economy_sim_v4.py            # tables
    PYTHONPATH=. python3 tools/economy_sim_v4.py --json out.json
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field

import importlib.util
import sys

from core import chests_v1 as chests

PRE_ECO02_CATALOG = "chests-mixed-s1-v2"      # tables before ECO-02: loot_scale below imitates the ECO-02 cut on them

WEEKS = 520
ZAR_PER_STAR = 10
PACK_BONUS = 1.09                 # average bonus of the Stars packs (215/200 ... 4400/4000)
UAH_PER_STAR = 1.0                # owner: 1 star ~ 1 UAH
CHF_PER_UAH = 0.02

def use_tables(path: str) -> None:
    """Load a chests_v1.py (e.g. the ECO-02 branch) instead of core.chests_v1 and stop scaling the loot."""
    global chests
    spec = importlib.util.spec_from_file_location("chests_tables", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["chests_tables"] = module
    spec.loader.exec_module(module)
    chests = module
    P["loot_scale"] = {k: 1.0 for k in P["loot_scale"]}


def guard_tables() -> str:
    """The cut must be applied once: tables already cut (ECO-02 merged) mean loot_scale 1.0."""
    version = chests.CATALOG_VERSION
    if version != PRE_ECO02_CATALOG and any(v != 1.0 for v in P["loot_scale"].values()):
        P["loot_scale"] = {k: 1.0 for k in P["loot_scale"]}
    return version


# ── proposed rules (all tunable) ──────────────────────────────────────────────
P = {
    # loot after ECO-02 (Zarniki are NOT cut: the owner says they are the base of the project)
    "loot_scale": {"mora": 0.49, "diamonds": 0.44, "zarniki": 1.0, "cards": 0.55, "jokers": 0.48},
    "joker_cards": 250,                       # a joker is this many cards of any species of its rarity
    # key ladder: tier -> (Mora, Diamonds, Zarniki, Essence, weekly cap or None for daily cap)
    "keys": {
        3: dict(mora=800, dia=0, zar=0, ess=0, cap=3),
        4: dict(mora=300, dia=0, zar=0, ess=200, cap=1),       # craft: Essence + Mora (F2P route)
        6: dict(mora=3000, dia=5, zar=0, ess=0, cap=1),        # owner: 5 diamonds + 3000 Mora (tier is a sweep)
    },
    "top_tier": 6,
    "paid_key": {"tier": 4, "zar": 120, "per_day": 2},        # paid route, daily limit
    "paid_split": 0.0,                                          # share of the key budget that goes to paid_key2
    "paid_key2": {"tier": 6, "zar": 300, "per_day": 1},
    "polish": dict(mora=600, dia=1, ess=60, cap=2),            # owner said 10 Essence; 1 diamond is worth ~250 Essence at skin prices
    # pets: one level-up L -> L+1 costs cards, Mora and (at stages) Essence
    "pet_cards_total": 89_586,                # owner-fixed Common/Rare L1->L16
    "pet_levels": 16,
    "pet_card_curve": 2.0,                    # cost_L ~ L^curve
    "pet_mora_total": 3_000,                  # per Common pet, L1->L16 (rarity multiplier below)
    "pet_mora_curve": 1.6,
    "pet_essence_stage": {5: 20, 10: 60, 15: 150},
    "rarity_mult": {"common": 1.0, "uncommon": 1.1, "rare": 1.25, "epic": 1.5, "legendary": 1.8},
    "rarity_cards_mult": {"common": 1.0, "uncommon": 1.0, "rare": 1.0, "epic": 0.7, "legendary": 0.5},
    # season pass (approved budget): full track 1200 Mora + 300 Essence per 30.5 weeks
    "pass_weeks": 30.5, "pass_mora": 1200, "pass_ess": 300, "pass_dia_per_season": 6,
    "achievements_mora": 2575,
    # pet route rewards (ECO-04, PR #29): Mora per completed expedition, EV 80 at 6h, up to +24% at L16, weekly cap
    "pet_route": {"ev": 80, "max_uplift": 0.24, "weekly_cap": 400, "enabled": True},
    # gifts: tier -> (currency, price)
    "gifts": {"T1": ("mora", 300), "T2": ("mora", 1500), "T3": ("dia", 4), "T4": ("zar", 1500)},
}
SPECIES = {"common": 5, "uncommon": 3, "rare": 2, "epic": 1, "legendary": 1}


@dataclass
class Profile:
    name: str
    label: str
    quest_mora: float        # per week
    quest_ess: float
    quest_keys: float        # free tier-1 keys from quests per week (ECO-02: daily set 2, weekly set 3)
    pet_keys: float          # free tier-1 keys from pet runs per week
    pass_completion: float   # share of the season-pass track finished
    ach_weeks: int           # lifetime achievements are earned over this many weeks
    gifts_per_week: float    # gifts sent per week (average over the year)
    stars_per_month: float = 0.0
    key_budget_share: float = 0.0   # share of Zarniki a payer is willing to put into paid keys
    vip: bool = False
    exchange_z: float = 0.0          # Zarniki a payer sends through the Zarniki->Mora/Diamond exchange per week
    exchange_dia_share: float = 0.0
    skin_chain: bool = False
    note: str = ""


PROFILES = [
    Profile("casual", "Малоактивный", 215, 40, 7, 2, 0.10, 400, 0.05, note="2 набора дня в неделю + недельный, раз в пару дней в боте"),
    Profile("mid", "Средний", 255, 50, 11, 3, 0.40, 250, 0.10, note="4 набора дня + недельный"),
    Profile("active", "Активный", 315, 65, 17, 5, 1.00, 156, 0.20, note="всё, каждый день"),
    Profile("payer_light", "Платящий лёгкий", 255, 50, 11, 3, 0.40, 250, 0.20, stars_per_month=100, key_budget_share=0.30,
            exchange_z=25, exchange_dia_share=0.0, skin_chain=True,
            note="как средний + 100⭐ (≈100 грн) в месяц"),
    Profile("payer_heavy", "Платящий крупный", 315, 65, 17, 5, 1.00, 156, 0.60, stars_per_month=400, key_budget_share=0.30, vip=True,
            exchange_z=150, exchange_dia_share=0.35, skin_chain=True,
            note="как активный + VIP + 400⭐ (≈400 грн) в месяц"),
]


# ── chest tables per tier (real weights) ──────────────────────────────────────
def tier_table(tier: int, loot: dict) -> dict:
    weights = {s: w for s, w in chests.STAR_WEIGHTS.items() if s >= tier}
    weights[tier] += sum(w for s, w in chests.STAR_WEIGHTS.items() if s < tier)
    total = sum(weights.values())
    out = {"mora": 0.0, "diamonds": 0.0, "zarniki": 0.0, "jokers": {r: 0.0 for r in chests.JOKER_RARITIES},
           "cards": {r: 0.0 for r in chests.JOKER_RARITIES}}
    species = {r: [k for k, v in chests.PET_SPECIES.items() if v["rarity"] == r] for r in chests.JOKER_RARITIES}
    for star, w in weights.items():
        p = w / total
        for kind, pct in chests.REWARD_WEIGHTS[star].items():
            q = p * pct / 100
            if kind == "mora":
                out["mora"] += q * sum(chests.MORA_RANGES[star]) / 2 * loot["mora"]
            elif kind == "diamonds":
                out["diamonds"] += q * sum(chests.DIAMOND_RANGES[star]) / 2 * loot["diamonds"]
            elif kind == "zarniki":
                out["zarniki"] += q * sum(chests.ZARNIKI_RANGES[star]) / 2 * loot["zarniki"]
            elif kind == "pet_card":
                for r, share in chests.CARD_RARITY_WEIGHTS[star].items():
                    out["cards"][r] += q * share / 100 / len(species[r]) * chests.CARD_AMOUNTS[star] * loot["cards"]
            elif kind == "joker":
                for r, share in chests.JOKER_RARITY_WEIGHTS[star].items():
                    out["jokers"][r] += q * share / 100 * chests.JOKER_AMOUNTS[star] * loot["jokers"]
    return out


def pet_costs(rarity: str) -> list[tuple[float, float]]:
    """(cards, mora) for each level step 1..15."""
    n = P["pet_levels"] - 1
    curve_c = [(l ** P["pet_card_curve"]) for l in range(1, n + 1)]
    curve_m = [(l ** P["pet_mora_curve"]) for l in range(1, n + 1)]
    kc = P["pet_cards_total"] * P["rarity_cards_mult"][rarity] / sum(curve_c)
    km = P["pet_mora_total"] * P["rarity_mult"][rarity] / sum(curve_m)
    return [(kc * a, km * b) for a, b in zip(curve_c, curve_m)]


# ── one player ────────────────────────────────────────────────────────────────
@dataclass
class State:
    mora: float = 0.0
    dia: float = 0.0
    ess: float = 0.0
    zar: float = 0.0
    keys: dict = field(default_factory=lambda: {1: 0.0})
    pets: list = field(default_factory=list)       # dicts: rarity, level, cards
    spent: dict = field(default_factory=dict)
    earned: dict = field(default_factory=dict)
    opens: dict = field(default_factory=dict)
    stars: float = 0.0


def add(d: dict, k: str, v: float) -> None:
    d[k] = d.get(k, 0.0) + v


def simulate(profile: Profile, weeks: int = WEEKS) -> dict:
    tables = {t: tier_table(t, P["loot_scale"]) for t in range(1, 9)}
    st = State()
    for rarity, n in SPECIES.items():
        for _ in range(n):
            st.pets.append({"rarity": rarity, "level": 1, "cards": 0.0, "costs": pet_costs(rarity)})
    rows, first_max = [], {}
    for week in range(1, weeks + 1):
        # 1. income -----------------------------------------------------------
        pass_share = profile.pass_completion / P["pass_weeks"]
        inc = {"mora": profile.quest_mora + P["pass_mora"] * pass_share + (240 if profile.vip else 0),
               "ess": profile.quest_ess + P["pass_ess"] * pass_share,
               "dia": P["pass_dia_per_season"] * pass_share}
        if week <= profile.ach_weeks:
            inc["mora"] += P["achievements_mora"] / profile.ach_weeks
        st.mora += inc["mora"]; st.ess += inc["ess"]; st.dia += inc["dia"]
        for k, v in inc.items():
            add(st.earned, f"{k}_free", v)
        st.keys[1] = st.keys.get(1, 0.0) + profile.quest_keys + profile.pet_keys + (2 if profile.vip else 0)
        if P["pet_route"]["enabled"]:
            best = max((pet["level"] for pet in st.pets), default=1)
            route = profile.pet_keys / 2 * P["pet_route"]["ev"] * (1 + P["pet_route"]["max_uplift"] * (best - 1) / (P["pet_levels"] - 1))
            route = min(route, P["pet_route"]["weekly_cap"])
            st.mora += route
            add(st.earned, "mora_route", route)
        if profile.stars_per_month and week % 4 == 1:          # Zarniki purchase once a month
            z = profile.stars_per_month * ZAR_PER_STAR * PACK_BONUS
            st.zar += z; st.stars += profile.stars_per_month
            add(st.earned, "zar_bought", z)
        if profile.exchange_z:                                   # Zarniki -> Mora / Diamonds (cap 50 per day)
            z = min(profile.exchange_z, st.zar, 350)
            to_dia = z * profile.exchange_dia_share
            st.zar -= z; st.mora += (z - to_dia) * 10; st.dia += to_dia * 0.01
            add(st.earned, "mora_exchange", (z - to_dia) * 10); add(st.earned, "dia_exchange", to_dia * 0.01)
            add(st.spent, "zar_exchange", z)
        # 2. open every key in stock ------------------------------------------
        cards = {r: 0.0 for r in SPECIES}
        for tier, n in list(st.keys.items()):
            if n <= 0:
                continue
            t = tables[tier]
            st.mora += n * t["mora"]; st.dia += n * t["diamonds"]; st.zar += n * t["zarniki"]
            add(st.earned, "mora_chests", n * t["mora"]); add(st.earned, "dia_chests", n * t["diamonds"])
            add(st.earned, "zar_chests", n * t["zarniki"])
            for r in SPECIES:
                cards[r] += n * t["cards"][r] + n * t["jokers"][r] * P["joker_cards"] / SPECIES[r]
            add(st.opens, f"opened_t{tier}", n)
            st.keys[tier] = 0.0
        # 3. pets first: level-ups are the main Mora sink -----------------------
        for pet in sorted(st.pets, key=lambda p: p["level"]):
            pet["cards"] += cards[pet["rarity"]]
            while pet["level"] < P["pet_levels"]:
                need_c, need_m = pet["costs"][pet["level"] - 1]
                stage = P["pet_essence_stage"].get(pet["level"] + 1, 0)
                if pet["cards"] < need_c or st.mora < need_m or st.ess < stage:
                    break
                pet["cards"] -= need_c; st.mora -= need_m; st.ess -= stage
                add(st.spent, "mora_pets", need_m); add(st.spent, "ess_pets", stage)
                pet["level"] += 1
                if pet["level"] == P["pet_levels"]:
                    first_max.setdefault(pet["rarity"], week)
        # 4. Zarniki keys (payers, daily limit); the budget is split between the two paid keys --------
        if profile.stars_per_month:
            budget = profile.stars_per_month * ZAR_PER_STAR * PACK_BONUS * profile.key_budget_share / 4.33
            for name, share in (("paid_key", 1 - P["paid_split"]), ("paid_key2", P["paid_split"])):
                rule = P[name]
                if not rule["zar"] or share <= 0:
                    continue
                n = min(budget * share / rule["zar"], rule["per_day"] * 7, st.zar / rule["zar"])
                st.keys[rule["tier"]] = st.keys.get(rule["tier"], 0.0) + n
                st.zar -= n * rule["zar"]; add(st.spent, "zar_keys", n * rule["zar"])
                add(st.opens, f"bought_t{rule['tier']}", n)
        # 5. shop for Mora / Diamonds / Essence ---------------------------------
        keys = P["keys"]
        top = P["top_tier"]
        reserve = keys[top]["mora"] if st.dia >= keys[top]["dia"] else 0     # a top key is worth saving for
        order = (top, 4, 3)
        for tier in order:
            rule = keys[tier]
            hold = reserve if tier != top else 0
            n = 0.0
            ess_floor = max(P["pet_essence_stage"].values()) if any(p["level"] < 15 for p in st.pets) and tier == 4 else 0
            while n < rule["cap"] and st.mora - hold >= rule["mora"] and st.dia >= rule["dia"] and st.ess - ess_floor >= rule["ess"]:
                st.mora -= rule["mora"]; st.dia -= rule["dia"]; st.ess -= rule["ess"]
                add(st.spent, "mora_keys", rule["mora"]); add(st.spent, "dia_keys", rule["dia"])
                add(st.spent, "ess_keys", rule["ess"])
                n += 1
            st.keys[tier] = st.keys.get(tier, 0.0) + n
            add(st.opens, f"crafted_t{tier}" if rule["ess"] else f"shop_t{tier}", n)
        rule = P["polish"]
        n = 0
        reserve = keys[top]["mora"] if st.dia >= keys[top]["dia"] else 0
        while n < rule["cap"] and st.mora - reserve >= rule["mora"] and st.dia - keys[top]["dia"] >= rule["dia"]:
            st.mora -= rule["mora"]; st.dia -= rule["dia"]; st.ess += rule["ess"]
            add(st.spent, "mora_polish", rule["mora"]); add(st.spent, "dia_polish", rule["dia"])
            add(st.earned, "ess_polish", rule["ess"])
            n += 1
        # 6. gifts from what is left, social, cheapest tier most often -------------
        for tier, share in (("T1", 0.55), ("T2", 0.30), ("T3", 0.10), ("T4", 0.05)):
            cur, price = P["gifts"][tier]
            bal = {"mora": max(st.mora - reserve, 0), "dia": max(st.dia - keys[top]["dia"], 0), "zar": st.zar}[cur]
            k = min(share * profile.gifts_per_week, bal / price)
            if cur == "zar" and not profile.stars_per_month:
                k = 0.0
            if k > 0:
                if cur == "mora": st.mora -= k * price
                elif cur == "dia": st.dia -= k * price
                else: st.zar -= k * price
                add(st.spent, f"{cur}_gifts", k * price)
        # 7. payers spend the rest of the month's Zarniki on things outside this model (VIP, skins, Essence packs)
        if profile.stars_per_month and st.zar > 0:
            out = st.zar
            add(st.spent, "zar_store_other", out); st.zar = 0.0
            if profile.skin_chain:                                # payers own skins: Essence goes into tier steps
                use = st.ess
                add(st.spent, "ess_skins", use); st.ess = 0.0
        if week % 26 == 0 or week == 1:
            rows.append(snapshot(st, week, profile))
    return {"profile": profile.name, "label": profile.label, "note": profile.note, "rows": rows,
            "first_max_week": first_max, "spent": st.spent, "earned": st.earned, "opens": st.opens,
            "stars_total": st.stars,
            "revenue_uah": st.stars * UAH_PER_STAR, "revenue_chf": st.stars * UAH_PER_STAR * CHF_PER_UAH}


def snapshot(st: State, week: int, profile: Profile) -> dict:
    by_r: dict[str, list] = {}
    for p in st.pets:
        by_r.setdefault(p["rarity"], []).append(p["level"])
    income = (profile.quest_mora + 1) or 1
    return {"week": week, "year": round(week / 52, 1), "mora": round(st.mora), "dia": round(st.dia, 2),
            "ess": round(st.ess), "zar": round(st.zar),
            "avg_level": round(sum(p["level"] for p in st.pets) / len(st.pets), 2),
            "levels": {r: round(sum(v) / len(v), 1) for r, v in by_r.items()},
            "hoard_weeks": round(st.mora / income, 1)}


def with_params(changes: dict, profile_names=None):
    """Run the profiles with ``P`` patched by ``changes`` ({"paid_key.zar": 200}); P is restored afterwards."""
    import copy
    saved = copy.deepcopy(P)
    try:
        for path, value in changes.items():
            node = P
            *head, last = path.split(".")
            for part in head:
                node = node[int(part)] if part.isdigit() and int(part) in node else node[part]
            node[int(last) if last.isdigit() and int(last) in node else last] = value
        return [simulate(p) for p in PROFILES if not profile_names or p.name in profile_names]
    finally:
        P.clear(); P.update(saved)


def brief(r: dict) -> dict:
    fm = r["first_max_week"]
    last = r["rows"][-1]
    return {"profile": r["profile"], "common_max_year": round(fm["common"] / 52, 1) if "common" in fm else None,
            "rare_max_year": round(fm["rare"] / 52, 1) if "rare" in fm else None,
            "lvl10": last["avg_level"], "stars": r["stars_total"],
            "bought": {k: round(v) for k, v in r["opens"].items() if k.startswith(("bought", "shop", "crafted"))}}


def sweeps() -> None:
    print("\n== ПРОГОН: цена платного ключа 4★ в зарниках")
    for z in (60, 120, 200, 300):
        out = with_params({"paid_key.zar": z}, ("payer_light", "payer_heavy"))
        print(z, [(b["profile"], b["common_max_year"], b["bought"].get("bought_t4")) for b in map(brief, out)])
    print("\n== ПРОГОН: платный ключ 4★ (120) против 6★ (300) и их смесь")
    for tier, z, split in ((4, 120, 0.0), (6, 300, 1.0), (5, 200, 1.0), (7, 600, 1.0)):
        out = with_params({"paid_key2.tier": tier, "paid_key2.zar": z, "paid_split": split}, ("payer_light", "payer_heavy"))
        print(tier, z, [(b["profile"], b["common_max_year"], b["bought"]) for b in map(brief, out)])
    print("\n== ПРОГОН: бесплатный лут (масштаб карт 0.55 -> другой)")
    for sc in (0.35, 0.55, 0.8, 1.0):
        out = with_params({"loot_scale.cards": sc})
        print(sc, [(b["profile"], b["common_max_year"], b["lvl10"]) for b in map(brief, out)])
    print("\n== ПРОГОН: ключ за Алмазы — какой тир при цене 5 алмазов + 3000 Моры")
    for tier in (5, 6, 7):
        ladder = {3: P["keys"][3], 4: P["keys"][4], tier: dict(mora=3000, dia=5, zar=0, ess=0, cap=1)}
        out = with_params({"top_tier": tier, "keys": ladder})
        print(tier, [(b["profile"], b["common_max_year"], b["bought"].get(f"shop_t{tier}")) for b in map(brief, out)])
    print("\n== ПРОГОН: платящий вкладывает в ключи 30% / 60% / 100% покупок (ключ 4★ за 120)")
    for share in (0.3, 0.6, 1.0):
        saved = [pr.key_budget_share for pr in PROFILES]
        for pr in PROFILES:
            if pr.stars_per_month:
                pr.key_budget_share = share
        out = with_params({}, ("payer_light", "payer_heavy"))
        for pr, v in zip(PROFILES, saved):
            pr.key_budget_share = v
        print(share, [(b["profile"], b["common_max_year"], b["bought"].get("bought_t4")) for b in map(brief, out)])


def run() -> list[dict]:
    return [simulate(p) for p in PROFILES]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json")
    ap.add_argument("--sweep", action="store_true")
    ap.add_argument("--tables", help="path to a chests_v1.py (e.g. the ECO-02 branch); loot is then not scaled again")
    args = ap.parse_args()
    if args.tables:
        use_tables(args.tables)
    print("таблицы сундуков:", guard_tables(), "| лут ×", P["loot_scale"])
    if args.sweep:
        sweeps()
        return
    results = run()
    for r in results:
        print(f"\n== {r['label']} ({r['note']})")
        print(" год   Мора  Алм  Эсс  Зарн  ср.ур.пит  запас Моры в неделях дохода")
        for row in r["rows"]:
            if row["week"] % 52 == 0:
                print(f"{row['year']:>4} {row['mora']:>6} {row['dia']:>5} {row['ess']:>5} {row['zar']:>5} "
                      f"{row['avg_level']:>8}   {row['hoard_weeks']:>6}")
        print(" макс. уровень (неделя):", r["first_max_week"] or "никто за 10 лет")
        print(" потрачено:", {k: round(v) for k, v in r["spent"].items()})
        print(" выручка: %.0f⭐ = %.0f грн = %.1f CHF" % (r["stars_total"], r["revenue_uah"], r["revenue_chf"]))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump({"params": P, "results": results}, fh, ensure_ascii=False, indent=1, default=str)


if __name__ == "__main__":
    main()
