"""«бот тег» и «бот теги» — теги участников чата (подпись справа от имени в списке участников Telegram).

Тег игрока бот пишет рядом с именем во всех своих сообщениях (санкции, ранги, топ, профиль, чистка): здесь же его можно
посмотреть и найти человека по тегу. Хранение и захват — services/member_tags.py."""
from __future__ import annotations

import html

from bot.chat.framework import Ctx, registry
from bot.chat.style import quote
from bot.chat.targets import NOT_FOUND, names_someone, resolve_target
from services import member_tags

SHOWN = 40
ZW = "​"   # «@» + нулевой пробел: ник виден, но участника не пингует


def _name(uid: int, uname: str | None) -> str:
    return html.escape(f"@{ZW}{uname}" if uname else f"id{uid}")


def _rows(found: list[tuple[int, str | None, str]]) -> str:
    return quote([f"<b>{html.escape(tag)}</b> · {_name(uid, uname)}" for uid, uname, tag in found])


@registry.command(
    "тег", aliases=("мой тег", "метка"), usage="бот тег [@ник | часть тега]", private=False, section="profile",
    summary="Тег игрока в этом чате. С частью тега вместо ника — кто в чате носит такой тег.",
    example="бот тег Сяо",
)
async def cmd_tag(ctx: Ctx) -> None:
    chat = ctx.message.chat
    target, rest = await resolve_target(ctx.db, ctx.message, ctx.args)
    if target is None and names_someone(ctx.args):
        await ctx.reply(NOT_FOUND)
        return
    if target is None and rest.strip():
        found = await member_tags.find(ctx.db, chat.id, rest, SHOWN + 1)
        if not found:
            await ctx.reply(f"🏷 Тега «{html.escape(rest.strip()[:40])}» в этом чате ни у кого нет.")
            return
        more = f"\nПоказаны первые {SHOWN}, уточните запрос." if len(found) > SHOWN else ""
        await ctx.reply(f"🏷 <b>Тег «{html.escape(rest.strip()[:40])}»</b> · {min(len(found), SHOWN)}\n"
                        + _rows(found[:SHOWN]) + more)
        return
    if target is None:
        uid, label, tag = ctx.user_id, "У вас", await member_tags.get(ctx.db, chat.id, ctx.user_id)
    else:
        uid = target.user_id
        replied = getattr(ctx.message.reply_to_message, "from_user", None)
        if uid == ctx.user_id or (replied and replied.id == uid):
            tag = target.tag   # свой тег и тег автора сообщения, на которое ответили, уже свежие: они пришли вместе с сообщением
        else:   # про другого спрашиваем Telegram: человек мог сменить тег, давно ничего не написав
            _, tag = await member_tags.refresh(ctx.bot, ctx.db, chat.id, uid)
        label = "У " + html.escape(target.plain_name)
    if tag:
        await ctx.reply(f"🏷 {label} тег: <b>{html.escape(tag)}</b>")
    else:
        await ctx.reply(f"🏷 {label} нет тега в этом чате.\n"
                        "<i>Тег — подпись справа от имени в списке участников чата.</i>")


@registry.command(
    "теги", aliases=("список тегов", "метки"), usage="бот теги", private=False, section="profile",
    summary="У кого в этом чате есть теги и какие.",
)
async def cmd_tags(ctx: Ctx) -> None:
    total, found = await member_tags.listing(ctx.db, ctx.message.chat.id, SHOWN)
    if not total:
        await ctx.reply("🏷 В этом чате бот пока не видит ни одного тега.\n"
                        "<i>Тег появляется у игрока, как только он напишет в чат, и обновляется при каждой смене.</i>")
        return
    more = f"\nЕщё {total - SHOWN}: найти нужного можно командой <code>бот тег часть_тега</code>" if total > SHOWN else ""
    await ctx.reply(f"🏷 <b>Теги чата</b> · {total}\n" + _rows(found) + more)
