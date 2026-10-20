"""Skins V3 in group chats: how a worn skin decorates the bot's text about its owner.

Telegram gives a bot no colour or font in text, and Cyrillic has no Unicode "fancy" letters, so a skin decorates with
what every client shows the same way: section icons, a separator, ornament lines and one phrase. Everything is derived
from the catalog (`kinds.pt` gives icons and separator, `kinds.frame` the ornament), so a new skin gets a style for free.
Only the SSS phrase is written by hand (core/skins_v3_chat_phrases.py).

What the tier adds (the tier is the one the owner may show: core.appearance_v3.cap_tier):
  D, C   icon in front of the name, title line, section icons
  B, A   + the skin's separator instead of «·» and an ornament under the header
  S, SS  + ornament lines above and below the message, like a frame
  SSS    + the skin's phrase as the last line
"""
from __future__ import annotations

from dataclasses import dataclass

from core.skins_v3 import TIERS
from core.skins_v3_catalog import SETS, SKINS
from core.skins_v3_chat_phrases import PHRASES
from core.skins_v3_collection import SET_GLYPH

SEP_FROM = "B"
FRAME_FROM = "S"
PHRASE_AT = "SSS"
ORNAMENT_MAX = 20       # a phone line holds about 32 characters; ornament stays well inside it

# kinds.pt -> (messages, progress, wallet) icons and the separator character
ICONS = {
    "dot": ("🫧", "🔆", "🪙", "•"),
    "leaf": ("🍃", "🌿", "🍄", "❦"),
    "petal": ("💮", "🎐", "🏮", "✿"),
    "snow": ("🧊", "🌨", "💎", "❄"),
    "spark": ("💫", "⚡", "💠", "✦"),
    "glint": ("🌌", "✨", "🌙", "⋆"),
    "star": ("⭐", "💫", "🎀", "✧"),
    "ember": ("🔥", "☄️", "🪔", "✶"),
    "drop": ("🩸", "🥀", "🖤", "♦"),
    "ring": ("🌀", "🌊", "🐚", "◦"),
    "sand": ("⏳", "⚙️", "🪙", "∴"),
}
DEFAULT_ICONS = ("💬", "🔥", "💰", "·")

# kinds.frame -> (frame line, divider); {s} is the separator
ORNAMENTS = {
    "ring": ("◦ ── {s} ── ◦", "── {s} ──"),
    "dash": ("┄┄┄┄ {s} ┄┄┄┄", "┄┄ {s} ┄┄"),
    "double": ("═══ {s} ═══", "═ {s} ═"),
    "seg": ("╾── {s} ──╼", "── {s} ──"),
    "drip": ("▾ ▿ ▾ {s} ▾ ▿ ▾", "▿ {s} ▿"),
}


def _at_least(tier: str, need: str) -> bool:
    return TIERS.index(tier) >= TIERS.index(need)


def glyph_of(skin_id: str) -> str:
    """The emoji the skin's title starts with: the mark in front of the owner's name in lists."""
    return SKINS[skin_id]["items"]["title"].split(" ", 1)[0]


def title_of(skin_id: str) -> str:
    """The title without its emoji («Дитя Стужи»)."""
    parts = SKINS[skin_id]["items"]["title"].split(" ", 1)
    return parts[1] if len(parts) > 1 else parts[0]


@dataclass(frozen=True)
class ChatLook:
    skin_id: str
    tier: str
    glyph: str
    title: str
    name: str
    icons: tuple[str, str, str]
    sep: str                    # «·» below SEP_FROM
    divider: str | None         # ornament under the header (B+)
    frame: str | None           # ornament above and below (S+)
    phrase: str | None          # last line (SSS)
    crest: str | None           # «🌸 Набор «Сад Сакуры» собран» when the set is complete

    @property
    def skin_line(self) -> str:
        """«Дитя Стужи · Изморозь · B», without repeating a title that equals the name. Plain text: the caller escapes it."""
        parts = [self.title] + ([self.name] if self.name != self.title else []) + [self.tier]
        return " · ".join(parts)


def chat_look(skin_id: str, tier: str, *, set_complete: bool = False) -> ChatLook | None:
    skin = SKINS.get(skin_id)
    if not skin or tier not in TIERS:
        return None
    m, p, w, s = ICONS.get(skin["kinds"].get("pt"), DEFAULT_ICONS)
    line, div = ORNAMENTS.get(skin["kinds"].get("frame"), ORNAMENTS["ring"])
    crest = None
    if set_complete and skin["set"]:
        crest = f"{SET_GLYPH.get(skin['set'], '◈')} Набор «{SETS[skin['set']]['name']}» собран"
    return ChatLook(
        skin_id=skin_id, tier=tier, glyph=glyph_of(skin_id), title=title_of(skin_id), name=skin["name"], icons=(m, p, w),
        sep=s if _at_least(tier, SEP_FROM) else "·",
        divider=div.format(s=s) if _at_least(tier, SEP_FROM) else None,
        frame=line.format(s=s) if _at_least(tier, FRAME_FROM) else None,
        phrase=PHRASES.get(skin_id) if tier == PHRASE_AT else None,
        crest=crest,
    )


def ornament_line(skin_id: str) -> str:
    """The skin's frame line whatever the tier: chat news always carry it."""
    skin = SKINS[skin_id]
    s = ICONS.get(skin["kinds"].get("pt"), DEFAULT_ICONS)[3]
    return ORNAMENTS.get(skin["kinds"].get("frame"), ORNAMENTS["ring"])[0].format(s=s)


__all__ = ["ChatLook", "chat_look", "glyph_of", "title_of", "ornament_line", "ICONS", "ORNAMENTS", "ORNAMENT_MAX"]
