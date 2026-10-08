"""Админ-чат: куда бот шлёт служебные сообщения, и пинги админов под ними."""
from __future__ import annotations

import html
import secrets

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup

from bot.chat import ranks
from bot.chat.framework import Ctx, registry


async def admin_chat_of(db, chat_id: int) -> int | None:
    async with db.execute("SELECT admin_chat_id FROM chat_links WHERE main_chat_id = ?", (chat_id,)) as cur:
        row = await cur.fetchone()
    return int(row[0]) if row and row[0] else None


async def ping_line(db, chat_id: int) -> str:
    """Упоминания всех, у кого ранг не ниже порога «pinged» (владелец настраивает)."""
    need = (await ranks.rights_map(db, chat_id))["pinged"]
    owner = await ranks.get_owner(db, chat_id)
    async with db.execute(
        "SELECT s.user_tg_id, u.user_tg_username, s.chat_rank "
        "FROM user_chat_stats s LEFT JOIN users u ON u.user_tg_id = s.user_tg_id "
        "WHERE s.chat_tg_id = ? AND s.is_left = FALSE",
        (chat_id,),
    ) as cur:
        rows = await cur.fetchall()
    people = []
    for uid, uname, cr in rows:
        rank = ranks.OWNER if uid == owner else int(cr or 0)
        if rank >= need:
            people.append((rank, int(uid), uname))
    if owner and all(p[1] != owner for p in people):
        people.append((ranks.OWNER, owner, None))
    people.sort(reverse=True)
    links = [
        f'<a href="tg://user?id={uid}">{html.escape(uname or "админ")}</a>'
        for _, uid, uname in people[:25]
    ]
    return ("🔔 " + " ".join(links)) if links else ""


async def send_admin(bot: Bot, db, chat_id: int, text: str, *, markup: InlineKeyboardMarkup | None = None,
                     ping: bool = True):
    """Отправить в админ-чат, а если его нет — в сам чат."""
    dest = await admin_chat_of(db, chat_id) or chat_id
    if ping:
        line = await ping_line(db, chat_id)
        if line:
            text = f"{text}\n\n{line}"
    return await bot.send_message(dest, text, parse_mode="HTML", reply_markup=markup,
                                  disable_web_page_preview=True)


# ── Привязка: код в основном чате -> ввод кода в админ-чате ────────────────

@registry.command(
    "привязать админ чат", aliases=("админ чат", "привязать админ-чат", "админ-чат"), usage="бот привязать админ чат",
    private=False, section="settings",
    summary="Получить код, чтобы назначить отдельный чат для служебных сообщений бота.",
)
async def cmd_bind_start(ctx: Ctx) -> None:
    chat = ctx.message.chat
    if ctx.args.strip():
        await _bind_finish(ctx, ctx.args.strip())
        return
    await ranks.sync_owner(ctx.db, ctx.bot, chat.id)
    if not await ranks.can(ctx.db, chat.id, ctx.user_id, "admin_chat"):
        await ctx.reply("⛔ У вашего ранга нет права привязывать админ-чат.")
        return
    token = secrets.token_hex(4)
    await ctx.db.execute("DELETE FROM chat_bind_tokens WHERE main_chat_id = ?", (chat.id,))
    await ctx.db.execute(
        "INSERT INTO chat_bind_tokens (token, main_chat_id, main_chat_title) VALUES (?, ?, ?)",
        (token, chat.id, chat.title or ""),
    )
    await ranks._commit(ctx.db)
    await ctx.reply(
        "🔗 <b>Привязка админ-чата</b>\n\n"
        "Добавьте бота в админ-чат и напишите там в течение 10 минут:\n"
        f"<code>бот админ чат {token}</code>"
    )


async def _bind_finish(ctx: Ctx, token: str) -> None:
    admin_chat = ctx.message.chat.id
    async with ctx.db.execute(
        "SELECT main_chat_id, main_chat_title FROM chat_bind_tokens "
        "WHERE token = ? AND created_at > NOW() - INTERVAL '10 minutes'",
        (token.lower(),),
    ) as cur:
        row = await cur.fetchone()
    if not row:
        await ctx.reply("⛔ Код не найден или устарел. Получите новый в основном чате: «бот привязать админ чат».")
        return
    main_chat = int(row[0])
    if main_chat == admin_chat:
        await ctx.reply("⛔ Код нужно ввести в другом чате — том, который станет админским.")
        return
    if not await ranks.can(ctx.db, main_chat, ctx.user_id, "admin_chat"):
        await ctx.reply("⛔ В основном чате у вас нет права привязывать админ-чат.")
        return
    await ctx.db.execute("DELETE FROM chat_links WHERE admin_chat_id = ? AND main_chat_id <> ?", (admin_chat, main_chat))
    await ctx.db.execute(
        "INSERT INTO chat_links (main_chat_id, admin_chat_id) VALUES (?, ?) "
        "ON CONFLICT (main_chat_id) DO UPDATE SET admin_chat_id = EXCLUDED.admin_chat_id, added_at = NOW()",
        (main_chat, admin_chat),
    )
    await ctx.db.execute("DELETE FROM chat_bind_tokens WHERE token = ?", (token.lower(),))
    await ranks._commit(ctx.db)
    await ctx.reply(f"✅ Этот чат стал админ-чатом для «{html.escape(row[1] or str(main_chat))}».")


@registry.command(
    "отвязать админ чат", aliases=("отвязать админ-чат",), usage="бот отвязать админ чат", private=False, section="settings",
    summary="Служебные сообщения снова пойдут в сам чат.",
)
async def cmd_unbind(ctx: Ctx) -> None:
    chat_id = ctx.message.chat.id
    if not await ranks.can(ctx.db, chat_id, ctx.user_id, "admin_chat"):
        await ctx.reply("⛔ У вашего ранга нет права менять админ-чат.")
        return
    await ctx.db.execute("DELETE FROM chat_links WHERE main_chat_id = ?", (chat_id,))
    await ranks._commit(ctx.db)
    await ctx.reply("✅ Админ-чат отвязан.")
