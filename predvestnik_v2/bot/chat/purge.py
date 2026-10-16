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
from dataclasses import asdict
from uuid import uuid4
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
from bot.chat.moderation import (FOREVER, TG_FAIL, active_warns, commit, do_ban, do_kick, do_mute, do_warn, log,
                                 rank_block, warn_limit_alert)
from bot.chat.tracking import PRESENCE_SQL, local_now, stay_start, tz_delta
from bot.chat.style import quote
from infrastructure.database import get_pool
from infrastructure.pg_adapter import PGAdapter
from services import chat_bots, member_tags
from services import purge as purge_flow

router = Router(name="chat_purge")
USAGE = "бот чистка, норма [01.12.2026-07.12.2026]"
MAX_NORM = 100000   # норма в сообщениях; больше не помещалась бы в счётчики
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
    if not rng and re.search(r"\d{1,2}\.\d{1,2}(?:\.\d{2,4})?", text):   # «07.10» без второй даты принимали за норму 7
        raise UsageError(USAGE + "\nПериод пишите через дефис: 01.12.2026-07.12.2026")
    norm_part = (text[:rng.start()] + " " + text[rng.end():]) if rng else text
    nums = re.findall(r"\d+", norm_part)
    norm = int(nums[0]) if nums else usual_norm
    if norm is not None and norm > MAX_NORM:
        raise UsageError(USAGE + f"\nНорма — число сообщений, не больше {MAX_NORM}.")
    if rng:
        try:
            a = _mkdate(rng.group(1), rng.group(2), rng.group(3), today)
            b = _mkdate(rng.group(4), rng.group(5), rng.group(6), today)
        except ValueError:
            raise UsageError(USAGE + "\nНе понял даты. Пример: 01.12.2026-07.12.2026")
        if b < a and not rng.group(3) and not rng.group(6):   # «28.12-03.01»: начало было в прошлом году
            try:
                a = a.replace(year=a.year - 1)
            except ValueError:
                pass
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
    tag: str | None = None   # тег в этом чате: по нему админы узнают человека; в базе он есть не у всех, поэтому его уточняют в Telegram


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
        f"{PRESENCE_SQL}, s.muted_until, s.user_messages_count_all_time, "
        "COALESCE((SELECT SUM(d.message_count) FROM daily_user_stats d WHERE d.chat_id = s.chat_tg_id "
        "  AND d.user_id = s.user_tg_id AND d.date BETWEEN ? AND ?), 0), "
        "(SELECT MAX(l.created_at) FROM moderation_logs l WHERE l.chat_id = s.chat_tg_id "
        "  AND l.user_id = s.user_tg_id AND l.action = 'mute'), s.member_tag "
        "FROM user_chat_stats s LEFT JOIN users u ON u.user_tg_id = s.user_tg_id "
        "WHERE s.chat_tg_id = ? AND s.is_left = FALSE AND COALESCE(s.is_bot, FALSE) = FALSE",
        (plan.start.isoformat(), plan.end.isoformat(), chat_id),
    ) as cur:
        rows = await cur.fetchall()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    out: list[Violator] = []
    for uid, uname, rank, immune, shielded, joined_at, member_since, back_at, first_day, muted_until, total, count, mute_at, tag in rows:
        uid = int(uid)
        if is_developer(uid) or uid == owner or immune or shielded or chat_bots.is_service(uid):
            continue
        if int(rank) >= rights["purge_write"]:
            continue   # состав чата, который пишет и во время чистки
        blocked, notes = 0.0, []
        since_naive = stay_start(joined_at, member_since, back_at, first_day)
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
                            len(await active_warns(db, chat_id, uid)), ", ".join(notes), member_tags.clean(tag)))
    out.sort(key=lambda v: (v.count - v.required, v.count))
    return out


