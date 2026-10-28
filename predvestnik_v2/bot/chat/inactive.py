"""«бот неактивы»: a compact, paged view of silence in the current group."""
from __future__ import annotations

import asyncio
from datetime import timedelta
from html import escape

from aiogram import Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramNetworkError
from aiogram.filters.callback_data import CallbackData
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from loguru import logger

from bot.chat.durations import split_duration
from bot.chat.framework import Ctx, registry
from bot.chat.style import profile_link, quote
from bot.chat.tracking import tz_delta
from core.chat_inactivity import (
    DAY_SECONDS, DEFAULT_SECONDS, MAX_DAYS, MAX_PAGE, MAX_PERIOD_LENGTH,
    PAGE_SIZE, QUERY_TIMEOUT_SECONDS, QUICK_PERIODS, InactivePage,
)
from services import chat_inactivity, feature_switches, global_moderation

router = Router(name="chat_inactive")
USAGE = "бот неактивы 7д"
PERIOD_HINT = (
    "Укажи срок от 1 дня до 100 лет: <code>бот неактивы 7д</code>.\n"
    "д — дни, н — недели, мес — месяцы, г — годы (365 дней).\n"
    "Например: <code>5д</code> · <code>1н</code> · <code>29д</code> · <code>1г</code>."
)
UNAVAILABLE = "Не удалось обновить список. Попробуй ещё раз: бот неактивы."


class InactiveCB(CallbackData, prefix="idle"):
    uid: int
    chat: int
    seconds: int
    page: int


def parse_period(args: str) -> int:
    if not args.strip():
        return DEFAULT_SECONDS
    if len(args) > MAX_PERIOD_LENGTH:
        raise ValueError("period too long")
    duration, rest = split_duration(args, max_days=MAX_DAYS)
    if not isinstance(duration, timedelta) or rest or duration.total_seconds() < DAY_SECONDS:
        raise ValueError("invalid inactivity period")
    return int(duration.total_seconds())


def period_label(seconds: int) -> str:
    days, remainder = divmod(seconds, DAY_SECONDS)
    parts = [f"{days} дн."] if days else []
    hours, remainder = divmod(remainder, 3600)
    if hours:
        parts.append(f"{hours} ч")
    if remainder // 60:
        parts.append(f"{remainder // 60} мин")
    return " ".join(parts)


def render(result: InactivePage, seconds: int) -> str:
    head = f"👻 <b>Кто молчит в этом чате</b>\nБез сообщений от <b>{period_label(seconds)}</b> · найдено <b>{result.total}</b>"
    lines = []
    for index, member in enumerate(result.items, result.page * PAGE_SIZE + 1):
        if member.username:
            name = profile_link(member.user_id, member.username[:32])
        else:
            label = " ".join((member.name or "").split())[:40] or "Игрок без ника"
            name = f'<a href="tg://user?id={member.user_id}">{escape(label)}</a>'
        note = " · не писал при боте" if member.never_spoke else " · после возвращения" if member.rejoined else ""
        lines.append(f"{index}. {name} — <b>{member.seconds // DAY_SECONDS} дн.</b>{note}")
    body = quote(lines) if lines else "За этот срок молчунов не найдено. Выбери другой срок или обнови список позже."
    footer = f"Страница {result.page + 1} из {result.pages}. Дольше молчащие — выше.\n" if result.total else ""
    footer += "Только известные боту участники. Учитываются сообщения здесь, а не статус «онлайн»."
    if result.unknown:
        footer += f"\nЕщё {result.unknown} — пока без данных о сроке."
    return (f"{head}\n\n{body}\n\n<i>{footer}</i>\n"
            "Другой срок: <code>бот неактивы 5д</code> · <code>1н</code> · <code>29д</code> · <code>1г</code>.")


