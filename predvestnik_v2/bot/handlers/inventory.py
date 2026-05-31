from aiogram import Router, types, F
from aiogram.filters.callback_data import CallbackData
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.filters.text_commands import TextCmd
from core.registry import ITEMS_REGISTRY, PET_SPECIES
from infrastructure.repositories.economy import get_inventory
from infrastructure.repositories.zoo import open_eggs_batch
from services.utils import safe_html, check_callback_owner
from services.zoo import apply_pet_milestones
from services.achievements import increment_metric, format_achievement_notification
from services.quests import increment_metric as quest_increment

router = Router(name="inventory_router")

RARITY_EMOJI = {"legendary": "🟡", "epic": "🟣", "rare": "🔵", "common": "⚪️"}
RARITY_NAMES = {"legendary": "Легендарный", "epic": "Эпический", "rare": "Редкий", "common": "Обычный"}
RARITY_ORDER = ["legendary", "epic", "rare", "common"]


async def _process_milestones(db, user_id: int, dropped: list) -> list[dict]:
    """Apply one-time milestone rewards for all pet_ids returned by open_eggs_batch.
    Commits once if anything was granted. Returns list of all granted milestone dicts."""
    all_granted = []
    for r in dropped:
        pet_id = r.get("pet_id")
        milestones = r.get("milestones_unlocked", [])
        if not milestones or not pet_id:
            continue
        granted = await apply_pet_milestones(db, user_id, pet_id, milestones)
        all_granted.extend(granted)
    if all_granted:
        await db.commit()
    return all_granted


def _fmt_milestone_lines(granted: list[dict]) -> str:
    """Formats granted milestone rewards into a multi-line string to append to egg-open messages."""
    if not granted:
        return ""
    lines = ["\n\n🏆 <b>НАГРАДЫ ЗА УРОВНИ:</b>"]
    for g in granted:
        level = g["level"]
        reward = g["reward"]
        parts = []
        if reward["mora"] > 0:
            parts.append(f"+{int(reward['mora'])} 🪙")
        if reward["diamonds"] > 0:
            parts.append(f"+{reward['diamonds']} 💎")
        for item_id, qty in reward.get("items", ()):
            name = ITEMS_REGISTRY.get(item_id, {}).get("name", item_id)
            parts.append(f"+{qty}× {name}")
        prefix = "├" if g is not granted[-1] else "└"
        lines.append(f"{prefix} Ур.{level}: {', '.join(parts)}")
    return "\n".join(lines)


class InvCB(CallbackData, prefix="inv"):
    action: str
    item_id: str
    user_id: int = 0


@router.message(TextCmd(["инвентарь", "рюкзак", "вещи"]))
async def cmd_inventory(message: types.Message, db):
    if message.chat.type == "private":
        return
    user_id = message.from_user.id
    name = safe_html(message.from_user.first_name)

    async with db.execute("SELECT item_id, quantity FROM inventory WHERE user_id = ?", (user_id,)) as cursor:
        rows = await cursor.fetchall()

    if not rows:
        return await message.answer(
            "🎒 <b>ИНВЕНТАРЬ ПУСТ</b>\n<i>Загляните в «бот магазин» за яйцами и кормом.</i>",
            parse_mode="HTML"
        )

    lines = [f"🎒 <b>ИНВЕНТАРЬ:</b> {name}\n"]
    builder = InlineKeyboardBuilder()

    items_list = list(rows)
    for idx, (item_id, qty) in enumerate(items_list):
        item_data = ITEMS_REGISTRY.get(item_id, {"name": "Неизвестный предмет", "category": "other"})
        prefix = "└" if idx == len(items_list) - 1 else "├"
        lines.append(f"{prefix} <b>{item_data['name']}</b> — <code>x{qty}</code>")

        if item_data.get("category") == "egg":
            builder.button(
                text=f"🐣 Открыть {item_data['name']}",
                callback_data=InvCB(action="open_egg", item_id=item_id)
            )

    builder.adjust(1)
    await message.answer("\n".join(lines), reply_markup=builder.as_markup(), parse_mode="HTML")


