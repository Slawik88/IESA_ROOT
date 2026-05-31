"""
bot/handlers/identity.py
Profile display commands (unified design).

  бот я / бот профиль → full own profile card (same output, aliases)
  бот кто, @user       → target's card
  бот анкета           → own detailed card with shareable tg-link
"""
from datetime import datetime

from aiogram import Router, types
from bot.filters.text_commands import TextCmd
from core.constants import XP_PER_LEVEL
from core.registry import PET_SPECIES
from infrastructure.repositories import chat as chat_repo, marriages as marriage_repo
from infrastructure.repositories import economy as eco_repo
from infrastructure.repositories import users as users_repo
from infrastructure.repositories import zoo as zoo_db
from infrastructure.repositories.streak import get_streak
from services import roles
from services.formatting import parse_dt, format_currency
from services.utils import safe_html, resolve_target

router = Router(name="identity_router")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _xp_bar(current: int, maximum: int, length: int = 10) -> str:
    filled = int((min(current, maximum) / maximum) * length) if maximum > 0 else 0
    return "█" * filled + "░" * (length - filled)


def _marriage_duration(val) -> str:
    if not val:
        return "?"
    dt = parse_dt(val)
    if not dt:
        return "?"
    delta = datetime.now() - dt
    d, h = delta.days, delta.seconds // 3600
    return f"{d} дн." if d > 0 else f"{h} ч."


def _ecosystem_age(val) -> str:
    if not val:
        return "—"
    dt = parse_dt(val)
    if not dt:
        return "—"
    return f"{(datetime.now() - dt).days} дн."


def _fatigue_icon(fatigue: int) -> str:
    if fatigue >= 100: return "⛔"
    if fatigue >= 80:  return "🔴"
    if fatigue >= 40:  return "🟡"
    return "🟢"


def _active_pet_str(nursery_pets: list) -> str:
    p = next((p for p in nursery_pets if p["placement"] == "active"), None)
    if not p:
        return "нет"
    sp = PET_SPECIES.get(p["species_id"], {}).get("name", p["species_id"])
    lvl = p.get("pet_level", 1) or 1
    fat = p.get("fatigue", 0)
    return f"{sp} Lv{lvl} {_fatigue_icon(fat)}"


def _pets_block(nursery_pets: list) -> str:
    if not nursery_pets:
        return "└ <i>Питомник пуст</i>"
    role_map = {"active": "⚔️", "passive": "💤"}
    lines = []
    for p in nursery_pets:
        sp = PET_SPECIES.get(p["species_id"], {}).get("name", p["species_id"])
        icon = role_map.get(p["placement"], "📦")
        lvl = p.get("pet_level", 1) or 1
        fat = p.get("fatigue", 0)
        lines.append(f"├ {icon} <b>{p['name']}</b> <i>({sp})</i> · Lv{lvl} · {fat}/100 {_fatigue_icon(fat)}")
    lines[-1] = lines[-1].replace("├", "└")
    return "\n".join(lines)


# ── бот я / бот профиль (unified) ─────────────────────────────────────────────

