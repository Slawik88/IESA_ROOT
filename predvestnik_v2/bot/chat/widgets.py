"""A reversible player preference; works even when menu widgets are switched off."""

from bot.chat.framework import Ctx, registry
from infrastructure.repositories import widget_cards as repo


@registry.command(
    "виджеты",
    usage="виджеты вкл / виджеты выкл",
    section="personal",
    summary="Карточки меню или обычный текст в личке с ботом.",
)
async def cmd_widgets(ctx: Ctx) -> None:
    if ctx.message.chat.type != "private" or ctx.message.business_connection_id:
        await ctx.reply(
            "Напиши мне в личку: <code>виджеты вкл</code> или <code>виджеты выкл</code>."
        )
        return
    value = ctx.args.strip().lower()
    if value not in ("вкл", "выкл"):
        await ctx.reply(
            "<b>Меню в личке</b>\n<code>виджеты вкл</code> — карточки со страницами.\n"
            "<code>виджеты выкл</code> — обычный текст.\nНастройка действует на новые меню."
        )
        return
    await repo.set_enabled(ctx.db, ctx.user_id, value == "вкл")
    await ctx.reply(
        "Карточки включены. Открой нужное меню заново."
        if value == "вкл"
        else "Текстовый режим включён. Открой нужное меню заново."
    )
