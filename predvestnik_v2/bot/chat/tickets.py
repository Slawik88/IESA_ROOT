"""Обращения к администрации из лички: игрок пишет «бот обращение …», персонал отвечает кнопкой, ответ приходит игроку в личку.

Правила и проверки прав — в services/dm_tickets.py (роль та же, что открывает «Жалобы» в админке, действия пишутся в журнал).
Здесь только приём текста, карточки и кнопки. Карточка уходит каждому подходящему сотруднику: ответить или закрыть может один,
остальные при нажатии узнают, что коллега уже успел.
"""
from __future__ import annotations

import asyncio
import html

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest, TelegramForbiddenError
from aiogram.types import CallbackQuery, ForceReply, InlineKeyboardButton, InlineKeyboardMarkup, Message
from loguru import logger

from bot.chat.framework import Ctx, registry
from core import dm_tickets as rules
from services import dm_tickets as service

router = Router(name="chat_tickets")


def _btn(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=data)


def _who(ticket: dict) -> str:
    name = f"@{ticket['username']}" if ticket.get("username") else (ticket.get("name") or "игрок")
    return f"{html.escape(str(name))} (id <code>{ticket['user_id']}</code>)"


def card(ticket: dict) -> tuple[str, InlineKeyboardMarkup | None]:
    """Карточка обращения для сотрудника. У отвеченного и закрытого кнопок нет."""
    lines = [f"📩 <b>Обращение №{ticket['id']}</b>", f"От: {_who(ticket)}", f"<blockquote>{html.escape(ticket['text'])}</blockquote>"]
    if ticket["status"] != "new":
        lines.append(f"<i>{rules.STATUS_TITLES[ticket['status']]}</i>")
        if ticket.get("answer"):
            lines.append(f"Ответ: {html.escape(ticket['answer'])}")
        return "\n".join(lines), None
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=[
        [_btn("✍️ Ответить", f"tk:a:{ticket['id']}"), _btn("🚫 Закрыть без ответа", f"tk:c:{ticket['id']}")]])


# ── игрок ───────────────────────────────────────────────────────────────────

@registry.command("обращение", aliases=("обратиться", "вопрос админам", "написать админам"), section="basic",
                  summary="Написать администрации бота: вопрос или проблема. Ответ придёт сюда, в личку.",
                  usage="бот обращение текст", example="бот обращение не пришла награда за задание")
async def cmd_ticket(ctx: Ctx) -> None:
    if ctx.message.chat.type != "private":
        await ctx.reply("📩 Обращения принимаю в личке с ботом: открой чат со мной и напиши «бот обращение» и свой вопрос.")
        return
    if not ctx.args.strip():
        await ctx.reply("📩 <b>Обращение к администрации</b>\n"
                        "Напиши вопрос или проблему после слова «обращение», например:\n"
                        "<code>бот обращение не пришла награда за задание</code>\n\n"
                        "Ответ придёт сюда, в этот чат. Не больше 3 обращений в сутки.")
        return
    try:
        ticket = await service.create(ctx.db, user_id=ctx.user_id, text=ctx.args)
    except service.TicketError as exc:
        await ctx.reply(f"📩 {html.escape(str(exc))}")
        return
    delivered, queued = await _deliver_card(ctx.bot, ctx.db, ticket["id"], exclude=ctx.user_id)
    if delivered:
        await ctx.reply(f"📨 Обращение №{ticket['id']} принято. Ответ придёт сюда, в личку с ботом.")
    elif queued:   # у всей администрации за этот час уже много карточек: обращение ждёт в их списке «бот обращения»
        await ctx.reply(f"📨 Обращение №{ticket['id']} принято. Сейчас вопросов много, поэтому оно в очереди. Ответ придёт сюда, в личку с ботом.")
    else:   # ни один сотрудник не открывал личку с ботом: обращение сохранено и ждёт в списке «бот обращения»
        await ctx.reply(f"📨 Обращение №{ticket['id']} принято, но сейчас никого из администрации нет на связи. Оно сохранено: ответ придёт сюда, когда они появятся.")


