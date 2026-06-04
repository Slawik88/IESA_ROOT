from aiogram import Router, F, types
from aiogram.filters.callback_data import CallbackData
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.filters.text_commands import TextCmd
from core.registry import ITEMS_REGISTRY
from services.economy import EconomyService
from services.achievements import increment_metric as ach_incr
from infrastructure.repositories.economy import get_inventory, get_balance
from services.utils import format_currency, check_callback_owner, safe_html

router = Router(name="shop_router")
from bot.middlewares.module_check_mw import ModuleCheckMiddleware
router.message.middleware(ModuleCheckMiddleware("module_shop"))


class ShopCB(CallbackData, prefix="shop"):
    action: str          # "qty" | "do_buy" | "back" | "info"
    item_id: str = ""
    qty: int = 0
    user_id: int = 0


CATEGORIES = {
    "food":    ("🥩", "ЕДА И КОРМ"),
    "egg":     ("🥚", "ЯЙЦА ПИТОМЦЕВ"),
    "utility": ("🛠", "УТИЛИТЫ"),
}

QTY_PRESETS = {
    "egg":     [1, 3, 5, 10],
    "food":    [1, 5, 10, 25],
    "utility": [1],
}
QTY_MAX_CAP = {"egg": 50, "food": 99, "utility": 5}

# Short item descriptions shown on ℹ️ press
_ITEM_INFO: dict[str, str] = {
    "food_basic":   "Снимает 15 усталости. Базовое питание.",
    "food_elite":   "Снимает 50 усталости. В 3× эффективнее базового.",
    "food_energy":  "−20 усталости + сбрасывает кулдаун экспедиции.",
    "food_super":   "−60 активному + −5 всем питомцам в питомнике.",
    "food_diamond": "Снимает усталость полностью + +20% эффективность на 24ч. Лучший корм.",
    "egg_basic":    "80% Обычный / 19% Редкий / 1% Эпический. Купить → «бот инвентарь» → Открыть.",
    "egg_summon":   "Крафтится из 5 💠 Осколков в магазине. Не даёт осколков при распылении.",
    "egg_silver":   "50% Обычный / 40% Редкий / 10% Эпический.",
    "egg_gold":     "75% Редкий / 25% Эпический. Только сильные питомцы.",
    "egg_mythic":   "40% Редкий / 60% Эпический. Только за алмазы.",
    "egg_unity":    "100% Легендарный. Только для семейных пар (общак).",
    "egg_crystal":  "30% Эпический / 70% Легендарный. Только из гачи.",
    "egg_daily":    "70% / 29% / 1%. Бесплатно из ежедневных заданий.",
    "study_notes":  "+50% XP от сообщений на 4 часа. Отлично для прокачки уровня.",
    "slot_expander":"Постоянно +1 слот в питомнике. Максимум 6 расширений.",
}


def _price_str(prices: dict) -> str:
    parts = []
    if prices["mora"] > 0:
        parts.append(f"{format_currency(prices['mora'])} 🪙")
    if prices["diamonds"] > 0:
        parts.append(f"{prices['diamonds']} 💎")
    return " / ".join(parts) if parts else "🔧 крафт"