@router.message(TextCmd(["открыть"]))
async def cmd_open_eggs(message: types.Message, db, text_args: str = None):
    raw_args = text_args
    if not raw_args:
        return await message.answer(
            "ℹ️ <b>Использование:</b> <code>бот открыть, [egg_id] [количество]</code>\n"
            "<i>Совет: проще нажать кнопку «🐣 Открыть» прямо в инвентаре.</i>",
            parse_mode="HTML"
        )

    args = raw_args.split()
    egg_id = args[0]
    try:
        count = int(args[1]) if len(args) > 1 else 1
    except ValueError:
        return await message.answer("❌ <b>Отказ:</b> количество должно быть числом.", parse_mode="HTML")

    if count < 1 or count > 50:
        return await message.answer("❌ <b>Отказ:</b> можно открыть от 1 до 50 яиц за раз.", parse_mode="HTML")

    inv = await get_inventory(db, message.from_user.id)
    user_egg_count = next((i['quantity'] for i in inv if i['item_id'] == egg_id), 0)

    if user_egg_count < count:
        return await message.answer(
            f"❌ <b>Отказ:</b> недостаточно яиц этого типа (<code>{user_egg_count}/{count}</code>).",
            parse_mode="HTML"
        )

    is_summoned = (egg_id == "egg_summon")
    dropped = await open_eggs_batch(db, message.from_user.id, egg_id, count, is_summoned=is_summoned)

    summary: dict = {}
    for r in dropped:
        key = (r['rarity'], r['species_name'])
        if key not in summary:
            summary[key] = {
                "rarity": r['rarity'],
                "name": r['species_name'],
                "count": 0,
                "leveled_up": False,
                "new_copy": False,
                "overflow_mora": 0.0,
                "overflow_stardust": 0,
            }
        summary[key]["count"] += 1
        if r['outcome'] == "leveled_up":
            summary[key]["leveled_up"] = True
        elif r['outcome'] == "new_copy_created":
            summary[key]["new_copy"] = True
        elif r['outcome'] == "overflow" and r.get("overflow"):
            summary[key]["overflow_mora"] += r["overflow"]["mora"]
            summary[key]["overflow_stardust"] += r["overflow"]["stardust"]

    sorted_pets = sorted(
        summary.values(),
        key=lambda x: RARITY_ORDER.index(x['rarity']) if x['rarity'] in RARITY_ORDER else 99
    )

    lines = [f"🐣 <b>ОТКРЫТО ЯИЦ: {count}</b>\n"]
    for idx, entry in enumerate(sorted_pets):
        prefix = "└" if idx == len(sorted_pets) - 1 else "├"
        emoji = RARITY_EMOJI.get(entry['rarity'], "•")
        marks = []
        if entry["new_copy"]:
            marks.append("🆕 новая копия")
        if entry["leveled_up"]:
            marks.append("⬆️ Lv UP")
        if entry["overflow_mora"] or entry["overflow_stardust"]:
            marks.append(
                f"💰 +{int(entry['overflow_mora'])} Моры, +{entry['overflow_stardust']} 🌟"
            )
        suffix = f" — <i>{', '.join(marks)}</i>" if marks else ""
        lines.append(f"{prefix} {emoji} {entry['name']} — <code>x{entry['count']}</code>{suffix}")

    lines.append("\n<i>Питомцы отправлены на склад — «бот зоопарк».</i>")

    granted = await _process_milestones(db, message.from_user.id, dropped)
    milestone_text = _fmt_milestone_lines(granted)

    # Achievement + quest: eggs_opened
    ach_grants = await increment_metric(db, message.from_user.id, "eggs_opened", delta=float(count))
    await quest_increment(db, message.from_user.id, message.chat.id, "eggs_opened_today", delta=float(count))

    # Quest: rare_or_better_pet_dups_today / pet_level_ups_today
    for r in dropped:
        if r.get("rarity") in ("rare", "epic", "legendary"):
            await quest_increment(db, message.from_user.id, message.chat.id,
                                  "rare_or_better_pet_dups_today", delta=1.0)
        if r.get("outcome") == "leveled_up" and r.get("milestones_unlocked"):
            await quest_increment(db, message.from_user.id, message.chat.id,
                                  "pet_level_ups_today", delta=1.0)
    await db.commit()

    ach_text = format_achievement_notification(ach_grants)
    await message.answer("\n".join(lines) + milestone_text, parse_mode="HTML")
    if ach_text:
        await message.answer(ach_text, parse_mode="HTML")

    # Lv10 announcement
    if any(g["level"] == 10 for g in granted):
        for r in dropped:
            if 10 in r.get("milestones_unlocked", []) and r.get("pet_id"):
                sp = PET_SPECIES.get(r.get("species_id", ""), {})
                await message.answer(
                    f"🏆 <b>ПИТОМЕЦ ДОСТИГ МАКСИМАЛЬНОГО УРОВНЯ!</b>\n\n"
                    f"👑 <b>{sp.get('name', '?')}</b> — <i>Lv10!</i>\n"
                    f"✨ Все бонусы работают на полную мощность!\n"
                    f"🎁 Награда: 3 000 🪙 + 2 💎 уже на вашем счету",
                    parse_mode="HTML",
                )
                break


