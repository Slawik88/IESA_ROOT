"""Чистка чата: «бот чистка, норма [дд.мм.гггг-дд.мм.гггг]».

Чат закрывается, сообщения без права удаляются (раз в 20 удалений — «Тсссс»),
в админ-чат уходит досье на каждого, кто не набрал норму, с кнопками решения.
После «бот чистка стоп» чат открывается и получает итог.
Таблицы: purge_sessions, purge_targets (+required_norm), chat_settings.is_purging.
"""
from __future__ import annotations

import asyncio
import html
import math
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from aiogram import Bot, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters.callback_data import CallbackData
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from loguru import logger

from bot.chat import ranks
from bot.chat.access import is_developer
from bot.chat.admin_chat import admin_chat_of, ping_line
from bot.chat.framework import Ctx, UsageError, registry
from bot.chat.moderation import FOREVER, TG_FAIL, active_warns, commit, do_ban, do_kick, do_mute, log
from bot.chat.tracking import local_now, tz_delta
from infrastructure.database import get_pool
from infrastructure.pg_adapter import PGAdapter

router = Router(name="chat_purge")
USAGE = "бот чистка, норма [01.12.2026-07.12.2026]"
_DATE = r"(\d{1,2})\.(\d{1,2})(?:\.(\d{2,4}))?"
_RANGE = re.compile(rf"{_DATE}\s*[-–—]\s*{_DATE}")


@dataclass(frozen=True)
class Plan:
    norm: int
    start: date
    end: date      # включительно

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1


def _mkdate(d: str, m: str, y: str | None, today: date) -> date:
    year = int(y) if y else today.year
    if year < 100:
        year += 2000
    return date(year, int(m), int(d))


def fmt(d: date) -> str:
    return d.strftime("%d.%m.%Y")


def plan_purge(args: str, today: date, usual_norm: int | None) -> Plan | str:
    """План чистки или текст-подсказка (с готовой командой), если запускать рано."""
    text = args.strip()
    rng = _RANGE.search(text)
    norm_part = (text[:rng.start()] + " " + text[rng.end():]) if rng else text
    nums = re.findall(r"\d+", norm_part)
    norm = int(nums[0]) if nums else usual_norm
    if rng:
        try:
            a = _mkdate(rng.group(1), rng.group(2), rng.group(3), today)
            b = _mkdate(rng.group(4), rng.group(5), rng.group(6), today)
        except ValueError:
            raise UsageError(USAGE + "\nНе понял даты. Пример: 01.12.2026-07.12.2026")
        if b < a:
            a, b = b, a
        if b > today:
            raise UsageError(USAGE + "\nКонец периода не может быть в будущем.")
        if norm is None:
            raise UsageError(USAGE + "\nУкажите норму сообщений, например: бот чистка, 100")
        return Plan(norm, a, b)
    if norm is None:
        raise UsageError(USAGE + "\nУкажите норму сообщений, например: бот чистка, 100")
    if today.weekday() == 6:   # воскресенье: обычная неделя пн–вс
        return Plan(norm, today - timedelta(days=6), today)
    a, b = today - timedelta(days=7), today - timedelta(days=1)
    return (
        "📅 Сегодня не воскресенье, поэтому неделя считается по-другому.\n"
        "Чтобы получилась ровно неделя, запустите так:\n"
        f"<code>бот чистка, {norm} {fmt(a)}-{fmt(b)}</code>"
    )


def required_norm(norm: int, period_days: int, blocked_days: float) -> int:
    """Норма с поправкой: дни в муте или до входа в чат не считаются."""
    free = max(0.0, period_days - blocked_days)
    return max(0, math.ceil(norm * free / period_days)) if period_days else norm


async def usual_norm(db, chat_id: int) -> int | None:
    async with db.execute(
        "SELECT norm FROM purge_sessions WHERE chat_id = ? ORDER BY id DESC LIMIT 5", (chat_id,)
    ) as cur:
        rows = [int(r[0]) for r in await cur.fetchall()]
    return max(set(rows), key=rows.count) if rows else None


async def active_session(db, chat_id: int):
    async with db.execute(
        "SELECT id, norm, date_from, date_to, dest_chat_id, initiator_id FROM purge_sessions "
        "WHERE chat_id = ? AND status = 'active' ORDER BY id DESC LIMIT 1", (chat_id,)
    ) as cur:
        return await cur.fetchone()


# ── Подсчёт нарушителей ───────────────────────────────────────────────────

@dataclass
class Violator:
    user_id: int
    username: str | None
    count: int
    required: int
    total: int
    days_in_chat: int
    warns: int
    note: str


