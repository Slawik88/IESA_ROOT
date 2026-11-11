"""Личка с ботом: настройки уведомлений («бот уведомления»), «план дня» и кнопки «забрать» без Mini App.

Награды берутся теми же сервисами, что в Mini App (services.quests_v1, services.league_pass), поэтому действуют те же
ограничения и чеки: двойное нажатие не выдаёт награду дважды. Рассылает уведомления services/dm_push.py.
"""
from __future__ import annotations

import hmac
import html
import re
import time
from datetime import date, datetime, timezone

from aiogram import F, Router
from aiogram.filters import Command as SlashCommand
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from loguru import logger

from bot.chat.framework import Ctx, registry
from core import dm_push as rules
from core.economy_contract import IdempotencyConflict, InsufficientBalance
from core.zarniki_exchange_v1 import ZarnikiExchangePolicyError, quote
from infrastructure.repositories import dm_push as repo
from infrastructure.repositories import casino_v1 as casino_repo, system_flags, zarniki_exchange_v1 as exchange_repo
from services import casino_v1, chests_v1, dm_plan, dm_push, dm_push_events, feature_switches, zarniki_exchange_v1

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
    if button.get("kind") == "url":
        return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=button["label"], url=button["url"])]])
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


def message_url(chat, message_id: int | None) -> str | None:
    """Ссылка на сообщение в группе: публичный чат — по имени, супергруппа — t.me/c/…; у обычной группы ссылок нет."""
    if not message_id:
        return None
    if getattr(chat, "username", None):
        return f"https://t.me/{chat.username}/{int(message_id)}"
    cid = str(getattr(chat, "id", ""))
    return f"https://t.me/c/{cid[4:]}/{int(message_id)}" if cid.startswith("-100") and cid[4:].isdigit() else None


async def social_event(db, *, user_id: int, dedup_key: str, text: str, chat=None, message_id: int | None = None) -> bool:
    """«Люди»: событие с другим игроком в чате — в личку тому, кого оно касается, если он включил «Люди».
    Кнопка ведёт к сообщению в чате, где можно ответить. Ошибки не мешают самому действию в чате."""
    url = message_url(chat, message_id) if chat is not None else None
    button = {"kind": "url", "url": url, "label": "💬 Открыть сообщение"} if url else None
    return await dm_push_events.social(db, user_id=user_id, dedup_key=dedup_key, text=text, button=button)


def chat_name(chat) -> str:
    return f"«{html.escape(getattr(chat, 'title', None) or 'чат')}»"


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


_EXCHANGE_COMMAND = "обменять зарники"
_GIFT_COMMAND = "подарок фортуны"
_EXCHANGE_TTL = 300


def _exchange_signature(bot, uid: int, amount: int, issued: int, message_id: int, policy) -> str:
    payload = f"dm-exchange:{uid}:{amount}:{issued}:{message_id}:{policy.policy_version}:{policy.amount_received}"
    return hmac.digest(bot.token.encode(), payload.encode(), "sha256").hex()[:24]


@registry.command(_EXCHANGE_COMMAND, section="basic",
                  summary="Обменять Зарники на Мору с подтверждением в личке.",
                  usage="бот обменять зарники 5", example="бот обменять зарники 5")
async def cmd_exchange(ctx: Ctx) -> None:
    if ctx.message.chat.type != "private":
        await ctx.reply("Обменять Зарники можно в личке с ботом.")
        return
    if not re.fullmatch(r"[0-9]{1,16}", ctx.args.strip()):
        await ctx.reply("Напиши «бот обменять зарники 5», где 5 — сколько Зарников ты хочешь обменять.")
        return
    try:
        amount = int(ctx.args.strip())
        policy = quote(zarniki=amount, target="mora")
    except ZarnikiExchangePolicyError as exc:
        await ctx.reply(str(exc))
        return
    issued, message_id = int(time.time()), ctx.message.message_id
    signature = _exchange_signature(ctx.bot, ctx.user_id, amount, issued, message_id, policy)
    payload = f"dn:x:{amount:x}:{issued:x}:{message_id:x}:{signature}"
    await ctx.reply(
        f"Обменять {amount} Зарников на {policy.amount_received:.0f} Моры? Кнопка действует 5 минут.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[_btn("Подтвердить обмен", payload)]]),
    )


