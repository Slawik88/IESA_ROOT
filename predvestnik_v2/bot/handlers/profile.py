from aiogram import Router, types
from datetime import datetime
import aiosqlite

from infrastructure.repositories import economy, chat, users, marriages
from infrastructure.repositories import zoo as zoo_db
from services import roles
from services.utils import format_currency, safe_html, resolve_target, parse_dt, resolve_display_name
from services.zoo import format_pet_bonus_short
from services import ui
from bot.filters.text_commands import TextCmd
from core.constants import XP_PER_LEVEL
from core.registry import PET_SPECIES


def _fatigue_icon(fatigue: int) -> str:
    return ui.fatigue_icon(fatigue)


router = Router(name="profile_router")


def _pet_block(nursery_pets: list) -> str:
    if not nursery_pets:
        return "\n\n🐾 <b>ПИТОМЦЫ</b>\n└ <i>Питомник пуст</i>"
    role_map = {"active": "⚔️", "passive": "💤"}
    pet_lines = []
    for p in nursery_pets:
        species_name = PET_SPECIES.get(p['species_id'], {}).get('name', p['species_id'])
        role_icon = role_map.get(p['placement'], "📦")
        level = p.get('pet_level', 1) or 1
        fatigue = p.get('fatigue', 0)
        r_badge = ui.rarity_badge(p.get('rarity', 'common'))
        pet_lines.append(
            f"{role_icon} {r_badge} <b>{p['name']}</b> <i>{species_name}</i> · "
            f"Lv{level} · {ui.fatigue_icon(fatigue)} {fatigue}/100"
        )
    return "\n\n🐾 <b>ПИТОМЦЫ</b>\n" + ui.tree(pet_lines)


