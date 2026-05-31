from aiogram import Router, F, types
from aiogram.filters.callback_data import CallbackData
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.filters.text_commands import TextCmd
from core.registry import ITEMS_REGISTRY
from services.economy import EconomyService
from infrastructure.repositories.economy import get_inventory, get_balance
from services.utils import format_currency

router = Router(name="shop_router")
from bot.middlewares.module_check_mw import ModuleCheckMiddleware
router.message.middleware(ModuleCheckMiddleware("module_shop"))


class ShopCB(CallbackData, prefix="shop"):
    action: str          # "qty" | "do_buy" | "back"
    item_id: str = ""
    qty: int = 0


CATEGORIES = {
    "food":    "🥩 ЕДА И РАСХОДНИКИ",
    "egg":     "🥚 ЯЙЦА ПИТОМЦЕВ",
    "utility": "🛠 УТИЛИТЫ",
}

# Пресеты количества по категории
QTY_PRESETS = {
    "egg":     [1, 3, 5, 10],
    "food":    [1, 5, 10, 25],
    "utility": [1],
}
QTY_MAX_CAP = {"egg": 50, "food": 99, "utility": 5}


async def render_shop(target: types.Message, db, user_id: int, *, is_edit: bool):
    economy = EconomyService(db)
    has_discount = await economy.has_turtle_discount(user_id)
    inv = {r["item_id"]: r["quantity"] for r in await get_inventory(db, user_id)}

    lines = ["🏪 <b>ГЛОБАЛЬНЫЙ МАГАЗИН</b>"]
    if has_discount:
        lines.append("🐢 <i>Черепаха: скидка 5% активна!</i>")

    builder = InlineKeyboardBuilder()

    for cat_id, cat_name in CATEGORIES.items():
        items_in_cat = [(k, v) for k, v in ITEMS_REGISTRY.items() if v.get("category") == cat_id]
        if not items_in_cat:
            continue

        lines.append(f"\n<b>{cat_name}</b>")
        for item_id, item in items_in_cat:
            prices = await economy.get_item_prices(item_id, user_id, has_discount=has_discount)

            price_parts = []
            if prices["mora"] > 0:
                price_parts.append(f"<code>{prices['mora']}</code> 🪙")
            if prices["diamonds"] > 0:
                price_parts.append(f"<code>{prices['diamonds']}</code> 💎")
            price_str = " / ".join(price_parts) if price_parts else "<i>Только крафт</i>"

            owned = inv.get(item_id, 0)
            owned_badge = f"  <i>· у вас: {owned} шт.</i>" if owned > 0 else ""

            lines.append(
                f"┌ <b>{item['name']}</b> — {price_str}{owned_badge}\n"
                f"└ <i>{item.get('description', '')}</i>"
            )

            if price_parts:
                builder.button(
                    text=f"🛒 {item['name']}",
                    callback_data=ShopCB(action="qty", item_id=item_id),
                )

    builder.adjust(1)
    text = "\n".join(lines)

    if is_edit:
        await target.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    else:
        await target.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")


@router.message(TextCmd(["магазин", "лавка", "шоп"]))
async def cmd_shop(message: types.Message, db):
    if message.chat.type == "private":
        return
    await render_shop(message, db, message.from_user.id, is_edit=False)


# ── Шаг 1: показать выбор количества ─────────────────────────────────────────

@router.callback_query(ShopCB.filter(F.action == "qty"))
async def cb_shop_qty(query: types.CallbackQuery, callback_data: ShopCB, db):
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

    # Максимально доступное количество
    if prices["mora"] > 0 and prices["diamonds"] > 0:
        max_by_mora = int(balance["user_balance_mora"] // prices["mora"])
        max_by_dia = int(balance["user_balance_diamonds"] // prices["diamonds"])
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

    text = (
        f"🛒 <b>ПОКУПКА: {item['name']}</b>\n\n"
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
                callback_data=ShopCB(action="do_buy", item_id=item_id, qty=q),
            )

        # Кнопка MAX — если max выходит за пресеты
        if effective_max > 0 and effective_max not in presets_to_show:
            builder.button(
                text=f"×MAX ({effective_max})",
                callback_data=ShopCB(action="do_buy", item_id=item_id, qty=effective_max),
            )

        # Разбивка рядов: пресеты в первой строке (до 4), MAX отдельно, Back отдельно
        n_preset_btns = len(presets_to_show)
        n_max_btn = 1 if effective_max > 0 and effective_max not in presets_to_show else 0
        builder.button(text="🔙 Назад", callback_data=ShopCB(action="back"))

        rows = []
        if n_preset_btns:
            rows.append(min(4, n_preset_btns))
            remaining = n_preset_btns - rows[0]
            if remaining:
                rows.append(remaining)
        if n_max_btn:
            rows.append(1)
        rows.append(1)  # кнопка "Назад"
        builder.adjust(*rows)

    if max_affordable <= 0:
        builder.button(text="🔙 Назад", callback_data=ShopCB(action="back"))
        builder.adjust(1)

    await query.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await query.answer()


# ── Шаг 2: выполнить покупку ──────────────────────────────────────────────────

@router.callback_query(ShopCB.filter(F.action == "do_buy"))
async def cb_shop_do_buy(query: types.CallbackQuery, callback_data: ShopCB, db):
    item_id = callback_data.item_id
    qty = callback_data.qty

    if qty <= 0:
        return await query.answer("❌ Некорректное количество.", show_alert=True)

    economy = EconomyService(db)
    success, msg = await economy.purchase_item(query.from_user.id, item_id, qty)

    if success:
        item = ITEMS_REGISTRY.get(item_id, {})
        async with db.execute(
            "SELECT quantity FROM inventory WHERE user_id = ? AND item_id = ?",
            (query.from_user.id, item_id),
        ) as c:
            row = await c.fetchone()
            new_qty = row[0] if row else qty

        await query.answer(
            f"✅ Куплено {qty} шт. {item.get('name', item_id)}!\n"
            f"Теперь в наличии: {new_qty} шт.",
            show_alert=True,
        )
        await render_shop(query.message, db, query.from_user.id, is_edit=True)
    else:
        await query.answer(f"❌ Отказ: {msg}", show_alert=True)


# ── Назад в магазин ───────────────────────────────────────────────────────────

@router.callback_query(ShopCB.filter(F.action == "back"))
async def cb_shop_back(query: types.CallbackQuery, db):
    await render_shop(query.message, db, query.from_user.id, is_edit=True)
    await query.answer()