async def _deliver_card(bot, db, ticket_id: int, *, exclude: int) -> tuple[int, int]:
    """Показать обращение сотрудникам. Возвращает (скольким дошло, скольким не прислано из-за предела карточек в час).
    Недоступная личка сотрудника — не ошибка; такая попытка не занимает место в его пределе."""
    ticket = await service.get(db, ticket_id)
    if ticket is None:
        return 0, 0
    text, kb = card(ticket)
    delivered = queued = 0
    for staff_id in await service.recipients(db, exclude=exclude):
        try:
            slot = await service.reserve_card(db, ticket_id, staff_id)
        except Exception as exc:   # учёт карточек недоступен (например, таблица не создалась): карточку всё равно отправляем
            logger.warning(f"ticket {ticket_id}: card limit skipped for {staff_id}: {exc!r}")
            slot = "send"
        if slot == "limited":
            queued += 1
            continue
        body = text + ("\n\n<i>Это восьмая карточка за последний час. Следующие придут, когда освободится место, "
                       "а пока они ждут в «бот обращения».</i>" if slot == "last" else "")
        try:
            await bot.send_message(staff_id, body, parse_mode="HTML", reply_markup=kb)
            delivered += 1
        except TelegramAPIError as exc:
            await _release(db, ticket_id, staff_id)
            if not isinstance(exc, (TelegramForbiddenError, TelegramBadRequest)):   # сеть или 429: сотрудник на связи, обращение ждёт в списке
                queued += 1
            logger.debug(f"ticket {ticket_id}: card to {staff_id} not delivered: {exc}")
    if not delivered:
        logger.warning(f"ticket {ticket_id}: nobody got a card (limited or failed for {queued})")
    return delivered, queued


async def _release(db, ticket_id: int, staff_id: int) -> None:
    try:
        await service.release_card(db, ticket_id, staff_id)
    except Exception as exc:
        logger.warning(f"ticket {ticket_id}: card slot of {staff_id} not released: {exc!r}")


# ── персонал ────────────────────────────────────────────────────────────────

@registry.command("обращения", section="basic", summary="Для персонала: обращения игроков, которые ждут ответа. Старые первыми, по 10 на странице.",
                  usage="бот обращения [страница]", example="бот обращения 2")
async def cmd_open_tickets(ctx: Ctx) -> None:
    if ctx.message.chat.type != "private":
        await ctx.reply("📩 Обращения показываю в личке с ботом.")
        return
    if not await service.is_staff(ctx.db, ctx.user_id):
        await ctx.reply("📩 Этот список — только для персонала бота. Чтобы написать администрации: «бот обращение» и вопрос.")
        return
    first = ctx.args.strip().split(maxsplit=1)[0] if ctx.args.strip() else "1"
    await _send_page(ctx.message, ctx.db, int(first) if first.isascii() and first.isdigit() and len(first) <= 6 else 1)


async def _send_page(target: Message, db, page: int) -> None:
    """Одна страница открытых обращений: заголовок, карточки и, если страниц больше одной, кнопки листания."""
    found = await service.open_page(db, page)
    items, total, page, pages = found["items"], found["total"], found["page"], found["pages"]
    if not items:
        await target.answer("📩 Все обращения разобраны.")
        return
    await target.answer(f"📩 Ждут ответа: {total}" + (f". Страница {page} из {pages}, старые первыми" if pages > 1 else "") + ".")
    for ticket in items:
        text, kb = card(ticket)
        await target.answer(text, parse_mode="HTML", reply_markup=kb)
    if pages > 1:
        nav = [_btn(f"‹ Страница {page - 1}", f"tk:p:{page - 1}")] if page > 1 else []
        if page < pages:
            nav.append(_btn(f"Страница {page + 1} ›", f"tk:p:{page + 1}"))
        await target.answer(f"📩 Это страница {page} из {pages}. Листай кнопками или напиши «бот обращения {page % pages + 1}».",
                            reply_markup=InlineKeyboardMarkup(inline_keyboard=[nav]))


