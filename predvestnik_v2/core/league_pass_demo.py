"""Demo track of the new season pass: free and VIP rows, shown only — nothing here is ever granted.

Experience comes from League levels and successful pet actions (early access only).  Reward kinds follow the owner's
brief: chests of different stars, food, pets, Mora, diamonds, jokers, a little of Zarniki (30 on the
free row, 80 on the VIP row over the whole season); never skins.  Amounts are placeholders until the
economy check of the real pass.
"""
from __future__ import annotations

from typing import Final

XP_PER_LEVEL: Final = 300
LEVELS: Final = 30
PET_ACTION_XP: Final = 10

# level: (free reward, VIP reward)
TRACK: Final = {
    1: ("🪙 150 Моры", "🪙 300 Моры"),
    2: ("🍖 Еда ×3", "🍖 Еда ×6"),
    3: ("📦 Сундук ★", "📦 Сундук ★★"),
    4: ("🪙 200 Моры", "💎 5 Алмазов"),
    5: ("✨ 5 Зарников", "✨ 10 Зарников"),
    6: ("🍖 Еда ×3", "🃏 Джокер"),
    7: ("📦 Сундук ★", "📦 Сундук ★★"),
    8: ("🪙 250 Моры", "🪙 500 Моры"),
    9: ("💎 3 Алмаза", "💎 8 Алмазов"),
    10: ("🐾 Питомец (обычный)", "🐾 Питомец (редкий)"),
    11: ("🍖 Еда ×4", "🍖 Еда ×8"),
    12: ("✨ 5 Зарников", "✨ 10 Зарников"),
    13: ("📦 Сундук ★★", "📦 Сундук ★★★"),
    14: ("🃏 Джокер", "🃏 Джокер ×2"),
    15: ("✨ 5 Зарников", "✨ 10 Зарников"),
    16: ("🪙 300 Моры", "🪙 600 Моры"),
    17: ("🍖 Еда ×4", "💎 10 Алмазов"),
    18: ("📦 Сундук ★★", "📦 Сундук ★★★"),
    19: ("💎 5 Алмазов", "🍖 Еда ×10"),
    20: ("✨ 5 Зарников", "✨ 15 Зарников"),
    21: ("🪙 300 Моры", "🪙 600 Моры"),
    22: ("🍖 Еда ×5", "🃏 Джокер ×2"),
    23: ("📦 Сундук ★★", "📦 Сундук ★★★"),
    24: ("💎 5 Алмазов", "💎 12 Алмазов"),
    25: ("✨ 5 Зарников", "✨ 15 Зарников"),
    26: ("🪙 350 Моры", "🪙 700 Моры"),
    27: ("🃏 Джокер", "🍖 Еда ×12"),
    28: ("📦 Сундук ★★★", "📦 Сундук ★★★ ×2"),
    29: ("✨ 5 Зарников", "✨ 20 Зарников"),
    30: ("🐾 Питомец (редкий)", "🐾 Питомец (эпический)"),
}
ZARNIKI_FREE: Final = 30
ZARNIKI_VIP: Final = 80


def _zarniki(index: int) -> int:
    total = 0
    for free, vip in TRACK.values():
        text = (free, vip)[index]
        if "Зарник" in text:
            total += int(text.split()[1])
    return total


assert len(TRACK) == LEVELS and _zarniki(0) == ZARNIKI_FREE and _zarniki(1) == ZARNIKI_VIP


def view(xp: int) -> dict:
    level = min(LEVELS, max(0, int(xp)) // XP_PER_LEVEL)
    return {
        "xp": int(xp), "level": level, "levels": LEVELS, "xp_per_level": XP_PER_LEVEL,
        "xp_to_next": 0 if level >= LEVELS else XP_PER_LEVEL - int(xp) % XP_PER_LEVEL,
        "track": [{"level": n, "free": free, "vip": vip, "reached": n <= level} for n, (free, vip) in TRACK.items()],
        "fake": True,
    }
