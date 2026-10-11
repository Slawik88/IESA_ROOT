"""«бот жалоба»: анонимная жалоба на нарушителя, она уходит в очередь админки (раздел «Жалобы») и по настройкам жалоб:
в админ-чат и/или в личку модераторам. Автора не видит никто, кроме персонала с доступом."""
from __future__ import annotations

import html

from loguru import logger

from bot.chat.access import is_developer
from bot.chat.admin_chat import admin_chat_of
from bot.chat.framework import Ctx, UsageError, registry
from bot.chat.style import quote
from bot.chat.targets import resolve_target
from services import reports as reports_service

USAGE = "бот жалоба причина  (ответом на сообщение нарушителя)  ·  бот жалоба, @ник причина"


def _message_link(chat_id: int, message_id: int | None) -> str:
    """Ссылка на сообщение: есть только у супергрупп (id вида -100…)."""
    raw = str(chat_id)
    return f"https://t.me/c/{raw[4:]}/{message_id}" if message_id and raw.startswith("-100") and len(raw) > 4 else ""


async def _hide_command(ctx: Ctx) -> bool:
    """Жалоба анонимна: команду автора убираем из чата. Нужно право бота удалять сообщения."""
    try:
        await ctx.message.delete()
        return True
    except Exception:
        return False


async def _answer(ctx: Ctx, text: str, chat_text: str, hidden: bool) -> None:
    """Ответ автору: в личку; если она закрыта — коротко в чат без имён; если команду не убрать — обычным ответом."""
    if hidden:
        try:
            await ctx.bot.send_message(ctx.user_id, text, parse_mode="HTML")
            return
        except Exception:
            pass
        try:
            await ctx.bot.send_message(ctx.message.chat.id, chat_text, parse_mode="HTML",
                                       message_thread_id=getattr(ctx.message, "message_thread_id", None))
        except Exception as exc:
            logger.debug(f"report answer failed: {exc}")
        return
    await ctx.reply(text)


async def _notify(ctx: Ctx, rid: int, target_label: str, reason: str, text: str, message_id: int | None,
                  hidden: bool) -> None:
    """Отчёт о жалобе без имени автора: в админ-чат и/или в личку модераторам, как настроено в «Настройках»."""
    conf = await reports_service.settings(ctx.db)
    chat = ctx.message.chat
    lines = [f"Причина: {html.escape(reason)}"]
    if text:
        lines.append(f"Сообщение: «{html.escape(text[:300])}»")
    link = _message_link(chat.id, message_id)
    if link:
        lines.append(f'<a href="{link}">К сообщению</a>')
    if not hidden:
        lines.append("⚠️ Команду автора не удалось убрать из чата: дайте боту право удалять сообщения.")
    body = f"📨 <b>Жалоба №{rid}</b> на {html.escape(target_label)}\n" + quote(lines)
    dest = await admin_chat_of(ctx.db, chat.id) if conf["to_admin_chat"] else None
    if dest:
        try:
            await ctx.bot.send_message(dest, body, parse_mode="HTML", disable_web_page_preview=True)
        except Exception as exc:   # админ-чат могли удалить — жалоба всё равно в очереди
            logger.debug(f"report {rid} admin chat notify failed: {exc}")
    where = f" · {html.escape(chat.title)}" if chat.title else ""
    for uid in await reports_service.recipients(ctx.db, chat.id, ctx.user_id, conf):
        try:
            await ctx.bot.send_message(uid, body + f"\n<i>Чат{where}</i>", parse_mode="HTML",
                                       disable_web_page_preview=True)
        except Exception as exc:   # не открывал личку с ботом
            logger.debug(f"report {rid} dm {uid} failed: {exc}")


# СТИЛЬ v1 (черновик): подтверждение автору в личку, в админ-чат и модераторам — событие и цитата без имени автора.
@registry.command("жалоба", aliases=("репорт", "report", "пожаловаться"), usage=USAGE, private=False,
                  section="moderation", summary="Анонимно пожаловаться на нарушителя: жалоба уйдёт модераторам бота.",
                  example="бот жалоба спам в чате")
async def cmd_report(ctx: Ctx) -> None:
    target, rest = await resolve_target(ctx.db, ctx.message, ctx.args)
    if target is None:
        raise UsageError(USAGE)
    reason = " ".join(rest.split())
    if not reason:
        raise UsageError(USAGE + "\nНапишите причину: что нарушено.")
    me = await ctx.bot.me()
    replied = ctx.message.reply_to_message
    quoted = replied if replied and replied.from_user and replied.from_user.id == target.user_id else None
    text = (quoted.text or quoted.caption or "") if quoted else ""
    chat_id = ctx.message.chat.id
    hidden = await _hide_command(ctx)
    if target.user_id in (ctx.user_id, me.id) or is_developer(target.user_id):
        msg = "🙃 На этого игрока жалобу подать нельзя."
        await _answer(ctx, msg, msg, hidden)
        return
    try:
        rid = await reports_service.create(ctx.db, chat_id=chat_id, reporter_id=ctx.user_id, target_id=target.user_id,
                                           reason=reason, message_id=quoted.message_id if quoted else None,
                                           message_text=text)
    except reports_service.ReportError as exc:
        msg = f"📨 {html.escape(str(exc))}"
        await _answer(ctx, msg, msg, hidden)
        return
    await _answer(ctx, f"📨 Жалоба на {html.escape(target.label())} принята, номер {rid}. Она анонимна: "
                       "автора видит только персонал с доступом. Результат придёт сюда.",
                  "📨 Жалоба принята.", hidden)
    await _notify(ctx, rid, target.label(), reason, text, quoted.message_id if quoted else None, hidden)
