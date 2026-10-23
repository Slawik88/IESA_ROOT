"""Separate entry to the online hub. The local «бот мафия» command is unchanged."""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from bot.chat.framework import Ctx, registry
from core.miniapp_links import miniapp_url, miniapp_web_url
from infrastructure.repositories import system_flags


@registry.command("мафия онлайн", aliases=("межчатовая мафия", "мафия межчат"), usage="бот мафия онлайн",
                  private=True, section="games", summary="Мафия с игроками из разных чатов в Mini App.")
async def cmd_mafia_online(ctx: Ctx):
    if not ctx.is_dev and not await system_flags.is_enabled(ctx.db, "game_mafia_online"):
        return await ctx.reply("Межчатовая мафия пока закрыта. Локальная: <b>бот мафия</b>.")
    web = miniapp_web_url("mfo")
    button = (InlineKeyboardButton(text="Войти в Мафию", web_app=WebAppInfo(url=web))
              if ctx.message.chat.type == "private" and web else
              InlineKeyboardButton(text="Войти в Мафию", url=miniapp_url("mfo")))
    await ctx.reply("🕵️ <b>Мафия · один город для всех</b>\nИгроки из разных чатов. Роли и разговор — за общим столом.",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[[button]]))