async def screen_violators(bot: Bot, db, chat_id: int, violators: list[Violator]) -> tuple[list[Violator], int]:
    """Убрать из списка ботов, в том числе самого Предвестника: чистка людям, а не ботам. Бот не всегда помечен в базе,
    поэтому список сверяется с Telegram. Возвращает (список без ботов, сколько ботов убрано)."""
    if not violators:
        return violators, 0
    bots = await chat_bots.screen(bot, db, chat_id, [v.user_id for v in violators])
    return [v for v in violators if v.user_id not in bots], len([v for v in violators if v.user_id in bots])


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
    facts = [
        f"Сообщений за период: <b>{v.count}</b> из {v.required}",
        f"Всего сообщений: <b>{v.total}</b> · в чате {v.days_in_chat} дн",
        f"Действующих варнов: <b>{v.warns}</b>",
    ]
    if v.note:
        facts.append(f"Учтено: <i>{html.escape(v.note)}</i>")
    # СТИЛЬ v1 (оформлено, см. docs/CHAT_BOT_DESIGN_HANDOFF.md): игрок ссылкой (пинг нужен), факты цитатой
    tag_line = f"\n🏷 <b>{html.escape(v.tag)}</b>" if v.tag else ""   # тег из списка участников чата
    return (f"📁 <b>Досье</b> · {html.escape(chat_title)}\n"
            f'👤 <a href="tg://user?id={v.user_id}">{html.escape(name)}</a>{tag_line}\n' + quote(facts))


def dossier_kb(session_id: int, user_id: int) -> InlineKeyboardMarkup:
    b = lambda act: InlineKeyboardButton(text=VERDICTS[act], callback_data=PurgeCB(act=act, s=session_id, u=user_id).pack())
    return InlineKeyboardMarkup(inline_keyboard=[[b("ban"), b("kick")], [b("warn"), b("mute"), b("forgive")]])


async def web_keyboard(bot, chat_id: int):
    try:
        me = await bot.me()
        if me.username:
            return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
                text="Продолжить на сайте", url=f"https://t.me/{me.username}?startapp=purge_{chat_id}")]])
    except Exception:
        logger.warning("purge: web navigation unavailable; session remains usable")
    return None


async def _skip_target(session_id: int, user_id: int) -> None:
    """Оказался ботом: досье не нужно. Запись остаётся с отметкой «пропущен», в итоги она не входит."""
    async with get_pool().acquire() as conn:
        db = PGAdapter(conn)
        await chat_bots.mark(db, user_id)
        await db.execute("UPDATE purge_targets SET verdict = 'skip', verdict_at = NOW() WHERE session_id = ? AND user_id = ? AND verdict IS NULL AND decision_state IN ('idle','failed')",
                         (session_id, user_id))
        await commit(db)


