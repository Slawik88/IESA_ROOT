"""Small release-scope profile card for Telegram chat.

The former profile renderer exposed retired levels, currencies, achievements,
themes and pets.  The Mini App is the detailed personal centre; this chat card
only presents identity, family status and the approved activity hub.
"""
from __future__ import annotations

from aiogram import Router, types
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.filters.text_commands import TextCmd
from infrastructure.repositories import marriages
from core.miniapp_links import miniapp_url
from services.utils import safe_html

router = Router(name="release_profile_router")


def _hub_keyboard() -> types.InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🎮 Открыть Центр активностей", url=miniapp_url("game"))
    return kb.as_markup()


@router.message(TextCmd(["я", "профиль", "анкета", "кто", "инфо", "досье"]))
async def cmd_release_profile(message: types.Message, db, text_args: str = ""):
    """Show a truthful compact card; never read or mutate retired progression."""
    user = message.from_user
    marriage = await marriages.get_user_marriage(db, int(user.id))
    if marriage:
        partner = marriage["user2_name"] if int(marriage["user1_id"]) == int(user.id) else marriage["user1_name"]
        family_line = f"💍 В браке с <b>{safe_html(str(partner or 'партнёром'))}</b>"
    else:
        family_line = "💔 Брак не заключён"
    target_note = "\n<i>Просмотр чужих досье вернётся только вместе с новым профилем.</i>" if (text_args or "").strip() else ""
    name = safe_html(user.full_name or user.first_name or "Игрок")
    text = (
        f"👤 <b>{name}</b>\n"
        f"<code>🆔 {user.id}</code>\n\n"
        f"{family_line}\n"
        "🎮 Доступные активности: Ритм, Сапёр и Мафия."
        f"{target_note}"
    )
    await message.answer(text, reply_markup=_hub_keyboard(), parse_mode="HTML")