async def find_violators(db, chat_id: int, plan: Plan) -> list[Violator]:
    rights = await ranks.rights_map(db, chat_id)
    owner = await ranks.get_owner(db, chat_id)
    # Период задан в местных датах; в БД время UTC (naive) — переводим границы.
    shift = tz_delta()
    start_dt = datetime.combine(plan.start, datetime.min.time()) - shift
    end_dt = datetime.combine(plan.end + timedelta(days=1), datetime.min.time()) - shift
    async with db.execute(
        "SELECT s.user_tg_id, u.user_tg_username, COALESCE(s.chat_rank, 0), s.is_immune, "
        "(s.immune_until IS NOT NULL AND s.immune_until > NOW()), "
        "s.membership_since, s.muted_until, s.user_messages_count_all_time, "
        "COALESCE((SELECT SUM(d.message_count) FROM daily_user_stats d WHERE d.chat_id = s.chat_tg_id "
        "  AND d.user_id = s.user_tg_id AND d.date BETWEEN ? AND ?), 0), "
        "(SELECT MAX(l.created_at) FROM moderation_logs l WHERE l.chat_id = s.chat_tg_id "
        "  AND l.user_id = s.user_tg_id AND l.action = 'mute') "
        "FROM user_chat_stats s LEFT JOIN users u ON u.user_tg_id = s.user_tg_id "
        "WHERE s.chat_tg_id = ? AND s.is_left = FALSE AND COALESCE(s.is_bot, FALSE) = FALSE",
        (plan.start.isoformat(), plan.end.isoformat(), chat_id),
    ) as cur:
        rows = await cur.fetchall()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    out: list[Violator] = []
    for uid, uname, rank, immune, shielded, since, muted_until, total, count, mute_at in rows:
        uid = int(uid)
        if is_developer(uid) or uid == owner or immune or shielded:
            continue
        if int(rank) >= rights["purge_write"]:
            continue   # состав чата, который пишет и во время чистки
        blocked, notes = 0.0, []
        since_naive = since.astimezone(timezone.utc).replace(tzinfo=None) if since and since.tzinfo else since
        if since_naive and since_naive > start_dt:
            blocked += (min(since_naive, end_dt) - start_dt).total_seconds() / 86400
            notes.append(f"в чате с {(since_naive + shift).strftime('%d.%m')}")
        if muted_until and mute_at:
            a, b = max(mute_at, start_dt), min(muted_until, end_dt)
            if b > a:
                blocked += (b - a).total_seconds() / 86400
                notes.append(f"в муте {(b - a).total_seconds() / 86400:.1f} дн")
        need = required_norm(plan.norm, plan.days, blocked)
        if int(count) >= need:
            continue
        days_in = (now - since_naive).days if since_naive else 0
        out.append(Violator(uid, uname, int(count), need, int(total or 0), days_in,
                            len(await active_warns(db, chat_id, uid)), ", ".join(notes)))
    out.sort(key=lambda v: (v.count - v.required, v.count))
    return out


# ── Досье и кнопки ────────────────────────────────────────────────────────

class PurgeCB(CallbackData, prefix="pg"):
    act: str      # ban | kick | forgive | warn | mute
    s: int
    u: int


VERDICTS = {
    "ban": "⛔ Бан", "kick": "👢 Кик", "forgive": "🕊 Прощён", "warn": "⚠️ Варн", "mute": "🔇 Мут 1ч",
}


def dossier_text(v: Violator, chat_title: str) -> str:
    name = f"@{v.username}" if v.username else f"id{v.user_id}"
    lines = [
        f"📁 <b>Досье</b> · {html.escape(chat_title)}",
        f'<a href="tg://user?id={v.user_id}">{html.escape(name)}</a>',
        f"Сообщений за период: <b>{v.count}</b> из {v.required}",
        f"Всего сообщений: {v.total} · в чате {v.days_in_chat} дн",
        f"Действующих варнов: {v.warns}",
    ]
    if v.note:
        lines.append(f"Учтено: {html.escape(v.note)}")
    return "\n".join(lines)


def dossier_kb(session_id: int, user_id: int) -> InlineKeyboardMarkup:
    b = lambda act: InlineKeyboardButton(text=VERDICTS[act], callback_data=PurgeCB(act=act, s=session_id, u=user_id).pack())
    return InlineKeyboardMarkup(inline_keyboard=[[b("ban"), b("kick")], [b("warn"), b("mute"), b("forgive")]])


