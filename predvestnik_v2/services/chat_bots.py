"""Боты среди участников чата: их нет ни в чистке, ни в топах и списках.

Telegram сообщает «это бот» вместе с пользователем: в сообщении, в событии участника, в списке администраторов и в ответе
getChatMember. Раньше бот этот признак не сохранял, и колонка user_chat_stats.is_bot всегда оставалась пустой:
другие боты (и сам Предвестник) попадали в чистку как «не набравшие норму».

Теперь признак ставится из любого из этих мест, а перед чисткой список нарушителей сверяется с Telegram.
Только добавление и пометки: строки не удаляются, колонка is_bot уже есть."""
from __future__ import annotations

import asyncio

from loguru import logger

# Служебные аккаунты Telegram: у них is_bot = False или он не всегда приходит, но людьми они не являются.
SERVICE_IDS = frozenset({
    777000,        # Telegram: подписывает посты, пересланные из канала
    1087968824,    # GroupAnonymousBot: сообщения анонимных админов
    136817688,     # Channel_Bot: сообщения от имени канала
    1271266957,    # Replies: ответы на посты канала
})
SCREEN_LIMIT = 400      # сколько человек из списка нарушителей сверяем с Telegram за один раз
SCREEN_PARALLEL = 8
SCREEN_TIMEOUT = 40.0
CACHE_LIMIT = 50_000

# Условие для запросов по daily_user_stats d: строки ботов (в любом чате) в рейтинги не идут.
NOT_BOT_DAILY = "NOT EXISTS (SELECT 1 FROM user_chat_stats b WHERE b.user_tg_id = d.user_id AND COALESCE(b.is_bot, FALSE))"

_marked: set[int] = set()   # кого уже пометили в этом запуске: лишний запрос на каждое сообщение бота не нужен


def is_service(user_id) -> bool:
    return int(user_id or 0) in SERVICE_IDS


def is_bot(user) -> bool:
    """Бот ли это по данным Telegram (пользователь из сообщения или события) или служебный аккаунт."""
    return bool(user) and (bool(getattr(user, "is_bot", False)) or is_service(getattr(user, "id", 0)))


async def mark(db, user_id: int) -> None:
    """Пометить пользователя как бота во всех чатах. Повторные вызовы за запуск ничего не делают."""
    uid = int(user_id)
    if uid in _marked:
        return
    try:
        await db.execute("UPDATE user_chat_stats SET is_bot = TRUE WHERE user_tg_id = ? AND NOT COALESCE(is_bot, FALSE)", (uid,))
        commit = getattr(db, "commit", None)
        if commit:
            await commit()
        if len(_marked) > CACHE_LIMIT:
            _marked.clear()
        _marked.add(uid)
    except Exception as exc:   # пометка — дополнение: потеря одной не должна ломать учёт сообщений
        logger.warning(f"bot mark skipped for {uid}: {exc}")


async def observe(db, user) -> bool:
    """Увидели пользователя из Telegram: если это бот, пометить. True — бот."""
    if not is_bot(user):
        return False
    await mark(db, user.id)
    return True


async def known(db, user_ids) -> set[int]:
    """Кого из списка база уже знает как бота."""
    ids = list(dict.fromkeys(int(i) for i in user_ids))
    if not ids:
        return set()
    marks = ", ".join("?" for _ in ids)
    async with db.execute(
        f"SELECT DISTINCT user_tg_id FROM user_chat_stats WHERE COALESCE(is_bot, FALSE) AND user_tg_id IN ({marks})",
        tuple(ids)) as cur:
        return {int(r[0]) for r in await cur.fetchall()}


async def startup(db, bot) -> None:
    """При запуске: сам Предвестник и служебные аккаунты Telegram — боты, чьи бы строки ни остались в базе."""
    try:
        me = await bot.me()
        await mark(db, me.id)
    except Exception as exc:
        logger.warning(f"own bot id not marked: {exc}")
    for uid in SERVICE_IDS:
        await mark(db, uid)


async def admin_bots(bot, db, chat_id: int, admins=None) -> set[int]:
    """Боты среди администраторов чата (одним запросом к Telegram); найденных сразу помечает."""
    if admins is None:
        try:
            admins = await bot.get_chat_administrators(chat_id)
        except Exception as exc:
            logger.debug(f"admins of {chat_id} unavailable: {exc}")
            return set()
    found = {int(a.user.id) for a in admins if is_bot(getattr(a, "user", None))}
    for uid in found:
        await mark(db, uid)
    return found


async def screen(bot, db, chat_id: int, user_ids, *, limit: int | None = None) -> set[int]:
    """Какие из этих людей на самом деле боты (например, среди нарушителей чистки).

    Свой бот, служебные аккаунты и помеченные в базе известны сразу, остальные находятся списком администраторов и
    ответом getChatMember (по нескольку параллельно, не дольше SCREEN_TIMEOUT). Кого проверить не удалось, остаётся
    в списке: решение по нему примет человек, а при отправке досье его проверят ещё раз."""
    from services import member_tags   # tags зависят от этого модуля только через probe: импорт внутри, чтобы не было круга
    ids = list(dict.fromkeys(int(i) for i in user_ids))
    bots: set[int] = {i for i in ids if is_service(i)}
    try:
        me = int((await bot.me()).id)
        if me in ids:
            bots.add(me)
    except Exception as exc:
        logger.debug(f"own bot id unavailable: {exc}")
    bots |= await known(db, ids)
    bots |= await admin_bots(bot, db, chat_id) & set(ids)
    todo = [i for i in ids if i not in bots][:SCREEN_LIMIT if limit is None else limit]
    if not todo or int(chat_id) >= 0:
        return bots
    gate = asyncio.Semaphore(SCREEN_PARALLEL)

    async def ask(uid: int):
        async with gate:
            return uid, await member_tags.probe(bot, chat_id, uid)

    tasks = [asyncio.ensure_future(ask(u)) for u in todo]
    try:
        done, pending = await asyncio.wait(tasks, timeout=SCREEN_TIMEOUT)
    except Exception as exc:
        logger.debug(f"screen {chat_id}: {exc}")
        done, pending = set(), set(tasks)
    for t in pending:
        t.cancel()
    for t in done:
        if t.cancelled() or t.exception():
            continue
        uid, (state, tag) = t.result()
        if state == "bot":
            bots.add(uid)
            await mark(db, uid)
        elif state == "ok":
            await member_tags.observe(db, chat_id, uid, tag)   # раз уж спросили: тег сохраняем
    for uid in bots:   # свой бот и служебные аккаунты тоже запоминаем, чтобы следующая чистка их не искала
        await mark(db, uid)
    commit = getattr(db, "commit", None)
    if commit:
        await commit()
    return bots