async def render_shop(
    target: types.Message,
    db,
    user_id: int,
    *,
    is_edit: bool,
    selected_item: str = "",
):
    economy = EconomyService(db)
    has_discount = await economy.has_turtle_discount(user_id)
    inv = {r["item_id"]: r["quantity"] for r in await get_inventory(db, user_id)}
    bal = await get_balance(db, user_id)
    mora_str = format_currency(bal["user_balance_mora"])
    dia_str  = format_currency(bal["user_balance_diamonds"])

    lines = [
        "🏪 <b>ГЛОБАЛЬНЫЙ МАГАЗИН</b>",
        f"💳 <code>{mora_str} 🪙</code>  ·  <code>{dia_str} 💎</code>",
    ]
    if has_discount:
        lines.append("🐢 <i>Черепаха: −5% цена активна!</i>")

    builder = InlineKeyboardBuilder()

    for cat_id, (cat_icon, cat_label) in CATEGORIES.items():
        items_in_cat = [(k, v) for k, v in ITEMS_REGISTRY.items() if v.get("category") == cat_id]
        if not items_in_cat:
            continue

        lines.append(f"\n{cat_icon} <b>{cat_label}</b>")

        for item_id, item in items_in_cat:
            prices = await economy.get_item_prices(item_id, user_id, has_discount=has_discount)
            p_str = _price_str(prices)
            owned = inv.get(item_id, 0)
            owned_str = f"  <b>×{owned}</b>" if owned > 0 else ""

            mark = "▸ " if item_id == selected_item else ""
            lines.append(f"{'└' if item_id == items_in_cat[-1][0] else '├'} {mark}{item['name']} — {p_str}{owned_str}")

            can_buy = prices["mora"] > 0 or prices["diamonds"] > 0
            if can_buy:
                builder.button(
                    text=f"🛒 {item['name']}",
                    callback_data=ShopCB(action="qty", item_id=item_id, user_id=user_id),
                )
            builder.button(
                text="ℹ️",
                callback_data=ShopCB(action="info", item_id=item_id, user_id=user_id),
            )

    # Item description block if selected
    if selected_item and selected_item in ITEMS_REGISTRY:
        item = ITEMS_REGISTRY[selected_item]
        desc = _ITEM_INFO.get(selected_item) or item.get("description", "")
        lines.append(
            f"\n{'─' * 18}\n"
            f"📦 <b>{safe_html(item['name'])}</b>\n"
            f"<i>{safe_html(desc)}</i>"
        )

    lines.append("\n<i>Нажми ℹ️ рядом с предметом для описания.</i>")

    # Adjust: pairs (buy+info) for purchasable, single (info) for craft-only
    rows = []
    for cat_id, _ in CATEGORIES.items():
        for item_id, item in ((k, v) for k, v in ITEMS_REGISTRY.items() if v.get("category") == cat_id):
            prices_dummy = {"mora": item.get("price_mora", 0), "diamonds": item.get("price_diamonds", 0)}
            can_buy = prices_dummy["mora"] > 0 or prices_dummy["diamonds"] > 0
            rows.append(2 if can_buy else 1)

    builder.adjust(*rows)
    text = "\n".join(lines)

    if is_edit:
        try:
            await target.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        except Exception:
            pass
    else:
        await target.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")


@router.message(TextCmd(["магазин", "лавка", "шоп"]))
async def cmd_shop(message: types.Message, db):
    if message.chat.type == "private":
        return
    await render_shop(message, db, message.from_user.id, is_edit=False)


# ── Info ──────────────────────────────────────────────────────────────────────

@router.callback_query(ShopCB.filter(F.action == "info"))
async def cb_shop_info(query: types.CallbackQuery, callback_data: ShopCB, db):
    await render_shop(
        query.message, db, query.from_user.id,
        is_edit=True, selected_item=callback_data.item_id,
    )
    await query.answer()


# ── Шаг 1: показать выбор количества ─────────────────────────────────────────

