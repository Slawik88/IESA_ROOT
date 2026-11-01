"""«Шипперим»: случайные пары игроков в чате и процент их совместимости (S21).

Команды: «шипирить» (+ @ник), «шипирить меня», личный отказ «не шипирить меня»
и возврат «шипирить меня разрешаю». Пара случайная на каждый вызов; процент
пары детерминирован (core.ship: hash двух id). Случайных людей не пингуем:
ссылка t.me или текст «id…», tg://user?id= запрещён.

Выключатели: группа group:ship в «Функциях» (глобально и по чату) и команда
владельца чата «бот шипирить вкл/выкл» (ключ module_ship, право rights). По
решению владельца функция включена по умолчанию.
"""
from __future__ import annotations

import html
import random

from bot.chat import ranks
from bot.chat.framework import Ctx, norm, registry
from bot.chat.ship_texts import BANK
from core import ship
from infrastructure.repositories import chat_module_audit
from infrastructure.repositories import ship_v1

ON_WORDS = ("вкл", "включить", "on", "да")
OFF_WORDS = ("выкл", "выключить", "off", "нет")
WHAT = "<i>Бот случайно выбирает двоих в чате и объявляет процент их совместимости. Случайных людей бот не пингует.</i>"


def _display(user_id: int, username: str | None) -> str:
    """Имя без пинга: ссылка на профиль t.me или текст «id…» (tg://user?id= запрещён)."""
    if username:
        return f'<a href="https://t.me/{html.escape(username, quote=True)}">@{html.escape(username)}</a>'
    return f"id{int(user_id)}"


def _verdict_line(low: int, high: int, percent: int) -> str:
    """Процент и вердикт: у одной пары они всегда одни и те же (pick_stable)."""
    verdict = BANK.pick_stable(ship.percent_bucket_key(percent), f"ship:{low}:{high}")
    return f"💖 Совместимость: {percent}% — {verdict}"


def _announce_line(category: str, low: int, high: int, **subs: str) -> str:
    seed = f"ship:{low}:{high}" if category == "author_included" else None
    text = BANK.pick_stable(category, seed, **subs) if seed else BANK.pick(category, **subs)
    return f"💞 {text}"


async def _pool(db, chat_id: int) -> list[tuple[int, str | None]]:
    """Кандидаты: недавно активные, не боты, не отказавшиеся, служебные аккаунты отфильтрованы."""
    from services import chat_bots
    pool = await ship_v1.active_pool(db, chat_id, ship.ACTIVE_DAYS)
    return [entry for entry in pool if not chat_bots.is_service(entry[0])]


async def _cooldown_left(ctx: Ctx, chat_id: int) -> int:
    return await ship_v1.pause_left(ctx.db, chat_id, ctx.user_id)


def _pair_message(category: str, one: tuple[int, str | None], two: tuple[int, str | None]) -> str:
    low, high = sorted((one[0], two[0]))
    announce = _announce_line(category, low, high,
                              a=_display(*one), b=_display(*two))
    return announce + "\n" + _verdict_line(low, high, ship.compatibility_percent(low, high))


async def _toggle_chat(ctx: Ctx, chat_id: int, want: bool) -> None:
    """«бот шипирить вкл/выкл»: выключатель чата для того, кто меняет права рангов."""
    if not await ranks.can(ctx.db, chat_id, ctx.user_id, "rights"):
        await ctx.reply("💞 Это может тот, кто настраивает права рангов в чате (обычно владелец).")
        return
    result = await chat_module_audit.set_chat_module(
        ctx.db, chat_id=chat_id, module_key=ship_v1.MODULE_KEY, enabled=want,
        actor_id=ctx.user_id, source="chat_command")
    if not result["changed"]:
        await ctx.reply(f"💞 Шипперим в этом чате уже {'включён' if want else 'выключен'}.")
        return
    state = "включён" if want else "выключен"
    await ctx.reply(f"💞 Шипперим в этом чате <b>{state}</b>.\n{WHAT}")


