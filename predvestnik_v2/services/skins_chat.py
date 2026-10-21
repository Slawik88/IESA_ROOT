"""Which look the bot shows for a player in a chat (docs/SKINS_CHAT_DESIGN_HANDOFF.md).

A message in a group is one for everybody, so the Mini App rule «others see a look only while the owner has VIP» does not
apply here: whoever wears a skin is shown in it. The tier is the one the owner may show (cap_tier: SSS needs VIP).
The chat's «Косметика в чате» switch turns all of it off.
"""
from __future__ import annotations

from loguru import logger

from core.appearance_v3 import cap_tier
from core.skins_v3_catalog import SETS, SKINS
from core.skins_v3_chat import ChatLook, chat_look
from infrastructure.repositories import skin_chat_v1 as chat_repo
from infrastructure.repositories import skins_v3 as skins_repo
from services.vip import is_vip_active_batch

NEWS_KINDS = ("buy", "sss")


async def looks(db, user_ids: list[int], chat_id: int) -> dict[int, ChatLook]:
    """Compact looks for list rows (no set crest). Empty when cosmetics are off in this chat."""
    ids = [int(u) for u in dict.fromkeys(user_ids or [])]
    if not ids or not await chat_repo.cosmetics_enabled(db, chat_id):
        return {}
    worn = await skins_repo.equipped_batch(db, ids)
    if not worn:
        return {}
    vip = await is_vip_active_batch(db, list(worn))
    out = {}
    for uid, (skin_id, tier) in worn.items():
        look = chat_look(skin_id, cap_tier(tier, uid in vip))
        if look:
            out[uid] = look
    return out


async def card_look(db, user_id: int, chat_id: int) -> ChatLook | None:
    """The full look for one player's card, with the set crest when the set is complete."""
    found = (await looks(db, [int(user_id)], chat_id)).get(int(user_id))
    if not found:
        return None
    set_id = SKINS[found.skin_id]["set"]
    if not set_id:
        return found
    owned = await skins_repo.owned(db, int(user_id))
    return chat_look(found.skin_id, found.tier, set_complete=all(m in owned for m in SETS[set_id]["members"]))


async def safe_card_look(db, user_id: int, chat_id: int) -> ChatLook | None:
    """card_look для сообщений бота: сбой косметики не должен мешать самому сообщению."""
    try:
        return await card_look(db, user_id, chat_id)
    except Exception as exc:
        logger.warning(f"skin look for {user_id} in {chat_id}: {type(exc).__name__}: {exc}")
        return None


async def glyphs(db, user_ids: list[int], chat_id: int) -> dict[int, str]:
    """{user_id: emoji} for marks in front of names in the bot's lists. A failure here leaves the list without marks, never breaks it."""
    try:
        return {uid: look.glyph for uid, look in (await looks(db, user_ids, chat_id)).items()}
    except Exception as exc:
        logger.warning(f"skin marks for chat {chat_id}: {type(exc).__name__}: {exc}")
        return {}


async def news(db, user_id: int, skin_id: str, kind: str, tier: str) -> None:
    """Queue a chat news item inside the caller's transaction (purchase or raise to SSS). Tables come from start-up (bot/startup_schema.py)."""
    if kind not in NEWS_KINDS:
        raise ValueError(f"unknown skin news kind: {kind}")
    await chat_repo.enqueue(db, user_id, skin_id, kind, tier)


__all__ = ["looks", "card_look", "safe_card_look", "glyphs", "news"]