async def _send_dossiers(bot: Bot, session_id: int, chat_id: int, chat_title: str, dest: int,
                         violators: list[Violator]) -> None:
    """Фоном: по одному сообщению на нарушителя (не блокирует команду)."""
    for v in violators:
        try:
            await bot.send_message(dest, dossier_text(v, chat_title), parse_mode="HTML",
                                   reply_markup=dossier_kb(session_id, v.user_id))
            async with get_pool().acquire() as conn:
                db = PGAdapter(conn)
                await db.execute("UPDATE purge_targets SET dossier_sent = TRUE WHERE session_id = ? AND user_id = ?",
                                 (session_id, v.user_id))
                await commit(db)
        except Exception as exc:
            logger.warning(f"purge dossier {session_id}/{v.user_id} failed: {exc}")
        await asyncio.sleep(0.4)


# ── Команды ───────────────────────────────────────────────────────────────

@registry.command(
    "чистка", usage=USAGE, private=False, section="purge", example="бот чистка, 100 01.12.2026-07.12.2026",
    summary="Начать чистку: чат закрывается, админам приходят досье на тех, кто не набрал норму.",
)
async def cmd_purge(ctx: Ctx) -> None:
    sub = ctx.args.strip().lower()
    if sub in ("стоп", "завершить", "конец", "stop"):
        await finish(ctx)
        return
    if sub in ("статус", "status"):
        await status(ctx)
        return
    chat = ctx.message.chat
    await ranks.sync_owner(ctx.db, ctx.bot, chat.id)
    if not await ranks.can(ctx.db, chat.id, ctx.user_id, "purge"):
        await ctx.reply("⛔ У вашего ранга нет права проводить чистку.")
        return
    if await active_session(ctx.db, chat.id):
        await ctx.reply("🧹 Чистка уже идёт. Итог и открытие чата: <code>бот чистка стоп</code>")
        return
    plan = plan_purge(ctx.args, local_now().date(), await usual_norm(ctx.db, chat.id))
    if isinstance(plan, str):
        await ctx.reply(plan)
        return
    violators = await find_violators(ctx.db, chat.id, plan)
    dest = await admin_chat_of(ctx.db, chat.id) or chat.id
    async with ctx.db.execute(
        "INSERT INTO purge_sessions (chat_id, initiator_id, norm, date_from, date_to, dest_chat_id) "
        "VALUES (?, ?, ?, ?, ?, ?) RETURNING id",
        (chat.id, ctx.user_id, plan.norm, plan.start.isoformat(), plan.end.isoformat(), dest),
    ) as cur:
        session_id = int((await cur.fetchone())[0])
    for v in violators:
        await ctx.db.execute(
            "INSERT INTO purge_targets (session_id, user_id, username, msg_count, days_in_chat, warns, required_norm) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (session_id, v.user_id, v.username, v.count, v.days_in_chat, v.warns, v.required))
    await ctx.db.execute(
        "INSERT INTO chat_settings (chat_id, is_purging) VALUES (?, TRUE) "
        "ON CONFLICT (chat_id) DO UPDATE SET is_purging = TRUE", (chat.id,))
    await log(ctx.db, chat.id, 0, ctx.user_id, "purge_start", f"норма {plan.norm}")
    await commit(ctx.db)
    _hush[chat.id] = 0
    await ctx.reply(
        "🧹 <b>Чистка началась</b>\n"
        f"Период: {fmt(plan.start)} – {fmt(plan.end)} · норма {plan.norm}\n"
        f"Не набрали норму: <b>{len(violators)}</b>\n\n"
        "Чат закрыт до конца чистки."
    )
    if dest != chat.id or violators:
        head = (f"🧹 <b>Чистка в «{html.escape(chat.title or '')}»</b>\n"
                f"Нарушителей: {len(violators)}. Досье идут ниже, по одному на игрока.")
        line = await ping_line(ctx.db, chat.id)
        await ctx.bot.send_message(dest, head + (f"\n\n{line}" if line else ""), parse_mode="HTML")
    asyncio.create_task(_send_dossiers(ctx.bot, session_id, chat.id, chat.title or "", dest, violators))


async def status(ctx: Ctx) -> None:
    s = await active_session(ctx.db, ctx.message.chat.id)
    if not s:
        await ctx.reply("Чистка сейчас не идёт.")
        return
    counts = await verdict_counts(ctx.db, int(s[0]))
    await ctx.reply(f"🧹 Идёт чистка · норма {s[1]} · {s[2]} – {s[3]}\n" + summary_lines(counts))


async def verdict_counts(db, session_id: int) -> dict[str, int]:
    async with db.execute(
        "SELECT COALESCE(verdict, 'none'), COUNT(*) FROM purge_targets WHERE session_id = ? GROUP BY 1",
        (session_id,)) as cur:
        return {r[0]: int(r[1]) for r in await cur.fetchall()}


def summary_lines(c: dict[str, int]) -> str:
    total = sum(c.values())
    parts = [f"Не набрали норму: {total}"]
    for key, label in (("ban", "⛔ Забанено"), ("kick", "👢 Кикнуто"), ("warn", "⚠️ Выдано варнов"),
                       ("mute", "🔇 Замучено"), ("forgive", "🕊 Прощено"), ("none", "⏳ Без решения")):
        if c.get(key):
            parts.append(f"{label}: {c[key]}")
    return "\n".join(parts)


async def finish(ctx: Ctx) -> None:
    chat_id = ctx.message.chat.id
    if not await ranks.can(ctx.db, chat_id, ctx.user_id, "purge"):
        await ctx.reply("⛔ У вашего ранга нет права завершать чистку.")
        return
    s = await active_session(ctx.db, chat_id)
    if not s:
        await ctx.reply("Чистка сейчас не идёт.")
        return
    counts = await verdict_counts(ctx.db, int(s[0]))
    await ctx.db.execute("UPDATE purge_sessions SET status = 'finished', finished_at = NOW() WHERE id = ?", (s[0],))
    await ctx.db.execute("UPDATE chat_settings SET is_purging = FALSE WHERE chat_id = ?", (chat_id,))
    await log(ctx.db, chat_id, 0, ctx.user_id, "purge_finish")
    await commit(ctx.db)
    _hush.pop(chat_id, None)
    await ctx.message.answer("✅ <b>Чистка завершена, чат открыт</b>\n\n" + summary_lines(counts), parse_mode="HTML")


# ── Тишина во время чистки ────────────────────────────────────────────────

_hush: dict[int, int] = {}


async def purge_gate(db, bot: Bot, message: Message) -> bool:
    """Во время чистки удалить сообщение того, кому писать нельзя. True — удалено."""
    if message.chat.type not in ("group", "supergroup") or not message.from_user or message.from_user.is_bot:
        return False
    async with db.execute("SELECT is_purging FROM chat_settings WHERE chat_id = ?", (message.chat.id,)) as cur:
        row = await cur.fetchone()
    if not row or not row[0]:
        return False
    if await ranks.can(db, message.chat.id, message.from_user.id, "purge_write"):
        return False
    try:
        await message.delete()
    except Exception:
        return False
    n = _hush.get(message.chat.id, 0) + 1
    _hush[message.chat.id] = n
    if n % 20 == 0:
        try:
            await bot.send_message(message.chat.id, "🤫 Тсссс, идёт чистка. Чат откроется после её окончания.")
        except Exception:
            pass
    return True


# ── Решения по досье ──────────────────────────────────────────────────────

@router.callback_query(PurgeCB.filter())
async def on_verdict(call: CallbackQuery, callback_data: PurgeCB, bot: Bot, db) -> None:
    cb, actor = callback_data, call.from_user.id
    async with db.execute("SELECT chat_id, status FROM purge_sessions WHERE id = ?", (cb.s,)) as cur:
        row = await cur.fetchone()
    if not row or row[1] != "active":
        await call.answer("Эта чистка уже завершена.", show_alert=True)
        return
    chat_id = int(row[0])
    if not await ranks.can(db, chat_id, actor, "purge"):
        await call.answer("У вашего ранга нет права решать по чистке.", show_alert=True)
        return
    if is_developer(cb.u) and cb.act != "forgive":
        await call.answer("К разработчику бота санкции не применяются.", show_alert=True)
        return
    try:
        if cb.act == "ban":
            await do_ban(bot, db, chat_id, cb.u, actor, FOREVER, "чистка")
        elif cb.act == "kick":
            await do_kick(bot, db, chat_id, cb.u, actor, "чистка")
        elif cb.act == "mute":
            await do_mute(bot, db, chat_id, cb.u, actor, timedelta(hours=1), "чистка")
        elif cb.act == "warn":
            await db.execute("INSERT INTO user_warnings (chat_id, user_id, admin_id, reason) VALUES (?, ?, ?, ?)",
                             (chat_id, cb.u, actor, "чистка: не набрана норма"))
            await log(db, chat_id, cb.u, actor, "warn", "чистка")
    except (TelegramBadRequest, TelegramForbiddenError):
        await call.answer(TG_FAIL, show_alert=True)
        return
    await db.execute(
        "UPDATE purge_targets SET verdict = ?, verdict_by = ?, verdict_at = NOW() WHERE session_id = ? AND user_id = ?",
        (cb.act, actor, cb.s, cb.u))
    await commit(db)
    try:
        await call.message.edit_text(
            f"{call.message.html_text}\n\n<b>{VERDICTS[cb.act]}</b> · {html.escape(call.from_user.full_name)}",
            parse_mode="HTML")
    except Exception:
        pass
    await call.answer("Готово")