@registry.command("шипирить", usage="бот шипирить [@ник]", bare=True, private=False,
                  section="social", group="ship",
                  summary="Случайная пара игроков в чате и процент их совместимости.",
                  example="бот шипирить")
async def cmd_ship(ctx: Ctx) -> None:
    chat_id = ctx.message.chat.id
    word = norm(ctx.args)
    if ctx.prefixed and word in ON_WORDS + OFF_WORDS:
        await _toggle_chat(ctx, chat_id, word in ON_WORDS)
        return
    if not await ship_v1.chat_enabled(ctx.db, chat_id):
        await ctx.reply("💞 Шипперим в этом чате выключен. Владелец может включить: <code>бот шипирить вкл</code>")
        return
    from bot.chat.targets import NOT_FOUND, names_someone, resolve_target
    target, _rest = await resolve_target(ctx.db, ctx.message, ctx.args)
    if target is not None:
        await _ship_with_target(ctx, chat_id, target.user_id, target.username)
        return
    if names_someone(ctx.args):
        await ctx.reply(NOT_FOUND)
        return
    if not ctx.prefixed and ctx.args.strip():
        return   # без «бот» и без адресата это разговор, а не команда (как у варпов)
    await _ship_random(ctx, chat_id)


@registry.command("шипирить меня", aliases=("шипперим меня", "шиперим меня"), usage="шипирить меня",
                  bare=True, private=False, section="social", group="ship",
                  summary="Судьба подберёт пару для тебя самого.",
                  example="шипирить меня")
async def cmd_ship_me(ctx: Ctx) -> None:
    chat_id = ctx.message.chat.id
    if not await ship_v1.chat_enabled(ctx.db, chat_id):
        await ctx.reply("💞 Шипперим в этом чате выключен. Владелец может включить: <code>бот шипирить вкл</code>")
        return
    if await ship_v1.opted_out(ctx.db, ctx.user_id):
        await ctx.reply("🙈 Ты сам попросил не выбирать тебя в пары. Вернуться: <code>шипирить меня разрешаю</code>")
        return
    await _ship_random(ctx, chat_id, for_user_id=ctx.user_id, category="self_pair")


async def _ship_random(ctx: Ctx, chat_id: int, *, for_user_id: int | None = None, category: str = "announce") -> None:
    """Случайная пара из активных: с указанным «заказчиком» или совсем наугад."""
    left = await _cooldown_left(ctx, chat_id)
    if left:
        await ctx.reply(BANK.pick("cooldown", sec=left))
        return
    pool = await _pool(ctx.db, chat_id)
    if len(pool) < 2:
        await ctx.reply(BANK.pick("nobody"))
        return
    recent = await _recent(ctx, chat_id)
    if for_user_id is not None:
        author = (for_user_id, _username_of(pool, for_user_id))
        partner = _pick_partner(pool, recent, author, exclude={for_user_id})
        if partner is None:
            await ctx.reply(BANK.pick("nobody"))
            return
        chosen = [author, partner]
    else:
        chosen = _sample_pair(pool, recent)
        if any(entry[0] == ctx.user_id for entry in chosen):
            category = "author_included"   # случай выбрал пару с самим автором команды
    await _finish_ship(ctx, chat_id, chosen, category)


async def _recent(ctx: Ctx, chat_id: int) -> set[tuple[int, int]]:
    return await ship_v1.recent_pairs(ctx.db, chat_id, ship.RECENT_PAIR_MINUTES)


def _pick_partner(pool: list[tuple[int, str | None]], taken: set[tuple[int, int]],
                  with_user: tuple[int, str | None], *, exclude: set[int]) -> tuple[int, str | None] | None:
    """Случайный партнёр к with_user; недавние пары пропускаем, пока есть из кого выбрать."""
    others = [entry for entry in pool if entry[0] not in exclude]
    if not others:
        return None
    fresh = [entry for entry in others if tuple(sorted((with_user[0], entry[0]))) not in taken]
    return random.choice(fresh or others)


