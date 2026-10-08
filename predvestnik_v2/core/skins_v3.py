"""Skins V3 rules: tiers, prices, upgrade costs, Essence, and app-palette derivation.

A skin is a complete look: the app palette plus the profile cosmetics (nickname style, title, frame, halo,
background, particles). Every skin is obtained at tier D and is raised step by step with Essence up to the common
ceiling SSS (the rarity of a skin only sets its price and its collection row). The current tier decides how rich the look is and how many effects run (core/appearance_v3.py
keeps the visibility rule: others see a look only while the owner has VIP).
"""
from __future__ import annotations

from typing import Final

TIERS: Final = ("D", "C", "B", "A", "S", "SS", "SSS")
CEILING: Final = "SSS"      # every skin can be raised to the last tier; the tier written in the catalog is the skin's RARITY (price and collection row)
DEFAULT_SKIN_ID: Final = "default"

# ── Prices ─────────────────────────────────────────────────────────────────────────────────────────────────────
# Price of the skin itself (it starts at tier D); the ceiling decides how far it can grow. Launch prices were
# 100/160/240/340/480/650/900; they are now x3.0 (D) rising to x4.0 (SSS) of that.
BUY_PRICE_ZARNIKI: Final = {"D": 300, "C": 500, "B": 750, "A": 1100, "S": 1700, "SS": 2500, "SSS": 3600}
# Essence needed to move a skin INTO the given tier. C and B are cheap on purpose: a player who never pays sees the first tiers
# fall within one and three weeks of quests, so free progress looks real. From A on the steps are the full ones, and the road to
# a full set stays months long (tools/test_skins_v3_economy.py pins the number of weeks).
UPGRADE_ESSENCE: Final = {"C": 60, "B": 140, "A": 560, "S": 1000, "SS": 1600, "SSS": 2600}

# Essence is sold at ONE fixed rate. There is no volume bonus on purpose: whatever pack is bought, a step costs the same
# Zarniki, so the Zarniki price of a fully raised skin is exactly buy price + chain / ESSENCE_PER_ZARNIK (full_price below).
ESSENCE_PER_ZARNIK: Final = 4
ESSENCE_PACKS: Final = (10, 30, 80, 200)     # Zarniki per pack; a pack gives ESSENCE_PER_ZARNIK * n Essence

# Free Essence is small by design. Every source is listed here so the economy test can add them up:
#   quests: about 65 a week; a set, a rarity row and the collection milestones pay a few percent of what they cost to own.
ESSENCE_QUEST_REWARD: Final = {"daily": 5, "weekly": 20, "combined": 10}
FREE_ESSENCE_PER_WEEK: Final = ESSENCE_QUEST_REWARD["daily"] * 7 + ESSENCE_QUEST_REWARD["weekly"] + ESSENCE_QUEST_REWARD["combined"]   # every quest done, every day
BONUS_SHARE: Final = 0.03        # sets and rarity rows pay this share of the Zarniki price of their members, as Essence
FEATURED_SHARE: Final = 0.05     # skin of the week: buying it during its week pays this share of its price, as Essence
BONUS_STEP: Final = 10           # bonuses are rounded to this many Essence


def tier_index(tier: str) -> int:
    """1 for D … 7 for SSS."""
    return TIERS.index(tier) + 1


def next_tier(tier: str) -> str | None:
    index = TIERS.index(tier)
    return TIERS[index + 1] if index + 1 < len(TIERS) else None


def upgrade_cost(current: str, ceiling: str) -> tuple[str, int] | None:
    """(next tier, Essence) or None when the skin already reached its ceiling."""
    nxt = next_tier(current)
    if nxt is None or tier_index(nxt) > tier_index(ceiling):
        return None
    return nxt, UPGRADE_ESSENCE[nxt]


def total_upgrade_cost(ceiling: str) -> int:
    return sum(UPGRADE_ESSENCE[t] for t in TIERS[1:tier_index(ceiling)])


