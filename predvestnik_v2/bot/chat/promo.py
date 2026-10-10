"""«бот промокод КОД» — активация промокода (создаются в админке на сайте)."""
from __future__ import annotations

import html

from loguru import logger

from bot.chat.framework import Ctx, UsageError, registry
from bot.chat.style import quote
from services import promo_v2


@registry.command("промокод", aliases=("промо", "код"), usage="бот промокод КОД", section="profile",
                  summary="Активировать промокод и получить награду.")
async def cmd_promo(ctx: Ctx) -> None:
    code = ctx.args.strip().split()[0] if ctx.args.strip() else ""
    if not code:
        raise UsageError("бот промокод КОД")
    chat = ctx.message.chat
    chat_id = chat.id if chat.type in ("group", "supergroup") else None
    try:
        result = await promo_v2.redeem(ctx.db, user_id=ctx.user_id, code=code, chat_id=chat_id)
    except promo_v2.PromoError as exc:
        await ctx.reply(f"🎟 {html.escape(str(exc))}")
        return
    except Exception:
        logger.exception("promo redeem failed")
        await ctx.reply("🎟 Не получилось активировать промокод. Ничего не списано и не начислено, попробуйте позже.")
        return
    lines = quote([html.escape(x) for x in result.granted])   # СТИЛЬ v1 (оформлено): награды цитатой
    await ctx.reply(f"🎟 Промокод <b>{html.escape(result.code)}</b> активирован!\n{lines}")