@router.message(TextCmd(["я", "профиль", "стата", "стат", "мой профиль"]))
async def cmd_profile_unified(message: types.Message, db, developer_id: int = 0):
    if message.chat.type == "private":
        return await message.answer("❌ Эта команда доступна только в группах.")

    user_id = message.from_user.id
    chat_id = message.chat.id

    nickname = await users_repo.get_nickname(db, user_id, chat_id)
    display_name = safe_html(nickname or message.from_user.first_name)

    bal = await eco_repo.get_balance(db, user_id)
    stats = await chat_repo.get_chat_stats(db, user_id, chat_id)
    global_rank_id = await users_repo.get_global_rank(db, user_id)
    nursery_pets = await zoo_db.get_user_pets(db, user_id, placement="nursery")
    streak_row = await get_streak(db, user_id, chat_id)
    marriage = await marriage_repo.get_user_marriage(db, chat_id, user_id)
    hamster_income = await zoo_db.get_pending_hamster_income(db, user_id)

    await zoo_db.apply_fatigue_decay(db, user_id)

    global_rank = roles.get_global_rank_name(user_id, global_rank_id, developer_id=developer_id)
    local_rank  = roles.get_local_rank_name(user_id, stats.get("local_rank", 0), developer_id=developer_id)

    lvl = stats.get("user_level", 1)
    xp = stats.get("user_xp", 0)
    xp_in_lvl = xp % XP_PER_LEVEL
    bar = _xp_bar(xp_in_lvl, XP_PER_LEVEL)
    xp_left = XP_PER_LEVEL - xp_in_lvl

    mora = format_currency(bal["user_balance_mora"])
    diamonds = format_currency(bal["user_balance_diamonds"])

    partner_line = "нет"
    if marriage:
        p_name = marriage["user2_name"] if marriage["user1_id"] == user_id else marriage["user1_name"]
        dur = _marriage_duration(marriage.get("marriage_date"))
        partner_line = f"<b>{safe_html(p_name)}</b> · {dur}"

    warns = stats.get("warnings", 0)
    is_immune = stats.get("is_immune", False)
    immune_until = stats.get("immune_until")
    if is_immune:
        shield_line = "🛡 <b>Абсолютный иммунитет</b>"
    elif immune_until:
        dt = parse_dt(immune_until)
        if dt and dt > datetime.now():
            shield_line = f"🔰 Временный щит до <code>{dt.strftime('%d.%m %H:%M')}</code>"
        else:
            shield_line = "нет"
    else:
        shield_line = "нет"

    d_msgs = stats.get("user_messages_count_per_day", 0)
    w_msgs = stats.get("user_messages_count_per_week", 0)
    a_msgs = stats.get("user_messages_count_all_time", 0)
    streak = streak_row.get("streak", 0)

    text = (
        f"👤 <b>ПРОФИЛЬ</b> — {display_name}\n"
        f"<code>ID: {user_id}</code>\n\n"

        f"🌐 <b>Ранги</b>\n"
        f"├ 🌍 Глобально: <b>{global_rank}</b>\n"
        f"└ 🏘 В чате: <b>{local_rank}</b>\n\n"

        f"⭐ <b>Уровень {lvl}</b>  {bar}  <i>{xp_in_lvl}/{XP_PER_LEVEL} XP</i>\n"
        f"└ До {lvl + 1} уровня: <code>{xp_left}</code> XP\n\n"

        f"💰 <b>Баланс</b>\n"
        f"├ 🪙 Мора: <code>{mora}</code>"
    )

    if hamster_income > 0:
        text += f"  <i>(+{format_currency(hamster_income)} от хомяков)</i>"
    text += (
        f"\n└ 💎 Алмазы: <code>{diamonds}</code>\n\n"

        f"💍 <b>Отношения</b>\n"
        f"├ Партнёр: {partner_line}\n"
        f"├ ⚠️ Варны: <code>{warns}</code>\n"
        f"└ Защита: {shield_line}\n\n"

        f"⚡ <b>Активность</b>\n"
        f"├ 🔥 Стрик: <b>{streak}</b> дн.\n"
        f"├ 📅 Сегодня: <code>{d_msgs}</code>  · 🗓 Неделя: <code>{w_msgs}</code>  · 🏆 Всего: <code>{a_msgs}</code>\n\n"

        f"🐾 <b>Питомцы</b>\n"
        + _pets_block(nursery_pets)
    )

    await message.answer(text, parse_mode="HTML")


# ── бот кто ───────────────────────────────────────────────────────────────────

@router.message(TextCmd(["кто"]))
async def cmd_kto(message: types.Message, db, text_args: str = None, developer_id: int = 0):
    if message.chat.type == "private":
        return

    target_id, target_name, extra = await resolve_target(message, db, text_args)

    if extra == "error_user_not_found":
        return await message.answer(
            "❌ <b>Пользователь не найден.</b> Пусть напишет хоть одно сообщение.",
            parse_mode="HTML",
        )
    if not target_id:
        return await message.answer(
            "ℹ️ <b>Использование:</b> <code>бот кто, @юзер</code> или ответом на сообщение.",
            parse_mode="HTML",
        )

    chat_id = message.chat.id
    nickname = await users_repo.get_nickname(db, target_id, chat_id)
    display_name = safe_html(nickname or target_name)

    stats = await chat_repo.get_chat_stats(db, target_id, chat_id)
    global_rank_id = await users_repo.get_global_rank(db, target_id)
    nursery_pets = await zoo_db.get_user_pets(db, target_id, placement="nursery")
    marriage = await marriage_repo.get_user_marriage(db, chat_id, target_id)
    streak_row = await get_streak(db, target_id, chat_id)

    global_rank = roles.get_global_rank_name(target_id, global_rank_id, developer_id=developer_id)
    local_rank  = roles.get_local_rank_name(target_id, stats.get("local_rank", 0), developer_id=developer_id)

    lvl = stats.get("user_level", 1)
    xp = stats.get("user_xp", 0)
    xp_in_lvl = xp % XP_PER_LEVEL
    bar = _xp_bar(xp_in_lvl, XP_PER_LEVEL)

    partner_line = "нет"
    if marriage:
        p_name = marriage["user2_name"] if marriage["user1_id"] == target_id else marriage["user1_name"]
        dur = _marriage_duration(marriage.get("marriage_date"))
        partner_line = f"<b>{safe_html(p_name)}</b> · {dur}"

    d_msgs = stats.get("user_messages_count_per_day", 0)
    w_msgs = stats.get("user_messages_count_per_week", 0)
    a_msgs = stats.get("user_messages_count_all_time", 0)
    streak = streak_row.get("streak", 0)

    text = (
        f"🔍 <b>КАРТОЧКА</b> — {display_name}\n"
        f"<code>ID: {target_id}</code>\n\n"

        f"🌍 <b>{global_rank}</b>  ·  🏘 <b>{local_rank}</b>\n"
        f"⭐ Уровень: <b>{lvl}</b>  {bar}\n\n"

        f"💍 Партнёр: {partner_line}\n"
        f"🔥 Стрик: <b>{streak}</b> дн.\n"
        f"💬 Сегодня: <code>{d_msgs}</code> · Неделя: <code>{w_msgs}</code> · Всего: <code>{a_msgs}</code>\n\n"

        f"🐾 <b>Активный питомец:</b> {_active_pet_str(nursery_pets)}"
    )
    await message.answer(text, parse_mode="HTML")


