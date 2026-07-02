"""
services/ui.py
Shared visual-design helpers for consistent, compact, beautiful bot messages.
Pure formatting — no DB, no platform imports.

Design language:
  • Headers: emoji + bold caps, e.g. "👤 <b>ПРОФИЛЬ</b>"
  • Trees:   ├ for middle items, └ for the last  (use tree())
  • Bars:    ▰▱ for emphasis bars, █░ for fatigue/progress
  • Inline:  combine related stats on one line with " · " separator
  • Dividers: thin "─" line between logical blocks (use DIVIDER)
"""
from services.formatting import format_currency


DIVIDER = "━━━━━━━━━━━━━━"
THIN = "─────────────"


def tree(lines: list[str]) -> str:
    """Turn a flat list into a ├/└ tree block.
    Last item gets └, the rest get ├. Empty list → ''."""
    if not lines:
        return ""
    out = []
    for i, line in enumerate(lines):
        prefix = "└" if i == len(lines) - 1 else "├"
        out.append(f"{prefix} {line}")
    return "\n".join(out)


def bar(current: float, maximum: float, length: int = 10, style: str = "block") -> str:
    """Progress bar. style='block' → █░, style='thick' → ▰▱."""
    if maximum <= 0:
        empty = "░" if style == "block" else "▱"
        return empty * length
    ratio = min(max(current / maximum, 0.0), 1.0)
    filled = round(ratio * length)
    if style == "thick":
        return "▰" * filled + "▱" * (length - filled)
    return "█" * filled + "░" * (length - filled)


def fatigue_icon(fatigue: int) -> str:
    """Traffic-light icon for a 0..100 fatigue value (lower = better)."""
    if fatigue >= 100:
        return "⛔"
    if fatigue >= 80:
        return "🔴"
    if fatigue >= 40:
        return "🟡"
    return "🟢"


RARITY_BADGE = {"common": "⚪️", "rare": "🔵", "epic": "🟣", "legendary": "🟡", "mythic": "🔴"}


def rarity_badge(rarity: str) -> str:
    return RARITY_BADGE.get(rarity, "⚪️")


def money(mora: float = None, diamonds: float = None, dark: float = None, zarniki: float = None) -> str:
    """Compact inline money string: '1 383 🪙 · 2 💎'. Skips zero/None values."""
    parts = []
    if mora is not None and mora != 0:
        parts.append(f"{format_currency(mora)} 🪙")
    if diamonds is not None and diamonds != 0:
        parts.append(f"{format_currency(diamonds)} 💎")
    if dark is not None and dark != 0:
        parts.append(f"{dark:.0f} 🌑")
    if zarniki is not None and zarniki != 0:
        parts.append(f"{zarniki:.0f} ✨")
    return " · ".join(parts) if parts else "0 🪙"


def header(emoji: str, title: str, subtitle: str = "") -> str:
    """Standard screen header: '👤 <b>ПРОФИЛЬ</b>' + optional subtitle line."""
    h = f"{emoji} <b>{title}</b>"
    if subtitle:
        h += f"\n{subtitle}"
    return h


def medal(rank: int) -> str:
    """1→🥇 2→🥈 3→🥉 else numeric."""
    return {1: "🥇", 2: "🥈", 3: "🥉"}.get(rank, f"{rank}.")
