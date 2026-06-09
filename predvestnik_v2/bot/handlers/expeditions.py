import random
from aiogram import Router, types, F
from aiogram.filters.callback_data import CallbackData
from aiogram.utils.keyboard import InlineKeyboardBuilder
from datetime import datetime, timedelta

from bot.filters.text_commands import TextCmd
from services.utils import check_callback_owner, safe_html
from core.registry import EXPEDITIONS_DATA, PET_SPECIES
from core.constants import get_pet_bonus
from infrastructure.repositories import economy as eco_db
from infrastructure.repositories.zoo import get_active_species_level
from services.zoo import get_wolf_fatigue_reduction

router = Router(name="expeditions_router")
from bot.middlewares.module_check_mw import ModuleCheckMiddleware
router.message.middleware(ModuleCheckMiddleware("module_expeditions"))


def _build_expedition_list() -> str:
    lines = ["🗺 <b>ДОСТУПНЫЕ ЭКСПЕДИЦИИ</b>\n"]
    items = list(EXPEDITIONS_DATA.items())
    for idx, (hours, data) in enumerate(items):
        is_last = idx == len(items) - 1
        prefix = "└" if is_last else "├"
        cost = "Бесплатно" if data["cost"] == 0 else f"{data['cost']} 🪙"
        lines.append(
            f"{prefix} <code>бот поход, {hours}</code> · {hours} ч. · "
            f"<i>{data['min_m']}-{data['max_m']} 🪙, {data['min_xp']}-{data['max_xp']} XP</i> · {cost}"
        )
    lines.append(
        "\n<i>💡 Нужен Активный питомец — «бот зоопарк».\n"
        "⏩ Ускорители походов: «бот ускорить поход»</i>"
    )
    return "\n".join(lines)


