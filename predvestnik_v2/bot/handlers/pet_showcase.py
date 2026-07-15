# DEPRECATED — МЁРТВЫЙ КОД (БЛОК19 «Web First»): роутер этого файла НЕ зарегистрирован
# в bot/handlers/__init__.py::main_router — ни одна команда/кнопка отсюда не выполняется.
# Механика живёт в мини-аппе (FastAPI/), чат-алиасы ловит web_redirect.py.
# Файл оставлен как референс. НЕ подключать без ревизии: тексты/поля могли устареть.
from aiogram import Router, types

from bot.filters.text_commands import TextCmd
from infrastructure.repositories import zoo as zoo_db
from core.registry import PET_SPECIES
from core.constants import (
    PET_LEVEL_DUPLICATES,
    MAX_PET_COPIES,
    get_total_duplicates_for_level,
)
from services.zoo import format_pet_bonus_short
from bot.keyboards.cta import answer_group_only

router = Router(name="pet_showcase_router")


_RARITY_LABELS = {
    "common": "⚪ Обычный",
    "rare": "🔵 Редкий",
    "epic": "🟣 Эпический",
    "legendary": "🟡 Легендарный",
}


def _fatigue_icon(fatigue: int) -> str:
    if fatigue == 100:
        return "⛔"
    if fatigue >= 80:
        return "🔴"
    if fatigue >= 40:
        return "🟡"
    return "🟢"


def _duplicates_bar(rarity: str, pet_level: int, duplicates: int) -> str:
    if pet_level >= 10:
        return "[██████] MAX"
    table = PET_LEVEL_DUPLICATES.get(rarity, PET_LEVEL_DUPLICATES["common"])
    spent_for_current = get_total_duplicates_for_level(rarity, pet_level)
    need_to_next = table.get(pet_level + 1, 0)
    have_in_level = duplicates - spent_for_current
    ratio = max(0.0, min(1.0, have_in_level / need_to_next)) if need_to_next > 0 else 1.0
    filled = round(ratio * 5)
    bar = "█" * filled + "░" * (5 - filled)
    return f"[{bar}] {have_in_level}/{need_to_next} к Ур.{pet_level + 1}"


@router.message(TextCmd(["питомец", "мой питомец", "активный питомец"]))
async def cmd_pet_showcase(message: types.Message, db):
    if message.chat.type == "private":
        return await answer_group_only(message)

    user_id = message.from_user.id

    # Apply lazy fatigue decay first
    await zoo_db.apply_fatigue_decay(db, user_id)

    async with db.execute(
        "SELECT id, name, species_id, rarity, placement, fatigue, "
        "COALESCE(pet_level, 1) as pet_level, "
        "COALESCE(duplicates_collected, 0) as duplicates_collected, "
        "COALESCE(copy_index, 1) as copy_index "
        "FROM pets WHERE owner_id = ? AND placement = 'active'",
        (user_id,),
    ) as cursor:
        pet = await cursor.fetchone()

    if not pet:
        return await message.answer(
            "😿 <b>Активный питомец не выбран.</b>\n\n"
            "<i>Назначьте питомца через</i> <code>бот зоопарк</code>",
            parse_mode="HTML",
        )

    pet = dict(pet)
    species_id = pet["species_id"]
    species_data = PET_SPECIES.get(species_id, {})
    species_name = species_data.get("name", species_id)
    rarity_label = _RARITY_LABELS.get(pet["rarity"], pet["rarity"])
    level = pet["pet_level"]
    fatigue = pet["fatigue"]
    fatigue_icon = _fatigue_icon(fatigue)
    progress_bar = _duplicates_bar(pet["rarity"], level, pet["duplicates_collected"])
    copy_index = pet["copy_index"]
    is_exhausted = (fatigue == 100)

    # Bonuses section — pulled from the per-species level curve.
    bonus_desc = format_pet_bonus_short(species_id, level)
    if bonus_desc:
        if is_exhausted:
            bonus_block = (
                f"├ ✨ <b>БОНУСЫ:</b> <s>{bonus_desc}</s>\n"
                f"│  <i>(питомец без сил — накормите его)</i>"
            )
        else:
            bonus_block = f"├ ✨ <b>БОНУСЫ:</b> {bonus_desc}"
    else:
        bonus_block = "├ ✨ <b>БОНУСЫ:</b> —"

    exhaustion_note = (
        "\n└ ⚠️ <i>Бонусы прекращаются только при 100 усталости</i>"
        if not is_exhausted else
        "\n└ 😴 <i>Питомец без сил — бонусы не работают!</i>"
    )

    # Check for active expedition
    async with db.execute(
        "SELECT ends_at FROM active_expeditions WHERE pet_id = ?", (pet["id"],)
    ) as cursor:
        expedition = await cursor.fetchone()

    expedition_line = ""
    if expedition:
        expedition_line = f"\n├ 🗺 <b>В ПОХОДЕ</b> до <code>{expedition[0]}</code>"

    text = (
        f"🐾 <b>ПИТОМЕЦ: {pet['name']}</b>\n\n"
        f"├ 🔍 Вид: {species_name} · Копия {copy_index}/{MAX_PET_COPIES}\n"
        f"├ 🏷 Редкость: {rarity_label} · Ур. {level}\n"
        f"├ 📊 Прогресс: {progress_bar}\n"
        f"├ 🔋 Усталость: {fatigue}/100 {fatigue_icon}"
        f"{expedition_line}\n"
        f"{bonus_block}"
        f"{exhaustion_note}\n\n"
        f"💡 <i>Возможно, вас интересует:</i>\n"
        f"├ <code>бот поход, [2/4/6/8]</code> — отправить в экспедицию\n"
        f"├ <code>бот зоопарк</code> — управление питомником и кормёжка\n"
        f"└ <code>бот профиль</code> — ваш профиль и баланс"
    )

    await message.answer(text, parse_mode="HTML")
