import random
from aiogram import Router, types
from datetime import datetime, timedelta

from bot.filters.text_commands import TextCmd
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
    lines.append("\n<i>💡 Нужен Активный питомец. Настройте его командой «бот зоопарк».</i>")
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
        "SELECT ends_at FROM active_expeditions WHERE pet_id = ?", (pet_id,)
    ) as cursor:
        active_row = await cursor.fetchone()
    if active_row:
        return await message.answer(
            f"⏳ <b>Питомец уже в походе!</b>\n<i>Вернётся в <code>{active_row[0]}</code>.</i>",
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

    text = (
        f"🎒 <b>ЭКСПЕДИЦИЯ НАЧАЛАСЬ!</b>\n\n"
        f"├ 🐾 Питомец: <b>{pet_name}</b> <i>({species_name})</i>\n"
        f"├ ⏳ Длительность: <code>{duration_str}</code>\n"
        f"├ 🕒 Возвращение: <code>{ends_at.strftime('%H:%M')}</code>\n"
        f"└ 💪 Усталость: <code>{fatigue} → {fatigue + expedition_fatigue}/100</code>"
        f"{dog_block}{wolf_bonus_line}{zero_line}{turtle_bonus_line}"
    )
    await message.answer(text, parse_mode="HTML")