@router.message(TextCmd(["поход", "экспедиция"]))
async def cmd_expedition(message: types.Message, db, text_args: str = None):
    if message.chat.type == "private":
        return

    user_id = message.from_user.id
    args = text_args

    if not args:
        return await message.answer(_build_expedition_list(), parse_mode="HTML")

    parts = args.split()
    if not parts[0].isdigit() or int(parts[0]) not in EXPEDITIONS_DATA:
        return await message.answer("❌ <b>Отказ:</b> доступно только 2, 4, 6 или 8 часов.", parse_mode="HTML")

    hours = int(parts[0])
    exp_data = EXPEDITIONS_DATA[hours]

    async with db.execute(
        "SELECT id, name, species_id, fatigue FROM pets WHERE owner_id = ? AND placement = 'active'", (user_id,)
    ) as cursor:
        pet = await cursor.fetchone()

    if not pet:
        return await message.answer(
            "❌ <b>Нет активного питомца!</b>\n<i>Откройте «бот зоопарк» и сделайте кого-то Активным.</i>",
            parse_mode="HTML"
        )

    pet_id, pet_name, species_id, fatigue = pet

    async with db.execute(
        "SELECT ae.ends_at FROM active_expeditions ae "
        "JOIN pets p ON ae.pet_id = p.id "
        "WHERE p.owner_id = ? AND ae.ends_at > NOW() LIMIT 1",
        (user_id,)
    ) as cursor:
        active_row = await cursor.fetchone()
    if active_row:
        raw_ends = active_row[0]
        if hasattr(raw_ends, "strftime"):
            now = datetime.now()
            if raw_ends.date() == now.date():
                ends_display = raw_ends.strftime("%H:%M")
            else:
                ends_display = raw_ends.strftime("%d.%m %H:%M")
        else:
            ends_display = str(raw_ends)[:16]
        return await message.answer(
            f"⏳ <b>Питомец уже в походе!</b>\n"
            f"<i>Вернётся в <code>{ends_display}</code>.</i>\n"
            f"<i>Ускорить: «бот ускорить поход»</i>",
            parse_mode="HTML"
        )

    # Wolf reduces all received fatigue, including expedition fatigue cost.
    wolf_reduction = await get_wolf_fatigue_reduction(db, user_id)
    base_fatigue = exp_data["fatigue"] * (1.0 - wolf_reduction)

    # Dog (any nursery slot): speed_reduction shrinks duration.
    # If active pet IS the dog: self_fatigue_reduction applies on top.
    # Lv8+ dog: zero_fatigue_chance for the whole expedition.
    # Lv10 dog: capstone -5% expedition cost.
    dog_level = await get_active_species_level(db, user_id, "dog")
    dog_extra_lines = []
    expedition_cost_reduction = 0.0
    self_fatigue_reduction = 0.0
    zero_fatigue_chance = 0.0
    speed_reduction = 0.0
    if dog_level > 0:
        dog = get_pet_bonus("dog", dog_level)
        speed_reduction = dog.get("speed_reduction", 0.0)
        expedition_cost_reduction = dog.get("expedition_cost_reduction", 0.0)
        zero_fatigue_chance = dog.get("zero_fatigue_chance", 0.0)
        if species_id == "dog":
            self_fatigue_reduction = dog.get("self_fatigue_reduction", 0.0)
        if speed_reduction > 0:
            dog_extra_lines.append(
                f"🐕 Дворовая Собака (Ур.{dog_level}): ускорение −{int(speed_reduction * 100)}%"
            )

    if self_fatigue_reduction > 0:
        base_fatigue *= (1.0 - self_fatigue_reduction)
        dog_extra_lines.append(
            f"🐕 Своя собака бережёт силы (-{int(self_fatigue_reduction * 100)}% усталость)"
        )

    expedition_fatigue = int(base_fatigue)
    zero_fatigue_triggered = False
    if zero_fatigue_chance > 0 and random.random() < zero_fatigue_chance:
        expedition_fatigue = 0
        zero_fatigue_triggered = True

    if fatigue + expedition_fatigue > 100:
        return await message.answer(
            f"❌ <b>Отказ:</b> питомец слишком устал ({fatigue}/100).\n<i>Покормите его через «бот зоопарк».</i>",
            parse_mode="HTML"
        )

    # Turtle (any nursery slot): expedition cost discount from the level curve.
    turtle_level = await get_active_species_level(db, user_id, "turtle")
    turtle_bonus_line = ""
    if turtle_level > 0 and exp_data["cost"] > 0:
        turtle = get_pet_bonus("turtle", turtle_level)
        turtle_discount = turtle.get("expedition_discount", 0.0)
        combined = 1.0 - turtle_discount
        if expedition_cost_reduction > 0:
            combined *= (1.0 - expedition_cost_reduction)
        actual_cost = max(0, int(exp_data["cost"] * combined))
        if actual_cost < exp_data["cost"]:
            turtle_bonus_line = (
                f"\n<i>🐢 Черепаха (Ур.{turtle_level}) снизила цену: "
                f"{exp_data['cost']} → {actual_cost} 🪙</i>"
            )
    else:
        actual_cost = (
            max(0, int(exp_data["cost"] * (1.0 - expedition_cost_reduction)))
            if expedition_cost_reduction > 0
            else exp_data["cost"]
        )

    if actual_cost > 0:
        ok, _ = await eco_db.spend_mora(db, user_id, actual_cost)
        if not ok:
            return await message.answer(
                f"❌ <b>Отказ:</b> недостаточно Моры (нужно {actual_cost} 🪙).",
                parse_mode="HTML"
            )

    duration = hours * (1.0 - speed_reduction)
    ends_at = datetime.now() + timedelta(hours=duration)

    try:
        await db.execute("BEGIN")
        await db.execute(
            "INSERT INTO active_expeditions (pet_id, chat_id, duration_hours, cost_mora, ends_at) VALUES (?, ?, ?, ?, ?)",
            (pet_id, message.chat.id, hours, actual_cost, ends_at.strftime("%Y-%m-%d %H:%M:%S"))
        )
        await db.execute("UPDATE pets SET fatigue = fatigue + ? WHERE id = ?", (expedition_fatigue, pet_id))
        await db.commit()
    except Exception:
        await db.rollback()
        if actual_cost > 0:
            await eco_db.add_balance(db, user_id, mora=actual_cost)
        return await message.answer(
            "❌ <b>Не удалось запустить экспедицию.</b> Мора возвращена.",
            parse_mode="HTML"
        )

    h = int(duration)
    m = round((duration - h) * 60)
    duration_str = f"{h} ч. {m} мин." if m else f"{h} ч."
    species_name = PET_SPECIES.get(species_id, {}).get("name", species_id)
    wolf_bonus_line = (
        f"\n<i>🐺 Волк снизил усталость похода: {exp_data['fatigue']} → {expedition_fatigue}</i>"
        if wolf_reduction > 0 and not zero_fatigue_triggered
        else ""
    )
    zero_line = (
        "\n<i>🐕 Питомец нашёл лёгкую тропу — усталость не получена!</i>"
        if zero_fatigue_triggered else ""
    )
    dog_block = ("\n" + "\n".join(f"<i>{l}</i>" for l in dog_extra_lines)) if dog_extra_lines else ""

    now = datetime.now()
    if ends_at.date() == now.date():
        ends_str = ends_at.strftime("%H:%M")
    else:
        ends_str = ends_at.strftime("%d.%m %H:%M")
    text = (
        f"🎒 <b>ЭКСПЕДИЦИЯ НАЧАЛАСЬ!</b>\n\n"
        f"├ 🐾 Питомец: <b>{pet_name}</b> <i>({species_name})</i>\n"
        f"├ ⏳ Длительность: <code>{duration_str}</code>\n"
        f"├ 🕒 Возвращение: <code>{ends_str}</code>\n"
        f"└ 💪 Усталость: <code>{fatigue} → {fatigue + expedition_fatigue}/100</code>"
        f"{dog_block}{wolf_bonus_line}{zero_line}{turtle_bonus_line}"
    )
    await message.answer(text, parse_mode="HTML")


