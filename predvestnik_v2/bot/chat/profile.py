"""«бот я», «бот кто» — карточка игрока; «бот баланс» — кошелёк.

Никого, кроме самого игрока, карточка не пингует: партнёр и прочие имена
выводятся с невидимым пробелом после «@».
"""
from __future__ import annotations

import html
from datetime import timedelta

from core.economy_contract import CURRENCY_SPECS
from infrastructure.repositories import skins_v3 as skins_v3_repo
from bot.chat import family, global_ranks, ranks
from bot.chat.framework import Ctx, UsageError, registry
from bot.chat.moderation import active_warns
from bot.chat.settings import CURRENCY_VIEW
from bot.chat.targets import Target, resolve_target
from bot.chat.tracking import local_now

# Валюты, которые сейчас в игре (остальные — легаси и не показываются).
SHOWN_CURRENCIES = ("mora", "diamonds", "essence", "zarniki")


def esc(s) -> str:
    return html.escape(str(s or ""))


def quiet(username: str | None, fallback: str) -> str:
    return f"@​{username}" if username else fallback


def fmt_num(v: float, decimals: int = 0) -> str:
    s = f"{v:,.{decimals}f}".replace(",", " ")
    return s.rstrip("0").rstrip(".") if decimals else s


def days_word(n: int) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return "день"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return "дня"
    return "дней"


async def balances(db, user_id: int) -> list[str]:
    ledger = [c for c in SHOWN_CURRENCIES if c in CURRENCY_SPECS]
    cols = ", ".join(CURRENCY_SPECS[c].balance_column for c in ledger)
    async with db.execute(f"SELECT {cols} FROM users WHERE user_tg_id = ?", (user_id,)) as cur:
        row = await cur.fetchone()
    values = {c: float(row[i] or 0) if row else 0.0 for i, c in enumerate(ledger)}
    values["essence"] = float(await skins_v3_repo.essence_balance(db, user_id))
    out = []
    for code in SHOWN_CURRENCIES:
        spec = CURRENCY_VIEW[code]
        out.append(f"{spec.icon} {spec.label}: <b>{fmt_num(values[code], spec.display_decimals)}</b>")
    return out


async def message_counts(db, chat_id: int, user_id: int) -> dict[str, int]:
    today = local_now().date()
    ranges = {
        "day": (today, today),
        "week": (today - timedelta(days=today.weekday()), today),
        "month": (today.replace(day=1), today),
    }
    out = {}
    for key, (a, b) in ranges.items():
        async with db.execute(
            "SELECT COALESCE(SUM(message_count), 0) FROM daily_user_stats "
            "WHERE chat_id = ? AND user_id = ? AND date BETWEEN ? AND ?",
            (chat_id, user_id, a.isoformat(), b.isoformat())) as cur:
            out[key] = int((await cur.fetchone())[0])
    async with db.execute(
        "SELECT user_messages_count_all_time FROM user_chat_stats WHERE chat_tg_id = ? AND user_tg_id = ?",
        (chat_id, user_id)) as cur:
        row = await cur.fetchone()
    out["all"] = int(row[0] or 0) if row else 0
    async with db.execute(
        "SELECT COALESCE(SUM(user_messages_count_all_time), 0) FROM user_chat_stats WHERE user_tg_id = ?",
        (user_id,)) as cur:
        out["everywhere"] = int((await cur.fetchone())[0])
    return out