@router.callback_query(ShopCB.filter(F.action == "qty"))
async def cb_shop_qty(query: types.CallbackQuery, callback_data: ShopCB, db):
    if not await check_callback_owner(query, callback_data.user_id):
        return
    item_id = callback_data.item_id
    item = ITEMS_REGISTRY.get(item_id)
    if not item:
        return await query.answer("❌ Предмет не найден.", show_alert=True)

    economy = EconomyService(db)
    has_discount = await economy.has_turtle_discount(query.from_user.id)
    prices = await economy.get_item_prices(item_id, query.from_user.id, has_discount=has_discount)
    balance = await get_balance(db, query.from_user.id)
    inv = {r["item_id"]: r["quantity"] for r in await get_inventory(db, query.from_user.id)}
    owned = inv.get(item_id, 0)

    if prices["mora"] > 0 and prices["diamonds"] > 0:
        max_by_mora = int(balance["user_balance_mora"] // prices["mora"])
        max_by_dia  = int(balance["user_balance_diamonds"] // prices["diamonds"])
        max_affordable = min(max_by_mora, max_by_dia)
        balance_str = f"{format_currency(balance['user_balance_mora'])} 🪙  ·  {format_currency(balance['user_balance_diamonds'])} 💎"
    elif prices["mora"] > 0:
        max_affordable = int(balance["user_balance_mora"] // prices["mora"])
        balance_str = f"{format_currency(balance['user_balance_mora'])} 🪙"
    elif prices["diamonds"] > 0:
        max_affordable = int(balance["user_balance_diamonds"] // prices["diamonds"])
        balance_str = f"{format_currency(balance['user_balance_diamonds'])} 💎"
    else:
        max_affordable = 0
        balance_str = "—"

    price_parts = []
    if prices["mora"] > 0:
        price_parts.append(f"{prices['mora']} 🪙/шт.")
    if prices["diamonds"] > 0:
        price_parts.append(f"{prices['diamonds']} 💎/шт.")
    price_str = " · ".join(price_parts)

    desc = _ITEM_INFO.get(item_id) or item.get("description", "")
    text = (
        f"🛒 <b>ПОКУПКА: {item['name']}</b>\n\n"
        f"💬 <i>{safe_html(desc)}</i>\n\n"
        f"💰 Цена: {price_str}\n"
        f"🎒 В наличии: <b>{owned} шт.</b>\n"
        f"💳 Баланс: {balance_str}\n\n"
    )

    builder = InlineKeyboardBuilder()

    if max_affordable <= 0:
        text += "❌ <i>Недостаточно средств для покупки.</i>"
    else:
        text += "<i>Выберите количество:</i>"
        cat = item.get("category", "food")
        presets = QTY_PRESETS.get(cat, [1, 5, 10])
        cap = QTY_MAX_CAP.get(cat, 99)
        effective_max = min(max_affordable, cap)

        presets_to_show = [q for q in presets if q <= effective_max]
        for q in presets_to_show:
            builder.button(
                text=f"×{q}",
                callback_data=ShopCB(action="do_buy", item_id=item_id, qty=q, user_id=callback_data.user_id),
            )
        if effective_max > 0 and effective_max not in presets_to_show:
            builder.button(
                text=f"×MAX ({effective_max})",
                callback_data=ShopCB(action="do_buy", item_id=item_id, qty=effective_max, user_id=callback_data.user_id),
            )

        n_preset_btns = len(presets_to_show)
        n_max_btn = 1 if effective_max > 0 and effective_max not in presets_to_show else 0
        builder.button(text="🔙 Назад", callback_data=ShopCB(action="back", user_id=callback_data.user_id))
        rows = []
        if n_preset_btns:
            rows.append(min(4, n_preset_btns))
            remaining = n_preset_btns - rows[0]
            if remaining:
                rows.append(remaining)
        if n_max_btn:
            rows.append(1)
        rows.append(1)
        builder.adjust(*rows)

    if max_affordable <= 0:
        builder.button(text="🔙 Назад", callback_data=ShopCB(action="back", user_id=callback_data.user_id))
        builder.adjust(1)

    await query.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await query.answer()


# ── Шаг 2: выполнить покупку ──────────────────────────────────────────────────

@router.callback_query(ShopCB.filter(F.action == "do_buy"))
async def cb_shop_do_buy(query: types.CallbackQuery, callback_data: ShopCB, db):
    if not await check_callback_owner(query, callback_data.user_id):
        return
    item_id = callback_data.item_id
    qty = callback_data.qty

    if qty <= 0:
        return await query.answer("❌ Некорректное количество.", show_alert=True)

    item = ITEMS_REGISTRY.get(item_id, {})
    cat = item.get("category", "food")
    cap = QTY_MAX_CAP.get(cat, 99)
    if qty > cap:
        return await query.answer(f"❌ Максимум: {cap} шт.", show_alert=True)

    economy = EconomyService(db)
    success, msg = await economy.purchase_item(query.from_user.id, item_id, qty)

    if success:
        # Track patron achievement (mora spent in shop)
        prices = await economy.get_item_prices(item_id, query.from_user.id)
        mora_spent = prices["mora"] * qty
        if mora_spent > 0:
            try:
                await ach_incr(db, query.from_user.id, "total_mora_spent_shop", delta=mora_spent)
                await db.commit()
            except Exception:
                pass
        async with db.execute(
            "SELECT quantity FROM inventory WHERE user_id = ? AND item_id = ?",
            (query.from_user.id, item_id),
        ) as c:
            row = await c.fetchone()
            new_qty = row[0] if row else qty

        await query.answer(
            f"✅ Куплено {qty}× {item.get('name', item_id)}!\nТеперь: {new_qty} шт.",
            show_alert=True,
        )
        await render_shop(query.message, db, query.from_user.id, is_edit=True)
    else:
        await query.answer(f"❌ {msg}", show_alert=True)


# ── Назад в магазин ───────────────────────────────────────────────────────────

@router.callback_query(ShopCB.filter(F.action == "back"))
async def cb_shop_back(query: types.CallbackQuery, callback_data: ShopCB, db):
    if not await check_callback_owner(query, callback_data.user_id):
        return
    await render_shop(query.message, db, query.from_user.id, is_edit=True)
    await query.answer()
