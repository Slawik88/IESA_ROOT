"""Варп-команды: «бот обнять, @ник», «обнять» ответом на сообщение, «обнять @ник».

Без слова «бот» варп срабатывает только когда понятно, к кому он (ответ или @ник),
иначе это обычная фраза в чате. 18+ варпы — только если цель разрешила их
(users.allow_adult_warps) и чат их не запретил (chat_settings.nsfw_warps_allowed).
"""
from __future__ import annotations

import html
import random
from dataclasses import dataclass

from bot.chat.framework import Ctx, UsageError, registry
from bot.chat.targets import resolve_target


@dataclass(frozen=True)
class Warp:
    name: str
    responses: tuple[str, ...]
    aliases: tuple[str, ...] = ()
    adult: bool = False
    emoji: str = ""


def link(user_id: int, name: str) -> str:
    return f'<a href="tg://user?id={user_id}">{html.escape(name or "игрок")}</a>'


def render(template: str, actor: str, target: str) -> str:
    return template.format(a=actor, b=target)


async def adult_allowed(db, chat_id: int, target_id: int) -> tuple[bool, str]:
    async with db.execute("SELECT allow_adult_warps FROM users WHERE user_tg_id = ?", (target_id,)) as cur:
        row = await cur.fetchone()
    if not (row and row[0]):
        return False, "🔞 Этот игрок не разрешил 18+ варпы в свой адрес."
    if chat_id < 0:
        async with db.execute("SELECT nsfw_warps_allowed FROM chat_settings WHERE chat_id = ?", (chat_id,)) as cur:
            r = await cur.fetchone()
        if r is not None and not r[0]:
            return False, "🔞 В этом чате 18+ варпы выключены."
    return True, ""


def make_handler(warp: Warp):
    async def handler(ctx: Ctx) -> None:
        if not ctx.prefixed and len((ctx.message.text or "").split()) > 6:
            return   # длинная фраза без «бот» — это разговор, а не команда
        target, rest = await resolve_target(ctx.db, ctx.message, ctx.args)
        if target is None:
            if ctx.prefixed:
                raise UsageError(f"бот {warp.name}, @ник  (или ответом на сообщение)")
            return
        actor = ctx.message.from_user
        if warp.adult:
            ok, why = await adult_allowed(ctx.db, ctx.message.chat.id, target.user_id)
            if not ok:
                if ctx.prefixed:
                    await ctx.reply(why)
                return
        if target.user_id == actor.id:
            text = f"{link(actor.id, actor.first_name)} пытается {warp.name} сам(а) себя. Ну, тоже вариант 🙃"
        else:
            text = render(random.choice(warp.responses), link(actor.id, actor.first_name),
                          link(target.user_id, target.name.lstrip("@")))
        if rest.strip():
            text += f"\n💬 «{html.escape(rest.strip()[:200])}»"
        await ctx.message.answer(text, parse_mode="HTML", disable_web_page_preview=True)
    return handler


def register_all(warps: tuple[Warp, ...]) -> None:
    for w in warps:
        registry.command(w.name, aliases=w.aliases, bare=True,
                         usage=f"бот {w.name}, @ник")(make_handler(w))


@registry.command("варпы", aliases=("варп", "варп команды", "рп"), usage="бот варпы [18+]", section="social",
                  summary="Список варп-команд: обнять, погладить и ещё больше сотни.")
async def cmd_warp_list(ctx: Ctx) -> None:
    from bot.chat.warps_data import WARPS
    adult = "18" in ctx.args
    items = [w for w in WARPS if w.adult == adult]
    head = "🔞 <b>18+ варпы</b>" if adult else "🤗 <b>Варп-команды</b>"
    body = ", ".join(f"{w.emoji}{w.name}" for w in items)
    hint = ("Работают, только если игрок включил их для себя: <code>бот 18+ вкл</code>" if adult else
            "Пишите <code>обнять @ник</code> или просто ответьте на сообщение словом. 18+: <code>бот варпы 18+</code>")
    await ctx.reply(f"{head} · {len(items)}\n\n{body}\n\n{hint}")


@registry.command("18+", aliases=("18 +", "взрослые варпы"), usage="бот 18+ вкл | выкл", section="social",
                  summary="Разрешить или запретить 18+ варпы в ваш адрес.")
async def cmd_adult_toggle(ctx: Ctx) -> None:
    arg = ctx.args.strip().lower()
    if arg in ("вкл", "да", "on", "включить", "+"):
        value = True
    elif arg in ("выкл", "нет", "off", "выключить", "-"):
        value = False
    else:
        async with ctx.db.execute("SELECT allow_adult_warps FROM users WHERE user_tg_id = ?", (ctx.user_id,)) as cur:
            row = await cur.fetchone()
        state = "включены" if row and row[0] else "выключены"
        await ctx.reply(f"🔞 18+ варпы в ваш адрес сейчас {state}.\nИзменить: <code>бот 18+ вкл</code> или <code>бот 18+ выкл</code>")
        return
    u = ctx.message.from_user
    await ctx.db.execute(
        "INSERT INTO users (user_tg_id, user_tg_username, allow_adult_warps) VALUES (?, ?, ?) "
        "ON CONFLICT (user_tg_id) DO UPDATE SET allow_adult_warps = EXCLUDED.allow_adult_warps",
        (u.id, u.username, value))
    commit = getattr(ctx.db, "commit", None)
    if commit:
        await commit()
    await ctx.reply("🔞 Теперь 18+ варпы в ваш адрес разрешены." if value else "✅ 18+ варпы в ваш адрес выключены.")
