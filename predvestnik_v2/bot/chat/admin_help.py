"""«бот админ помощь» — что в этом чате можно с какого ранга, и вход в Путеводитель администрации (S09).

В группе — пороги именно этого чата (их меняет владелец командой «бот права») и твой ранг; в личке — пороги по умолчанию.
Персоналу бота (роль от младшего хелпера) — кнопка «Путеводитель администрации» (экран Путеводителя в Mini App, app.57.js).
Обычному участнику команда отвечает, где искать обычную помощь: справка для модераторов ему не нужна."""
from __future__ import annotations

import html

from aiogram.types import InlineKeyboardMarkup

from bot.chat import ranks
from bot.chat.framework import Ctx, registry
from bot.chat.global_ranks import get_bot_rank
from bot.chat.site import site_keyboard
from core.chat_rank_policy import ACTIONS, rank_name

STAFF_RANK = 2   # младший хелпер: с этой роли открывается админка (FastAPI/routers/bot_admin/auth.py)


def _guide_keyboard(chat_type: str, bot_username: str) -> InlineKeyboardMarkup | None:
    # Тот же экран, что Путеводитель игрока, книга администрации (app.57.js, ?startapp=adminguide)
    return site_keyboard(chat_type, bot_username, "adminguide", "📘 Путеводитель администрации")


def rights_text(rights: dict[str, int], my_rank: int | None) -> str:
    lines = []
    for action in ACTIONS:
        need = rights.get(action.key, action.default)
        mark = "" if my_rank is None else ("✅ " if my_rank >= need else "▫️ ")
        lines.append(f"{mark}{html.escape(action.label)} — с {html.escape(rank_name(need))} ({need})")
    return "\n".join(lines)


@registry.command(
    "админ помощь", aliases=("админ-помощь", "помощь админа", "справка админа"), usage="бот админ помощь", section="moderation",
    summary="Что в этом чате можно с какого ранга; персоналу — Путеводитель администрации.",
)
async def cmd_admin_help(ctx: Ctx) -> None:
    private = ctx.message.chat.type == "private"
    staff = await get_bot_rank(ctx.db, ctx.user_id) >= STAFF_RANK
    me = await ctx.bot.me()
    if private:
        text = ("🛡 <b>Админ-помощь</b>\n\nПороги по умолчанию (в каждом чате их можно изменить командой «бот права»):\n"
                f"{rights_text({}, None)}\n\nВ группе эта команда покажет пороги именно этого чата.")
    else:
        chat_id = ctx.message.chat.id
        rights = await ranks.rights_map(ctx.db, chat_id)
        my_rank = await ranks.get_rank(ctx.db, chat_id, ctx.user_id)
        if not staff and my_rank < rights.get("lists", 3):
            await ctx.reply("🛡 Эта справка — для модераторов чата. Обычные команды: «бот помощь», правила игры — «бот путеводитель».")
            return
        text = (f"🛡 <b>Админ-помощь · этот чат</b>\nТвой ранг: {html.escape(rank_name(my_rank))}\n\n{rights_text(rights, my_rank)}\n\n"
                "✅ — тебе доступно. Наказания: «бот мут, @ник 2ч причина», «бот бан, @ник 5д». Полный список — «бот помощь» › «Модерация».")
    await ctx.reply(text, reply_markup=_guide_keyboard(ctx.message.chat.type, me.username or "") if staff else None)
