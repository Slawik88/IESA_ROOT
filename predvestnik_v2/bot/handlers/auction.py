"""
bot/handlers/auction.py
B13: Global auction — create lots, browse, bid, cancel.
Uses in-memory pending_lots dict for multi-step creation (no FSM needed).
"""
import asyncio
from datetime import datetime, timezone, timedelta

from aiogram import Router, types, F
from aiogram.filters.callback_data import CallbackData
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.filters.text_commands import TextCmd
from core.constants import AUCTION_MIN_BID, AUCTION_COMMISSION
from core.registry import ITEMS_REGISTRY, PET_SPECIES
from infrastructure.repositories import economy as eco_repo
from infrastructure.repositories.auction import (
    get_active_lots, get_lot, get_seller_active_lots, get_highest_bid,
    get_user_active_bids, get_reserve,
)
from services.auction import create_auction_lot, place_bid, cancel_lot
from services.quests import increment_metric as quest_increment
from services.utils import safe_html, format_currency

router = Router(name="auction_router")
from bot.middlewares.module_check_mw import ModuleCheckMiddleware
router.message.middleware(ModuleCheckMiddleware("module_auction"))

# ── In-memory pending lot creation state ─────────────────────────────────────
_pending: dict[int, dict] = {}  # {user_id: {...creation state...}}

_CATEGORIES = {
    "pets":         ("🐾", "Питомцы"),
    "consumables":  ("🍗", "Расходники"),
    "eggs":         ("🥚", "Яйца"),
    "materials":    ("🪨", "Материалы"),
    "boosters":     ("⚡", "Бусты"),
}

_ITEM_CATEGORIES = {
    "food":       "consumables",
    "egg":        "eggs",
    "material":   "materials",
    "booster":    "boosters",
    "spin_token": "boosters",
}


def _item_category(item_id: str) -> str:
    item = ITEMS_REGISTRY.get(item_id, {})
    cat = item.get("category", "")
    for prefix, auc_cat in _ITEM_CATEGORIES.items():
        if cat.startswith(prefix) or cat == prefix:
            return auc_cat
    return "consumables"


