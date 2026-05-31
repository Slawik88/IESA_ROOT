# bot/handlers/zoo.py
import random
from datetime import datetime

from aiogram import Router, types, F
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters.callback_data import CallbackData

from bot.filters.text_commands import TextCmd
from infrastructure.repositories import zoo as zoo_db
from infrastructure.repositories.economy import add_item, remove_item, add_balance, get_item_quantity
from core.registry import PET_SPECIES
from core.constants import (
    PET_PLACEMENT_FATIGUE_RESTORE,
    HAMSTER_BONUSES,
    PET_LEVEL_DUPLICATES,
    MAX_PET_COPIES,
    get_pet_bonus,
    get_total_duplicates_for_level,
)
from services.zoo import (
    get_wolf_fatigue_reduction,
    is_wolf_active_slot,
    get_active_wolf_food_extra,
    apply_pet_milestones,
)
from infrastructure.repositories.zoo import grant_duplicate
from services.quests import increment_metric as quest_increment


router = Router(name="zoo_router")
from bot.middlewares.module_check_mw import ModuleCheckMiddleware
router.message.middleware(ModuleCheckMiddleware("module_zoo"))


class ZooCB(CallbackData, prefix="zoo"):
    action: str
    pet_id: int = 0
    page: int = 1


# ── Helpers ───────────────────────────────────────────────────────────────────

