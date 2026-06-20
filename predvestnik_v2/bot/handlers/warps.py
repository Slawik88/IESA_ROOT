"""
bot/handlers/warps.py
B10: Варп-команды — социальные действия в чате.
"""
import random

from aiogram import Router, types

from bot.filters.text_commands import WarpCmd
from core.warp_responses import ALL_WARP_COMMANDS, NSFW_TYPES, resolve_warp
from infrastructure.repositories import moderation as mod_db
from services.quests import increment_metric as quest_increment
from services.utils import safe_html, resolve_target, resolve_display_name
from services.vip import is_vip_active

router = Router(name="warps_router")
from bot.middlewares.module_check_mw import ModuleCheckMiddleware
router.message.middleware(ModuleCheckMiddleware("module_warps"))


def _extract_quote(message: types.Message) -> str:
    """Extract text after first newline as a quote (реплика)."""
    if not message.text:
        return ""
    lines = message.text.split("\n", 2)
    if len(lines) >= 2:
        quote = "\n".join(lines[1:]).strip()
        return f"\n<i>«{safe_html(quote)}»</i>" if quote else ""
    return ""


# ── Build TextCmd aliases dynamically ─────────────────────────────────────────

def _all_aliases() -> list[str]:
    aliases = []
    for cmd_name, data in ALL_WARP_COMMANDS.items():
        aliases.append(cmd_name)
        aliases.extend(data.get("aliases", []))
    return aliases


ALL_WARP_ALIASES = _all_aliases()


@router.message(WarpCmd(ALL_WARP_ALIASES))
async def cmd_warp(message: types.Message, db, text_args: str = None):
    if message.chat.type == "private":
        return

    # Команда — первая строка, без запятых-аргументов и опционального префикса «бот»
    raw_cmd = message.text.lower().split("\n", 1)[0].split(",")[0].strip()
    if raw_cmd.startswith("бот"):
        raw_cmd = raw_cmd[3:].strip()
    warp_name = resolve_warp(raw_cmd)
    if not warp_name:
        return

    warp_data = ALL_WARP_COMMANDS.get(warp_name)
    if not warp_data:
        return

    actor_id = message.from_user.id
    chat_id = message.chat.id
    is_nsfw = warp_data.get("type") in NSFW_TYPES

    # NSFW: check chat setting only (no per-user consent)
    if is_nsfw:
        settings = await mod_db.get_chat_settings(db, chat_id)
        if not settings.get("nsfw_warps_allowed", 1):
            return await message.answer(
                "🔞 18+ команды отключены в этом чате.\n"
                "<i>Администратор может включить их в настройках чата.</i>",
                parse_mode="HTML",
            )

    # Resolve target
    target_id, target_name, _ = await resolve_target(message, db, text_args)
    if not target_id:
        return await message.answer(
            f"ℹ️ <code>{warp_name}, @юзер</code> — укажите цель или ответьте на сообщение.",
            parse_mode="HTML",
        )

    # Self-warp
    if target_id == actor_id:
        self_resp = warp_data.get("self_response", f"{{actor}} использует {warp_name} на себе 🤷")
        actor_name = await resolve_display_name(db, actor_id, chat_id, message.from_user.first_name)
        text = self_resp.replace("{actor}", f"<b>{actor_name}</b>").replace("{target}", f"<b>{actor_name}</b>")
        return await message.answer(text, parse_mode="HTML")

    # Pick response (VIP gets extra phrases added to the pool — больше разнообразия)
    responses = warp_data.get("responses", [])
    if not responses:
        return
    pool = responses
    if warp_data.get("responses_vip") and await is_vip_active(db, actor_id):
        pool = responses + warp_data["responses_vip"]
    template = random.choice(pool)

    actor_name = await resolve_display_name(db, actor_id, chat_id, message.from_user.first_name)
    target_disp = await resolve_display_name(db, target_id, chat_id, target_name)

    text = template.replace("{actor}", f"<b>{actor_name}</b>").replace("{target}", f"<b>{target_disp}</b>")
    quote = _extract_quote(message)
    await message.answer(text + quote, parse_mode="HTML")

    # Quest metrics
    try:
        await quest_increment(db, actor_id, chat_id, "warps_to_distinct_users_today", delta=1.0)
        if warp_name == "обнять":
            await quest_increment(db, actor_id, chat_id, "warps_hug_distinct_today", delta=1.0)
        await db.commit()
    except Exception:
        pass