async def card(db, chat_id: int, target: Target, viewer_id: int, is_group: bool) -> str:
    uid = target.user_id
    async with db.execute("SELECT user_tg_username FROM users WHERE user_tg_id = ?", (uid,)) as cur:
        row = await cur.fetchone()
    username = (row[0] if row else None) or target.username
    nick = None
    if is_group:
        async with db.execute("SELECT nickname FROM user_nicknames WHERE user_id = ? AND chat_id = ?", (uid, chat_id)) as cur:
            r = await cur.fetchone()
        nick = r[0] if r else None
    title = nick or target.name or (f"@{username}" if username else f"id{uid}")
    lines = [f"👤 <b>{esc(title)}</b>"]
    if username:
        lines.append(f"@{esc(username)}")   # сам игрок — единственный, кого можно отметить
    if await global_ranks.get_bot_rank(db, viewer_id) >= global_ranks.HELPER_MIN:
        lines.append(f"ID: <code>{uid}</code>")

    roles = []
    if is_group:
        roles.append(ranks.rank_name(await ranks.get_rank(db, chat_id, uid)))
    bot_rank = await global_ranks.get_bot_rank(db, uid)
    if bot_rank:
        roles.append(global_ranks.bot_rank_name(bot_rank))
    if await global_ranks.is_sponsor(db, uid):
        roles.append("💖 Спонсор")
    if roles:
        lines.append("\n" + " · ".join(roles))

    if is_group:
        c = await message_counts(db, chat_id, uid)
        lines.append(
            "\n💬 <b>Сообщения</b>\n"
            f"Сегодня: {fmt_num(c['day'])} · неделя: {fmt_num(c['week'])}\n"
            f"Месяц: {fmt_num(c['month'])} · всего: {fmt_num(c['all'])}"
        )
        if c["everywhere"] > c["all"]:
            lines.append(f"Во всех чатах: {fmt_num(c['everywhere'])}")
        async with db.execute(
            "SELECT s.membership_since, (SELECT MIN(date) FROM daily_user_stats d "
            "WHERE d.chat_id = s.chat_tg_id AND d.user_id = s.user_tg_id) "
            "FROM user_chat_stats s WHERE s.chat_tg_id = ? AND s.user_tg_id = ?", (chat_id, uid)) as cur:
            r = await cur.fetchone()
        if r:
            since, first = r
            if since:
                days = (local_now().date() - since.date()).days
                lines.append(f"\n📅 В чате: {days} {days_word(days)} (с {since.strftime('%d.%m.%Y')})")
            if first:
                y, m, d = first.split("-")
                lines.append(f"👁 Впервые замечен: {d}.{m}.{y}")
        warns = await active_warns(db, chat_id, uid)
        if warns:
            lines.append(f"⚠️ Варнов: {len(warns)}")

    fam = await family.family_of(db, uid)
    if fam:
        names = await family.labels(db, fam.members)
        if fam.is_parent(uid):
            partner = fam.partner_of(uid)
            since = f" с {fam.since.strftime('%d.%m.%Y')}" if fam.since else ""
            lines.append(f"\n💞 В браке с {names[partner]}{since}")
        else:
            parents = " и ".join(names[p] for p in fam.parents)
            lines.append(f"\n👪 В семье {parents} · {fam.roles.get(uid, 'ребёнок')}")

    lines.append("\n💰 <b>Баланс</b>\n" + "\n".join(await balances(db, uid)))
    return "\n".join(lines)


@registry.command("я", aliases=("профиль", "кто я"), usage="бот я", section="profile",
                  summary="Ваша карточка: сообщения, ранг, брак, баланс.")
async def cmd_me(ctx: Ctx) -> None:
    u = ctx.message.from_user
    target = Target(u.id, u.username, u.full_name)
    is_group = ctx.message.chat.type in ("group", "supergroup")
    await ctx.reply(await card(ctx.db, ctx.message.chat.id, target, ctx.user_id, is_group))


@registry.command("кто", usage="бот кто, @ник  (или ответом на сообщение)", section="profile",
                  summary="Карточка другого игрока.", example="бот кто, @ник")
async def cmd_who(ctx: Ctx) -> None:
    target, _ = await resolve_target(ctx.db, ctx.message, ctx.args, allow_id=True)
    if target is None:
        if ctx.args.strip():
            await ctx.reply("🤔 Не нашёл такого игрока. Он должен хотя бы раз написать в чат с ботом.")
            return
        raise UsageError("бот кто, @ник  (или ответом на сообщение)")
    is_group = ctx.message.chat.type in ("group", "supergroup")
    await ctx.reply(await card(ctx.db, ctx.message.chat.id, target, ctx.user_id, is_group))


@registry.command("баланс", aliases=("кошелек", "кошелёк"), usage="бот баланс", section="profile",
                  summary="Сколько у вас валюты.")
async def cmd_balance(ctx: Ctx) -> None:
    await ctx.reply("💰 <b>Баланс</b>\n" + "\n".join(await balances(ctx.db, ctx.user_id)))