async def _send_dossiers(bot: Bot, session_id: int, chat_id: int, chat_title: str, dest: int,
                         violators: list[Violator]) -> None:
    """Фоном: по одному сообщению на нарушителя (не блокирует команду)."""
    for v in violators:
        try:
            async with get_pool().acquire() as connection:
                adapter = PGAdapter(connection)
                async with adapter.execute("SELECT s.status,t.verdict,t.dossier_sent FROM purge_targets t JOIN purge_sessions s ON s.id=t.session_id "
                                           "WHERE t.session_id=? AND t.user_id=?", (session_id, v.user_id)) as cursor:
                    pending = await cursor.fetchone()
            if not pending or pending[0] != "active" or pending[1] or pending[2]:
                continue
            # Тех, кто мало пишет, бот мог ни разу не видеть с тегом: спрашиваем Telegram прямо перед досье
            state, tag = await member_tags.probe(bot, chat_id, v.user_id)
            if state == "bot":   # проверка перед чисткой не дошла до этого человека, а он бот: досье не нужно
                await _skip_target(session_id, v.user_id)
                continue
            known = state == "ok"
            if known:
                v.tag = tag
            await bot.send_message(dest, dossier_text(v, chat_title), parse_mode="HTML",
                                   reply_markup=dossier_kb(session_id, v.user_id))
            async with get_pool().acquire() as conn:
                db = PGAdapter(conn)
                if known:
                    await member_tags.observe(db, chat_id, v.user_id, tag)
                await db.execute("UPDATE purge_targets SET dossier_sent = TRUE, member_tag = ? "
                                 "WHERE session_id = ? AND user_id = ?", (v.tag, session_id, v.user_id))
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
    try:
        await authorize_shared(ctx.bot, ctx.db, chat.id, ctx.user_id)
        violators = await find_violators(ctx.db, chat.id, plan)
        violators, skipped_bots = await screen_violators(ctx.bot, ctx.db, chat.id, violators)
        dest = await admin_chat_of(ctx.db, chat.id) or chat.id
        receipt = await start_shared(ctx.bot, ctx.db, chat.id, ctx.user_id, plan, violators, dest,
                                        action_id=f"telegram:{ctx.message.message_id}")
    except purge_flow.PurgeConflict as error:
        await ctx.reply(str(error)); return
    session_id = receipt["session_id"]
    if not receipt["created"]:
        await ctx.reply("Этот запуск уже обработан. " + ("Чистка продолжается." if receipt["active"] else "Чистка завершена."))
        return
    _hush[chat.id] = 0
    await ctx.reply(
        "🧹 <b>Чистка началась</b>\n"   # СТИЛЬ v1 (оформлено)
        + quote([f"Период: {fmt(plan.start)} – {fmt(plan.end)} · норма {plan.norm}",
                 f"Не набрали норму: <b>{len(violators)}</b>"]
                + ([f"Боты не считаются: {skipped_bots}"] if skipped_bots else []))
        + "\n🔒 Чат закрыт до конца чистки.",
        reply_markup=await web_keyboard(ctx.bot, chat.id),
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
    await ctx.reply(f"🧹 Идёт чистка · норма {s[1]} · {s[2]} – {s[3]}\n" + summary_lines(counts)
                    + await outcome_lines(ctx.db, int(s[0]), ("none",)),
                    reply_markup=await web_keyboard(ctx.bot, ctx.message.chat.id))


async def verdict_counts(db, session_id: int) -> dict[str, int]:
    async with db.execute(
        "SELECT COALESCE(verdict, 'none'), COUNT(*) FROM purge_targets WHERE session_id = ? "
        "AND COALESCE(verdict, '') <> 'skip' GROUP BY 1",
        (session_id,)) as cur:
        return {r[0]: int(r[1]) for r in await cur.fetchall()}


def summary_lines(c: dict[str, int]) -> str:
    total = sum(c.values())
    parts = [f"Не набрали норму: {total}"]
    for key, label in (("ban", "⛔ Забанено"), ("kick", "👢 Кикнуто"), ("warn", "⚠️ Выдано варнов"),
                       ("mute", "🔇 Замучено"), ("forgive", "🕊 Прощено"), ("none", "⏳ Без решения")):
        if c.get(key):
            parts.append(f"{label}: {c[key]}")
    return quote(parts)   # СТИЛЬ v1 (оформлено): итоги чистки цитатой


OUTCOME_TITLES = {"ban": "⛔ Забанены", "kick": "👢 Кикнуты"}
OUTCOME_SHOWN = 20


async def outcome_lines(db, session_id: int, verdicts: tuple[str, ...], pending: str = "⏳ Ждут решения") -> str:
    """Кто именно получил решение (или ждёт его), с тегами: по одному блоку на решение. Пусто, если показывать нечего."""
    blocks = []
    for key in verdicts:
        cond = "verdict IS NULL" if key == "none" else "verdict = ?"
        params = (session_id,) if key == "none" else (session_id, key)
        async with db.execute(
            f"SELECT user_id, username, member_tag FROM purge_targets WHERE session_id = ? AND {cond} "
            "ORDER BY msg_count - COALESCE(required_norm, 0), msg_count, user_id",
            params) as cur:
            rows = await cur.fetchall()
        if not rows:
            continue
        names = [html.escape(member_tags.with_tag(f"@\u200b{u}" if u else f"id{i}", member_tags.clean(t)))
                 for i, u, t in rows[:OUTCOME_SHOWN]]
        if len(rows) > OUTCOME_SHOWN:
            names.append(f"…и ещё {len(rows) - OUTCOME_SHOWN}")
        blocks.append(f"\n<b>{pending if key == 'none' else OUTCOME_TITLES[key]}</b>\n" + quote(names))
    return "".join(blocks)


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
    try:
        await authorize_shared(ctx.bot, ctx.db, chat_id, ctx.user_id, action="read")
        await purge_flow.complete(ctx.db, chat_id=chat_id, actor=ctx.user_id)
    except purge_flow.PurgeConflict as error:
        await ctx.reply(str(error)); return
    _hush.pop(chat_id, None)
    await ctx.message.answer("✅ <b>Чистка завершена, чат открыт</b>\n" + summary_lines(counts)
                             + await outcome_lines(ctx.db, int(s[0]), ("ban", "kick", "none"), "⏳ Без решения"), parse_mode="HTML")


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
    try:
        result = await decide_shared(bot, db, chat_id, cb.s, cb.u, actor, cb.act,
                                     f"tg:{call.id}")
    except purge_flow.PurgeConflict as error:
        await call.answer(str(error)[:190], show_alert=True); return
    if result.get("replayed"):
        await call.answer("Решение уже принято: " + VERDICTS.get(result["verdict"], result["verdict"]), show_alert=True); return
    try:
        await call.message.edit_text(
            f"{call.message.html_text}\n\n<b>{VERDICTS[cb.act]}</b> · {html.escape(call.from_user.full_name)}",
            parse_mode="HTML")
    except Exception:
        pass
    await call.answer("Готово")




async def authorize_shared(bot, db, chat_id: int, actor: int, target: int | None = None, action: str | None = None) -> None:
    """Current local delegation plus fresh Telegram membership and bot capability."""
    await ranks.sync_owner(db, bot, chat_id)
    if not await ranks.can(db, chat_id, actor, "purge"):
        raise purge_flow.PurgeConflict("У вашего ранга нет права проводить чистку.")
    if action != "read":
        from services import feature_switches
        disabled = await feature_switches.disabled(db, feature_switches.command_features("чистка", "purge", None), chat_id)
        if disabled is not None:
            raise purge_flow.PurgeConflict("Чистка сейчас отключена настройками бота или чата.")
    try:
        member = await bot.get_chat_member(chat_id, actor)
        me = await bot.me()
        own = await bot.get_chat_member(chat_id, me.id)
    except Exception:
        raise purge_flow.PurgeConflict("Не удалось проверить текущие права в Telegram. Повторите позже.") from None
    if member.status in ("left", "kicked") or (member.status == "restricted" and not member.is_member):
        raise purge_flow.PurgeConflict("Вы больше не состоите в этом чате.")
    if action != "read" and (own.status != "administrator" or not own.can_delete_messages):
        raise purge_flow.PurgeConflict("Боту нужны права администратора и удаления сообщений.")
    if action in {"ban", "kick", "mute"} and not own.can_restrict_members:
        raise purge_flow.PurgeConflict("Боту нужны права блокировки участников.")
    if target is None or action == "forgive":
        return
    if target == me.id or is_developer(target):
        raise purge_flow.PurgeConflict("К этому участнику санкции не применяются.")
    denied = await rank_block(db, chat_id, actor, target)
    if denied:
        raise purge_flow.PurgeConflict(denied)
    async with db.execute("SELECT is_immune,(immune_until IS NOT NULL AND immune_until>NOW()) FROM user_chat_stats "
                          "WHERE chat_tg_id=? AND user_tg_id=?", (chat_id, target)) as cursor:
        protected = await cursor.fetchone()
    if protected and any(protected):
        raise purge_flow.PurgeConflict("У участника сейчас иммунитет или щит.")
    try:
        live_target = await bot.get_chat_member(chat_id, target)
    except Exception:
        raise purge_flow.PurgeConflict("Не удалось проверить текущий статус участника.") from None
    if live_target.status in ("creator", "administrator"):
        raise purge_flow.PurgeConflict("Участник теперь администратор Telegram; санкция заблокирована.")


async def start_shared(bot, db, chat_id: int, actor: int, plan: Plan, violators: list[Violator], dest: int,
                       action_id: str | None = None) -> dict:
    async with db.connection.transaction():
        receipt = await purge_flow.begin_with_receipt(db, chat_id=chat_id, actor=actor, norm=plan.norm,
            date_from=plan.start.isoformat(), date_to=plan.end.isoformat(), destination=dest,
            targets=[asdict(v) for v in violators], action_id=action_id)
        if receipt["created"]:
            # Commit chat closure and pausing all Mafia topics together, exactly once.
            from services import mafia_v1
            async with db.execute("SELECT id FROM mafia_v1_matches WHERE chat_id=? AND phase IN ('night','discussion','voting')", (chat_id,)) as cursor:
                matches = await cursor.fetchall()
            for match in matches:
                await mafia_v1.pause_for_moderation_intervention(db, match_id=int(match[0]))
        return receipt


async def decide_shared(bot, db, chat_id: int, session_id: int, target: int, actor: int, action: str, action_id: str) -> dict:
    warned = None
    async def authorize(cid, uid, act):
        if cid != chat_id:
            raise purge_flow.PurgeConflict("Чистка относится к другому чату.")
        await authorize_shared(bot, db, cid, actor, uid, act)
    async def execute(cid, uid, act):
        nonlocal warned
        try:
            if act == "ban": await do_ban(bot, db, cid, uid, actor, FOREVER, "чистка")
            elif act == "kick": await do_kick(bot, db, cid, uid, actor, "чистка")
            elif act == "mute": await do_mute(bot, db, cid, uid, actor, timedelta(hours=1), "чистка")
            elif act == "warn": warned = await do_warn(db, cid, uid, actor, None, "чистка: не набрана норма")
        except (TelegramBadRequest, TelegramForbiddenError):
            # Kick is ban+unban: a rejection of step two can follow a successful ban.
            if act == "kick": raise RuntimeError("kick delivery requires verification") from None
            raise purge_flow.DeliveryRejected() from None
    result = await purge_flow.decide(db, session_id=session_id, user_id=target, actor=actor,
                                     action=action, action_id=action_id, authorize=authorize, execute=execute)
    if warned and warned[0] >= warned[1]:
        try:
            await warn_limit_alert(bot, db, chat_id, None, target, str(target), warned[0], warned[1])
        except Exception as error:
            logger.warning("purge warning notification failed: {}", type(error).__name__)
    return result


async def materialize_reconciled(bot, db, chat_id: int, row: dict, *, applied: bool) -> None:
    """Reflect verified Telegram state locally without another sanction request."""
    try:
        member = await bot.get_chat_member(chat_id, int(row["user_id"]))
    except Exception:
        raise purge_flow.PurgeConflict("Не удалось сверить статус участника в Telegram.") from None
    action, uid, actor = row["decision_action"], int(row["user_id"]), int(row["decision_actor"])
    banned = member.status == "kicked"
    muted = member.status == "restricted" and not member.can_send_messages
    if not applied:
        if banned or (action == "mute" and muted):
            raise purge_flow.PurgeConflict("Telegram показывает применённую или частично применённую санкцию. Сначала разберите её отдельно.")
        return
    if action == "ban":
        if not banned:
            raise purge_flow.PurgeConflict("Telegram не подтверждает текущий бан. Не отмечайте его исполненным.")
        await db.execute("INSERT INTO chat_blacklist(chat_id,user_id,reason,added_by) VALUES (?,?,'чистка: подтверждено сверкой',?) "
                         "ON CONFLICT(chat_id,user_id) DO UPDATE SET reason=EXCLUDED.reason,added_by=EXCLUDED.added_by,expires_at=NULL", (chat_id, uid, actor))
    elif action == "mute":
        if not muted or not member.until_date:
            raise purge_flow.PurgeConflict("Telegram не подтверждает действующий мут со сроком.")
        await db.execute("UPDATE user_chat_stats SET muted_until=? WHERE chat_tg_id=? AND user_tg_id=?",
                         (member.until_date, chat_id, uid))
    elif action == "kick" and banned:
        raise purge_flow.PurgeConflict("Кик выполнен частично: участник ещё заблокирован. Снимите бан отдельно и повторите сверку.")
    if action in {"ban", "kick"}:
        await db.execute("UPDATE user_chat_stats SET is_left=? WHERE chat_tg_id=? AND user_tg_id=?",
                         (member.status in {"left", "kicked"}, chat_id, uid))
    await log(db, chat_id, uid, actor, action, "чистка: исполнение подтверждено сверкой")
