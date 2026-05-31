"""
bot/handlers/identity.py
B7: бот я / бот кто / бот анкета

бот я      → own brief card, no partner tag, show nickname if set
бот кто    → target's brief card, no partner tag, WITH message counts
бот анкета → target's full card, WITH partner tag, global stats, ecosystem age
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
from services.utils import format_currency, safe_html, resolve_target

router = Router(name="identity_router")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _marriage_duration(marriage_date_str: str | None) -> str:
    """Return 'X дн Y ч' since the marriage date, or 'Нет'."""
    if not marriage_date_str:
        return "Нет"
    try:
        dt = datetime.strptime(marriage_date_str, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        try:
            dt = datetime.strptime(marriage_date_str, "%Y-%m-%d")
        except ValueError:
            return "Нет"
    delta = datetime.now() - dt
    days = delta.days
    hours = delta.seconds // 3600
    return f"{days} дн {hours} ч" if days > 0 else f"{hours} ч"


def _ecosystem_age(first_seen: str | None) -> str:
    if not first_seen:
        return "—"
    try:
        dt = datetime.strptime(first_seen, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        try:
            dt = datetime.strptime(first_seen, "%Y-%m-%d")
        except ValueError:
            return "—"
    days = (datetime.now() - dt).days
    return f"{days} дн."


def _active_pet_line(nursery_pets: list) -> str:
    active = next((p for p in nursery_pets if p["placement"] == "active"), None)
    if not active:
        return "Нет"
    sp = PET_SPECIES.get(active["species_id"], {}).get("name", active["species_id"])
    lvl = active.get("pet_level", 1) or 1
    return f"{sp} Lv{lvl}"


def _msg_counts(stats: dict) -> str:
    d = stats.get("user_messages_count_per_day", 0)
    w = stats.get("user_messages_count_per_week", 0)
    a = stats.get("user_messages_count_all_time", 0)
    return f"{d} / {w} / {a}"


# ── бот я ─────────────────────────────────────────────────────────────────────

@router.message(TextCmd(["я"]))
async def cmd_ya(message: types.Message, db, developer_id: int = 0):
    if message.chat.type == "private":
        return

    user_id = message.from_user.id
    chat_id = message.chat.id

    # Nickname if set
    nickname = await users_repo.get_nickname(db, user_id, chat_id)
    display_name = safe_html(nickname or message.from_user.first_name)

    bal = await eco_repo.get_balance(db, user_id)
    stats = await chat_repo.get_chat_stats(db, user_id, chat_id)
    global_rank_id = await users_repo.get_global_rank(db, user_id)
    nursery_pets = await zoo_db.get_user_pets(db, user_id, placement="nursery")
    streak_row = await get_streak(db, user_id, chat_id)
    marriage = await marriage_repo.get_user_marriage(db, chat_id, user_id)

    global_rank_name = roles.get_global_rank_name(user_id, global_rank_id, developer_id=developer_id)
    local_rank_name = roles.get_local_rank_name(user_id, stats.get("local_rank", 0), developer_id=developer_id)

    xp = stats.get("user_xp", 0)
    xp_in_lvl = xp % XP_PER_LEVEL

    married_text = "Нет"
    if marriage:
        p_name = marriage["user2_name"] if marriage["user1_id"] == user_id else marriage["user1_name"]
        dur = _marriage_duration(marriage.get("marriage_date"))
        married_text = f"<b>{safe_html(p_name)}</b> ({dur})"

    text = (
        f"👤 <b>ВАШ ПРОФИЛЬ:</b> {display_name}\n\n"
        f"├ 🌍 Глобально: <b>{global_rank_name}</b>\n"
        f"├ 🏘 В чате: <b>{local_rank_name}</b>\n"
        f"├ ⭐ Уровень: <b>{stats.get('user_level', 1)}</b> · ✨ XP: <code>{xp_in_lvl}/{XP_PER_LEVEL}</code>\n"
        f"├ 💰 Баланс: <code>{format_currency(bal['user_balance_mora'])} 🪙</code> · <code>{format_currency(bal['user_balance_diamonds'])} 💎</code>\n"
        f"├ 💍 В браке: {married_text}\n"
        f"├ 🐾 Активный: {_active_pet_line(nursery_pets)}\n"
        f"├ 🔥 Стрик: <b>{streak_row.get('streak', 0)}</b> дн.\n"
        f"└ 💬 В чате (день/нед/всё): <code>{_msg_counts(stats)}</code>"
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

    # Nickname if set for this user in this chat
    nickname = await users_repo.get_nickname(db, target_id, chat_id)
    display_name = safe_html(nickname or target_name)

    stats = await chat_repo.get_chat_stats(db, target_id, chat_id)
    global_rank_id = await users_repo.get_global_rank(db, target_id)
    nursery_pets = await zoo_db.get_user_pets(db, target_id, placement="nursery")
    marriage = await marriage_repo.get_user_marriage(db, chat_id, target_id)

    global_rank_name = roles.get_global_rank_name(target_id, global_rank_id, developer_id=developer_id)
    local_rank_name = roles.get_local_rank_name(target_id, stats.get("local_rank", 0), developer_id=developer_id)

    married_text = "Нет"
    if marriage:
        p_name = marriage["user2_name"] if marriage["user1_id"] == target_id else marriage["user1_name"]
        dur = _marriage_duration(marriage.get("marriage_date"))
        married_text = f"<b>{safe_html(p_name)}</b> ({dur})"

    text = (
        f"🔍 <b>{display_name}</b> — {global_rank_name} · {local_rank_name}\n\n"
        f"├ ⭐ Уровень: <b>{stats.get('user_level', 1)}</b>\n"
        f"├ 💍 В браке: {married_text}\n"
        f"├ 🐾 Активный: {_active_pet_line(nursery_pets)}\n"
        f"└ 💬 В чате (день/нед/всё): <code>{_msg_counts(stats)}</code>"
    )
    await message.answer(text, parse_mode="HTML")


# ── бот анкета ────────────────────────────────────────────────────────────────

@router.message(TextCmd(["анкета"]))
async def cmd_anketa(message: types.Message, db, developer_id: int = 0):
    """Полная карточка о СЕБЕ с тегами (партнёр с тегом, глобальная статистика)."""
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

    # Nickname or TG name
    nickname = await users_repo.get_nickname(db, user_id, chat_id)
    display_name = safe_html(nickname or message.from_user.first_name)
    self_link = f'<a href="tg://user?id={user_id}">{display_name}</a>'

    global_rank_name = roles.get_global_rank_name(user_id, global_rank_id, developer_id=developer_id)
    local_rank_name = roles.get_local_rank_name(user_id, stats.get("local_rank", 0), developer_id=developer_id)

    married_text = "Нет"
    if marriage:
        p_name = marriage["user2_name"] if marriage["user1_id"] == user_id else marriage["user1_name"]
        dur = _marriage_duration(marriage.get("marriage_date"))
        married_text = f"Да — <b>{safe_html(p_name)}</b> ({dur})"

    pets_count = len(nursery_pets)
    active_pet = _active_pet_line(nursery_pets)
    local_msgs = _msg_counts(stats)
    global_msgs_str = f"{global_msgs['day']} / {global_msgs['week']} / {global_msgs['all_time']}"

    text = (
        f"📜 <b>АНКЕТА:</b> {self_link}\n\n"
        f"├ 🌍 {global_rank_name} · 🏘 {local_rank_name} · ⭐ Ур.{stats.get('user_level', 1)}\n"
        f"├ 💍 В браке: {married_text}\n"
        f"├ 🐾 Питомцев: {pets_count} · Активный: {active_pet}\n"
        f"├ 🔥 Стрик: <b>{streak_row.get('streak', 0)}</b> дн.\n"
        f"├ ⏳ В Предвестнике: <b>{_ecosystem_age(first_seen)}</b>\n"
        f"├ 💬 В чате (день/нед/всё): <code>{local_msgs}</code>\n"
        f"└ 🌐 Глобально (день/нед/всё): <code>{global_msgs_str}</code>"
    )
    await message.answer(text, parse_mode="HTML")
