"""Личка с ботом: настройки уведомлений («бот уведомления»), «план дня» и кнопки «забрать» без Mini App.

Награды берутся теми же сервисами, что в Mini App (services.quests_v1, services.league_pass), поэтому действуют те же
ограничения и чеки: двойное нажатие не выдаёт награду дважды. Рассылает уведомления services/dm_push.py.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.filters import Command as SlashCommand
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from loguru import logger

from bot.chat.framework import Ctx, registry
from core import dm_push as rules
from infrastructure.repositories import dm_push as repo
from services import dm_plan, dm_push, dm_push_events

router = Router(name="chat_notify")
# Слэш-команды из меню «/» живут в отдельном роутере: он подключается раньше общего обработчика чата (bot/handlers/__init__.py),
# который ловит все сообщения и иначе проглотил бы /plan и /notify.
slash_router = Router(name="chat_notify_slash")

_TZ = re.compile(r"^(?:пояс|utc|мск)?\s*([+-]?\d{1,2})$", re.I)


def _btn(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=data)


async def markup_for(button: dict | None, bot) -> InlineKeyboardMarkup | None:
    """Кнопка под уведомлением: открыть раздел Mini App или нажатие внутри лички."""
    if not button:
        return None
    if button.get("kind") == "cb":
        return InlineKeyboardMarkup(inline_keyboard=[[_btn(button["label"], button["data"])]])
    from bot.chat.site import site_keyboard
    me = await bot.me()
    return site_keyboard("private", me.username or "", button.get("section", ""), button["label"])


# ── настройки ───────────────────────────────────────────────────────────────

def _offset_label(offset: int) -> str:
    return "по Москве" if offset == 3 else f"пояс {offset:+d}"


async def settings_view(db, user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    on = await repo.consented(db, user_id)
    state = await repo.get_settings(db, user_id)
    lines = ["🔔 <b>Уведомления в личку</b>",
             "Бот пишет только о том, что ты включил. Сейчас включено: "
             + (", ".join(c.label.split(" ", 1)[1] for c in rules.CATEGORIES if c.live and c.key in on) or "ничего") + ".",
             "",
             f"• Не больше {rules.DAILY_CAP} сообщений в сутки: если событий много, соберу их в одно.",
             f"• Ночью не пишу: с {rules.QUIET_START_HOUR}:00 до {rules.QUIET_END_HOUR:02d}:00 ({_offset_label(state['tz_offset'])}; поменять: «бот уведомления пояс +5»)."
             if state["quiet_enabled"] else "• Тихие часы выключены: пишу в любое время.",
             "• Нажми на название, чтобы включить или выключить."]
    if state["paused_at"] is not None:
        lines += ["", "⏸ Ты давно не отвечал, поэтому я замолчал. Напиши мне что угодно — и я продолжу."]
    rows = [[_btn(("✅ " if c.key in on else "▫️ ") + c.label, f"dn:t:{c.key}")] for c in rules.CATEGORIES if c.live]
    rows.append([_btn("🌙 Тихие часы: " + ("вкл" if state["quiet_enabled"] else "выкл"), "dn:q")])
    rows.append([_btn("📋 План дня", "dn:plan")])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


async def _show(ctx: Ctx) -> None:
    await dm_push.confirm_contact(ctx.db, ctx.user_id)
    text, kb = await settings_view(ctx.db, ctx.user_id)
    await ctx.reply(text, reply_markup=kb)


async def _need_private(ctx: Ctx, what: str) -> bool:
    """Личное состояние игрока (настройки, план) не показываем в общем чате."""
    if ctx.message.chat.type == "private":
        return False
    await ctx.reply(f"🔔 {what} — в личке с ботом: открой чат со мной и напиши «{ctx.command.name}».")
    return True


@registry.command("уведомления", aliases=("уведомление", "пуши", "notify"), section="basic",
                  summary="Что бот присылает тебе в личку, и ночные часы.", usage="бот уведомления [пояс +5 | тихие вкл/выкл]",
                  example="бот уведомления")
async def cmd_notify(ctx: Ctx) -> None:
    if await _need_private(ctx, "Уведомления настраиваются"):
        return
    arg = ctx.args.strip().lower()
    if arg:
        if arg.startswith("тих"):
            if "выкл" in arg or "off" in arg:
                await repo.set_quiet(ctx.db, ctx.user_id, False)
            elif "вкл" in arg or "on" in arg:
                await repo.set_quiet(ctx.db, ctx.user_id, True)
            else:
                await ctx.reply("Тихие часы: напиши <code>бот уведомления тихие вкл</code> или <code>бот уведомления тихие выкл</code>.")
                return
        else:
            found = _TZ.match(arg.removeprefix("пояс").strip() if arg.startswith("пояс") else arg)
            offset = int(found.group(1)) if found else None
            if offset is None or not rules.MIN_TZ <= offset <= rules.MAX_TZ:
                await ctx.reply("Не понял пояс. Напиши число от -12 до 14, например: <code>бот уведомления пояс +5</code> (Москва — +3).")
                return
            await repo.set_tz(ctx.db, ctx.user_id, offset)
    await _show(ctx)


# ── план дня ────────────────────────────────────────────────────────────────

async def plan_view(db, user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    now = datetime.now(timezone.utc)
    lines, rows = ["📋 <b>План дня</b>", ""], []
    quests = await dm_plan.quests_state(db, user_id)
    if quests is not None and (quests["daily"]["quests"] or quests["weekly"]["quests"]):
        done = sum(1 for q in quests["daily"]["quests"] if q["completed"])
        lines.append(f"<b>Задания дня</b>: сделано {done} из {len(quests['daily']['quests'])}.")
        names = {"daily": "дня", "weekly": "недели", "combined": "за день и неделю вместе"}
        ready = [k for k, v in quests["rewards"]["items"].items() if v["claimable"]]
        for kind in ready:
            lines.append(f"🎁 Награда за задания {names[kind]} готова.")
            rows.append([_btn(f"🎁 Забрать: {names[kind]}", f"dn:claim:{kind}")])
        if not ready and done < len(quests["daily"]["quests"]):
            lines.append("Выполни все задания дня — получишь награду.")
        lines.append("")
    pets = await dm_plan.pets_state(db, user_id)
    if pets is not None and (pets[0] or pets[1]):
        if pets[0]:
            lines.append(f"<b>Питомцы</b>: вернулись {pets[0]} — добыча ждёт.")
        if pets[1]:
            lines.append(f"<b>Питомцы</b>: ещё в пути {pets[1]}.")
        rows.append([_btn("🐾 Открыть питомцев", "dn:pets")])
        lines.append("")
    try:
        if await dm_push_events.ready_pass_seasons(db, user_id, now):
            lines += ["<b>Пропуск</b>: есть награды, которые можно забрать.", ""]
            rows.append([_btn("🏆 Забрать награды Пропуска", "dn:claim:pass")])
    except Exception as exc:
        logger.warning(f"plan: pass unavailable: {type(exc).__name__}: {exc}")
    if len(lines) == 2:
        lines.append("Сейчас забирать нечего. Загляни в приложение: там игры и новые задания.")
    rows.append([_btn("🔔 Уведомления", "dn:menu")])
    return "\n".join(lines).rstrip(), InlineKeyboardMarkup(inline_keyboard=rows)


@registry.command("план", aliases=("план дня", "plan"), section="basic",
                  summary="Что забрать и что сделать сегодня: задания, питомцы, Пропуск.", usage="бот план", example="бот план")
async def cmd_plan(ctx: Ctx) -> None:
    if await _need_private(ctx, "План дня показываю"):
        return
    await dm_push.confirm_contact(ctx.db, ctx.user_id)
    text, kb = await plan_view(ctx.db, ctx.user_id)
    await ctx.reply(text, reply_markup=kb)


# ── кнопки ──────────────────────────────────────────────────────────────────

async def _claim_quest(db, user_id: int, kind: str) -> str:
    from infrastructure.repositories.economy_ledger import ensure_tables as ensure_ledger
    from infrastructure.repositories.quests_v1 import ensure_tables
    from services import quests_v1 as quests
    from services.vip import is_vip_active
    await ensure_tables(db)
    await ensure_ledger(db)
    sources = await quests.available_sources(db, user_id=user_id)
    state = await quests.claim_reward(db, user_id=user_id, vip_active=await is_vip_active(db, user_id), kind=kind, sources=sources)
    result = state["reward_result"]
    if result["already_claimed"]:
        return "Эту награду ты уже забрал."
    parts = [f"Мора +{result['amount_mora']}"]
    if result.get("amount_keys"):
        parts.append(f"ключей +{result['amount_keys']}")
    if result.get("amount_essence"):
        parts.append(f"Эссенции +{result['amount_essence']}")
    return "✅ Забрано: " + ", ".join(parts) + "."


async def _claim_pass(db, user_id: int) -> str:
    from infrastructure.repositories.economy_ledger import ensure_tables as ensure_ledger
    from services import league_pass
    await ensure_ledger(db)
    seasons = await dm_push_events.ready_pass_seasons(db, user_id, datetime.now(timezone.utc))
    if not seasons:
        return "Сейчас в Пропуске нечего забирать."
    texts = []
    for season in seasons:
        try:
            result = await league_pass.claim(db, user_id=user_id, season=season)
        except league_pass.PassError as exc:
            if texts:
                break
            return str(exc)
        texts += [g["text"] for g in result["granted"]]
    return "✅ Забрано из Пропуска: " + ", ".join(texts[:8]) + ("…" if len(texts) > 8 else "") + "."


@router.callback_query(F.data.startswith("dn:"))
async def on_notify_button(call: CallbackQuery, db) -> None:
    msg = call.message
    if msg is None or msg.chat.type != "private" or msg.chat.id != call.from_user.id:
        await call.answer("Это работает только в личке с ботом.", show_alert=True)
        return
    uid, parts = call.from_user.id, (call.data or "").split(":")
    if not await dm_push.player_reachable(db, uid):   # аккаунт на удалении или заблокирован: награды здесь не выдаём
        await call.answer("Сейчас это недоступно.", show_alert=True)
        return
    try:
        await dm_push.confirm_contact(db, uid)
        notice = ""
        if parts[1] == "t" and len(parts) == 3 and parts[2] in rules.LIVE_KEYS:
            on = parts[2] in await repo.consented(db, uid)
            await repo.set_consent(db, uid, parts[2], not on)
            notice = "Выключил." if on else "Включил."
        elif parts[1] == "q":
            await repo.set_quiet(db, uid, not (await repo.get_settings(db, uid))["quiet_enabled"])
        elif parts[1] == "claim" and len(parts) == 3:
            notice = await (_claim_pass(db, uid) if parts[2] == "pass" else _claim_quest(db, uid, parts[2]))
            text, kb = await plan_view(db, uid)
            await _edit(msg, text, kb)
            await call.answer(notice[:190], show_alert=not notice.startswith("✅"))
            return
        elif parts[1] == "pets":
            await _open_pets(call, db)
            return
        if parts[1] == "plan":
            text, kb = await plan_view(db, uid)
        else:
            text, kb = await settings_view(db, uid)
        await _edit(msg, text, kb)
        await call.answer(notice)
    except Exception as exc:
        from services import quests_v1
        if isinstance(exc, (quests_v1.QuestError,)):
            await call.answer(str(exc)[:190], show_alert=True)
            return
        logger.exception("notify button failed")
        await call.answer("Не получилось. Попробуй ещё раз чуть позже: награда не пропадёт и не выдастся дважды.", show_alert=True)


async def _edit(msg: Message, text: str, kb: InlineKeyboardMarkup) -> None:
    from aiogram.exceptions import TelegramBadRequest
    try:
        await msg.edit_text(text, parse_mode="HTML", reply_markup=kb, disable_web_page_preview=True)
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc):
            raise


async def _open_pets(call: CallbackQuery, db) -> None:
    from bot.chat import pets
    from infrastructure.repositories import pet_chat
    chat = call.message.chat
    if not await pets.available(db, call.from_user.id, chat, {"screen": "home"}):
        await call.answer("⛔ Питомцы сейчас недоступны.", show_alert=True)
        return
    await pet_chat.expire(db, call.from_user.id)
    text, kb = await pets.render(db, call.from_user.id, chat.id, {"screen": "home"})
    await call.message.answer(text, parse_mode="HTML", reply_markup=kb, disable_web_page_preview=True)
    await call.answer()


# ── слэш-команды из меню «/» (только в личке) ───────────────────────────────

async def _quiet(message: Message, db) -> bool:
    from bot.chat import _silent
    try:
        return await _silent(message, db)
    except Exception:
        return False


@slash_router.message(SlashCommand("notify"), F.chat.type == "private")
async def slash_notify(message: Message, db) -> None:
    if message.from_user is None or await _quiet(message, db):
        return
    await dm_push.confirm_contact(db, message.from_user.id)
    text, kb = await settings_view(db, message.from_user.id)
    await message.answer(text, parse_mode="HTML", reply_markup=kb)


@slash_router.message(SlashCommand("plan"), F.chat.type == "private")
async def slash_plan(message: Message, db) -> None:
    if message.from_user is None or await _quiet(message, db):
        return
    await dm_push.confirm_contact(db, message.from_user.id)
    text, kb = await plan_view(db, message.from_user.id)
    await message.answer(text, parse_mode="HTML", reply_markup=kb)
