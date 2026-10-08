"""«бот сайт» — вход в мини-приложение Предвестника."""
from __future__ import annotations

import os

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from bot.chat.framework import Ctx, registry


def site_keyboard(chat_type: str, bot_username: str) -> InlineKeyboardMarkup | None:
    url = os.getenv("MINIAPP_URL", "")
    short = os.getenv("MINIAPP_SHORT_NAME", "")
    if chat_type == "private" and url.startswith("https://"):
        # В личке кнопка открывает приложение прямо в Telegram.
        btn = InlineKeyboardButton(text="🔮 Открыть Предвестник", web_app=WebAppInfo(url=url))
    elif short and bot_username:
        # В группе web_app-кнопки запрещены Telegram — ведём по прямой ссылке
        # на мини-приложение, она тоже открывается внутри Telegram.
        btn = InlineKeyboardButton(text="🔮 Открыть Предвестник", url=f"https://t.me/{bot_username}/{short}")
    elif url.startswith("https://"):
        btn = InlineKeyboardButton(text="🔮 Открыть Предвестник", url=url)
    else:
        return None
    return InlineKeyboardMarkup(inline_keyboard=[[btn]])


SITE_TEXT = (
    "🔮 <b>Предвестник</b>\n\n"
    "Профиль, игры, косметика и награды — всё в одном месте.\n"
    "Нажмите кнопку ниже, приложение откроется прямо в Telegram."
)


@registry.command(
    "сайт", aliases=("приложение", "мини апп", "app"), usage="бот сайт",
    section="basic", summary="Ссылка на мини-приложение Предвестника.",
)
async def cmd_site(ctx: Ctx) -> None:
    me = await ctx.bot.me()
    kb = site_keyboard(ctx.message.chat.type, me.username or "")
    if kb is None:
        await ctx.reply("🔮 Мини-приложение сейчас недоступно. Попробуйте позже.")
        return
    await ctx.reply(SITE_TEXT, reply_markup=kb)


def admin_url() -> str:
    url = os.getenv("MINIAPP_URL", "").split("?")[0].split("#")[0].rstrip("/")
    return f"{url}/bot-admin" if url.startswith("https://") else ""


@registry.command("админка", aliases=("админ панель", "панель"), usage="бот админка")
async def cmd_admin_panel(ctx: Ctx) -> None:
    from bot.chat.global_ranks import get_bot_rank
    if await get_bot_rank(ctx.db, ctx.user_id) <= 0:
        await ctx.reply("🛠 Админка доступна только персоналу бота.")
        return
    url = admin_url()
    if not url:
        await ctx.reply("🛠 Адрес сайта не настроен (MINIAPP_URL).")
        return
    if ctx.message.chat.type == "private":
        btn = InlineKeyboardButton(text="🛠 Открыть админку", web_app=WebAppInfo(url=url))
        text = "🛠 <b>Админка Предвестника</b>"
    else:
        btn = InlineKeyboardButton(text="🛠 Открыть в браузере", url=url)
        text = "🛠 <b>Админка Предвестника</b>\nВнутри Telegram она открывается из лички с ботом: <code>бот админка</code>"
    await ctx.reply(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[btn]]))