@router.callback_query(InvCB.filter(F.action == "open_egg"))
async def cb_open_egg(callback: types.CallbackQuery, callback_data: InvCB, db):
    if not await check_callback_owner(callback, callback_data.user_id):
        return
    egg_id = callback_data.item_id
    user_id = callback.from_user.id

    inv = await get_inventory(db, user_id)
    qty = next((item['quantity'] for item in inv if item['item_id'] == egg_id), 0)
    if qty < 1:
        return await callback.answer("❌ У вас нет этого яйца.", show_alert=True)

    is_summoned = (egg_id == "egg_summon")
    dropped = await open_eggs_batch(db, user_id, egg_id, 1, is_summoned=is_summoned)

    if not dropped:
        return await callback.answer("❌ Ошибка при открытии яйца.", show_alert=True)

    r = dropped[0]
    emoji = RARITY_EMOJI.get(r['rarity'], "•")
    rarity_name = RARITY_NAMES.get(r['rarity'], r['rarity'])
    outcome = r['outcome']

    if outcome == "first_copy_created":
        headline = "Новый вид в коллекции!"
        detail = f"└ {emoji} <b>{r['species_name']}</b> — <i>{rarity_name}</i> · Lv1\n\n<i>Питомец на складе — «бот зоопарк».</i>"
    elif outcome == "new_copy_created":
        headline = "Создана новая копия!"
        detail = (
            f"└ {emoji} <b>{r['species_name']}</b> · Копия {r['copy_index']}/3 · Lv1\n\n"
            "<i>Все предыдущие копии уже на максимуме.</i>"
        )
    elif outcome == "leveled_up":
        headline = "Дубликат поднял уровень!"
        detail = (
            f"└ {emoji} <b>{r['species_name']}</b> · Копия {r['copy_index']}: "
            f"<b>Lv{r['prev_level']} → Lv{r['new_level']}</b>"
        )
    elif outcome == "overflow":
        ov = r.get("overflow") or {"mora": 0.0, "stardust": 0}
        headline = "Все копии на максимуме — компенсация!"
        detail = f"└ 💰 +{int(ov['mora'])} Моры, +{ov['stardust']} 🌟 Звёздной пыли"
    else:  # "added"
        headline = "Дубликат добавлен!"
        detail = (
            f"└ {emoji} <b>{r['species_name']}</b> · Копия {r['copy_index']} (Lv{r['new_level']})"
        )

    granted = await _process_milestones(db, user_id, dropped)
    milestone_text = _fmt_milestone_lines(granted)

    ach_grants = await increment_metric(db, user_id, "eggs_opened", delta=1.0)
    await db.commit()
    ach_text = format_achievement_notification(ach_grants)

    await callback.message.answer(
        f"🐣 <b>ЯЙЦО РАЗБИЛОСЬ!</b>\n\n"
        f"{headline}\n"
        f"{detail}"
        f"{milestone_text}",
        parse_mode="HTML",
    )
    if ach_text:
        await callback.message.answer(ach_text, parse_mode="HTML")
    await callback.answer()

    if any(g["level"] == 10 for g in granted):
        sp = PET_SPECIES.get(r.get("species_id", ""), {})
        await callback.message.answer(
            f"🏆 <b>ПИТОМЕЦ ДОСТИГ МАКСИМАЛЬНОГО УРОВНЯ!</b>\n\n"
            f"👑 <b>{sp.get('name', '?')}</b> — <i>Lv10!</i>\n"
            f"✨ Все бонусы теперь работают на 200% мощности!\n"
            f"🎁 Награда: 3 000 🪙 + 2 💎 уже на вашем счету",
            parse_mode="HTML",
        )