def keyboard(uid: int, chat: int, seconds: int, result: InactivePage) -> InlineKeyboardMarkup:
    def button(label: str, period: int, page: int = 0):
        return InlineKeyboardButton(text=label, callback_data=InactiveCB(
            uid=uid, chat=chat, seconds=period, page=page).pack())
    quick = [button(f"✓ {label}" if period == seconds else label, period) for label, period in QUICK_PERIODS]
    rows = [quick[:2], quick[2:]]
    navigation = []
    if result.page:
        navigation.append(button("‹ Назад", seconds, result.page - 1))
    navigation.append(button("Обновить", seconds, result.page))
    if result.page + 1 < result.pages:
        navigation.append(button("Далее ›", seconds, result.page + 1))
    rows.append(navigation)
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def build(db, bot, chat: int, seconds: int, page: int = 0) -> InactivePage:
    async with asyncio.timeout(QUERY_TIMEOUT_SECONDS):
        return await chat_inactivity.list_inactive(db, chat, seconds, page, bot_id=(await bot.me()).id,
                                                  timezone_seconds=int(tz_delta().total_seconds()))


@registry.command(
    "неактивы", aliases=("кто неактив", "призраки"), private=False, section="stats",
    usage="бот неактивы [срок: 1д, 5д, 7д, 1н, 29д, 1г]", example=USAGE,
    summary="Кто не пишет в этом чате. Без срока — 1 день; д — дни, н — недели, мес — 30 дней, г — 365 дней. Только список.",
)
async def cmd_inactive(ctx: Ctx) -> None:
    try:
        seconds = parse_period(ctx.args)
    except ValueError:
        await ctx.reply(PERIOD_HINT)
        return
    try:
        result = await build(ctx.db, ctx.bot, ctx.message.chat.id, seconds)
    except Exception as error:
        logger.warning("inactive list failed chat={} error={}", ctx.message.chat.id, type(error).__name__)
        await ctx.reply(UNAVAILABLE)
        return
    await ctx.reply(render(result, seconds), reply_markup=keyboard(ctx.user_id, ctx.message.chat.id, seconds, result))


@router.callback_query(InactiveCB.filter())
async def on_inactive(call: CallbackQuery, callback_data: InactiveCB, db, bot) -> None:
    data, message = callback_data, call.message
    if call.from_user.id != data.uid:
        await call.answer("Это чужой список. Открой свой: бот неактивы.", show_alert=True)
        return
    if (message is None or not callable(getattr(message, "edit_text", None))
            or message.chat.type not in ("group", "supergroup")
            or message.chat.id != data.chat or data.chat >= 0
            or not DAY_SECONDS <= data.seconds <= MAX_DAYS * DAY_SECONDS or not 0 <= data.page <= MAX_PAGE):
        await call.answer("Эта кнопка устарела. Напиши в группе: бот неактивы.", show_alert=True)
        return
    try:
        if (await global_moderation.is_blocked(db, call.from_user.id)
                or await feature_switches.disabled(db, feature_switches.command_features("неактивы", "stats", ""), data.chat)):
            await call.answer("Сейчас эта команда недоступна.", show_alert=True)
            return
        result = await build(db, bot, data.chat, data.seconds, data.page)
    except Exception as error:
        logger.warning("inactive refresh failed chat={} error={}", data.chat, type(error).__name__)
        await call.answer(UNAVAILABLE, show_alert=True)
        return
    try:
        await message.edit_text(render(result, data.seconds), parse_mode="HTML", disable_web_page_preview=True,
                                reply_markup=keyboard(data.uid, data.chat, data.seconds, result))
        await call.answer()
    except TelegramBadRequest as error:
        if "not modified" in str(error):
            await call.answer("Список актуален.")
            return
        logger.info("inactive message no longer editable chat={}", data.chat)
        await call.answer("Сообщение уже нельзя обновить. Напиши: бот неактивы.", show_alert=True)
    except (TelegramForbiddenError, TelegramNetworkError, asyncio.TimeoutError) as error:
        logger.info("inactive delivery failed chat={} error={}", data.chat, type(error).__name__)
        await call.answer(UNAVAILABLE, show_alert=True)
