"""Read-only Telegram view for the approved daily and weekly quests."""
from __future__ import annotations

import os

from aiogram import Router, types
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.filters.text_commands import TextCmd
from core.miniapp_links import miniapp_url
from bot.middlewares.module_check_mw import ModuleCheckMiddleware
from infrastructure.repositories.quests_v1 import ensure_tables
from services import quests_v1
from services.vip import is_vip_active
from services.utils import safe_html


router = Router(name="quests_v1_router")
router.message.middleware(ModuleCheckMiddleware("module_quests"))
router.callback_query.middleware(ModuleCheckMiddleware("module_quests"))
_BOT = os.getenv("BOT_USERNAME", "IIIPredvestnikIIIBot").strip().lstrip("@")


def _period_lines(label: str, quests: list[dict]) -> list[str]:
    lines = [f"<b>{label}</b>"]
    for quest in quests:
        done = " ✅" if quest["completed"] else ""
        lines.append(
            f"• {safe_html(str(quest['title']))} — <b>{int(quest['progress'])}/{int(quest['target'])}</b>{done}"
        )
    return lines


def render_quest_overview(view: dict) -> str:
    """Format only server-provided snapshots; it never performs an action."""
    lines = ["🧭 <b>КВЕСТЫ</b>", ""]
    lines.extend(_period_lines("Сегодня", list(view["daily"]["quests"])))
    lines.extend(["", *_period_lines("Неделя", list(view["weekly"]["quests"]))])
    rerolls = view["rerolls"]
    rewards = dict(view.get("rewards", {}).get("items", {}))
    reward_parts = []
    for kind, label in (("daily", "день"), ("weekly", "неделя"), ("combined", "всё вместе")):
        reward = dict(rewards.get(kind, {}))
        if not reward:
            continue
        part = f"{label}: {int(reward.get('amount_mora', 0))} Моры"
        if int(reward.get("amount_keys", 0)):
            part += f" + {int(reward['amount_keys'])} ключ"
        reward_parts.append(part)
    reward_line = "Награды: " + "; ".join(reward_parts) + "." if reward_parts else "Награды доступны в Mini App."
    lines.extend([
        "",
        f"Замены на этой неделе: <b>{int(rerolls['remaining'])}/{int(rerolls['limit'])}</b>.",
        "Заменить можно только незавершённое задание в Mini App.",
        reward_line,
    ])
    return "\n".join(lines)


@router.message(TextCmd(["квесты", "задания", "квест"]))
async def cmd_quests_v1(message: types.Message, db, text_args: str = "") -> None:
    """Show the authenticated player's current server-authoritative quest state."""
    del text_args
    user_id = int(message.from_user.id)
    await ensure_tables(db)
    view = await quests_v1.overview(db, user_id=user_id, vip_active=await is_vip_active(db, user_id))
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="🧭 Открыть квесты", url=miniapp_url("quests"))
    await message.answer(render_quest_overview(view), reply_markup=keyboard.as_markup(), parse_mode="HTML")
