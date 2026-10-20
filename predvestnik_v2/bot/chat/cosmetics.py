"""«бот косметика» — выключатель скинов в чате: карточки «бот я», знаки у ников в списках, новости о покупке образов.

Включено по умолчанию. Менять может тот, у кого право «Менять права рангов» (по умолчанию владелец чата); каждое
изменение пишется в журнал модулей (chat_module_audit). Состояние читает infrastructure/repositories/skin_chat_v1.py."""
from __future__ import annotations

from bot.chat import ranks
from bot.chat.framework import Ctx, registry
from infrastructure.repositories import chat_module_audit
from infrastructure.repositories import skin_chat_v1

ON_WORDS = ("вкл", "включить", "on", "да")
OFF_WORDS = ("выкл", "выключить", "off", "нет")
WHAT = "<i>Скины игроков в карточках «бот я», знаки у ников в списках бота и новости о покупке образов.</i>"


def _state(on: bool) -> str:
    return "включена" if on else "выключена"


@registry.command(
    "косметика", aliases=("скины в чате",), usage="бот косметика [вкл | выкл]", private=False, section="settings",
    summary="Скины игроков в сообщениях бота в этом чате. Без слова — показать, включены ли.",
    example="бот косметика выкл",
)
async def cmd_cosmetics(ctx: Ctx) -> None:
    chat_id = ctx.message.chat.id
    word = ctx.args.strip().lower()
    on_now = await skin_chat_v1.cosmetics_enabled(ctx.db, chat_id)
    if word not in ON_WORDS + OFF_WORDS:
        hint = "бот косметика выкл" if on_now else "бот косметика вкл"
        await ctx.reply(f"🎨 Косметика в этом чате: <b>{_state(on_now)}</b>\n{WHAT}\n\nПереключить: <code>{hint}</code>")
        return
    if not await ranks.can(ctx.db, chat_id, ctx.user_id, "rights"):
        await ctx.reply("🎨 Это может тот, кто настраивает права рангов в чате (обычно владелец).")
        return
    want = word in ON_WORDS
    result = await chat_module_audit.set_chat_module(
        ctx.db, chat_id=chat_id, module_key=skin_chat_v1.MODULE_KEY, enabled=want, actor_id=ctx.user_id, source="chat_command")
    if not result["changed"]:
        await ctx.reply(f"🎨 Косметика в этом чате уже <b>{_state(want)}</b>.")
        return
    after = await skin_chat_v1.cosmetics_enabled(ctx.db, chat_id)
    note = "" if after == want else "\n<i>Сейчас она выключена для всех чатов, настройка этого чата заработает, когда её включат.</i>"
    await ctx.reply(f"🎨 Косметика в этом чате <b>{_state(want)}</b>.\n{WHAT}{note}")
