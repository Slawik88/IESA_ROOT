"""«бот жалоба»: игрок жалуется на нарушителя, жалоба уходит в очередь админки (раздел «Жалобы»)."""
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


# СТИЛЬ v1 (черновик): подтверждение одной строкой, в админ-чат — событие и цитата с причиной и сообщением.
@registry.command("жалоба", aliases=("репорт", "report", "пожаловаться"), usage=USAGE, private=False,
                  section="moderation", summary="Пожаловаться на нарушителя: жалоба уйдёт модераторам бота.",
                  example="бот жалоба спам в чате")
async def cmd_report(ctx: Ctx) -> None:
    target, rest = await resolve_target(ctx.db, ctx.message, ctx.args)
    if target is None:
        raise UsageError(USAGE)
    reason = " ".join(rest.split())
    if not reason:
        raise UsageError(USAGE + "\nНапишите причину: что нарушено.")
    me = await ctx.bot.me()
    if target.user_id in (ctx.user_id, me.id) or is_developer(target.user_id):
        await ctx.reply("🙃 На этого игрока жалобу подать нельзя.")
        return
    replied = ctx.message.reply_to_message
    quoted = replied if replied and replied.from_user and replied.from_user.id == target.user_id else None
    text = (quoted.text or quoted.caption or "") if quoted else ""
    chat_id = ctx.message.chat.id
    try:
        rid = await reports_service.create(ctx.db, chat_id=chat_id, reporter_id=ctx.user_id, target_id=target.user_id,
                                           reason=reason, message_id=quoted.message_id if quoted else None,
                                           message_text=text)
    except reports_service.ReportError as exc:
        await ctx.reply(f"📨 {html.escape(str(exc))}")
        return
    await ctx.reply(f"📨 Жалоба на {html.escape(target.label())} принята, номер {rid}. Модераторы бота её рассмотрят.")
    dest = await admin_chat_of(ctx.db, chat_id)
    if dest:
        u = ctx.message.from_user
        lines = [f"Причина: {html.escape(reason)}"]
        if text:
            lines.append(f"Сообщение: «{html.escape(text[:300])}»")
        try:
            await ctx.bot.send_message(
                dest, f"📨 <b>Жалоба №{rid}</b> на {html.escape(target.label())} от {html.escape(u.full_name or str(u.id))}\n"
                + quote(lines), parse_mode="HTML", disable_web_page_preview=True)
        except Exception as exc:   # админ-чат могли удалить — жалоба всё равно в очереди
            logger.debug(f"report {rid} admin chat notify failed: {exc}")