async def _ship_with_target(ctx: Ctx, chat_id: int, target_id: int, target_username: str | None) -> None:
    """«шипирить @ник»: этот игрок + случайный участник."""
    if target_id == ctx.user_id:
        await ctx.reply("Себя в пару не поставить — для этого есть <code>шипирить меня</code> 😉")
        return
    left = await _cooldown_left(ctx, chat_id)
    if left:
        await ctx.reply(BANK.pick("cooldown", sec=left))
        return
    if await ship_v1.opted_out(ctx.db, target_id):
        await ctx.reply(BANK.pick("opted_out", b=_display(target_id, target_username)))
        return
    pool = await _pool(ctx.db, chat_id)
    if target_id not in [entry[0] for entry in pool]:
        await ctx.reply("Этот игрок пока не среди активных: пусть напишет в чат, и я его замечу 👀")
        return
    partner = _pick_partner(pool, await _recent(ctx, chat_id), (target_id, target_username), exclude={target_id})
    if partner is None:
        await ctx.reply(BANK.pick("nobody"))
        return
    await _finish_ship(ctx, chat_id, [(target_id, target_username), partner], "announce")


def _username_of(pool: list[tuple[int, str | None]], user_id: int) -> str | None:
    for uid, username in pool:
        if uid == user_id:
            return username
    return None


def _sample_pair(pool: list[tuple[int, str | None]], taken: set[tuple[int, int]]) -> list[tuple[int, str | None]]:
    """Два случайных человека; пара не повторяет недавние, пока есть из чего выбрать."""
    chosen: list[tuple[int, str | None]] = []
    for _ in range(12):
        chosen = random.sample(pool, 2)
        key = tuple(sorted((chosen[0][0], chosen[1][0])))
        if key not in taken or len(pool) < ship.MIN_POOL_FOR_UNIQUE:
            break
    return chosen


async def _finish_ship(ctx: Ctx, chat_id: int, chosen: list[tuple[int, str | None]], category: str) -> None:
    one, two = chosen
    await ship_v1.remember(ctx.db, chat_id, ctx.user_id)
    await ship_v1.record_pair(ctx.db, chat_id, one[0], two[0])
    commit = getattr(ctx.db, "commit", None)
    if commit:
        await commit()
    # СТИЛЬ v1 (см. docs/CHAT_BOT_DESIGN_HANDOFF.md): событие одной строкой с эмодзи, подробности под ним.
    await ctx.message.answer(_pair_message(category, one, two), parse_mode="HTML",
                             disable_web_page_preview=True)


@registry.command("не шипирить меня", usage="не шипирить меня", bare=True, private=True,
                  section="social", group="ship",
                  summary="Попросить судьбу не выбирать тебя в пары.",
                  example="не шипирить меня")
async def cmd_ship_opt_out(ctx: Ctx) -> None:
    if await ship_v1.opted_out(ctx.db, ctx.user_id):
        await ctx.reply("🙈 Ты уже вне игры для случайных пар. Вернуться: <code>шипирить меня разрешаю</code>")
        return
    await ship_v1.set_opt_out(ctx.db, ctx.user_id, True)
    commit = getattr(ctx.db, "commit", None)
    if commit:
        await commit()
    await ctx.reply("🙈 Готово: судьба больше не выбирает тебя в пары. Вернуться: <code>шипирить меня разрешаю</code>")


@registry.command("шипирить меня разрешаю", usage="шипирить меня разрешаю", bare=True, private=True,
                  section="social", group="ship",
                  summary="Вернуться в «Шипперим» после личного отказа.",
                  example="шипирить меня разрешаю")
async def cmd_ship_opt_in(ctx: Ctx) -> None:
    if not await ship_v1.opted_out(ctx.db, ctx.user_id):
        await ctx.reply("💞 Ты и так участвуешь в случайных парах.")
        return
    await ship_v1.set_opt_out(ctx.db, ctx.user_id, False)
    commit = getattr(ctx.db, "commit", None)
    if commit:
        await commit()
    await ctx.reply("💞 Снова в игре: судьба может выбрать тебя в пару. Отказ в любой момент: <code>не шипирить меня</code>")
