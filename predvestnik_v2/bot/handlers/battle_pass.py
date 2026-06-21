# bot/handlers/battle_pass.py
"""Боевой пропуск: прогресс сезона + получение наград (Implementation Block 5.6)."""
from aiogram import Router, types
from aiogram.filters.callback_data import CallbackData
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.filters.text_commands import TextCmd
from core.constants import BATTLE_PASS_XP_PER_LEVEL
from core.registry import BATTLE_PASS_REWARDS, ITEMS_REGISTRY
from core.themes import THEMES
from services.battle_pass import (
    claim_reward, get_active_season, get_progress, level_status, get_level_options,
)
from services.formatting import format_progress_bar

router = Router(name="battle_pass_router")


class BpClaimCB(CallbackData, prefix="bpclaim"):
    level: int
    track: str

class BpChoiceCB(CallbackData, prefix="bpchoice"):
    level: int
    track: str
    idx: int


_STATUS_MARKERS = {
    "claimed": "✅ получено",
    "available": "🎁 доступно — забрать",
    "locked_vip": "🔒 нужен VIP",
    "locked_level": "⏳ ещё не достигнут",
}


def _reward_line(reward: dict) -> str:
    parts = []
    if reward.get("mora"):
        parts.append(f"+{int(reward['mora'])} 🪙")
    if reward.get("diamonds"):
        parts.append(f"+{int(reward['diamonds'])} 💎")
    for item_id, qty in reward.get("items", ()):
        name = ITEMS_REGISTRY.get(item_id, {}).get("name", item_id)
        parts.append(f"+{qty} {name}")
    if reward.get("theme"):
        theme_name = THEMES.get(reward["theme"], {}).get("name", reward["theme"])
        parts.append(f"🎨 Тема «{theme_name}»")
    return ", ".join(parts) if parts else "—"


@router.message(TextCmd(["бп", "боевой пропуск"]))
async def cmd_battle_pass(message: types.Message, db):
    season = get_active_season()
    if not season:
        return await message.answer("🎫 Сезон Боевого пропуска скоро начнётся, следи за анонсами!")

    progress = await get_progress(db, message.from_user.id)
    level = progress["level"]
    max_level = progress["max_level"]
    bar = format_progress_bar(progress["xp_in_level"], BATTLE_PASS_XP_PER_LEVEL)

    lines = [
        f"🎫 <b>{season['label']}</b> | Уровень {level}/{max_level}",
        f"{bar} {progress['xp_in_level']}/{BATTLE_PASS_XP_PER_LEVEL} XP",
    ]
    if not progress["paid_track_open"]:
        lines.append("👑 VIP-трек закрыт — оформи VIP («бот vip»), чтобы забирать платные награды.")
    lines.append("")

    lo = max(1, level - 2)
    hi = min(max_level, level + 3)

    builder = InlineKeyboardBuilder()
    for lv in range(lo, hi + 1):
        rewards = BATTLE_PASS_REWARDS.get(lv, {})
        free_status = level_status(lv, "free", progress)
        paid_status = level_status(lv, "paid", progress)
        lines.append(f"<b>Ур.{lv}</b>")
        lines.append(f"  🆓 {_reward_line(rewards.get('free', {}))} — {_STATUS_MARKERS[free_status]}")
        lines.append(f"  👑 {_reward_line(rewards.get('paid', {}))} — {_STATUS_MARKERS[paid_status]}")
        if free_status == "available":
            builder.button(text=f"🎁 Ур.{lv} · Бесплатный", callback_data=BpClaimCB(level=lv, track="free"))
        if paid_status == "available":
            builder.button(text=f"🎁 Ур.{lv} · VIP", callback_data=BpClaimCB(level=lv, track="paid"))
    builder.adjust(1)

    await message.answer(
        "\n".join(lines),
        reply_markup=builder.as_markup() if builder.buttons else None,
        parse_mode="HTML",
    )


@router.callback_query(BpClaimCB.filter())
async def cb_bp_claim(query: types.CallbackQuery, callback_data: BpClaimCB, db):
    lv, track = callback_data.level, callback_data.track
    # Уровень-выбор: показываем варианты наград кнопками
    options = await get_level_options(db, lv, track)
    if options:
        builder = InlineKeyboardBuilder()
        for i, opt in enumerate(options):
            builder.button(text=f"🎁 {opt['text']}", callback_data=BpChoiceCB(level=lv, track=track, idx=i))
        builder.adjust(1)
        await query.message.answer(
            f"🎫 Уровень {lv}: выберите ОДНУ награду:",
            reply_markup=builder.as_markup(), parse_mode="HTML")
        return await query.answer()
    ok, msg = await claim_reward(db, query.from_user.id, lv, track)
    if ok:
        await query.message.answer(msg, parse_mode="HTML")
        await query.answer()
    else:
        await query.answer(msg, show_alert=True)


@router.callback_query(BpChoiceCB.filter())
async def cb_bp_choice(query: types.CallbackQuery, callback_data: BpChoiceCB, db):
    ok, msg = await claim_reward(db, query.from_user.id, callback_data.level,
                                 callback_data.track, choice_index=callback_data.idx)
    if ok:
        try:
            await query.message.edit_text(msg, parse_mode="HTML")
        except Exception:
            await query.message.answer(msg, parse_mode="HTML")
        await query.answer()
    else:
        await query.answer(msg, show_alert=True)