def _calc_hamster_income(
    last_collection: str | None,
    hamsters: list[dict],
) -> tuple[int, str]:
    """Returns (accumulated_mora, human_time_str). `hamsters` is the list of
    {pet_level, fatigue} dicts. Lv4+ hamsters keep earning at fatigue == 100."""
    if not last_collection or not hamsters:
        return 0, "—"
    try:
        last_dt = datetime.strptime(last_collection, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return 0, "—"
    hours = (datetime.now() - last_dt).total_seconds() / 3600.0

    total = 0.0
    for h in hamsters:
        level = h.get("pet_level") or 1
        bonus = HAMSTER_BONUSES.get(max(1, min(10, level)), {})
        if h.get("fatigue", 0) >= 100 and not bonus.get("ignore_exhaustion", False):
            continue
        rate = bonus.get("mora_per_hour", 0.0)
        cap = bonus.get("cap", 0)
        total += min(hours * rate, float(cap))

    time_str = f"{int(hours * 60)} мин." if hours < 1 else f"{hours:.1f} ч."
    return int(total), time_str


def _duplicates_bar(rarity: str, pet_level: int, duplicates: int) -> tuple[str, str]:
    """Returns (bar, label) for duplicate progress within the current level.
    Lv10 → full bar + 'MAX'."""
    if pet_level >= 10:
        return "██████", "MAX"
    table = PET_LEVEL_DUPLICATES.get(rarity, PET_LEVEL_DUPLICATES["common"])
    spent_for_current = get_total_duplicates_for_level(rarity, pet_level)
    need_to_next = table.get(pet_level + 1, 0)
    have_in_level = duplicates - spent_for_current
    ratio = max(0.0, min(1.0, have_in_level / need_to_next)) if need_to_next > 0 else 1.0
    filled = round(ratio * 5)
    bar = "█" * filled + "░" * (5 - filled)
    return bar, f"{have_in_level}/{need_to_next}"


# ── Render functions ──────────────────────────────────────────────────────────

async def render_main_zoo(message: types.Message, db, user_id: int, is_edit: bool = False):
    await zoo_db.apply_fatigue_decay(db, user_id)

    stats = await zoo_db.get_zoo_stats(db, user_id)
    nursery_pets = await zoo_db.get_user_pets(db, user_id, placement="nursery")

    lines = [f"🐾 <b>ПИТОМНИК:</b> {message.from_user.first_name}"]
    lines.append(f"📦 Слоты: <b>{len(nursery_pets)}/{stats['max_slots']}</b>\n")

    exhausted_names = []

    if not nursery_pets:
        lines.append("<i>Ваш питомник пуст. Перейдите на Склад, чтобы разместить животных.</i>")
    else:
        for p in nursery_pets:
            species_data = PET_SPECIES.get(p["species_id"], {})
            status_icon = "⚔️ Активный" if p["placement"] == "active" else "💤 Пассивный"
            pet_level = p.get("pet_level", 1) or 1
            lines.append(f"<b>{p['name']}</b> — {species_data.get('name', 'Неизвестный')} (Ур. {pet_level})")
            lines.append(f"├ Роль: {status_icon}")
            lines.append(f"└ Усталость: {p['fatigue']}/100\n")
            if p["fatigue"] == 100:
                exhausted_names.append(p["name"])

    if exhausted_names:
        lines.append(f"😴 <i>Без сил (бонусы не работают): {', '.join(exhausted_names)}</i>")

    # Hamster accumulated income preview (Lv4+ keeps earning even at fatigue==100)
    productive_hamsters = []
    for p in nursery_pets:
        if p["species_id"] != "hamster":
            continue
        bonus = HAMSTER_BONUSES.get(max(1, min(10, p.get("pet_level") or 1)), {})
        if p["fatigue"] < 100 or bonus.get("ignore_exhaustion", False):
            productive_hamsters.append(p)
    if productive_hamsters:
        accumulated, time_str = _calc_hamster_income(stats.get("last_income_collection"), productive_hamsters)
        if accumulated > 0:
            lines.append(f"💰 <i>Хомяки накопили: ~{accumulated} Моры за {time_str}</i>")

    builder = InlineKeyboardBuilder()
    builder.button(text="🔄 Покормить всех (Баз. корм)", callback_data=ZooCB(action="feed_all", page=1))
    # Show food_super button if user has any in inventory
    super_qty = await get_item_quantity(db, user_id, "food_super")
    if super_qty > 0:
        builder.button(text=f"💊 Суперкорм ×{super_qty} (−60 акт. + −5 всем)",
                        callback_data=ZooCB(action="feed_super", page=1))
    builder.button(text="💰 Собрать доход", callback_data=ZooCB(action="collect", page=1))
    builder.button(text="📦 Открыть Склад", callback_data=ZooCB(action="storage", page=1))
    builder.adjust(1, 1, 1, 1)

    text = "\n".join(lines)
    if is_edit:
        await message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    else:
        await message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")


async def render_storage(message: types.Message, db, user_id: int, page: int):
    await zoo_db.apply_fatigue_decay(db, user_id)

    storage_pets = await zoo_db.get_user_pets(db, user_id, placement="storage")

    lines = [f"📦 <b>СКЛАД ЖИВОТНЫХ</b> (Стр. {page})"]
    lines.append("<i>Здесь отдыхают ваши запасные питомцы.</i>\n")

    per_page = 5
    total_pages = max(1, (len(storage_pets) + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))

    start_idx = (page - 1) * per_page
    pets_on_page = storage_pets[start_idx: start_idx + per_page]

    builder = InlineKeyboardBuilder()

    if not storage_pets:
        lines.append("Склад пуст. Откройте яйцо в магазине!")
    else:
        for idx, p in enumerate(pets_on_page, start=start_idx + 1):
            species_data = PET_SPECIES.get(p["species_id"], {})
            lines.append(f"<b>{idx}.</b> {p['name']} <i>({species_data.get('name', '???')})</i>")
            builder.button(
                text=f"⚙️ Настроить {p['name']}",
                callback_data=ZooCB(action="pet_view", pet_id=p["id"], page=page),
            )

    nav_buttons = []
    if page > 1:
        nav_buttons.append(
            InlineKeyboardBuilder()
            .button(text="⬅️ Назад", callback_data=ZooCB(action="storage", page=page - 1))
            .as_markup().inline_keyboard[0][0]
        )
    if page < total_pages:
        nav_buttons.append(
            InlineKeyboardBuilder()
            .button(text="Вперед ➡️", callback_data=ZooCB(action="storage", page=page + 1))
            .as_markup().inline_keyboard[0][0]
        )
    if nav_buttons:
        builder.row(*nav_buttons)
    builder.row(
        InlineKeyboardBuilder()
        .button(text="🔙 Назад в Питомник", callback_data=ZooCB(action="main"))
        .as_markup().inline_keyboard[0][0]
    )
    builder.adjust(*[1] * len(pets_on_page), len(nav_buttons) if nav_buttons else 1, 1)

    await message.edit_text("\n".join(lines), reply_markup=builder.as_markup(), parse_mode="HTML")


# ── Command handlers ──────────────────────────────────────────────────────────

@router.message(TextCmd(["зоопарк", "питомник", "питомцы", "питомци", "мои питомцы", "мои питомци"]))
async def cmd_zoo(message: types.Message, db):
    if message.chat.type == "private":
        return
    await render_main_zoo(message, db, message.from_user.id, is_edit=False)


@router.callback_query(ZooCB.filter(F.action == "main"))
async def cb_zoo_main(query: types.CallbackQuery, db):
    await render_main_zoo(query.message, db, query.from_user.id, is_edit=True)
    await query.answer()


@router.callback_query(ZooCB.filter(F.action == "storage"))
async def cb_zoo_storage(query: types.CallbackQuery, callback_data: ZooCB, db):
    await render_storage(query.message, db, query.from_user.id, callback_data.page)
    await query.answer()


# ── Pet card ──────────────────────────────────────────────────────────────────

@router.callback_query(ZooCB.filter(F.action == "pet_view"))
async def cb_pet_view(query: types.CallbackQuery, callback_data: ZooCB, db):
    pet = await zoo_db.get_pet_by_id(db, callback_data.pet_id)
    if not pet:
        return await query.answer("❌ Питомец не найден! Возможно, он был отпущен.", show_alert=True)

    species_data = PET_SPECIES.get(pet["species_id"], {})
    rarity_emojis = {
        "common": "⚪️ Обычный", "rare": "🔵 Редкий",
        "epic": "🟣 Эпик",      "legendary": "🟡 Легендарный",
    }
    status_map = {
        "storage": "📦 На складе",
        "active":  "⚔️ Активный спутник",
        "passive": "💤 В питомнике (Пассив)",
    }

    pet_level = pet.get("pet_level", 1) or 1
    duplicates = pet.get("duplicates_collected", 0) or 0
    copy_index = pet.get("copy_index", 1) or 1
    rarity = pet.get("rarity", "common")

    lines = ["🔍 <b>ИНФОРМАЦИЯ О ПИТОМЦЕ</b>"]
    lines.append(
        f"Имя: <b>{pet['name']}</b> <i>({species_data.get('name', '???')})</i> · "
        f"Копия {copy_index}/{MAX_PET_COPIES}"
    )
    lines.append(f"Редкость: {rarity_emojis.get(pet['rarity'], 'Неизвестно')}")
    lines.append(f"Усталость: <b>{pet['fatigue']}/100</b>")
    lines.append(f"Бафф: {species_data.get('desc', 'Нет')}")

    bar, label = _duplicates_bar(rarity, pet_level, duplicates)
    if pet_level >= 10:
        lines.append(f"Уровень: <b>{pet_level}</b> ✨ Макс!  [{bar}]")
    else:
        lines.append(f"Уровень: <b>{pet_level}</b>  [{bar}] {label} к Ур.{pet_level + 1}")

    lines.append(f"\nЛокация: <b>{status_map.get(pet['placement'], 'Неизвестно')}</b>")

    if pet["fatigue"] == 100:
        lines.append("\n<i>😴 Питомец полностью устал — бонусы отключены. Покормите его.</i>")
    if pet["is_summoned"]:
        lines.append("\n<i>✨ Призван из Осколков (не даёт осколок при распылении)</i>")

    builder = InlineKeyboardBuilder()
    move_note = f"(+{PET_PLACEMENT_FATIGUE_RESTORE} уст.)"
    if pet["placement"] == "storage":
        builder.button(
            text=f"⚔️ Сделать Активным {move_note}",
            callback_data=ZooCB(action="equip_act", pet_id=pet["id"], page=callback_data.page),
        )
        builder.button(
            text=f"💤 В Питомник {move_note}",
            callback_data=ZooCB(action="equip_pas", pet_id=pet["id"], page=callback_data.page),
        )
    else:
        builder.button(
            text=f"📦 Убрать на Склад {move_note}",
            callback_data=ZooCB(action="store", pet_id=pet["id"], page=callback_data.page),
        )

    shard_text = " (0 Осколков)" if pet["is_summoned"] else " (1 Осколок)"
    builder.button(
        text=f"🔥 Отпустить на волю{shard_text}",
        callback_data=ZooCB(action="confirm_release", pet_id=pet["id"], page=callback_data.page),
    )

    # Star dust buttons: show only if pet is not Lv10 and user owns the item
    if pet_level < 10:
        dust_s = await get_item_quantity(db, query.from_user.id, "star_dust_s")
        dust_l = await get_item_quantity(db, query.from_user.id, "star_dust_l")
        if dust_s > 0:
            builder.button(
                text=f"🌟 Звёздная пыль ×{dust_s} → +1 дубликат",
                callback_data=ZooCB(action="use_dust_s", pet_id=pet["id"], page=callback_data.page),
            )
        if dust_l > 0:
            builder.button(
                text=f"✨ Небесная пыль ×{dust_l} → +5 дубликатов",
                callback_data=ZooCB(action="use_dust_l", pet_id=pet["id"], page=callback_data.page),
            )

    builder.button(
        text="🔙 Назад на Склад",
        callback_data=ZooCB(action="storage", page=callback_data.page),
    )
    builder.adjust(1, 1, 1, 1)

    await query.message.edit_text("\n".join(lines), reply_markup=builder.as_markup(), parse_mode="HTML")
    await query.answer()


# ── Pet movement (§2 atomic, §7 no-block, §9 wolf cost reduction) ─────────────

@router.callback_query(ZooCB.filter(F.action.in_(["equip_act", "equip_pas", "store"])))
async def cb_pet_move(query: types.CallbackQuery, callback_data: ZooCB, db):
    user_id = query.from_user.id
    pet_id = callback_data.pet_id
    new_placement = (
        "active"  if callback_data.action == "equip_act" else
        "passive" if callback_data.action == "equip_pas" else
        "storage"
    )

    try:
        # BEGIN IMMEDIATE acquires a write lock before any reads — prevents TOCTOU races
        await db.execute("BEGIN IMMEDIATE")

        pet = await zoo_db.get_pet_by_id(db, pet_id)
        if not pet:
            await db.rollback()
            return await query.answer("❌ Питомец не найден!", show_alert=True)

        if new_placement != "storage":
            nursery_count = await zoo_db.get_nursery_count(db, user_id)
            stats = await zoo_db.get_zoo_stats(db, user_id)
            if nursery_count >= stats["max_slots"]:
                await db.rollback()
                return await query.answer(
                    f"❌ Питомник: {nursery_count}/{stats['max_slots']} слотов занято. Уберите кого-то на склад.",
                    show_alert=True,
                )

            if new_placement == "active":
                active_count = await zoo_db.get_active_count(db, user_id)
                if active_count > 0:
                    await db.rollback()
                    return await query.answer(
                        "❌ У вас уже есть Активный питомец! Сначала уберите его.",
                        show_alert=True,
                    )

            species_count = await zoo_db.get_species_in_nursery_count(db, user_id, pet["species_id"])
            if species_count > 0:
                await db.rollback()
                return await query.answer(
                    "❌ В питомнике уже находится питомец такого вида! Ищите синергию.",
                    show_alert=True,
                )

        # Apply wolf reduction to movement fatigue cost
        wolf_reduction = await get_wolf_fatigue_reduction(db, user_id)
        fatigue_cost = int(PET_PLACEMENT_FATIGUE_RESTORE * (1.0 - wolf_reduction))

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if new_placement != "storage":
            # Reset fatigue decay timer when entering nursery
            await db.execute(
                "UPDATE pets SET placement = ?, fatigue = MIN(100, fatigue + ?), last_fatigue_update = ? WHERE id = ?",
                (new_placement, fatigue_cost, now_str, pet["id"]),
            )
        else:
            await db.execute(
                "UPDATE pets SET placement = ?, fatigue = MIN(100, fatigue + ?) WHERE id = ?",
                (new_placement, fatigue_cost, pet["id"]),
            )

        await db.commit()

    except Exception:
        await db.rollback()
        return await query.answer("❌ Ошибка при перемещении.", show_alert=True)

    updated_pet = await zoo_db.get_pet_by_id(db, pet_id)
    tired_note = " (питомец устал — бонусы отключены!)" if updated_pet and updated_pet["fatigue"] == 100 else ""

    await query.answer(
        f"✅ Питомец перемещён (+{fatigue_cost} уст.){tired_note}",
        show_alert=bool(tired_note),
    )
    callback_data.action = "pet_view"
    await cb_pet_view(query, callback_data, db)


# ── Release flow ──────────────────────────────────────────────────────────────

@router.callback_query(ZooCB.filter(F.action == "confirm_release"))
async def cb_confirm_release(query: types.CallbackQuery, callback_data: ZooCB, db):
    pet = await zoo_db.get_pet_by_id(db, callback_data.pet_id)
    if not pet:
        return await query.answer("❌ Питомец не найден!", show_alert=True)

    shard_note = (
        "Осколок Души не будет выдан (призванный)."
        if pet["is_summoned"]
        else "Вы получите 1 Осколок Души."
    )
    species_data = PET_SPECIES.get(pet["species_id"], {})

    builder = InlineKeyboardBuilder()
    builder.button(
        text="✅ Да, отпустить",
        callback_data=ZooCB(action="do_release", pet_id=callback_data.pet_id, page=callback_data.page),
    )
    builder.button(
        text="❌ Нет, назад",
        callback_data=ZooCB(action="pet_view", pet_id=callback_data.pet_id, page=callback_data.page),
    )
    builder.adjust(2)

    await query.message.edit_text(
        f"⚠️ <b>ПОДТВЕРЖДЕНИЕ</b>\n\n"
        f"Вы хотите отпустить питомца <b>{pet['name']}</b> ({species_data.get('name', '?')})?\n"
        f"<i>Это действие необратимо. {shard_note}</i>",
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )
    await query.answer()


@router.callback_query(ZooCB.filter(F.action == "do_release"))
async def cb_pet_release(query: types.CallbackQuery, callback_data: ZooCB, db):
    pet = await zoo_db.get_pet_by_id(db, callback_data.pet_id)
    if not pet:
        return await query.answer("❌ Питомец не найден!", show_alert=True)

    try:
        await db.execute("BEGIN TRANSACTION")
        await db.execute("DELETE FROM pets WHERE id = ?", (pet["id"],))
        msg = "🔥 Питомец отпущен на волю."
        if not pet["is_summoned"]:
            await add_item(db, query.from_user.id, "soul_shard", 1)
            msg += " Вы получили 1 Осколок Души!"
        await db.commit()
        await query.answer(msg, show_alert=True)
        await render_storage(query.message, db, query.from_user.id, callback_data.page)
    except Exception:
        await db.rollback()
        await query.answer("❌ Ошибка базы данных.", show_alert=True)


# ── Feed all (§6 dragon free food, §9 wolf extra restore, §15 pet XP) ─────────

@router.callback_query(ZooCB.filter(F.action == "feed_all"))
async def cb_zoo_feed_all(query: types.CallbackQuery, db):
    user_id = query.from_user.id

    pets = await zoo_db.get_user_pets(db, user_id, placement="nursery")
    hungry_pets = [p for p in pets if p["fatigue"] > 0]

    if not hungry_pets:
        return await query.answer("🟢 Все ваши питомцы уже сыты!", show_alert=True)

    food_count = await get_item_quantity(db, user_id, "food_basic")
    if food_count <= 0:
        return await query.answer(
            "❌ У вас нет Базового корма! Купите его через «бот магазин».", show_alert=True
        )

    wolf_active = await is_wolf_active_slot(db, user_id)
    wolf_food_extra = await get_active_wolf_food_extra(db, user_id) if wolf_active else 0
    restore_per_food = 15 + wolf_food_extra

    # Dragon free-food chance from level curve.
    dragon_level = await zoo_db.get_active_species_level(db, user_id, "dragon")
    dragon_free_chance = (
        get_pet_bonus("dragon", dragon_level).get("free_food_chance", 0.0)
        if dragon_level > 0 else 0.0
    )

    actions_taken = 0
    food_used = 0
    for p in hungry_pets:
        while p["fatigue"] > 0 and actions_taken < food_count:
            p["fatigue"] = max(0, p["fatigue"] - restore_per_food)
            actions_taken += 1
            if not (dragon_free_chance > 0 and random.random() < dragon_free_chance):
                food_used += 1

    try:
        for p in hungry_pets:
            await db.execute("UPDATE pets SET fatigue = ? WHERE id = ?", (p["fatigue"], p["id"]))

        if food_used > 0:
            await remove_item(db, user_id, "food_basic", food_used, commit=False)
        await db.commit()

        # Quest: pet_feeds_today
        if food_used > 0:
            await quest_increment(db, user_id, query.message.chat.id, "pet_feeds_today", delta=1.0)
            await db.commit()

        msg = f"🥩 Потрачено {food_used} ед. Базового корма."
        if wolf_food_extra > 0:
            msg += f" (🐺 Волк: +{wolf_food_extra} к восстановлению)"
        if dragon_free_chance > 0 and food_used < actions_taken:
            saved = actions_taken - food_used
            msg += f" (🐉 Дракон сэкономил: {saved} ед.)"
        await query.answer(msg, show_alert=True)
        await render_main_zoo(query.message, db, user_id, is_edit=True)
    except Exception:
        await db.rollback()
        await query.answer("❌ Ошибка БД при кормлении.", show_alert=True)


# ── Collect hamster income (§3/§8 accumulative model, §6 dragon bonus) ───────

@router.callback_query(ZooCB.filter(F.action == "collect"))
async def cb_zoo_collect(query: types.CallbackQuery, db):
    user_id = query.from_user.id

    pets = await zoo_db.get_user_pets(db, user_id, placement="nursery")
    # Lv4+ hamsters keep collecting even at fatigue == 100 (HAMSTER_BONUSES.ignore_exhaustion)
    productive_hamsters = []
    for p in pets:
        if p["species_id"] != "hamster":
            continue
        bonus = HAMSTER_BONUSES.get(max(1, min(10, p.get("pet_level") or 1)), {})
        if p["fatigue"] < 100 or bonus.get("ignore_exhaustion", False):
            productive_hamsters.append(p)

    if not productive_hamsters:
        return await query.answer(
            "❌ В Питомнике нет бодрствующих Хомяков-банкиров.", show_alert=True
        )

    stats = await zoo_db.get_zoo_stats(db, user_id)
    accumulated, _ = _calc_hamster_income(stats.get("last_income_collection"), productive_hamsters)

    if accumulated < 1:
        return await query.answer(
            "⏳ Хомяки ещё не накопили Мору. Попробуйте через несколько минут.", show_alert=True
        )

    # Hamster Lv8+: 5% chance per hamster to double its mora at collection.
    # Hamster Lv10: +0.5 💎/day capstone (one diamond grant per real day).
    double_mora_bonus = 0
    diamond_bonus = 0.0
    today_str = datetime.now().strftime("%Y-%m-%d")
    last_collect_day = (stats.get("last_income_collection") or "")[:10]
    for h in productive_hamsters:
        b = HAMSTER_BONUSES.get(max(1, min(10, h.get("pet_level") or 1)), {})
        if b.get("double_chance", 0.0) > 0 and random.random() < b["double_chance"]:
            double_mora_bonus += int(accumulated / max(1, len(productive_hamsters)))
        # daily_diamond is "per real day": grant only if last_collection was a previous day.
        if b.get("daily_diamond", 0.0) > 0 and last_collect_day != today_str:
            diamond_bonus = max(diamond_bonus, b["daily_diamond"])

    # Dragon flat bonus on collection (level-curve).
    dragon_level = await zoo_db.get_active_species_level(db, user_id, "dragon")
    dragon_bonus_mora = (
        int(get_pet_bonus("dragon", dragon_level).get("hamster_collect_bonus", 0.0))
        if dragon_level > 0 else 0
    )

    total_mora = accumulated + double_mora_bonus + dragon_bonus_mora

    try:
        await add_balance(db, user_id, mora=total_mora, diamonds=diamond_bonus, commit=False,
                          source="hamster_collect")
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        await db.execute(
            "UPDATE user_zoo_stats SET last_income_collection = ? WHERE user_id = ?",
            (now_str, user_id),
        )
        await db.commit()

        msg = f"💸 Вы собрали {accumulated} Моры со своих Хомяков!"
        if double_mora_bonus > 0:
            msg += f"\n🎰 Хомяк-удачник: +{double_mora_bonus} Моры!"
        if dragon_bonus_mora > 0:
            msg += f"\n🐉 Дракон добавил бонус: +{dragon_bonus_mora} Моры!"
        if diamond_bonus > 0:
            msg += f"\n💎 Капстоун Хомяка: +{diamond_bonus} Алмаза!"
        await query.answer(msg, show_alert=True)
        await render_main_zoo(query.message, db, user_id, is_edit=True)
    except Exception:
        await db.rollback()
        await query.answer("❌ Ошибка при сборе дохода.", show_alert=True)


# ── food_super: −60 active, −5 all nursery ────────────────────────────────────

@router.callback_query(ZooCB.filter(F.action == "feed_super"))
async def cb_zoo_feed_super(query: types.CallbackQuery, db):
    user_id = query.from_user.id
    qty = await get_item_quantity(db, user_id, "food_super")
    if qty < 1:
        return await query.answer("❌ Нет Суперкорма в инвентаре.", show_alert=True)

    pets = await zoo_db.get_user_pets(db, user_id, placement="nursery")
    active_pet = next((p for p in pets if p["placement"] == "active"), None)
    if not active_pet:
        return await query.answer("❌ Нет активного питомца в питомнике.", show_alert=True)

    try:
        new_active_fatigue = max(0, active_pet["fatigue"] - 60)
        await db.execute("UPDATE pets SET fatigue = ? WHERE id = ?",
                         (new_active_fatigue, active_pet["id"]))
        for p in pets:
            if p["placement"] == "passive":
                new_f = max(0, p["fatigue"] - 5)
                await db.execute("UPDATE pets SET fatigue = ? WHERE id = ?", (new_f, p["id"]))
        await remove_item(db, user_id, "food_super", 1, commit=False)
        await db.commit()
        msg = (f"💊 Суперкорм использован!\n"
               f"🐾 {active_pet['name']}: −60 усталости\n"
               f"💤 Питомники в питомнике: −5 усталости каждому")
        await query.answer(msg, show_alert=True)
        await render_main_zoo(query.message, db, user_id, is_edit=True)
    except Exception:
        await db.rollback()
        await query.answer("❌ Ошибка.", show_alert=True)


# ── Star dust usage ───────────────────────────────────────────────────────────

@router.callback_query(ZooCB.filter(F.action.in_(["use_dust_s", "use_dust_l"])))
async def cb_use_stardust(query: types.CallbackQuery, callback_data: ZooCB, db):
    """Apply Звёздная or Небесная пыль to the pet shown on the card.
    dust_s = +1 duplicate, dust_l = +5 duplicates."""
    user_id = query.from_user.id
    pet = await zoo_db.get_pet_by_id(db, callback_data.pet_id)
    if not pet or pet["owner_id"] != user_id:
        return await query.answer("❌ Питомец не найден.", show_alert=True)

    if (pet.get("pet_level") or 1) >= 10:
        return await query.answer("✨ Питомец уже на максимальном уровне!", show_alert=True)

    is_big = callback_data.action == "use_dust_l"
    item_id = "star_dust_l" if is_big else "star_dust_s"
    dup_count = 5 if is_big else 1
    item_name = "✨ Небесная пыль" if is_big else "🌟 Звёздная пыль"

    qty = await get_item_quantity(db, user_id, item_id)
    if qty < 1:
        return await query.answer(f"❌ Нет предмета «{item_name}».", show_alert=True)

    species_id = pet["species_id"]

    try:
        await db.execute("BEGIN IMMEDIATE")
        # Consume the dust
        await db.execute(
            "UPDATE inventory SET quantity = quantity - 1 WHERE user_id = ? AND item_id = ?",
            (user_id, item_id),
        )
        # Apply duplicates one by one (grant_duplicate auto-routes to first non-Lv10 copy)
        all_results = []
        for _ in range(dup_count):
            result = await grant_duplicate(db, user_id, species_id)
            all_results.append(result)
        await db.commit()
    except Exception:
        await db.rollback()
        return await query.answer("❌ Ошибка при использовании пыли.", show_alert=True)

    # Apply milestones (separate commit inside)
    all_milestones: list[dict] = []
    for r in all_results:
        if r.get("pet_id") and r.get("milestones_unlocked"):
            granted = await apply_pet_milestones(db, user_id, r["pet_id"], r["milestones_unlocked"])
            all_milestones.extend(granted)

    # Build response
    last = all_results[-1]
    new_level = last.get("new_level", 1)
    outcome = last.get("outcome", "added")

    if outcome == "overflow":
        msg = f"{item_name} → все копии на Lv10, получена компенсация!"
    elif outcome == "leveled_up":
        msg = f"{item_name} → <b>Lv{last['prev_level']} → Lv{new_level}!</b>"
    elif outcome in ("first_copy_created", "new_copy_created"):
        msg = f"{item_name} → создана новая копия питомца (Lv1)"
    else:
        msg = f"{item_name} → +{dup_count} дубликат{'а' if dup_count > 1 else ''}! (Lv{new_level})"

    if all_milestones:
        for m in all_milestones:
            r_info = m["reward"]
            parts = []
            if r_info["mora"] > 0:
                parts.append(f"+{int(r_info['mora'])} 🪙")
            if r_info["diamonds"] > 0:
                parts.append(f"+{r_info['diamonds']} 💎")
            for iid, iqty in r_info.get("items", ()):
                from core.registry import ITEMS_REGISTRY as IR
                parts.append(f"+{iqty}× {IR.get(iid, {}).get('name', iid)}")
            msg += f"\n🏆 Ур.{m['level']}: {', '.join(parts)}"

    await query.answer(msg, show_alert=True)

    # Refresh pet card
    callback_data.action = "pet_view"
    await cb_pet_view(query, callback_data, db)
