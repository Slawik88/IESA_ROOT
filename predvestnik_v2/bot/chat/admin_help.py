"""«бот админ помощь» — что в этом чате можно с какого ранга, и вход в Путеводитель администрации (S09).

В группе — пороги именно этого чата (их меняет владелец командой «бот права») и твой ранг; в личке — пороги по умолчанию.
Персоналу бота (роль от младшего хелпера) — кнопка «Путеводитель администрации»: админка открывается сразу с ним
(тот же экран, что Путеводитель игрока, слоем поверх админки: FastAPI/static/bot-admin/admin-guide.js).
Обычному участнику команда отвечает, где искать обычную помощь: справка для модераторов ему не нужна."""
from __future__ import annotations

import html
import os

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from bot.chat import ranks
from bot.chat.framework import Ctx, registry
from bot.chat.global_ranks import get_bot_rank
from bot.chat.site import admin_url
from core.chat_rank_policy import ACTIONS, rank_name

STAFF_RANK = 2   # младший хелпер: с этой роли открывается админка (FastAPI/routers/bot_admin/auth.py)


def _guide_keyboard(private: bool, bot_username: str) -> InlineKeyboardMarkup | None:
    label = "📘 Путеводитель администрации"
    if private:
        url = admin_url()
        return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=label, web_app=WebAppInfo(url=url + "?open=guide"))]]) if url else None
    short = os.getenv("MINIAPP_SHORT_NAME", "")
    if short and bot_username:   # в группе Web App кнопки нельзя: прямая ссылка открывает админку внутри Telegram (index.html: startapp=admin_*)
        return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=label, url=f"https://t.me/{bot_username}/{short}?startapp=admin_guide")]])
    return None


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
    await ctx.reply(text, reply_markup=_guide_keyboard(private, me.username or "") if staff else None)
