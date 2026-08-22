# DEPRECATED — МЁРТВЫЙ КОД (БЛОК19 «Web First»): роутер этого файла НЕ зарегистрирован
# в bot/handlers/__init__.py::main_router — ни одна команда/кнопка отсюда не выполняется.
# Механика живёт в мини-аппе (FastAPI/), чат-алиасы ловит web_redirect.py.
# Файл оставлен как референс. НЕ подключать без ревизии: тексты/поля могли устареть.
from aiogram import Router, types, F
from aiogram.filters.callback_data import CallbackData
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.filters.text_commands import TextCmd
from core.registry import ITEMS_REGISTRY
from services.inventory_resolve import resolve_and_migrate_item_id, item_display_name
from services.utils import safe_html, check_callback_owner
from services.zoo import apply_pet_milestones
from bot.keyboards.cta import answer_group_only

router = Router(name="inventory_router")

RARITY_EMOJI = {"legendary": "🟡", "epic": "🟣", "rare": "🔵", "common": "⚪️"}
RARITY_NAMES = {"legendary": "Легендарный", "epic": "Эпический", "rare": "Редкий", "common": "Обычный"}
RARITY_ORDER = ["legendary", "epic", "rare", "common"]

# ── Полные описания предметов ──────────────────────────────────────────────────

