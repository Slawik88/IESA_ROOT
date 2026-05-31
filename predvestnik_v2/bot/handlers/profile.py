from aiogram import Router, types
from datetime import datetime
import aiosqlite

from infrastructure.repositories import economy, chat, users, marriages
from infrastructure.repositories import zoo as zoo_db
from services import roles
from services.utils import format_currency, safe_html, resolve_target
from services.zoo import format_pet_bonus_short
from bot.filters.text_commands import TextCmd
from core.constants import XP_PER_LEVEL
from core.registry import PET_SPECIES


def _fatigue_icon(fatigue: int) -> str:
    if fatigue == 100:
        return "⛔"
    if fatigue >= 80:
        return "🔴"
    if fatigue >= 40:
        return "🟡"
    return "🟢"

router = Router(name="profile_router")

@router.message(TextCmd(["профиль", "стата", "кто я", "стат", "мой профиль"]))
async def cmd_profile(message: types.Message, db: aiosqlite.Connection, developer_id: int = 0):
    if message.chat.type == "private":
        return await message.answer("❌ Эта команда доступна только в группах.")

    user_id = message.from_user.id
    chat_id = message.chat.id
    raw_name = safe_html(message.from_user.first_name) 

    # 1. Сбор данных из разных таблиц
    await zoo_db.apply_fatigue_decay(db, user_id)
    balance = await economy.get_balance(db, user_id)
    stats = await chat.get_chat_stats(db, user_id, chat_id)
    global_rank_id = await users.get_global_rank(db, user_id)
    nursery_pets = await zoo_db.get_user_pets(db, user_id, placement="nursery")
    
    # 2. ОПРЕДЕЛЕНИЕ РАНГОВ (С передачей developer_id для возврата ранга Бога)
    global_rank_name = roles.get_global_rank_name(
        user_id, 
        global_rank_id, 
        developer_id=developer_id
    )
    local_rank_name = roles.get_local_rank_name(
        user_id, 
        stats.get('local_rank', 0), 
        developer_id=developer_id
    )

    # 3. ЛОГИКА СЕМЬИ
    marriage = await marriages.get_user_marriage(db, chat_id, user_id)
    marriage_text = "💔 <i>Одинок(а)</i>"
    if marriage:
        p_id = marriage['user2_id'] if marriage['user1_id'] == user_id else marriage['user1_id']
        p_name = marriage['user2_name'] if marriage['user1_id'] == user_id else marriage['user1_name']
        marriage_text = f'💍 в браке с <a href="tg://user?id={p_id}">{safe_html(p_name)}</a>'

    # 4. СИСТЕМА ЗАЩИТЫ И ВАРНОВ
    is_immune = stats.get('is_immune', 0)
    immune_until = stats.get('immune_until')
    warns = stats.get('warnings', 0)
    
    protection_text = "❌ <i>Отсутствует</i>"
    if is_immune:
        protection_text = "🛡 <b>Абсолютный иммунитет</b>"
    elif immune_until:
        try:
            # Используем осознанную дату
            dt = parse_dt(immune_until)
            if dt > datetime.now():
                protection_text = f"🔰 <b>Временный щит</b> <i>(до {dt.strftime('%d.%m %H:%M')})</i>"
        except Exception:
            pass

    # 5. ДАННЫЕ ДЛЯ ВЫВОДА
    mora = format_currency(balance['user_balance_mora'])
    diamonds = format_currency(balance['user_balance_diamonds'])
    has_turtle = any(p['species_id'] == 'turtle' and p['fatigue'] < 100 for p in nursery_pets)

    # Hamster accumulated income
    hamster_income = await zoo_db.get_pending_hamster_income(db, user_id)

    curr_xp = stats.get('user_xp', 0)
    xp_in_level = curr_xp % XP_PER_LEVEL
    xp_progress = f"{xp_in_level} / {XP_PER_LEVEL}"
    xp_to_next = XP_PER_LEVEL - xp_in_level

    profile_link = f'<a href="tg://user?id={user_id}">{raw_name}</a>'

    active_pet = next((p for p in nursery_pets if p['placement'] == 'active'), None)

    # 6. ФОРМИРОВАНИЕ ТЕКСТА — строим список строк, последней ставим └
    bal_lines = [f"🪙 Мора: <code>{mora}</code>"]
    if hamster_income > 0:
        bal_lines.append(f"💰 Хомяки (не собрано): <code>~{format_currency(hamster_income)}</code> 🪙")
    bal_lines.append(f"💎 Алмазы: <code>{diamonds}</code>")
    if has_turtle:
        bal_lines.append("🐢 <i>Черепаха: -10% к стоимости экспедиций</i>")
    if active_pet and active_pet['fatigue'] < 100:
        sp = active_pet['species_id']
        level = active_pet.get('pet_level', 1) or 1
        bonus_short = format_pet_bonus_short(sp, level)
        sp_name = PET_SPECIES.get(sp, {}).get('name', sp)
        if bonus_short:
            bal_lines.append(f"🐾 {sp_name} Ур.{level}: <i>{bonus_short}</i>")

    balance_lines_fmt = [f"├ {l}" for l in bal_lines]
    balance_lines_fmt[-1] = "└" + balance_lines_fmt[-1][1:]
    balance_section = "💰 <b>ЛИЧНЫЙ БАЛАНС</b>\n" + "\n".join(balance_lines_fmt) + "\n\n"

    text = (
        f"👤 <b>ПРОФИЛЬ: {profile_link}</b>\n"
        f"<code>ID: {user_id}</code>\n\n"

        f"🌐 <b>СТАТУС И ОТНОШЕНИЯ</b>\n"
        f"├ 🌍 Глобально: <b>{global_rank_name}</b>\n"
        f"├ 🏘️ В чате: <b>{local_rank_name}</b>\n"
        f"└ 💞 Семья: {marriage_text}\n\n"

        f"⚖️ <b>СИСТЕМА НАКАЗАНИЙ</b>\n"
        f"├ ⚠️ Предупреждения: <code>{warns}</code>\n"
        f"└ 🛡 Защита от чистки: {protection_text}\n\n"

        + balance_section +

        f"⭐ <b>УРОВЕНЬ И ОПЫТ</b>\n"
        f"├ 📊 Уровень: <code>{stats.get('user_level', 1)}</code>\n"
        f"├ ✨ Прогресс: <code>{xp_progress}</code>\n"
        f"└ 📈 До повышения: <code>{xp_to_next}</code> XP\n\n"

        f"📈 <b>АКТИВНОСТЬ</b>\n"
        f"├ 📅 День: <code>{stats.get('user_messages_count_per_day', 0)}</code>\n"
        f"├ 🗓️ Неделя: <code>{stats.get('user_messages_count_per_week', 0)}</code>\n"
        f"└ 🏆 Всего: <code>{stats.get('user_messages_count_all_time', 0)}</code>"
    )

    # 7. БЛОК ПИТОМЦЕВ
    if nursery_pets:
        role_map = {"active": "⚔️", "passive": "💤"}
        pet_lines = []
        for p in nursery_pets:
            species_name = PET_SPECIES.get(p['species_id'], {}).get('name', p['species_id'])
            role_icon = role_map.get(p['placement'], "📦")
            level = p.get('pet_level', 1) or 1
            fatigue = p.get('fatigue', 0)
            f_icon = _fatigue_icon(fatigue)
            pet_lines.append(
                f"├ {role_icon} <b>{p['name']}</b> <i>({species_name})</i> · Ур. {level} · {fatigue}/100 {f_icon}"
            )
        if pet_lines:
            pet_lines[-1] = pet_lines[-1].replace("├", "└")
        text += "\n\n🐾 <b>ПИТОМЦЫ</b>\n" + "\n".join(pet_lines)
    else:
        text += "\n\n🐾 <b>ПИТОМЦЫ</b>\n└ <i>Питомник пуст</i>"

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

    balance = await economy.get_balance(db, target_id)
    stats = await chat.get_chat_stats(db, target_id, message.chat.id)
    global_rank_id = await users.get_global_rank(db, target_id)
    nursery_pets = await zoo_db.get_user_pets(db, target_id, placement="nursery")

    global_rank_name = roles.get_global_rank_name(target_id, global_rank_id, developer_id=developer_id)
    local_rank_name = roles.get_local_rank_name(target_id, stats.get('local_rank', 0), developer_id=developer_id)

    marriage = await marriages.get_user_marriage(db, message.chat.id, target_id)
    marriage_text = "💔 <i>Одинок(а)</i>"
    if marriage:
        p_id = marriage['user2_id'] if marriage['user1_id'] == target_id else marriage['user1_id']
        p_name = marriage['user2_name'] if marriage['user1_id'] == target_id else marriage['user1_name']
        marriage_text = f'💍 в браке с <a href="tg://user?id={p_id}">{safe_html(p_name)}</a>'

    is_immune = stats.get('is_immune', 0)
    immune_until = stats.get('immune_until')
    warns = stats.get('warnings', 0)

    protection_text = "❌ <i>Отсутствует</i>"
    if is_immune:
        protection_text = "🛡 <b>Абсолютный иммунитет</b>"
    elif immune_until:
        try:
            dt = parse_dt(immune_until)
            if dt > datetime.now():
                protection_text = f"🔰 <b>Временный щит</b> <i>(до {dt.strftime('%d.%m %H:%M')})</i>"
        except Exception:
            pass

    mora = format_currency(balance['user_balance_mora'])
    diamonds = format_currency(balance['user_balance_diamonds'])

    curr_xp = stats.get('user_xp', 0)
    xp_in_level = curr_xp % XP_PER_LEVEL
    xp_progress = f"{xp_in_level} / {XP_PER_LEVEL}"
    xp_to_next = XP_PER_LEVEL - xp_in_level

    target_link = f'<a href="tg://user?id={target_id}">{safe_html(target_name)}</a>'

    text = (
        f"🔍 <b>ДОСЬЕ: {target_link}</b>\n"
        f"<code>ID: {target_id}</code>\n\n"

        f"🌐 <b>СТАТУС И ОТНОШЕНИЯ</b>\n"
        f"├ 🌍 Глобально: <b>{global_rank_name}</b>\n"
        f"├ 🏘️ В чате: <b>{local_rank_name}</b>\n"
        f"└ 💞 Семья: {marriage_text}\n\n"

        f"⚖️ <b>СИСТЕМА НАКАЗАНИЙ</b>\n"
        f"├ ⚠️ Предупреждения: <code>{warns}</code>\n"
        f"└ 🛡 Защита от чистки: {protection_text}\n\n"

        f"💰 <b>БАЛАНС</b>\n"
        f"├ 🪙 Мора: <code>{mora}</code>\n"
        f"└ 💎 Алмазы: <code>{diamonds}</code>\n\n"

        f"⭐ <b>УРОВЕНЬ И ОПЫТ</b>\n"
        f"├ 📊 Уровень: <code>{stats.get('user_level', 1)}</code>\n"
        f"├ ✨ Прогресс: <code>{xp_progress}</code>\n"
        f"└ 📈 До повышения: <code>{xp_to_next}</code> XP\n\n"

        f"📈 <b>АКТИВНОСТЬ</b>\n"
        f"├ 📅 День: <code>{stats.get('user_messages_count_per_day', 0)}</code>\n"
        f"├ 🗓️ Неделя: <code>{stats.get('user_messages_count_per_week', 0)}</code>\n"
        f"└ 🏆 Всего: <code>{stats.get('user_messages_count_all_time', 0)}</code>"
    )

    if nursery_pets:
        role_map = {"active": "⚔️", "passive": "💤"}
        pet_lines = []
        for p in nursery_pets:
            species_name = PET_SPECIES.get(p['species_id'], {}).get('name', p['species_id'])
            role_icon = role_map.get(p['placement'], "📦")
            level = p.get('pet_level', 1) or 1
            fatigue = p.get('fatigue', 0)
            f_icon = _fatigue_icon(fatigue)
            pet_lines.append(
                f"├ {role_icon} <b>{p['name']}</b> <i>({species_name})</i> · Ур. {level} · {fatigue}/100 {f_icon}"
            )
        if pet_lines:
            pet_lines[-1] = pet_lines[-1].replace("├", "└")
        text += "\n\n🐾 <b>ПИТОМЦЫ</b>\n" + "\n".join(pet_lines)
    else:
        text += "\n\n🐾 <b>ПИТОМЦЫ</b>\n└ <i>Питомник пуст</i>"

    await message.answer(text, parse_mode="HTML")