# ── Expedition boost (ускоритель) ─────────────────────────────────────────────

_BOOST_ITEMS = {
    "exp_boost_1h": {"label": "⏩ Ускоритель (1ч)",  "hours": 1},
    "exp_boost_2h": {"label": "⏩⏩ Ускоритель (2ч)", "hours": 2},
    "exp_boost_4h": {"label": "🚀 Ускоритель (4ч)",  "hours": 4},
}


class ExpBoostCB(CallbackData, prefix="expboost"):
    item_id: str
    user_id: int = 0


@router.message(TextCmd(["ускорить поход", "ускорить экспедицию", "ускорение похода"]))
async def cmd_exp_boost_menu(message: types.Message, db):
    if message.chat.type == "private":
        return
    user_id = message.from_user.id

    # Find active pet and its expedition
    async with db.execute(
        "SELECT ae.pet_id, ae.ends_at, p.name "
        "FROM active_expeditions ae "
        "JOIN pets p ON ae.pet_id = p.id "
        "WHERE p.owner_id = ? AND ae.ends_at > NOW() "
        "ORDER BY ae.ends_at ASC LIMIT 1",
        (user_id,),
    ) as c:
        exp_row = await c.fetchone()

    if not exp_row:
        return await message.answer(
            "❌ <b>Нет активной экспедиции.</b>\n<i>Сначала отправьте питомца в поход.</i>",
            parse_mode="HTML",
        )

    pet_name = safe_html(exp_row[2] or "?")
    ends_at = exp_row[1]
    ends_str = ends_at.strftime("%H:%M") if hasattr(ends_at, "strftime") else str(ends_at)[:16]

    # Check which boost items user has
    available = []
    for item_id, info in _BOOST_ITEMS.items():
        async with db.execute(
            "SELECT quantity FROM inventory WHERE user_id = ? AND item_id = ? AND quantity > 0",
            (user_id, item_id),
        ) as c:
            row = await c.fetchone()
        if row:
            available.append((item_id, info["label"], info["hours"], row[0]))

    if not available:
        return await message.answer(
            "❌ <b>Нет ускорителей.</b>\n<i>Их можно получить из гачи.</i>",
            parse_mode="HTML",
        )

    b = InlineKeyboardBuilder()
    for item_id, label, hours, qty in available:
        b.button(
            text=f"{label} (x{qty})",
            callback_data=ExpBoostCB(item_id=item_id, user_id=user_id),
        )
    b.adjust(1)

    await message.answer(
        f"⏩ <b>УСКОРИТЕЛЬ ПОХОДА</b>\n\n"
        f"├ 🐾 Питомец: <b>{pet_name}</b>\n"
        f"└ 🕒 Ожидаемое возвращение: <code>{ends_str}</code>\n\n"
        f"<i>Выберите ускоритель:</i>",
        reply_markup=b.as_markup(),
        parse_mode="HTML",
    )