async def _build_profile_text(
    db, user_id: int, chat_id: int, display_name: str,
    *, is_self: bool, developer_id: int = 0,
) -> str:
    await zoo_db.apply_fatigue_decay(db, user_id)
    balance = await economy.get_balance(db, user_id)
    stats = await chat.get_chat_stats(db, user_id, chat_id)
    global_rank_id = await users.get_global_rank(db, user_id)
    nursery_pets = await zoo_db.get_user_pets(db, user_id, placement="nursery")

    global_rank_name = roles.get_global_rank_name(user_id, global_rank_id, developer_id=developer_id)
    local_rank_name = roles.get_local_rank_name(user_id, stats.get('local_rank', 0), developer_id=developer_id)

    # Marriage
    marriage = await marriages.get_user_marriage(db, user_id)
    if marriage:
        partner_id = marriage['user2_id'] if marriage['user1_id'] == user_id else marriage['user1_id']
        p_name = marriage['user2_name'] if marriage['user1_id'] == user_id else marriage['user1_name']
        p_name = await resolve_display_name(db, partner_id, chat_id, p_name)
        marriage_text = f"💍 в браке с <b>{p_name}</b>"
    else:
        marriage_text = "💔 <i>Одинок(а)</i>"

    # Protection
    is_immune = stats.get('is_immune', 0)
    immune_until = stats.get('immune_until')
    warns = stats.get('warnings', 0)
    protection_text = "нет"
    if is_immune:
        protection_text = "🛡 иммунитет"
    elif immune_until:
        try:
            dt = parse_dt(immune_until)
            if dt and dt > datetime.now():
                protection_text = f"🔰 щит до {dt.strftime('%d.%m %H:%M')}"
        except Exception:
            pass

    # Money
    mora = format_currency(balance['user_balance_mora'])
    diamonds = format_currency(balance['user_balance_diamonds'])

    # XP
    curr_xp = stats.get('user_xp', 0)
    level = stats.get('user_level', 1)
    xp_in_level = curr_xp % XP_PER_LEVEL
    xp_to_next = XP_PER_LEVEL - xp_in_level
    xp_bar = ui.bar(xp_in_level, XP_PER_LEVEL, length=10)

    # Bonus extras (balance sub-lines)
    extras = []
    hamster_income = await zoo_db.get_pending_hamster_income(db, user_id)
    if hamster_income > 0:
        extras.append(f"💰 Хомяки: ~{format_currency(hamster_income)} 🪙 <i>(не собрано)</i>")
    has_turtle = any(p['species_id'] == 'turtle' and p['fatigue'] < 100 for p in nursery_pets)
    if has_turtle:
        extras.append("🐢 <i>Черепаха: −10% к экспедициям</i>")
    active_pet = next((p for p in nursery_pets if p['placement'] == 'active'), None)
    if active_pet and active_pet['fatigue'] < 100:
        sp = active_pet['species_id']
        lvl = active_pet.get('pet_level', 1) or 1
        bonus_short = format_pet_bonus_short(sp, lvl)
        sp_name = PET_SPECIES.get(sp, {}).get('name', sp)
        if bonus_short:
            extras.append(f"🐾 {sp_name} Ур.{lvl}: <i>{bonus_short}</i>")
    extras_block = ("\n" + ui.tree(extras)) if extras else ""

    link = f'<a href="tg://user?id={user_id}">{display_name}</a>'
    head_emoji = "👤" if is_self else "🔍"
    head_word = "ПРОФИЛЬ" if is_self else "ДОСЬЕ"

    text = (
        f"{head_emoji} <b>{head_word}</b> — {link}\n"
        f"<code>🆔 {user_id}</code>\n\n"

        f"🌍 {global_rank_name}  ·  🏘 {local_rank_name}\n"
        f"{marriage_text}\n"
        f"⚠️ {warns} варн(ов)  ·  🛡 {protection_text}\n\n"

        f"💰 <b>{mora} 🪙 · {diamonds} 💎</b>{extras_block}\n\n"

        f"⭐ <b>Lv{level}</b>  <code>[{xp_bar}]</code>  {xp_in_level}/{XP_PER_LEVEL}"
    )
    if level < 999:
        text += f" · +{xp_to_next} XP до Lv{level + 1}"

    text += (
        f"\n📊 День {stats.get('user_messages_count_per_day', 0)} · "
        f"Неделя {stats.get('user_messages_count_per_week', 0)} · "
        f"Всего {stats.get('user_messages_count_all_time', 0)}"
    )

    text += _pet_block(nursery_pets)
    return text


# профиль/я/стат now handled by identity_router which calls cmd_profile
async def cmd_profile(message: types.Message, db: aiosqlite.Connection, developer_id: int = 0):
    if message.chat.type == "private":
        return await message.answer("❌ Эта команда доступна только в группах.")

    user_id = message.from_user.id
    chat_id = message.chat.id
    from services.utils import resolve_display_name
    name = await resolve_display_name(db, user_id, chat_id, message.from_user.first_name)

    text = await _build_profile_text(
        db, user_id, chat_id, name, is_self=True, developer_id=developer_id
    )
    await message.answer(text, parse_mode="HTML")


@router.message(TextCmd(["инфо", "досье"]))
async def cmd_user_info(message: types.Message, db: aiosqlite.Connection, text_args: str = None, developer_id: int = 0):
    if message.chat.type == "private":
        return

    target_id, target_name, extra_args = await resolve_target(message, db, text_args)

    if extra_args == "error_user_not_found":
        return await message.answer(
            "❌ <b>Пользователь не найден!</b>\n"
            "Бот его ещё не запомнил. Пусть напишет хоть одно сообщение в чат.",
            parse_mode="HTML"
        )

    if not target_id:
        return await message.answer(
            "ℹ️ <b>Использование:</b> <code>бот инфо, @юзер</code>\n"
            "Или ответьте на сообщение пользователя.",
            parse_mode="HTML"
        )

    text = await _build_profile_text(
        db, target_id, message.chat.id, safe_html(target_name),
        is_self=False, developer_id=developer_id,
    )
    await message.answer(text, parse_mode="HTML")
