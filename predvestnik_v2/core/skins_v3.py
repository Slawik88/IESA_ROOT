"""Skins V3 rules: tiers, prices, upgrade costs, Essence, and app-palette derivation.

A skin is a complete look: the app palette plus the profile cosmetics (nickname style, title, frame, halo,
background, particles). Every skin is obtained at tier D and is raised step by step with Essence up to its own
ceiling (its rarity). The current tier decides how rich the look is and how many effects run (core/appearance_v3.py
keeps the visibility rule: others see a look only while the owner has VIP).
"""
from __future__ import annotations

from typing import Final

TIERS: Final = ("D", "C", "B", "A", "S", "SS", "SSS")
DEFAULT_SKIN_ID: Final = "default"

# Price of the skin itself (it starts at tier D); the ceiling decides how far it can grow.
BUY_PRICE_ZARNIKI: Final = {"D": 100, "C": 160, "B": 240, "A": 340, "S": 480, "SS": 650, "SSS": 900}
# Essence needed to move a skin INTO the given tier.
UPGRADE_ESSENCE: Final = {"C": 20, "B": 45, "A": 90, "S": 160, "SS": 280, "SSS": 480}
ESSENCE_PER_ZARNIK: Final = 4
ESSENCE_PACKS: Final = (10, 25, 60)          # Zarniki per pack, each pack = ESSENCE_PER_ZARNIK * n Essence
ESSENCE_QUEST_REWARD: Final = {"daily": 5, "weekly": 20, "combined": 10}


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
    """CSS custom properties for the whole app derived from bg, accent and two glow colours."""
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
        "--v3-faint": f"rgba({ir},{ig},{ib},.10)", "--v3-track": f"rgba({ir},{ig},{ib},.24)",
        "--v3-acc": acc, "--v3-on-acc": on_acc, "--v3-ok": "#7fd6a4",
        "--v3-sheet": sheet, "--v3-dock": f"rgba({_rgb(sheet)[0]},{_rgb(sheet)[1]},{_rgb(sheet)[2]},.97)",
        "--v3-dock-on": f"rgba({r},{g},{b},.14)", "--acc-rgb": f"{r},{g},{b}",
        "--v3-wash": (f"radial-gradient(120% 50% at 92% -5%, {spec['g1']}, transparent 60%), "
                      f"radial-gradient(80% 40% at 0% 105%, {spec['g2']}, transparent 60%)"),
    }