def essence_zarniki(essence: int) -> int:
    """Zarniki that buy this much Essence at the fixed rate (rounded up: nobody gets Essence below the rate)."""
    return -(-int(essence) // ESSENCE_PER_ZARNIK)


def full_price(rarity: str, ceiling: str = CEILING) -> int:
    """Zarniki to own a skin of this rarity fully raised when everything is bought: skin (by rarity) + all Essence steps up to the ceiling."""
    return BUY_PRICE_ZARNIKI[rarity] + essence_zarniki(total_upgrade_cost(ceiling))


def signature_tier(rarity: str) -> str:
    """Tier at which a skin's signature (its own drawn detail) appears: the skin's rarity from S up, SSS for the rest (their signature crowns the whole climb)."""
    return rarity if tier_index(rarity) >= tier_index("S") else CEILING


def free_weeks(essence: int) -> float:
    """Weeks of perfect quest play (the only free Essence) needed to earn this much Essence."""
    return essence / FREE_ESSENCE_PER_WEEK


def bonus_essence(price_zarniki: int, share: float) -> int:
    """Essence worth `share` of a Zarniki price at the fixed rate, rounded to BONUS_STEP (never below one step)."""
    raw = price_zarniki * share * ESSENCE_PER_ZARNIK
    return max(BONUS_STEP, int(round(raw / BONUS_STEP)) * BONUS_STEP)


# ── Colour helpers: the palette is derived from a few inputs and checked for contrast in tests ─────────────────
def _rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def _hex(rgb: tuple[float, float, float]) -> str:
    return "#" + "".join(f"{max(0, min(255, round(c))):02x}" for c in rgb)


def mix(a: str, b: str, share: float) -> str:
    """share of b in the mix."""
    ra, rb = _rgb(a), _rgb(b)
    return _hex(tuple(ra[i] * (1 - share) + rb[i] * share for i in range(3)))


def _linear(channel: int) -> float:
    c = channel / 255
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def luminance(value: str) -> float:
    r, g, b = _rgb(value)
    return 0.2126 * _linear(r) + 0.7152 * _linear(g) + 0.0722 * _linear(b)


def contrast(a: str, b: str) -> float:
    high, low = sorted((luminance(a), luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def app_tokens(spec: dict) -> dict[str, str]:
    """CSS custom properties for the whole app derived from bg, accent and two glow colours (optional: faint and track for tinted outlines)."""
    bg, acc = spec["bg"], spec["acc"]
    ink = mix("#f4f5f8", acc, 0.06)
    dim = mix(ink, bg, 0.40)
    while contrast(dim, bg) < 5.2 and dim != ink:           # keep small grey text readable (WCAG AA with margin)
        dim = mix(dim, ink, 0.12)
    on_acc = mix(bg, "#000000", 0.35)
    sheet = mix(bg, ink, 0.07)
    r, g, b = _rgb(acc)
    ir, ig, ib = _rgb(ink)
    return {
        "--v3-bg": bg, "--v3-ink": ink, "--v3-dim": dim,
        "--v3-faint": spec.get("faint") or f"rgba({ir},{ig},{ib},.10)", "--v3-track": spec.get("track") or f"rgba({ir},{ig},{ib},.24)",   # a skin may tint its hairlines (neon outlines)
        "--v3-acc": acc, "--v3-on-acc": on_acc, "--v3-ok": "#7fd6a4",
        "--v3-sheet": sheet, "--v3-dock": f"rgba({_rgb(sheet)[0]},{_rgb(sheet)[1]},{_rgb(sheet)[2]},.97)",
        "--v3-dock-on": f"rgba({r},{g},{b},.14)", "--acc-rgb": f"{r},{g},{b}",
        "--v3-wash": (f"radial-gradient(120% 50% at 92% -5%, {spec['g1']}, transparent 60%), "
                      f"radial-gradient(80% 40% at 0% 105%, {spec['g2']}, transparent 60%)"),
    }