@router.callback_query(ExpBoostCB.filter())
async def cb_exp_boost_apply(query: types.CallbackQuery, callback_data: ExpBoostCB, db):
    if not await check_callback_owner(query, callback_data.user_id):
        return

    user_id = query.from_user.id
    item_id = callback_data.item_id
    boost_info = _BOOST_ITEMS.get(item_id)
    if not boost_info:
        return await query.answer("❌ Неизвестный ускоритель.", show_alert=True)

    boost_hours = boost_info["hours"]

    # Find active pet's expedition (for update)
    async with db.execute(
        "SELECT ae.pet_id, ae.ends_at FROM active_expeditions ae "
        "JOIN pets p ON ae.pet_id = p.id "
        "WHERE p.owner_id = ? AND ae.ends_at > NOW() "
        "ORDER BY ae.ends_at ASC LIMIT 1",
        (user_id,),
    ) as c:
        exp_row = await c.fetchone()

    if not exp_row:
        return await query.answer("❌ Экспедиция уже завершилась!", show_alert=True)

    pet_id = exp_row[0]
    current_ends = exp_row[1]
    if not hasattr(current_ends, "tzinfo"):
        current_ends = datetime.strptime(str(current_ends)[:19], "%Y-%m-%d %H:%M:%S")

    # Calculate new ends_at — cap at now + 30 seconds to let scheduler finalize
    new_ends = max(
        current_ends - timedelta(hours=boost_hours),
        datetime.now() + timedelta(seconds=30),
    )

    # Atomic: remove item + update expedition in one transaction
    try:
        async with db.connection.transaction():
            # Check item still available (FOR UPDATE to prevent race)
            async with db.execute(
                "SELECT quantity FROM inventory WHERE user_id = ? AND item_id = ? FOR UPDATE",
                (user_id, item_id),
            ) as c:
                inv_row = await c.fetchone()
            if not inv_row or inv_row[0] < 1:
                raise ValueError("no_item")

            # Remove 1 item
            await db.execute(
                "UPDATE inventory SET quantity = quantity - 1 WHERE user_id = ? AND item_id = ?",
                (user_id, item_id),
            )
            await db.execute(
                "DELETE FROM inventory WHERE user_id = ? AND item_id = ? AND quantity <= 0",
                (user_id, item_id),
            )

            # Update expedition (also verify it's still active)
            async with db.execute(
                "UPDATE active_expeditions SET ends_at = ? "
                "WHERE pet_id = ? AND ends_at > NOW() RETURNING ends_at",
                (new_ends.strftime("%Y-%m-%d %H:%M:%S"), pet_id),
            ) as c:
                updated = await c.fetchone()

            if not updated:
                raise ValueError("already_done")

    except ValueError as e:
        if str(e) == "no_item":
            return await query.answer("❌ Предмет не найден в инвентаре.", show_alert=True)
        return await query.answer("❌ Экспедиция уже завершилась!", show_alert=True)
    except Exception:
        return await query.answer("❌ Ошибка. Попробуйте ещё раз.", show_alert=True)

    saved = current_ends - new_ends
    saved_min = int(saved.total_seconds() / 60)
    new_ends_str = new_ends.strftime("%H:%M")

    try:
        await query.message.edit_text(
            f"✅ <b>Ускоритель применён!</b>\n\n"
            f"├ Сэкономлено: <code>{saved_min} мин.</code>\n"
            f"└ Возвращение: <code>{new_ends_str}</code>",
            parse_mode="HTML",
        )
    except Exception:
        pass
    await query.answer()
