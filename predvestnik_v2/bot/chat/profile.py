"""«бот я», «бот кто» — карточка игрока; «бот баланс» — кошелёк.

Карточка компактная (стиль v2; макет — docs/design-refs/profile-card-preview.html):
шапка без рамок, каждый смысловой блок отделён пустой строкой, счётчики идут
парами в цитатах, значения — жирным вплотную к подписи (в начале строк цитат
ничего не «висит»). Никого, кроме самого игрока, карточка не пингует: партнёр и
прочие имена выводятся с невидимым пробелом после «@».
"""
from __future__ import annotations

import html
import re
from datetime import timedelta

from core.economy_contract import CURRENCY_SPECS
from infrastructure.repositories import skins_v3 as skins_v3_repo
from loguru import logger
from services import chat_bots, member_tags, vip as vip_service
from bot.chat import family, global_ranks, profile_view, ranks, skin_card, streak
from bot.chat.profile_view import CardData, esc
from bot.chat.achievements_data import ACHIEVEMENTS
from bot.chat.framework import Ctx, UsageError, registry
from bot.chat.moderation import active_warns
from bot.chat.settings import CURRENCY_VIEW
from bot.chat.style import quote
from bot.chat.targets import Target, resolve_target
from bot.chat.tracking import PRESENCE_SQL, local_now, presence_of
from core.skins_v3_chat import ChatLook
from services import skins_chat

# Валюты, которые сейчас в игре (остальные — легаси и не показываются).
SHOWN_CURRENCIES = ("mora", "diamonds", "essence", "zarniki")

CAPTION_LIMIT = 1024   # лимит подписи к фото у Telegram, видимых символов

# Знаменатель «достижения 23/641»: сумма максимальных уровней всех достижений.
ACHIEVEMENT_LEVELS_MAX = sum(a.max_level for a in ACHIEVEMENTS)


def quiet(username: str | None, fallback: str) -> str:
    return f"@\u200b{esc(username)}" if username else fallback


async def username_of(db, user_id: int) -> str | None:
    async with db.execute("SELECT user_tg_username FROM users WHERE user_tg_id = ?", (user_id,)) as cur:
        row = await cur.fetchone()
    return row[0] if row else None


async def quiet_name(db, user_id: int) -> str:
    """Имя игрока без пинга: «@ник» (с нулевым пробелом) или id."""
    return quiet(await username_of(db, user_id), f"id{user_id}")


def fmt_num(v: float, decimals: int = 0) -> str:
    s = f"{v:,.{decimals}f}".replace(",", " ")
    return s.rstrip("0").rstrip(".") if decimals else s


def days_word(n: int) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return "день"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return "дня"
    return "дней"


def ago(seconds: int) -> str:
    """Когда игрок писал в этот чат в последний раз: «<b>1</b> ч назад», «только что»."""
    if seconds < 60:
        return "только что"
    if seconds < 3600:
        return f"<b>{seconds // 60}</b> мин назад"
    if seconds < 86400:
        return f"<b>{seconds // 3600}</b> ч назад"
    days = seconds // 86400
    if days < 30:
        return f"<b>{days}</b> {days_word(days)} назад"
    return f"<b>{days // 30}</b> мес. назад"


async def wallet_values(db, user_id: int) -> dict[str, float]:
    ledger = [c for c in SHOWN_CURRENCIES if c in CURRENCY_SPECS]
    cols = ", ".join(CURRENCY_SPECS[c].balance_column for c in ledger)
    async with db.execute(f"SELECT {cols} FROM users WHERE user_tg_id = ?", (user_id,)) as cur:
        row = await cur.fetchone()
    values = {c: float(row[i] or 0) if row else 0.0 for i, c in enumerate(ledger)}
    values["essence"] = float(await skins_v3_repo.essence_balance(db, user_id))
    return values


async def balances(db, user_id: int) -> list[str]:
    values = await wallet_values(db, user_id)
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


async def chat_place(db, chat_id: int, user_id: int, since: str, until: str) -> int | None:
    """Место в чате по сообщениям за период: 1 — больше всех. None, если игрок не писал."""
    async with db.execute(
        "SELECT COALESCE(SUM(message_count), 0) FROM daily_user_stats "
        "WHERE chat_id = ? AND user_id = ? AND date BETWEEN ? AND ?",
        (chat_id, user_id, since, until)) as cur:
        mine = int((await cur.fetchone())[0])
    if mine <= 0:
        return None
    async with db.execute(
        "SELECT COUNT(*) FROM (SELECT d.user_id FROM daily_user_stats d "
        "WHERE d.chat_id = ? AND d.date BETWEEN ? AND ? AND " + chat_bots.NOT_BOT_DAILY +
        " GROUP BY d.user_id HAVING SUM(d.message_count) > ?) t",
        (chat_id, since, until, mine)) as cur:
        ahead = int((await cur.fetchone())[0])
    return ahead + 1