_ITEM_DETAILS: dict[str, dict] = {
    # Materials
    "soul_shard": {
        "use":    "Накопи 5 штук → скрафти 🎟 Жетон Призыва во вкладке «Крафт»",
        "get":    "Получается при распылении питомца через «бот зоопарк» → карточка питомца → Распылить",
        "tip":    "Призванный питомец из Жетона не даёт осколков при распылении — учти это",
        "cmds":   ["бот магазин", "бот зоопарк"],
    },
    "star_dust_s": {
        "use":    "Применяется через «бот зоопарк» → открой карточку питомца → кнопка «🌟 Пыль»",
        "get":    "Выпадает из яиц при переполнении (все копии на Lv10)",
        "tip":    "+1 дубликат к выбранному питомцу, моментально",
        "cmds":   ["бот зоопарк"],
    },
    "star_dust_l": {
        "use":    "Применяется через «бот зоопарк» → открой карточку питомца → кнопка «✨ Пыль»",
        "get":    "Выпадает из редких яиц при переполнении",
        "tip":    "+5 дубликатов сразу — экономит время",
        "cmds":   ["бот зоопарк"],
    },
    # Expedition boosters
    "treasure_map": {
        "use":    "Расходуется автоматически перед следующей экспедицией",
        "get":    "Выпадает из гачи (все типы крутки)",
        "tip":    "+50% к максимуму лута в следующем походе",
        "cmds":   ["бот поход, [2/4/6/8]", "бот крутка"],
    },
    "exp_boost_1h": {
        "use":    "Используй через «бот ускорить поход» пока питомец в активной экспедиции",
        "get":    "Выпадает из гачи",
        "tip":    "Сокращает время текущей экспедиции на 1 час",
        "cmds":   ["бот ускорить поход", "бот поход"],
    },
    "exp_boost_2h": {
        "use":    "Используй через «бот ускорить поход» пока питомец в активной экспедиции",
        "get":    "Выпадает из гачи",
        "tip":    "Сокращает время текущей экспедиции на 2 часа",
        "cmds":   ["бот ускорить поход", "бот поход"],
    },
    "exp_boost_4h": {
        "use":    "Используй через «бот ускорить поход» пока питомец в активной экспедиции",
        "get":    "Выпадает из гачи, квесты, ивенты",
        "tip":    "Самый мощный ускоритель — сокращает на 4 часа",
        "cmds":   ["бот ускорить поход", "бот поход"],
    },
    # Potions
    "potion_luck_s": {
        "use":    "Расходуется автоматически перед следующим спином гачи",
        "get":    "Магазин за 100 🪙, акция дня, гача",
        "tip":    "+15% к шансу Редкого+ в следующем 1 спине",
        "cmds":   ["бот крутка", "бот магазин"],
    },
    "potion_luck_m": {
        "use":    "Расходуется автоматически — действует на следующие 3 спина",
        "get":    "Квесты, ивенты, акция дня",
        "tip":    "+15% к шансу Редкого+ на 3 спина подряд",
        "cmds":   ["бот крутка"],
    },
    "potion_sprint": {
        "use":    "Расходуется автоматически перед следующей экспедицией",
        "get":    "Гача, ивенты",
        "tip":    "+30% к луту в следующей экспедиции",
        "cmds":   ["бот поход, [2/4/6/8]"],
    },
    # Spin token (единый, Block 8)
    "spin_token": {
        "use":    "Используется автоматически при крутке за Мору — спин бесплатно",
        "get":    "Стрик-блоки, достижения, БП, VIP, вехи питомцев, ивенты",
        "tip":    "Кнопка крутки за Мору показывает 'БЕСПЛАТНО' если жетон есть",
        "cmds":   ["бот крутка"],
    },
    # Food
    "food_basic": {
        "use":    "Используй через «бот зоопарк» → карточка питомца → «🍖 Покормить»",
        "get":    "Магазин за 50 🪙",
        "tip":    "Снижает 15 усталости питомца. Нужен для экспедиций (макс. 100)",
        "cmds":   ["бот зоопарк", "бот магазин"],
    },
    "food_elite": {
        "use":    "Используй через «бот зоопарк» → карточка питомца → «🍖 Покормить»",
        "get":    "Магазин за 150 🪙",
        "tip":    "Снижает 50 усталости — в 3 раза эффективнее базового",
        "cmds":   ["бот зоопарк", "бот магазин"],
    },
    "food_energy": {
        "use":    "Используй через «бот зоопарк» → карточка питомца",
        "get":    "Магазин за 250 🪙",
        "tip":    "20 усталости + сброс кулдауна экспедиции — если питомец уже вернулся",
        "cmds":   ["бот зоопарк", "бот магазин", "бот поход"],
    },
    "food_super": {
        "use":    "Используй через «бот зоопарк» → карточка активного питомца",
        "get":    "Магазин за 350 🪙",
        "tip":    "60 усталости активному + 5 всем в питомнике",
        "cmds":   ["бот зоопарк", "бот магазин"],
    },
    "food_diamond": {
        "use":    "Используй через «бот зоопарк» → карточка питомца",
        "get":    "Магазин за 8 💎",
        "tip":    "100% усталости снимается + +20% эффективность на 24ч",
        "cmds":   ["бот зоопарк", "бот магазин"],
    },
    # Utility
    "lucky_charm": {
        "use":    "Расходуется автоматически при следующей крутке гачи",
        "get":    "Гача, ивенты",
        "tip":    "+15% к шансу редкости в следующей крутке",
        "cmds":   ["бот крутка"],
    },
    "study_notes": {
        "use":    "Сохранён как архивный предмет и не расходуется",
        "get":    "Больше не выдаётся",
        "tip":    "Старый бонус XP от сообщений закрыт",
        "cmds":   ["бот инвентарь"],
    },
    "shield_day": {
        "use":    "Активируй через «бот использовать, shield_day»",
        "get":    "Магазин за 500 🪙",
        "tip":    "Иммунитет от штрафов и варнов на 24 часа",
        "cmds":   ["бот магазин"],
    },
    "shield_week": {
        "use":    "Активируй через «бот использовать, shield_week»",
        "get":    "Магазин за 3000 🪙",
        "tip":    "Иммунитет от штрафов на 7 дней",
        "cmds":   ["бот магазин"],
    },
    "key_chest": {
        "use":    "Используется при открытии дополнительного сундука в ивенте сундуков",
        "get":    "Магазин за 300 🪙",
        "tip":    "Ивент сундуков запускается ботом автоматически",
        "cmds":   ["бот магазин"],
    },
    "key_auction": {
        "use":    "Даёт +1 дополнительный лот на аукционе",
        "get":    "Магазин за 100 🪙",
        "tip":    "По умолчанию 1 активный лот, ключ добавляет ещё один",
        "cmds":   ["бот аукцион", "бот магазин"],
    },
    "scroll_quest": {
        "use":    "Открывает особый квест на день",
        "get":    "Ивенты, редкие достижения",
        "tip":    "Содержание квеста зависит от текущего ивента",
        "cmds":   ["бот задания"],
    },
}