@router.callback_query(F.data.startswith("tk:"))
async def on_ticket_button(call: CallbackQuery, db) -> None:
    msg = call.message
    parts = (call.data or "").split(":")
    if msg is not None and not isinstance(msg, Message):   # карточка слишком старая или удалена: Telegram её больше не отдаёт
        await call.answer("Эта карточка устарела. Напиши «бот обращения»: покажу свежий список.", show_alert=True)
        return
    if msg is None or msg.chat.type != "private" or msg.chat.id != call.from_user.id or len(parts) != 3 or not parts[2].isdigit():
        await call.answer("Это работает только в личке с ботом.", show_alert=True)
        return
    if not await service.is_staff(db, call.from_user.id):
        await call.answer("Обращения доступны только персоналу бота.", show_alert=True)
        return
    if parts[1] == "p":   # листание списка: старые кнопки убираем, новая страница приходит следом
        try:
            await msg.edit_reply_markup(reply_markup=None)
        except TelegramAPIError as exc:
            logger.debug(f"tickets page buttons not removed: {exc}")
        await call.answer()
        await _send_page(msg, db, int(parts[2]))
        return
    ticket_id = int(parts[2])
    ticket = await service.get(db, ticket_id)
    if ticket is None:
        await call.answer("Такого обращения нет.", show_alert=True)
        return
    if ticket["status"] != "new":
        await _show(msg, ticket)
        await call.answer("Обращение уже закрыто: коллега успел раньше.", show_alert=True)
        return
    if parts[1] == "a":
        short = html.escape(ticket["text"][:200])
        await msg.answer(f"{rules.ANSWER_MARK}{ticket_id}\nНапиши ответ одним сообщением: я перешлю его игроку.\n<blockquote>{short}</blockquote>",
                         parse_mode="HTML", reply_markup=ForceReply(selective=True, input_field_placeholder="Ответ игроку"))
        await call.answer()
    elif parts[1] == "c":
        try:
            ticket = await service.close(db, ticket_id=ticket_id, staff_id=call.from_user.id)
        except service.TicketError as exc:
            await call.answer(str(exc), show_alert=True)
            return
        await _show(msg, ticket)
        await call.answer("Закрыто.")
        try:   # игроку, который ждёт ответа, не оставляем тишину
            await call.bot.send_message(ticket["user_id"], f"📩 Обращение №{ticket['id']} закрыто. Если вопрос остался, напиши «бот обращение» ещё раз.")
        except TelegramAPIError as exc:
            logger.info(f"ticket {ticket['id']}: close notice not delivered: {exc}")
    else:
        await call.answer("Неизвестное действие.", show_alert=True)


async def _show(msg: Message, ticket: dict) -> None:
    text, kb = card(ticket)
    try:
        await msg.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc):
            raise


def is_answer_prompt(bot, message: Message) -> bool:
    reply = message.reply_to_message
    return bool(reply and reply.from_user and message.from_user and not message.from_user.is_bot and reply.from_user.id == bot.id
                and (reply.text or "").startswith(rules.ANSWER_MARK) and message.text is not None)


async def on_staff_reply(db, bot, message: Message) -> bool:
    """Сотрудник ответил на подсказку «Ответить»: ответ уходит игроку в личку. True — сообщение разобрано здесь."""
    if message.chat.type != "private" or message.from_user is None or message.reply_to_message is None or not is_answer_prompt(bot, message):
        return False
    head = (message.reply_to_message.text or "")[len(rules.ANSWER_MARK):].split("\n", 1)[0].strip()
    if not head.isdigit():
        return False
    try:
        ticket = await service.answer(db, ticket_id=int(head), staff_id=message.from_user.id, text=message.text)
    except service.TicketError as exc:
        await message.reply(f"📩 {html.escape(str(exc))}")
        return True
    answer = (f"💬 <b>Ответ администрации</b> на обращение №{ticket['id']}:\n"
              f"{html.escape(ticket['answer'])}\n\n<i>Остались вопросы — напиши «бот обращение» ещё раз.</i>")
    for attempt in (1, 2):
        try:
            await bot.send_message(ticket["user_id"], answer, parse_mode="HTML")
            break
        except TelegramForbiddenError:   # игрок закрыл личку с ботом: ответ записан, но он его не увидит
            await message.reply("⚠️ Ответ записан, но игрок закрыл личку с ботом — он его не увидит.")
            return True
        except TelegramAPIError as exc:   # сеть, 429, 5xx: пробуем ещё раз, потом честно говорим сотруднику
            logger.info(f"ticket {ticket['id']}: answer attempt {attempt} failed: {exc}")
            if attempt == 1:
                await asyncio.sleep(1.5)
                continue
            await message.reply("⚠️ Ответ записан, но Telegram сейчас не принял сообщение. Напиши игроку сам: вот текст ответа:\n"
                                f"<blockquote>{html.escape(ticket['answer'])}</blockquote>", parse_mode="HTML")
            return True
    await message.reply(f"✅ Ответ на обращение №{ticket['id']} отправлен игроку.")
    return True