async def achievement_levels(db, user_id: int) -> int:
    """Сколько уровней достижений набрано (максимум — ACHIEVEMENT_LEVELS_MAX)."""
    async with db.execute("SELECT COALESCE(SUM(level), 0) FROM chat_achievement_levels WHERE user_id = ?",
                          (user_id,)) as cur:
        return int((await cur.fetchone())[0])


# СТИЛЬ v2 (компактный; макет — docs/design-refs/profile-card-preview.html): шапка, блоки через
# пустую строку, счётчики парами в цитатах, значения жирным. Со скином — core/skins_v3_chat_layout.py.
async def _head(db, chat_id: int, target: Target, viewer_id: int, is_group: bool) -> CardData:
    uid = target.user_id
    username = await username_of(db, uid) or target.username
    # Имя из Telegram: ники старого бота удалены (владелец, 2026-10-21).
    data = CardData(title=target.name or (f"@{username}" if username else f"id{uid}"), username=username)
    tag = await member_tags.get(db, chat_id, uid) if is_group else None
    if tag:
        data.head.append(f"🏷 <b>{esc(tag)}</b>")   # подпись справа от имени в списке участников этого чата
    roles = []
    if is_group:
        rank = await ranks.get_rank(db, chat_id, uid)
        if rank > 0:
            roles.append(ranks.rank_name(rank))
    bot_rank = await global_ranks.get_bot_rank(db, uid)
    if bot_rank:
        roles.append(global_ranks.bot_rank_name(bot_rank))
    if await global_ranks.is_sponsor(db, uid):
        roles.append("💖 Спонсор")
    if roles:
        data.head.append(" · ".join(roles))
    tail = []
    if await vip_service.is_vip_active(db, uid):
        tail.append("👑 VIP")
    if await global_ranks.get_bot_rank(db, viewer_id) >= global_ranks.HELPER_MIN:
        tail.append(f"🆔 {uid}")   # ID игроков видят только хелперы и выше
    if tail:
        data.head.append(" · ".join(tail))
    return data


async def _counters(db, data: CardData, chat_id: int, uid: int, is_group: bool) -> None:
    today = local_now().date()
    if is_group:
        c = await message_counts(db, chat_id, uid)
        data.messages = [("сегодня", fmt_num(c["day"])), ("неделя", fmt_num(c["week"])), ("месяц", fmt_num(c["month"]))]
        data.totals = [("всего", fmt_num(c["all"]))]
        if c["everywhere"] > c["all"]:
            data.totals.append(("во всех", fmt_num(c["everywhere"])))
    current, best, _ = await streak.streak_of(db, uid, today)
    place = await chat_place(db, chat_id, uid, today.replace(day=1).isoformat(), today.isoformat()) if is_group else None
    levels = await achievement_levels(db, uid)
    items = []
    if current or best:
        items.append(("серия", f"{current} {days_word(current)}" if current else "—"))
    if best:
        items.append(("рекорд", f"{best} {days_word(best)}"))
    if place:
        items.append(("место", f"#{place}"))
    if levels:
        items.append(("достижения", f"{levels}/{ACHIEVEMENT_LEVELS_MAX}"))
    data.progress = items
    values = await wallet_values(db, uid)
    for code in SHOWN_CURRENCIES:
        spec = CURRENCY_VIEW[code]
        data.wallet.append(f"{spec.label.lower()} <b>{fmt_num(values[code], spec.display_decimals)}</b> {spec.icon}")


async def _presence(db, data: CardData, chat_id: int, uid: int) -> None:
    async with db.execute(
            f"SELECT {PRESENCE_SQL}, EXTRACT(EPOCH FROM NOW() - s.last_message_at)::BIGINT "
            "FROM user_chat_stats s WHERE s.chat_tg_id = ? AND s.user_tg_id = ?",
            (chat_id, uid)) as cur:
        r = await cur.fetchone()
    pres = presence_of(*r[:4]) if r else None
    away = int(r[4]) if r and r[4] is not None else None
    if pres:
        seen = f"В чате <b>{pres.days}</b> {days_word(pres.days)}" if pres.days else "В чате с сегодняшнего дня"
        data.personal.append("📅 " + seen + (f" · 🕓 {ago(away)}" if away is not None else ""))
        if pres.rejoined:
            data.personal.append(f"↩️ Вернулся в чат · впервые здесь {pres.first_seen.strftime('%d.%m.%Y')}")
    warns = await active_warns(db, chat_id, uid)
    if warns:
        data.personal.append(f"⚠️ Варнов <b>{len(warns)}</b>")