_CATEGORY_LABELS = {
    "food":       "🍖 Корм для питомцев",
    "booster":    "⚗️ Зелья и ускорители",
    "spin_token": "🎟 Жетоны гачи",
    "material":   "💠 Материалы",
    "utility":    "🔧 Прочее",
}


# ── Item description builder ──────────────────────────────────────────────────

def _shop_price_str(item: dict) -> str:
    """Реальная цена покупки из registry (единый источник — убирает стейл-цены
    из хардкод-строк _ITEM_DETAILS['get'])."""
    parts = []
    if item.get("price_mora", 0) > 0:     parts.append(f"{int(item['price_mora'])} 🪙")
    if item.get("price_diamonds", 0) > 0: parts.append(f"{int(item['price_diamonds'])} 💎")
    if item.get("price_zarniki", 0) > 0:  parts.append(f"{int(item['price_zarniki'])} ✨")
    return " / ".join(parts)


def _build_item_description(item_id: str, qty: int = 0) -> str:
    item = ITEMS_REGISTRY.get(item_id, {})
    name = item.get("name", item_id)
    base_desc = item.get("description", "")
    details = _ITEM_DETAILS.get(item_id, {})

    lines = [f"\n{'─' * 20}", f"📦 <b>{safe_html(name)}</b>"]
    if qty > 0:
        lines.append(f"└ В наличии: <code>{qty}</code> шт.\n")
    else:
        lines.append("")

    if base_desc:
        lines.append(f"💬 <i>{safe_html(base_desc)}</i>")

    if details.get("use"):
        lines.append(f"\n🔧 <b>Как использовать:</b>\n└ {safe_html(details['use'])}")

    # Цену для покупаемых предметов берём из registry (актуальную), а не из
    # хардкод-строки details['get'] (там копились стейл-цены). Непокупаемые
    # (гача/крафт) — оставляем их описание источника.
    price = _shop_price_str(item)
    get_info = f"Магазин за {price}" if price else details.get("get")
    if get_info:
        lines.append(f"\n📍 <b>Где получить:</b>\n└ {safe_html(get_info)}")

    if details.get("tip"):
        lines.append(f"\n💡 <b>Подсказка:</b> <i>{safe_html(details['tip'])}</i>")

    cmds = details.get("cmds", [])
    if cmds:
        cmd_str = " · ".join(f"<code>{safe_html(c)}</code>" for c in cmds)
        lines.append(f"\n⚡ <b>Связанные команды:</b> {cmd_str}")

    return "\n".join(lines)


# ── Inventory helpers ─────────────────────────────────────────────────────────

async def _process_milestones(db, user_id: int, dropped: list) -> list[dict]:
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


async def _pre_resolve_items(db, user_id: int, items: list[tuple[str, int]]) -> list[tuple[str, int]]:
    """Resolve numeric legacy item_ids via auction_lots history, self-healing
    the DB row to the real item_id."""
    resolved = []
    for item_id, qty in items:
        real = await resolve_and_migrate_item_id(db, user_id, item_id)
        resolved.append((real, qty))
    return resolved


def _build_inventory_text(name: str, items: list[tuple[str, int]]) -> str:
    lines = [f"🎒 <b>ИНВЕНТАРЬ:</b> {name}\n"]
    if not items:
        lines.append("<i>Пусто.</i>")
    else:
        for idx, (item_id, qty) in enumerate(items):
            prefix = "└" if idx == len(items) - 1 else "├"
            lines.append(f"{prefix} <b>{item_display_name(item_id)}</b> — <code>×{qty}</code>")
    return "\n".join(lines)


