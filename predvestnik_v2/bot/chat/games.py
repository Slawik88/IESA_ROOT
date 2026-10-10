"""Игры и квесты в чате — «как было» (разрешение владельца): чат только
показывает и ведёт в Mini App, сами игры живут там. Мафия — bot/chat/mafia.py."""
from __future__ import annotations

from aiogram import Router
from aiogram.filters.callback_data import CallbackData
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from core.miniapp_links import miniapp_url
from services.formatting import safe_html
from bot.chat.framework import Ctx, registry
from bot.chat.modules import module_disabled_reason

router = Router(name="chat_games")


async def _module_off(ctx: Ctx, module_key: str) -> bool:
    """Модуль выключен в этом чате или глобально — сказать и остановиться."""
    if ctx.message.chat.type not in ("group", "supergroup"):
        return False
    reason = await module_disabled_reason(ctx.db, ctx.message.chat.id, module_key)
    if reason:
        await ctx.reply(f"🔧 {safe_html(reason)}")
        return True
    return False


# ── Игры ──────────────────────────────────────────────────────────────────────

class LegacyGameRefundCB(CallbackData, prefix="game_refund"):
    user_id: int


def _games_kb(user_id: int, active_count: int) -> InlineKeyboardMarkup | None:
    rows = []
    if active_count > 0:
        rows.append([InlineKeyboardButton(text="↩ Вернуть старую ставку",
                                          callback_data=LegacyGameRefundCB(user_id=user_id).pack())])
    url = miniapp_url("game")
    if url:
        rows.append([InlineKeyboardButton(text="🎮 Открыть игры", url=url)])
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


@registry.command("игры", aliases=("сапёр", "казино", "азарт", "кости", "монетка", "числа", "угадай число", "рулетка"),
                  usage="бот игры", private=False, section="games",
                  summary="Ритм и Сапёр в Mini App; возврат старых ставок.")
async def cmd_games(ctx: Ctx) -> None:
    from services.skill_games import get_active_session_summary
    recovery = await get_active_session_summary(ctx.db, ctx.user_id)
    recovery_text = (
        f"\n\nУ тебя осталось старых ставок: <b>{recovery['active_count']}</b>. "
        f"К возврату: <b>{recovery['refundable_mora']:g} 🪙</b>."
        if recovery["active_count"] else ""
    )
    await ctx.message.answer(
        "🎮 <b>Игры Предвестника</b>\n"
        "🔔 <b>Ритм</b> — бесконечный забег на реакцию.\n"
        "💣 <b>Сапёр</b> — логическая игра с тремя сложностями и таблицами лидеров.\n"
        "🕵️ <b>Мафия</b> — прямо в группе: <code>бот мафия</code>\n"
        f"Открой Mini App → Игра, чтобы выбрать режим.{recovery_text}",
        reply_markup=_games_kb(ctx.user_id, recovery["active_count"]), parse_mode="HTML")


@router.callback_query(LegacyGameRefundCB.filter())
async def on_refund(call: CallbackQuery, callback_data: LegacyGameRefundCB, db) -> None:
    if call.from_user.id != callback_data.user_id:
        await call.answer("❌ Это не ваше меню.", show_alert=True)
        return
    from services.skill_games import refund_active_sessions
    result = await refund_active_sessions(db, call.from_user.id)
    await call.answer("Возврат выполнен." if result["count"] else "Возвращать уже нечего.")
    if call.message:
        await call.message.edit_reply_markup(reply_markup=_games_kb(call.from_user.id, 0))


@registry.command("ритм", aliases=("ритм дня", "контракт ритма", "мой контракт"), usage="бот ритм",
                  section="games", summary="Ритм — забег с рунами в Mini App.")
async def cmd_rhythm(ctx: Ctx) -> None:
    if await _module_off(ctx, "module_rhythm"):
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🎮 Открыть Центр Предвестника", url=miniapp_url("games"))]])
    await ctx.message.answer(
        "◌ <b>РИТМ</b>\n\n"
        "Бесконечный забег с рунами находится в Центре Предвестника. "
        "Там доступны обычный режим, режим аугментаций и отдельные таблицы лидеров.\n\n"
        "Старые ежедневные контракты и связанная с ними кампания сохранены в истории и больше не создают прогресс.",
        reply_markup=kb, parse_mode="HTML")


# ── Квесты ────────────────────────────────────────────────────────────────────

def _period_lines(label: str, quests: list[dict]) -> list[str]:
    lines = [f"<b>{label}</b>"]
    for quest in quests:
        done = " ✅" if quest["completed"] else ""
        lines.append(f"• {safe_html(str(quest['title']))} — <b>{int(quest['progress'])}/{int(quest['target'])}</b>{done}")
    return lines


def render_quest_overview(view: dict) -> str:
    """Только показывает снимок с сервера, ничего не меняет."""
    lines = ["🧭 <b>КВЕСТЫ</b>", ""]
    lines.extend(_period_lines("Сегодня", list(view["daily"]["quests"])))
    lines.extend(["", *_period_lines("Неделя", list(view["weekly"]["quests"]))])
    rerolls = view["rerolls"]
    rewards = dict(view.get("rewards", {}).get("items", {}))
    parts = []
    for kind, label in (("daily", "день"), ("weekly", "неделя"), ("combined", "всё вместе")):
        reward = dict(rewards.get(kind, {}))
        if not reward:
            continue
        part = f"{label}: {int(reward.get('amount_mora', 0))} Моры"
        if int(reward.get("amount_keys", 0)):
            part += f" + {int(reward['amount_keys'])} ключ"
        parts.append(part)
    reward_line = "Награды: " + "; ".join(parts) + "." if parts else "Награды доступны в Mini App."
    lines.extend([
        "",
        f"Замены на этой неделе: <b>{int(rerolls['remaining'])}/{int(rerolls['limit'])}</b>.",
        "Заменить можно только незавершённое задание в Mini App.",
        reward_line,
    ])
    return "\n".join(lines)


@registry.command("квесты", aliases=("задания", "квест"), usage="бот квесты", section="games",
                  summary="Ваши задания на день и неделю.")
async def cmd_quests(ctx: Ctx) -> None:
    if await _module_off(ctx, "module_quests"):
        return
    from infrastructure.repositories.quests_v1 import ensure_tables
    from services import quests_v1
    from services.vip import is_vip_active
    await ensure_tables(ctx.db)
    view = await quests_v1.overview(ctx.db, user_id=ctx.user_id, vip_active=await is_vip_active(ctx.db, ctx.user_id))
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🧭 Открыть квесты", url=miniapp_url("quests"))]])
    await ctx.message.answer(render_quest_overview(view), reply_markup=kb, parse_mode="HTML")