async def _family(db, data: CardData, chat_id: int, uid: int, is_group: bool) -> None:
    fam = await family.family_of(db, uid)
    if not fam:
        return
    if not fam.is_parent(uid):
        parents = " и ".join([await quiet_name(db, p) for p in fam.parents])
        data.personal.append(f"👪 В семье {parents} · {fam.roles.get(uid, 'ребёнок')}")
        return
    partner = fam.partner_of(uid)
    if not partner:
        return
    data.personal.append(f"💞 В браке с {await quiet_name(db, partner)}")
    parts = []
    partner_tag = await member_tags.get(db, chat_id, partner) if is_group else None
    if partner_tag:
        parts.append(f"[{esc(partner_tag)}]")
    days = family.days_together(fam.since)
    if days is not None:
        parts.append(f"вместе {days} {days_word(days)}")
    if parts:
        data.personal.append("\x00" + " · ".join(parts))   # подстрока: в обычной карточке — цитата, в стиле скина — «╰»


async def card(db, chat_id: int, target: Target, viewer_id: int, is_group: bool, look: ChatLook | None = None) -> str:
    """look — надетый скин игрока (services.skins_chat.card_look); без него карточка как раньше."""
    data = await _head(db, chat_id, target, viewer_id, is_group)
    await _counters(db, data, chat_id, target.user_id, is_group)
    if is_group:
        await _presence(db, data, chat_id, target.user_id)
    await _family(db, data, chat_id, target.user_id, is_group)
    return profile_view.styled(data, look) if look else profile_view.plain(data)


def caption_len(text: str) -> int:
    """Длина подписи к фото так, как её считает Telegram: без HTML-тегов, в UTF-16.

    Каждый эмодзи вне BMP — два символа; считаем консервативно, чтобы подпись
    гарантированно прошла лимит.
    """
    plain = html.unescape(re.sub(r"<[^>]+>", "", text))
    return len(plain.encode("utf-16-le")) // 2


async def send_media_card(ctx: Ctx, text: str, user_id: int, chat_scope: int | None, look: ChatLook | None,
                          name: str, username: str | None) -> None:
    """График (в стиле скина — картинкой или видео на SSS) с текстом в подписи.

    Текст, который не влезает в лимит подписи Telegram (или не принят подписью), уходит как
    раньше: график без подписи, затем текст. Если рисовать нечего — только текст."""
    try:
        media = await skin_card.graph_media(ctx.db, user_id, chat_scope, look, name, username)
    except Exception as exc:
        logger.warning(f"График активности не построен: {exc}")
        media = None
    if media:
        if caption_len(text) <= CAPTION_LIMIT:
            try:
                await skin_card.answer(ctx.message, media, text)
                return
            except Exception as exc:   # подпись важна, но карточку покажем и без неё
                logger.warning(f"Карточка не легла подписью к графику: {exc}")
        try:
            await skin_card.answer(ctx.message, media)
        except Exception as exc:   # карточка важнее: график не повод её не показать
            logger.warning(f"График активности не отправлен: {exc}")
    await ctx.reply(text)


async def send_card(ctx: Ctx, target: Target, is_group: bool) -> None:
    """«бот я / бот кто»: одним сообщением — график активности с карточкой в подписи.

    В группе график — по этому чату, в личке — по всем чатам."""
    chat_id = ctx.message.chat.id
    look = await skins_chat.safe_card_look(ctx.db, target.user_id, chat_id)
    text = await card(ctx.db, chat_id, target, ctx.user_id, is_group, look)
    await send_media_card(ctx, text, target.user_id, chat_id if is_group else None, look, target.name or "", target.username)


@registry.command("я", aliases=("профиль", "кто я"), usage="бот я", section="profile",
                  summary="Ваша карточка: сообщения, ранг, брак, баланс.")
async def cmd_me(ctx: Ctx) -> None:
    u = ctx.message.from_user
    target = Target(u.id, u.username, u.full_name)
    is_group = ctx.message.chat.type in ("group", "supergroup")
    await send_card(ctx, target, is_group)


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
    await send_card(ctx, target, is_group)


@registry.command("баланс", aliases=("кошелек", "кошелёк"), usage="бот баланс", section="profile",
                  summary="Сколько у вас валюты.")
async def cmd_balance(ctx: Ctx) -> None:
    lines = await balances(ctx.db, ctx.user_id)
    look = await skins_chat.safe_card_look(ctx.db, ctx.user_id, ctx.message.chat.id)
    if not look:
        await ctx.reply("💰 <b>Баланс</b>\n" + quote(lines))
        return
    await ctx.reply(profile_view.balance(look, lines))