def _build_inventory_kb(
    items: list[tuple[str, int]],
    user_id: int,
    mode: str,
    selected_item: str = "",
) -> types.InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()

    # Filter buttons
    in_btn  = "· В наличии" if mode == "has" else "В наличии"
    all_btn = "· Все предметы" if mode == "all" else "Все предметы"
    b.button(text=in_btn,  callback_data=InvCB(action="filter", item_id="has", user_id=user_id))
    b.button(text=all_btn, callback_data=InvCB(action="filter", item_id="all", user_id=user_id))

    # Item buttons
    for item_id, qty in items:
        item_data = ITEMS_REGISTRY.get(item_id, {"name": item_id, "category": "other"})
        mark = "▸ " if item_id == selected_item else ""
        b.button(
            text=f"{mark}{item_data['name']}",
            callback_data=InvCB(action="info", item_id=item_id, user_id=user_id),
        )

    b.adjust(2, *([1] * len(items)))

    # Rebuild with proper layout: 2 filter buttons, then each item row
    b2 = InlineKeyboardBuilder()
    b2.button(text=in_btn,  callback_data=InvCB(action="filter", item_id="has", user_id=user_id))
    b2.button(text=all_btn, callback_data=InvCB(action="filter", item_id="all", user_id=user_id))
    for item_id, qty in items:
        item_data = ITEMS_REGISTRY.get(item_id, {"name": item_id, "category": "other"})
        mark = "▸ " if item_id == selected_item else ""
        b2.button(
            text=f"{mark}{item_data['name']}",
            callback_data=InvCB(action="info", item_id=item_id, user_id=user_id),
        )

    # Layout: 2 filter buttons, then 1 per item
    b2.adjust(2, *([1] * len(items)))
    return b2.as_markup()


# ── Callback data ─────────────────────────────────────────────────────────────

class InvCB(CallbackData, prefix="inv"):
    action: str   # "info" | "filter"
    item_id: str = ""
    user_id: int = 0


# ── Main inventory command ────────────────────────────────────────────────────

@router.message(TextCmd(["использовать"]))
async def cmd_use_item(message: types.Message, db, text_args: str = None):
    """бот использовать, [item_id] — применить расходуемый предмет."""
    if message.chat.type == "private":
        return await answer_group_only(message)
    if not text_args:
        return await message.answer(
            "❓ <b>Использование:</b> <code>бот использовать, [item_id]</code>\n"
            "Активируемые предметы показывают способ применения в описании.",
            parse_mode="HTML",
        )
    item_id = text_args.strip().lower()
    user_id = message.from_user.id

    # Check inventory
    async with db.execute(
        "SELECT quantity FROM inventory WHERE user_id = ? AND item_id = ? AND quantity > 0",
        (user_id, item_id),
    ) as c:
        row = await c.fetchone()
    if not row:
        return await message.answer(f"❌ У вас нет <code>{item_id}</code> в инвентаре.", parse_mode="HTML")

    if item_id == "study_notes":
        return await message.answer(
            "📚 Конспект сохранён как архивный предмет и не расходуется. Старый бонус XP от сообщений закрыт.",
            parse_mode="HTML",
        )

    # ── Unknown usable item ──────────────────────────────────────────────────
    item_info = ITEMS_REGISTRY.get(item_id, {})
    await message.answer(
        f"⚠️ Предмет <b>{item_info.get('name', item_id)}</b> нельзя применить вручную.\n"
        f"<i>{item_info.get('description', '')}</i>",
        parse_mode="HTML",
    )


@router.message(TextCmd(["инвентарь", "рюкзак", "вещи"]))
async def cmd_inventory(message: types.Message, db):
    if message.chat.type == "private":
        return await answer_group_only(message)
    user_id = message.from_user.id
    from services.utils import resolve_display_name
    name = await resolve_display_name(db, user_id, message.chat.id, message.from_user.first_name)

    async with db.execute(
        "SELECT item_id, quantity FROM inventory WHERE user_id = ? ORDER BY item_id",
        (user_id,),
    ) as cursor:
        rows = await cursor.fetchall()

    # Default: only owned (qty > 0); resolve any numeric legacy item_ids
    owned = [(iid, qty) for iid, qty in rows if qty > 0]
    owned = await _pre_resolve_items(db, user_id, owned)

    if not owned:
        return await message.answer(
            "🎒 <b>ИНВЕНТАРЬ ПУСТ</b>\n\n"
            "<i>Загляни в «бот магазин» за кормом и припасами.</i>\n"
            "<i>Жми «Все предметы» чтобы увидеть что вообще есть в игре.</i>",
            reply_markup=_build_inventory_kb([], user_id, "has"),
            parse_mode="HTML",
        )

    text = _build_inventory_text(name, owned)
    await message.answer(
        text,
        reply_markup=_build_inventory_kb(owned, user_id, "has"),
        parse_mode="HTML",
    )