def _time_left(ends_at_str: str) -> str:
    try:
        ends = datetime.strptime(ends_at_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        delta = ends - datetime.now(timezone.utc)
        if delta.total_seconds() <= 0:
            return "истёк"
        h, rem = divmod(int(delta.total_seconds()), 3600)
        m = rem // 60
        return f"{h}ч {m}м"
    except Exception:
        return "?"


def _lot_line(lot: dict, show_timer: bool = True) -> str:
    name = lot.get("item_name", "?")
    qty = lot["quantity"]
    qty_str = f"×{qty}" if qty > 1 else ""
    timer = f" · ⏳{_time_left(lot['ends_at'])}" if show_timer else ""
    return f"<b>{name}{qty_str}</b> — от <code>{lot['min_bid']:.0f} 🪙</code>{timer}"


# ── Callbacks ──────────────────────────────────────────────────────────────────

class AucCB(CallbackData, prefix="auc"):
    action: str   # menu | browse | cat | lot | bid_prompt | bid_confirm | cancel_lot
                  # create_start | create_cat | create_item | create_qty | create_bid
                  # create_buyout | create_confirm | my_lots | my_bids | cancel_create
    v: str = ""   # flexible value
    page: int = 0


# ── Main menu ──────────────────────────────────────────────────────────────────

async def _build_menu_text(db, user_id: int) -> str:
    bal = await eco_repo.get_balance(db, user_id)
    reserved = await get_reserve(db, user_id)
    free = bal["user_balance_mora"] - reserved
    return (
        "🏛 <b>АУКЦИОН</b>\n\n"
        f"├ Баланс: <code>{format_currency(bal['user_balance_mora'])} 🪙</code>"
        f" · Свободно: <code>{format_currency(free)} 🪙</code>\n"
        f"└ Зарезервировано: <code>{format_currency(reserved)} 🪙</code>"
    )


def _menu_kb() -> types.InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for cat_id, (icon, label) in _CATEGORIES.items():
        b.button(text=f"{icon} {label}", callback_data=AucCB(action="cat", v=cat_id))
    b.button(text="➕ Выставить лот", callback_data=AucCB(action="create_start"))
    b.button(text="📋 Мои лоты",     callback_data=AucCB(action="my_lots"))
    b.button(text="🎯 Мои ставки",   callback_data=AucCB(action="my_bids"))
    b.adjust(2, 2, 1, 1, 1, 1)
    return b.as_markup()


@router.message(TextCmd(["аукцион"]))
async def cmd_auction(message: types.Message, db, text_args: str = None):
    if message.chat.type == "private":
        return
    text = await _build_menu_text(db, message.from_user.id)
    await message.answer(text, reply_markup=_menu_kb(), parse_mode="HTML")


@router.callback_query(AucCB.filter(F.action == "menu"))
async def cb_auc_menu(query: types.CallbackQuery, db):
    text = await _build_menu_text(db, query.from_user.id)
    await query.message.edit_text(text, reply_markup=_menu_kb(), parse_mode="HTML")
    await query.answer()


# ── Browse by category ─────────────────────────────────────────────────────────

@router.callback_query(AucCB.filter(F.action == "cat"))
async def cb_auc_category(query: types.CallbackQuery, callback_data: AucCB, db):
    cat_id = callback_data.v
    page = callback_data.page
    lots = await get_active_lots(db, category=cat_id, limit=8, offset=page * 8)
    icon, label = _CATEGORIES.get(cat_id, ("🏛", cat_id))

    b = InlineKeyboardBuilder()
    if not lots:
        text = f"{icon} <b>{label}</b>\n\n<i>Лотов пока нет.</i>"
    else:
        lines = [f"{icon} <b>{label}</b> ({len(lots)} лотов)\n"]
        for lot in lots:
            lines.append(f"├ {_lot_line(lot)}")
            b.button(
                text=f"🔍 Лот #{lot['id']}: {lot.get('item_name','?')}",
                callback_data=AucCB(action="lot", v=str(lot["id"])),
            )
        if lines[-1].startswith("├"):
            lines[-1] = "└" + lines[-1][1:]
        text = "\n".join(lines)

    b.button(text="⬅️ Меню", callback_data=AucCB(action="menu"))
    b.adjust(1)
    await query.message.edit_text(text, reply_markup=b.as_markup(), parse_mode="HTML")
    await query.answer()


# ── Lot detail & bidding ───────────────────────────────────────────────────────

@router.callback_query(AucCB.filter(F.action == "lot"))
async def cb_auc_lot(query: types.CallbackQuery, callback_data: AucCB, db):
    lot_id = int(callback_data.v)
    lot = await get_lot(db, lot_id)
    if not lot or lot["status"] != "active":
        await query.answer("❌ Лот недоступен.", show_alert=True)
        return

    highest = await get_highest_bid(db, lot_id)
    cur_bid = highest["amount"] if highest else lot["min_bid"]
    min_next = int(cur_bid * 1.05) if highest else int(lot["min_bid"])

    b = InlineKeyboardBuilder()
    if lot["seller_id"] != query.from_user.id:
        b.button(text=f"💰 Ставка {min_next} 🪙",
                 callback_data=AucCB(action="bid_confirm", v=f"{lot_id}:{min_next}"))
        if lot.get("buyout"):
            b.button(text=f"⚡ Выкуп {int(lot['buyout'])} 🪙",
                     callback_data=AucCB(action="bid_confirm", v=f"{lot_id}:{int(lot['buyout'])}"))
    else:
        b.button(text="❌ Отменить лот", callback_data=AucCB(action="cancel_lot", v=str(lot_id)))

    cat_id = lot["category"]
    b.button(text="⬅️ К категории", callback_data=AucCB(action="cat", v=cat_id))
    b.adjust(1)

    qty_str = f" ×{lot['quantity']}" if lot["quantity"] > 1 else ""
    raise_str = f" (×1.05 = {min_next} 🪙)" if highest else ""
    buyout_line = f"├ ⚡ Выкуп: <code>{lot['buyout']:.0f} 🪙</code>\n" if lot.get("buyout") else ""
    text = (
        f"🏛 <b>Лот #{lot_id}</b>\n\n"
        f"├ 📦 {lot.get('item_name', '?')}{qty_str}\n"
        f"├ 💰 Мин. ставка: <code>{lot['min_bid']:.0f} 🪙</code>\n"
        f"├ 🔼 Текущая: <code>{cur_bid:.0f} 🪙</code>{raise_str}\n"
        + buyout_line
        + f"└ ⏳ Осталось: <b>{_time_left(lot['ends_at'])}</b>"
    )
    await query.message.edit_text(text, reply_markup=b.as_markup(), parse_mode="HTML")
    await query.answer()


@router.callback_query(AucCB.filter(F.action == "bid_confirm"))
async def cb_bid_confirm(query: types.CallbackQuery, callback_data: AucCB, db):
    lot_id_str, amount_str = callback_data.v.split(":")
    lot_id = int(lot_id_str)
    amount = float(amount_str)

    result = await place_bid(db, lot_id, query.from_user.id, amount,
                             chat_id=query.message.chat.id)
    if not result["ok"]:
        await query.answer(f"❌ {result['error']}", show_alert=True)
        return

    # Quest: auction_bids_today
    try:
        await quest_increment(db, query.from_user.id, query.message.chat.id, "auction_bids_today", delta=1.0)
        await db.commit()
    except Exception:
        pass

    await query.answer(f"✅ Ставка {amount:.0f} 🪙 принята!", show_alert=False)

    # Notify outbid user via DM (best effort)
    if result.get("outbid_user_id"):
        try:
            bot = query.bot
            lot = result["lot"]
            await bot.send_message(
                result["outbid_user_id"],
                f"🎯 Вашу ставку на лот «{lot.get('item_name','?')}» перебили!\n"
                f"Текущая ставка: <code>{amount:.0f} 🪙</code>\n"
                f"Осталось: {_time_left(lot['ends_at'])}",
                parse_mode="HTML",
            )
        except Exception:
            pass

    if result.get("is_buyout"):
        await query.message.edit_text(
            f"⚡ <b>Моментальный выкуп!</b> Лот #{lot_id} продан за <code>{amount:.0f} 🪙</code>.",
            parse_mode="HTML",
        )
    else:
        await cb_auc_lot(query, AucCB(action="lot", v=str(lot_id)), db)


@router.callback_query(AucCB.filter(F.action == "cancel_lot"))
async def cb_cancel_lot(query: types.CallbackQuery, callback_data: AucCB, db):
    lot_id = int(callback_data.v)
    ok, msg = await cancel_lot(db, lot_id, query.from_user.id)
    await query.answer(f"{'✅' if ok else '❌'} {msg}", show_alert=True)
    if ok:
        await cb_auc_menu(query, db)


# ── My lots / My bids ──────────────────────────────────────────────────────────

@router.callback_query(AucCB.filter(F.action == "my_lots"))
async def cb_my_lots(query: types.CallbackQuery, db):
    lots = await get_seller_active_lots(db, query.from_user.id)
    b = InlineKeyboardBuilder()
    if not lots:
        text = "📋 <b>МОИ ЛОТЫ</b>\n\n<i>У вас нет активных лотов.</i>"
    else:
        lines = ["📋 <b>МОИ ЛОТЫ</b>\n"]
        for lot in lots:
            highest = await get_highest_bid(db, lot["id"])
            cur = f"Ставка: {highest['amount']:.0f} 🪙" if highest else "Ставок нет"
            lines.append(f"├ {_lot_line(lot)} · {cur}")
            b.button(text=f"🔍 #{lot['id']} {lot.get('item_name','?')}",
                     callback_data=AucCB(action="lot", v=str(lot["id"])))
        lines[-1] = "└" + lines[-1][1:]
        text = "\n".join(lines)
    b.button(text="⬅️ Меню", callback_data=AucCB(action="menu"))
    b.adjust(1)
    await query.message.edit_text(text, reply_markup=b.as_markup(), parse_mode="HTML")
    await query.answer()


@router.callback_query(AucCB.filter(F.action == "my_bids"))
async def cb_my_bids(query: types.CallbackQuery, db):
    bids = await get_user_active_bids(db, query.from_user.id)
    b = InlineKeyboardBuilder()
    if not bids:
        text = "🎯 <b>МОИ СТАВКИ</b>\n\n<i>Нет активных ставок.</i>"
    else:
        lines = ["🎯 <b>МОИ СТАВКИ</b>\n"]
        for bid in bids:
            lines.append(
                f"├ Лот #{bid['lot_id']} <b>{bid.get('item_name','?')}</b> — "
                f"<code>{bid['amount']:.0f} 🪙</code> · ⏳{_time_left(bid['ends_at'])}"
            )
        lines[-1] = "└" + lines[-1][1:]
        text = "\n".join(lines)
    b.button(text="⬅️ Меню", callback_data=AucCB(action="menu"))
    b.adjust(1)
    await query.message.edit_text(text, reply_markup=b.as_markup(), parse_mode="HTML")
    await query.answer()


# ── Lot creation (button-based multi-step) ────────────────────────────────────

@router.callback_query(AucCB.filter(F.action == "create_start"))
async def cb_create_start(query: types.CallbackQuery, db):
    _pending[query.from_user.id] = {}
    b = InlineKeyboardBuilder()
    for cat_id, (icon, label) in _CATEGORIES.items():
        b.button(text=f"{icon} {label}", callback_data=AucCB(action="create_cat", v=cat_id))
    b.button(text="❌ Отмена", callback_data=AucCB(action="cancel_create"))
    b.adjust(2, 2, 1)
    await query.message.edit_text(
        "🏛 <b>ВЫСТАВИТЬ ЛОТ</b>\n\nВыберите категорию предмета:",
        reply_markup=b.as_markup(),
        parse_mode="HTML",
    )
    await query.answer()


@router.callback_query(AucCB.filter(F.action == "create_cat"))
async def cb_create_cat(query: types.CallbackQuery, callback_data: AucCB, db):
    user_id = query.from_user.id
    cat = callback_data.v
    _pending.setdefault(user_id, {})["category"] = cat

    # Build item list from inventory
    inv = await eco_repo.get_inventory(db, user_id)
    b = InlineKeyboardBuilder()
    shown = 0
    for item in inv:
        iid = item["item_id"]
        item_data = ITEMS_REGISTRY.get(iid, {})
        if _item_category(iid) != cat and cat != "pets":
            continue
        qty = item["quantity"]
        name = item_data.get("name", iid)
        b.button(
            text=f"{name} ×{qty}",
            callback_data=AucCB(action="create_item", v=f"{iid}:{qty}"),
        )
        shown += 1

    if cat == "pets":
        pets = await _get_user_pets_for_auction(db, user_id)
        for pet in pets[:10]:
            sp = PET_SPECIES.get(pet["species_id"], {})
            name = f"{sp.get('name','?')} Lv{pet.get('pet_level') or 1}"
            b.button(
                text=name,
                callback_data=AucCB(action="create_item", v=f"PET:{pet['id']}"),
            )
            shown += 1

    if shown == 0:
        b.button(text="⬅️ Назад", callback_data=AucCB(action="create_start"))
        await query.message.edit_text(
            "🏛 <b>ВЫСТАВИТЬ ЛОТ</b>\n\n<i>В этой категории нет предметов в инвентаре.</i>",
            reply_markup=b.as_markup(),
            parse_mode="HTML",
        )
    else:
        b.button(text="❌ Отмена", callback_data=AucCB(action="cancel_create"))
        b.adjust(1)
        await query.message.edit_text(
            "🏛 <b>ВЫСТАВИТЬ ЛОТ</b>\n\nВыберите предмет:",
            reply_markup=b.as_markup(),
            parse_mode="HTML",
        )
    await query.answer()


async def _get_user_pets_for_auction(db, user_id: int) -> list[dict]:
    from infrastructure.repositories.zoo import get_user_pets
    pets = await get_user_pets(db, user_id, placement="storage")
    return pets[:10]


@router.callback_query(AucCB.filter(F.action == "create_item"))
async def cb_create_item(query: types.CallbackQuery, callback_data: AucCB, db):
    user_id = query.from_user.id
    v = callback_data.v
    _pending.setdefault(user_id, {})["item_v"] = v

    b = InlineKeyboardBuilder()
    if v.startswith("PET:"):
        # Pets: quantity always 1
        _pending[user_id]["quantity"] = 1
        _show_bid_step(b, user_id)
        await query.message.edit_text(
            "🏛 <b>ВЫСТАВИТЬ ЛОТ</b>\n\nМинимальная ставка (Моры):",
            reply_markup=b.as_markup(),
            parse_mode="HTML",
        )
    else:
        item_id, max_qty_str = v.split(":", 1)
        max_qty = int(max_qty_str)
        presets = [1, 5, 10, max_qty] if max_qty > 10 else list(range(1, min(max_qty + 1, 5)))
        for q in sorted(set(presets)):
            if q <= max_qty:
                b.button(text=str(q), callback_data=AucCB(action="create_qty", v=str(q)))
        b.button(text="❌ Отмена", callback_data=AucCB(action="cancel_create"))
        b.adjust(4, 1)
        await query.message.edit_text(
            f"🏛 <b>ВЫСТАВИТЬ ЛОТ</b>\n\nСколько выставить? (у вас {max_qty})",
            reply_markup=b.as_markup(),
            parse_mode="HTML",
        )
    await query.answer()


def _show_bid_step(b: InlineKeyboardBuilder, user_id: int):
    for preset in [100, 500, 1000, 5000]:
        b.button(text=f"{preset} 🪙", callback_data=AucCB(action="create_bid", v=str(preset)))
    b.button(text="❌ Отмена", callback_data=AucCB(action="cancel_create"))
    b.adjust(2, 2, 1)


@router.callback_query(AucCB.filter(F.action == "create_qty"))
async def cb_create_qty(query: types.CallbackQuery, callback_data: AucCB):
    user_id = query.from_user.id
    _pending.setdefault(user_id, {})["quantity"] = int(callback_data.v)
    b = InlineKeyboardBuilder()
    _show_bid_step(b, user_id)
    await query.message.edit_text(
        "🏛 <b>ВЫСТАВИТЬ ЛОТ</b>\n\nМинимальная ставка (Моры):",
        reply_markup=b.as_markup(),
        parse_mode="HTML",
    )
    await query.answer()


@router.callback_query(AucCB.filter(F.action == "create_bid"))
async def cb_create_bid(query: types.CallbackQuery, callback_data: AucCB):
    user_id = query.from_user.id
    _pending.setdefault(user_id, {})["min_bid"] = float(callback_data.v)
    b = InlineKeyboardBuilder()
    bid = float(callback_data.v)
    for mult in [2, 5, 10]:
        b.button(text=f"{int(bid * mult)} 🪙",
                 callback_data=AucCB(action="create_buyout", v=str(int(bid * mult))))
    b.button(text="Без выкупа", callback_data=AucCB(action="create_buyout", v="0"))
    b.button(text="❌ Отмена", callback_data=AucCB(action="cancel_create"))
    b.adjust(3, 1, 1)
    await query.message.edit_text(
        "🏛 <b>ВЫСТАВИТЬ ЛОТ</b>\n\nЦена моментального выкупа (опционально):",
        reply_markup=b.as_markup(),
        parse_mode="HTML",
    )
    await query.answer()


@router.callback_query(AucCB.filter(F.action == "create_buyout"))
async def cb_create_buyout(query: types.CallbackQuery, callback_data: AucCB, db):
    user_id = query.from_user.id
    buyout = float(callback_data.v)
    _pending.setdefault(user_id, {})["buyout"] = buyout if buyout > 0 else None

    pending = _pending.get(user_id, {})
    v = pending.get("item_v", "")
    qty = pending.get("quantity", 1)
    min_bid = pending.get("min_bid", AUCTION_MIN_BID)
    buyout_val = pending.get("buyout")
    cat = pending.get("category", "consumables")

    # Resolve item name
    if v.startswith("PET:"):
        pet_id = int(v.split(":")[1])
        async with db.execute("SELECT species_id, COALESCE(pet_level,1) FROM pets WHERE id = ?", (pet_id,)) as c:
            row = await c.fetchone()
        if row:
            sp = PET_SPECIES.get(row[0], {})
            item_name = f"{sp.get('name','?')} Lv{row[1]}"
        else:
            item_name = f"Питомец #{pet_id}"
    else:
        item_id = v.split(":")[0]
        item_name = ITEMS_REGISTRY.get(item_id, {}).get("name", item_id)

    b = InlineKeyboardBuilder()
    b.button(text="✅ Выставить", callback_data=AucCB(action="create_confirm"))
    b.button(text="❌ Отмена", callback_data=AucCB(action="cancel_create"))
    b.adjust(1)

    buyout_str = f"<code>{buyout_val:.0f} 🪙</code>" if buyout_val else "<i>Нет</i>"
    await query.message.edit_text(
        f"🏛 <b>ПОДТВЕРЖДЕНИЕ ЛОТА</b>\n\n"
        f"├ 📦 <b>{item_name}</b>"
        f"{f' ×{qty}' if qty > 1 else ''}\n"
        f"├ 💰 Мин. ставка: <code>{min_bid:.0f} 🪙</code>\n"
        f"├ ⚡ Выкуп: {buyout_str}\n"
        f"└ ⏳ Длительность: 24ч",
        reply_markup=b.as_markup(),
        parse_mode="HTML",
    )
    await query.answer()


@router.callback_query(AucCB.filter(F.action == "create_confirm"))
async def cb_create_confirm(query: types.CallbackQuery, db):
    user_id = query.from_user.id
    pending = _pending.pop(user_id, {})
    if not pending:
        return await query.answer("❌ Данные лота утеряны. Начните заново.", show_alert=True)

    v = pending.get("item_v", "")
    qty = pending.get("quantity", 1)
    min_bid = pending.get("min_bid", AUCTION_MIN_BID)
    buyout = pending.get("buyout")
    cat = pending.get("category", "consumables")

    if v.startswith("PET:"):
        pet_id = int(v.split(":")[1])
        item_type = "pet"
        item_id_or_pet_id = pet_id
        async with db.execute("SELECT species_id, COALESCE(pet_level,1) FROM pets WHERE id = ?", (pet_id,)) as c:
            row = await c.fetchone()
        sp = PET_SPECIES.get(row[0] if row else "", {})
        item_name = f"{sp.get('name','?')} Lv{row[1] if row else 1}"
        # Remove pet from seller's storage
        await db.execute("UPDATE pets SET placement = 'auction' WHERE id = ? AND owner_id = ?",
                         (pet_id, user_id))
    else:
        item_id = v.split(":")[0]
        item_type = "inventory"
        item_id_or_pet_id = 0  # stored as string in item_name context; we save item_id string as int hash
        item_name = ITEMS_REGISTRY.get(item_id, {}).get("name", item_id)
        # Remove from inventory
        from infrastructure.repositories.economy import remove_item
        ok = await remove_item(db, user_id, item_id, qty, commit=False)
        if not ok:
            await db.rollback()
            return await query.answer("❌ Недостаточно предметов.", show_alert=True)
        # Store item_id encoded as integer via hash (we use item_name for display)
        item_id_or_pet_id = abs(hash(item_id)) % (10**9)
        # Store actual item_id string in item_name suffix (workaround since column is INT)
        item_name = f"{item_name}||{item_id}"  # delimiter for resolver

    ok, result = await create_auction_lot(
        db, user_id, cat, item_type, item_id_or_pet_id, qty, item_name, min_bid, buyout
    )

    if not ok:
        await query.answer(f"❌ {result}", show_alert=True)
    else:
        await query.answer("✅ Лот выставлен!", show_alert=False)
        await query.message.edit_text(
            f"✅ <b>Лот #{result} создан!</b>\n<i>Аукцион длится 24 часа.</i>",
            parse_mode="HTML",
        )


@router.callback_query(AucCB.filter(F.action == "cancel_create"))
async def cb_cancel_create(query: types.CallbackQuery):
    _pending.pop(query.from_user.id, None)
    await query.answer("❌ Создание лота отменено.")
    await cb_auc_menu(query, query.bot)


# ── бот аукцион [sub] text commands ───────────────────────────────────────────

@router.message(TextCmd(["аукцион выставить", "аукцион создать"]))
async def cmd_auction_create(message: types.Message, db):
    if message.chat.type == "private":
        return
    _pending[message.from_user.id] = {}
    b = InlineKeyboardBuilder()
    for cat_id, (icon, label) in _CATEGORIES.items():
        b.button(text=f"{icon} {label}", callback_data=AucCB(action="create_cat", v=cat_id))
    b.button(text="❌ Отмена", callback_data=AucCB(action="cancel_create"))
    b.adjust(2, 2, 1)
    await message.answer(
        "🏛 <b>ВЫСТАВИТЬ ЛОТ</b>\n\nВыберите категорию предмета:",
        reply_markup=b.as_markup(),
        parse_mode="HTML",
    )


@router.message(TextCmd(["аукцион мои"]))
async def cmd_auction_my(message: types.Message, db):
    if message.chat.type == "private":
        return
    lots = await get_seller_active_lots(db, message.from_user.id)
    if not lots:
        return await message.answer("📋 <b>МОИ ЛОТЫ</b>\n\n<i>Нет активных лотов.</i>", parse_mode="HTML")
    lines = ["📋 <b>МОИ ЛОТЫ</b>\n"]
    for lot in lots:
        lines.append(f"├ Лот #{lot['id']}: {_lot_line(lot)}")
    lines[-1] = "└" + lines[-1][1:]
    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(TextCmd(["аукцион ставка"]))
async def cmd_auction_bid(message: types.Message, db, text_args: str = None):
    if message.chat.type == "private":
        return
    raw = (text_args or "").strip()
    parts = [p.strip() for p in raw.split(",")]
    if len(parts) < 2:
        return await message.answer(
            "ℹ️ <b>Использование:</b> <code>бот аукцион ставка, [lot_id], [сумма]</code>",
            parse_mode="HTML",
        )
    try:
        lot_id = int(parts[0])
        amount = float(parts[1])
    except ValueError:
        return await message.answer("❌ Неверный формат.", parse_mode="HTML")

    result = await place_bid(db, lot_id, message.from_user.id, amount, message.chat.id)
    if not result["ok"]:
        return await message.answer(f"❌ {result['error']}", parse_mode="HTML")

    await message.answer(f"✅ Ставка <code>{amount:.0f} 🪙</code> на лот #{lot_id} принята!", parse_mode="HTML")