async def _confirm_exchange(call: CallbackQuery, db, uid: int, parts: list[str]) -> str:
    amount, issued, message_id = (int(value, 16) for value in parts[2:5])
    policy = quote(zarniki=amount, target="mora")
    signature = _exchange_signature(call.bot, uid, amount, issued, message_id, policy)
    if not hmac.compare_digest(signature, parts[5]) or not 0 <= int(time.time()) - issued < _EXCHANGE_TTL:
        return "Подтверждение устарело. Напиши «бот обменять зарники» и сумму ещё раз."
    await exchange_repo.ensure_tables(db)
    try:
        result = await zarniki_exchange_v1.exchange(db, user_id=uid, zarniki=amount, target="mora",
                                                   action_id=f"dm-exchange:{uid}:{message_id}")
    except InsufficientBalance:
        return "Для обмена не хватает Зарников."
    except IdempotencyConflict:
        return "Этот обмен уже обработан. Открой новый запрос, чтобы обменять другую сумму."
    return ("✅ Уже обменяно." if result["idempotent_replay"]
            else f"✅ Получено {policy.amount_received:.0f} Моры.")


@registry.command(_GIFT_COMMAND, section="games",
                  summary="Забрать ежедневный подарок Зала Фортуны в личке.",
                  usage="бот подарок фортуны", example="бот подарок фортуны")
async def cmd_casino_gift(ctx: Ctx) -> None:
    if ctx.message.chat.type != "private":
        await ctx.reply("Подарок Зала Фортуны можно забрать в личке с ботом.")
        return
    if not await system_flags.is_enabled(ctx.db, "game_casino_v1"):
        await ctx.reply("Зал Фортуны сейчас закрыт.")
        return
    today = await casino_repo.today(ctx.db)
    await ctx.reply("🎁 <b>Подарок Зала Фортуны</b>\nЗабери ежедневные фишки, если ещё не забрал их сегодня.",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [_btn("🎁 Забрать подарок", f"dn:gift:{today.isoformat()}")],
                    ]))


async def _claim_casino_gift(db, uid: int, day: date) -> str:
    if not await system_flags.is_enabled(db, "game_casino_v1"):
        return "Зал Фортуны сейчас закрыт."
    result = await casino_v1.claim_gift(db, uid, expected_day=day)
    return f"✅ Получено фишек: {result['gift']}."


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
        elif (parts[1] == "x" and len(parts) == 6) or (parts[1] == "gift" and len(parts) == 3):
            is_exchange = parts[1] == "x"
            name, section = (_EXCHANGE_COMMAND, "basic") if is_exchange else (_GIFT_COMMAND, "games")
            if await feature_switches.disabled(db, ["all", f"section:{section}", f"cmd:{name}"], None):
                await call.answer("Это действие сейчас недоступно.", show_alert=True)
                return
            notice = await (_confirm_exchange(call, db, uid, parts) if is_exchange
                            else _claim_casino_gift(db, uid, date.fromisoformat(parts[2])))
            await call.answer(notice, show_alert=True)
            return
        elif parts[1] == "chest" and len(parts) == 3 and re.fullmatch(r"[0-9a-f]{32}", parts[2]):
            if not await system_flags.is_enabled(db, "content_chests_v1"):
                await call.answer("Сундуки сейчас закрыты.", show_alert=True)
                return
            result = await chests_v1.open_with_grant(db, user_id=uid, grant_id=parts[2])
            rewards = ", ".join(f"{reward['name']} ×{reward['amount']}" for reward in result["rewards"])
            await call.answer(f"🎁 Награда: {rewards}"[:190], show_alert=True)
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
        if isinstance(exc, (quests_v1.QuestError, casino_v1.CasinoError, chests_v1.ChestKeyConflict, ZarnikiExchangePolicyError)):
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