# ── Inventory callbacks ───────────────────────────────────────────────────────

@router.callback_query(InvCB.filter(F.action == "filter"))
async def cb_inv_filter(query: types.CallbackQuery, callback_data: InvCB, db):
    if not await check_callback_owner(query, callback_data.user_id):
        return
    user_id = query.from_user.id
    mode = callback_data.item_id  # "has" or "all"
    from services.utils import resolve_display_name
    name = await resolve_display_name(db, user_id, query.message.chat.id, query.from_user.first_name)

    async with db.execute(
        "SELECT item_id, quantity FROM inventory WHERE user_id = ? ORDER BY item_id",
        (user_id,),
    ) as cursor:
        rows = await cursor.fetchall()

    owned_map = {iid: qty for iid, qty in rows}

    if mode == "has":
        items = await _pre_resolve_items(db, user_id, [(iid, qty) for iid, qty in rows if qty > 0])
        text = _build_inventory_text(name, items) if items else (
            f"🎒 <b>ИНВЕНТАРЬ:</b> {name}\n\n<i>Инвентарь пуст.</i>"
        )
    else:
        # All game items grouped by category
        lines = ["📦 <b>ВСЕ ПРЕДМЕТЫ ИГРЫ</b>\n"]
        cat_order = ["food", "booster", "spin_token", "material", "utility"]
        by_cat: dict[str, list] = {}
        for iid, item in ITEMS_REGISTRY.items():
            cat = item.get("category", "utility")
            by_cat.setdefault(cat, []).append(iid)

        for cat in cat_order:
            if cat not in by_cat:
                continue
            lines.append(f"\n{_CATEGORY_LABELS.get(cat, cat)}")
            for iid in by_cat[cat]:
                item = ITEMS_REGISTRY[iid]
                qty = owned_map.get(iid, 0)
                qty_str = f" <code>×{qty}</code>" if qty > 0 else " <i>(нет)</i>"
                lines.append(f"├ <b>{item['name']}</b>{qty_str}")
        if lines:
            last_lines = [l for l in lines if l.startswith("├")]
            if last_lines:
                lines = [l.replace("├", "└", 1) if l == last_lines[-1] else l for l in lines]

        text = "\n".join(lines)
        items = [(iid, owned_map.get(iid, 0)) for iid in ITEMS_REGISTRY]

    try:
        await query.message.edit_text(
            text,
            reply_markup=_build_inventory_kb(
                [(iid, qty) for iid, qty in rows if qty > 0] if mode == "all"
                else items,
                user_id, mode,
            ),
            parse_mode="HTML",
        )
    except Exception:
        pass
    await query.answer()


@router.callback_query(InvCB.filter(F.action == "info"))
async def cb_inv_info(query: types.CallbackQuery, callback_data: InvCB, db):
    if not await check_callback_owner(query, callback_data.user_id):
        return
    user_id = query.from_user.id
    item_id = callback_data.item_id

    async with db.execute(
        "SELECT item_id, quantity FROM inventory WHERE user_id = ? ORDER BY item_id",
        (user_id,),
    ) as cursor:
        rows = await cursor.fetchall()

    owned = [(iid, qty) for iid, qty in rows if qty > 0]
    qty = next((q for iid, q in rows if iid == item_id), 0)

    from services.utils import resolve_display_name
    name = await resolve_display_name(db, user_id, query.message.chat.id, query.from_user.first_name)

    base_text = _build_inventory_text(name, owned) if owned else (
        f"🎒 <b>ИНВЕНТАРЬ:</b> {name}\n\n<i>Инвентарь пуст.</i>"
    )
    desc = _build_item_description(item_id, qty)

    try:
        await query.message.edit_text(
            base_text + desc,
            reply_markup=_build_inventory_kb(owned, user_id, "has", selected_item=item_id),
            parse_mode="HTML",
        )
    except Exception:
        pass
    await query.answer()

# cmd_open_eggs / cb_open_egg УДАЛЕНЫ (БЛОК19 Ч.2): открытие яиц вырезано —
# питомцы добываются только через Гачу.