# ── бот анкета ────────────────────────────────────────────────────────────────

@router.message(TextCmd(["анкета"]))
async def cmd_anketa(message: types.Message, db, developer_id: int = 0):
    if message.chat.type == "private":
        return

    user_id = message.from_user.id
    chat_id = message.chat.id

    stats = await chat_repo.get_chat_stats(db, user_id, chat_id)
    global_rank_id = await users_repo.get_global_rank(db, user_id)
    nursery_pets = await zoo_db.get_user_pets(db, user_id, placement="nursery")
    marriage = await marriage_repo.get_user_marriage(db, chat_id, user_id)
    streak_row = await get_streak(db, user_id, chat_id)
    global_msgs = await users_repo.get_messages_global(db, user_id)
    first_seen = await users_repo.get_first_seen(db, user_id)
    bal = await eco_repo.get_balance(db, user_id)

    nickname = await users_repo.get_nickname(db, user_id, chat_id)
    display_name = safe_html(nickname or message.from_user.first_name)
    self_link = f'<a href="tg://user?id={user_id}">{display_name}</a>'

    global_rank = roles.get_global_rank_name(user_id, global_rank_id, developer_id=developer_id)
    local_rank  = roles.get_local_rank_name(user_id, stats.get("local_rank", 0), developer_id=developer_id)

    lvl = stats.get("user_level", 1)
    xp_in_lvl = stats.get("user_xp", 0) % XP_PER_LEVEL
    bar = _xp_bar(xp_in_lvl, XP_PER_LEVEL)

    partner_line = "нет"
    if marriage:
        p_name = marriage["user2_name"] if marriage["user1_id"] == user_id else marriage["user1_name"]
        dur = _marriage_duration(marriage.get("marriage_date"))
        partner_line = f"<b>{safe_html(p_name)}</b> ({dur})"

    d_local = stats.get("user_messages_count_per_day", 0)
    w_local = stats.get("user_messages_count_per_week", 0)
    a_local = stats.get("user_messages_count_all_time", 0)
    gd = global_msgs.get("day", 0)
    gw = global_msgs.get("week", 0)
    ga = global_msgs.get("all_time", 0)

    mora = format_currency(bal["user_balance_mora"])
    diamonds = format_currency(bal["user_balance_diamonds"])

    text = (
        f"📜 <b>АНКЕТА</b>\n\n"
        f"👤 {self_link}\n"
        f"<code>ID: {user_id}</code>\n\n"

        f"🌍 <b>{global_rank}</b>  ·  🏘 <b>{local_rank}</b>  ·  ⭐ <b>Ур.{lvl}</b>\n"
        f"{bar}  <i>{xp_in_lvl}/{XP_PER_LEVEL} XP</i>\n\n"

        f"💰 <code>{mora}</code> 🪙  ·  <code>{diamonds}</code> 💎\n"
        f"💍 Партнёр: {partner_line}\n\n"

        f"🐾 Питомцев: <b>{len(nursery_pets)}</b>  ·  Активный: {_active_pet_str(nursery_pets)}\n"
        f"🔥 Стрик: <b>{streak_row.get('streak', 0)}</b> дн.\n"
        f"⏳ В Предвестнике: <b>{_ecosystem_age(first_seen)}</b>\n\n"

        f"💬 <b>В чате</b>: <code>{d_local}</code> / <code>{w_local}</code> / <code>{a_local}</code>  <i>(день/нед/всё)</i>\n"
        f"🌐 <b>Глобально</b>: <code>{gd}</code> / <code>{gw}</code> / <code>{ga}</code>"
    )
    await message.answer(text, parse_mode="HTML")
