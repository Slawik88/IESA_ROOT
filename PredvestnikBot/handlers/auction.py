"""
handlers/auction.py — Команды аукциона.

Команды:
  бот аукцион               — просмотр активных лотов
  бот продать <id> <цена>   — выставить предмет на аукцион
  бот продать <id> <цена> <выкуп> — с ценой мгновенного выкупа
  бот ставка <id> <сумма>   — сделать ставку
  бот выкупить <id>         — мгновенный выкуп
  бот мои лоты              — мои активные лоты и ставки
  бот отмена лот <id>       — отменить свой лот
"""

import html
from datetime import datetime, timezone

from aiogram import Router
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from filters.bot_command import BotCommand
from utils.helpers import user_mention

router = Router()


def esc(s) -> str:
    return html.escape(str(s or ""))


# ─── Список активных аукционов ────────────────────────────────────────────────

@router.message(BotCommand("аукцион"))
async def cmd_auction_list(message: Message, cmd_args: str):
    chat_id = message.chat.id
    from api.auction import get_active_auctions

    lots = await get_active_auctions(chat_id)
    if not lots:
        await message.answer("🏪 <b>Аукцион</b>\n\nАктивных лотов нет. Выставьте предмет командой:\n<code>бот продать &lt;id_предмета&gt; &lt;цена&gt;</code>", parse_mode="HTML")
        return

    lines = ["🏪 <b>Активные лоты аукциона:</b>\n"]
    for a in lots[:10]:
        buyout_str = f" | Выкуп: {a['buyout_price']} 🪙" if a.get("buyout_price") else ""
        lines.append(
            f"<b>#{a['id']}</b> {esc(a['item_emoji'])} <b>{esc(a['item_name'])}</b> "
            f"[{esc(a['item_rarity'])}]\n"
            f"   💰 Текущая: <b>{a['current_price']} 🪙</b> (мин. ставка: {a['min_bid']}){buyout_str}\n"
            f"   👤 Продавец: {esc(a.get('seller_name') or 'Аноним')} "
            f"| ⏳ Осталось: {a.get('remaining_str','?')}"
        )

    # Кнопки для первых 5 лотов
    buttons = []
    for a in lots[:5]:
        row = [InlineKeyboardButton(
            text=f"#{a['id']} {a['item_emoji']} {a['item_name'][:15]}",
            callback_data=f"auc_detail:{a['id']}"
        )]
        buttons.append(row)

    kb = InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None
    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=kb)


# ─── Детали лота ──────────────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data and c.data.startswith("auc_detail:"))
async def cb_auction_detail(callback: CallbackQuery):
    auction_id = int(callback.data.split(":")[1])
    chat_id    = callback.message.chat.id
    user_id    = callback.from_user.id

    from api.auction import get_auction_detail
    a = await get_auction_detail(auction_id, chat_id)
    if not a:
        await callback.answer("Лот не найден", show_alert=True)
        return

    status_str = {"active": "✅ Активен", "sold": "🔨 Продан", "expired": "⏰ Истёк", "cancelled": "❌ Отменён"}.get(a["status"], a["status"])
    buyout_str = f"\n💥 Мгновенный выкуп: <b>{a['buyout_price']} 🪙</b>" if a.get("buyout_price") else ""
    bids_str   = ""
    if a.get("bids_history"):
        bids_str = "\n\n<b>Последние ставки:</b>\n" + "\n".join(
            f"  • {esc(b.get('full_name','?'))} — {b['amount']} 🪙"
            for b in a["bids_history"][:5]
        )

    text = (
        f"🏪 <b>Лот #{a['id']}</b> {esc(a['item_emoji'])} <b>{esc(a['item_name'])}</b>\n"
        f"📊 Редкость: {esc(a['item_rarity'])}\n"
        f"💰 Стартовая: {a['start_price']} 🪙\n"
        f"💸 Текущая: <b>{a['current_price']} 🪙</b>{buyout_str}\n"
        f"📈 Ставок: {a['bid_count']}\n"
        f"⏳ Статус: {status_str}\n"
        f"🕐 Осталось: {a.get('remaining_str','завершён')}"
        f"{bids_str}"
    )

    buttons = []
    if a["status"] == "active" and a["seller_id"] != user_id:
        buttons.append([InlineKeyboardButton(
            text=f"💰 Ставка (мин. {a['min_bid']} 🪙)",
            callback_data=f"auc_bid_ask:{auction_id}:{a['min_bid']}"
        )])
        if a.get("buyout_price"):
            buttons.append([InlineKeyboardButton(
                text=f"💥 Выкупить за {a['buyout_price']} 🪙",
                callback_data=f"auc_buy:{auction_id}"
            )])
    if a["status"] == "active" and a["seller_id"] == user_id:
        buttons.append([InlineKeyboardButton(
            text="❌ Отменить лот",
            callback_data=f"auc_cancel:{auction_id}"
        )])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await callback.answer()


# ─── Предложить ставку (ask amount) ──────────────────────────────────────────

@router.callback_query(lambda c: c.data and c.data.startswith("auc_bid_ask:"))
async def cb_auction_bid_ask(callback: CallbackQuery):
    parts = callback.data.split(":")
    auction_id = int(parts[1])
    min_bid    = int(parts[2])
    await callback.answer(
        f"Используйте команду:\nбот ставка {auction_id} {min_bid}",
        show_alert=True
    )


# ─── Мгновенный выкуп (confirm) ───────────────────────────────────────────────

@router.callback_query(lambda c: c.data and c.data.startswith("auc_buy:"))
async def cb_auction_buyout_confirm(callback: CallbackQuery):
    auction_id = int(callback.data.split(":")[1])
    chat_id    = callback.message.chat.id
    from api.auction import get_auction_detail

    a = await get_auction_detail(auction_id, chat_id)
    if not a or not a.get("buyout_price"):
        await callback.answer("Лот не найден или выкуп недоступен", show_alert=True)
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"✅ Да, выкупить за {a['buyout_price']} 🪙", callback_data=f"auc_buy_confirm:{auction_id}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data=f"auc_detail:{auction_id}")],
    ])
    await callback.message.edit_text(
        f"💥 Подтвердить мгновенный выкуп лота #{auction_id}?\n"
        f"📦 <b>{esc(a['item_name'])}</b>\n"
        f"💰 Цена: <b>{a['buyout_price']} 🪙</b>",
        parse_mode="HTML",
        reply_markup=kb
    )
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("auc_buy_confirm:"))
async def cb_auction_buyout_do(callback: CallbackQuery):
    auction_id = int(callback.data.split(":")[1])
    user_id    = callback.from_user.id
    chat_id    = callback.message.chat.id

    from api.auction import buyout_auction
    try:
        result = await buyout_auction(user_id, chat_id, auction_id)
        await callback.message.edit_text(
            f"💥 <b>Выкуп выполнен!</b>\n\n"
            f"📦 Предмет: <b>{esc(result['item_name'])}</b>\n"
            f"💰 Уплачено: <b>{result['price_paid']} 🪙</b>\n"
            f"✅ Предмет добавлен в ваш инвентарь",
            parse_mode="HTML"
        )
    except ValueError as e:
        await callback.answer(str(e), show_alert=True)
    await callback.answer()


# ─── Отмена лота ──────────────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data and c.data.startswith("auc_cancel:"))
async def cb_auction_cancel_confirm(callback: CallbackQuery):
    auction_id = int(callback.data.split(":")[1])
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да, отменить", callback_data=f"auc_cancel_do:{auction_id}")],
        [InlineKeyboardButton(text="Назад", callback_data=f"auc_detail:{auction_id}")],
    ])
    await callback.message.edit_text(
        f"❌ Отменить лот #{auction_id}?\n\n"
        "⚠️ Если есть активные ставки, вы заплатите штраф 5% от стартовой цены, "
        "а ставка будет возвращена участнику.",
        reply_markup=kb
    )
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("auc_cancel_do:"))
async def cb_auction_cancel_do(callback: CallbackQuery):
    auction_id = int(callback.data.split(":")[1])
    user_id    = callback.from_user.id
    chat_id    = callback.message.chat.id

    from api.auction import cancel_auction
    try:
        result = await cancel_auction(user_id, chat_id, auction_id)
        msg = f"✅ Лот #{auction_id} отменён. Предмет <b>{esc(result['item_name'])}</b> возвращён в инвентарь."
        if result.get("refunded_bidder_id"):
            msg += f"\n💸 Ставка {result['refunded_amount']} 🪙 возвращена участнику."
        await callback.message.edit_text(msg, parse_mode="HTML")
    except ValueError as e:
        await callback.answer(str(e), show_alert=True)
    await callback.answer()


# ─── Команда: выставить предмет ─────────────────────────────────────────────

@router.message(BotCommand("продать"))
async def cmd_sell_item(message: Message, cmd_args: str):
    uid     = message.from_user.id
    chat_id = message.chat.id

    parts = cmd_args.split()
    if len(parts) < 2:
        await message.answer(
            "📦 <b>Аукцион — выставить предмет</b>\n\n"
            "Использование:\n"
            "<code>бот продать &lt;id_предмета&gt; &lt;стартовая_цена&gt;</code>\n"
            "<code>бот продать &lt;id_предмета&gt; &lt;стартовая&gt; &lt;цена_выкупа&gt;</code>\n\n"
            "📋 ID предметов смотрите в Мини Апп → Инвентарь",
            parse_mode="HTML"
        )
        return

    try:
        item_id     = int(parts[0])
        start_price = int(parts[1])
        buyout      = int(parts[2]) if len(parts) >= 3 else None
    except ValueError:
        await message.answer("❌ ID предмета и цены должны быть числами.")
        return

    from api.auction import create_auction
    try:
        result = await create_auction(uid, chat_id, item_id, start_price, buyout)
        from api.auction import AUCTION_DURATION_HOURS
        buyout_str = f"\n💥 Мгновенный выкуп: <b>{buyout} 🪙</b>" if buyout else ""
        await message.answer(
            f"✅ <b>Лот выставлен на аукцион!</b>\n\n"
            f"📦 <b>{esc(result['item_name'])}</b>\n"
            f"💰 Стартовая цена: <b>{start_price} 🪙</b>{buyout_str}\n"
            f"🆔 Номер лота: <b>#{result['auction_id']}</b>\n"
            f"⏳ Действует <b>{AUCTION_DURATION_HOURS} часов</b>",
            parse_mode="HTML"
        )
    except ValueError as e:
        await message.answer(f"❌ {e}")


# ─── Команда: сделать ставку ─────────────────────────────────────────────────

@router.message(BotCommand("ставка"))
async def cmd_place_bid(message: Message, cmd_args: str):
    uid     = message.from_user.id
    chat_id = message.chat.id

    parts = cmd_args.split()
    if len(parts) < 2:
        await message.answer(
            "📊 Использование: <code>бот ставка &lt;id_лота&gt; &lt;сумма&gt;</code>",
            parse_mode="HTML"
        )
        return

    try:
        auction_id = int(parts[0])
        amount     = int(parts[1])
    except ValueError:
        await message.answer("❌ ID лота и сумма должны быть числами.")
        return

    from api.auction import place_bid, get_auction_detail
    try:
        result = await place_bid(uid, chat_id, auction_id, amount)
        outbid_msg = ""
        if result.get("outbid_user_id"):
            outbid_msg = f"\n↩️ Предыдущая ставка {result['outbid_amount']} 🪙 возвращена участнику."
        await message.answer(
            f"✅ <b>Ставка принята!</b>\n\n"
            f"🆔 Лот #{auction_id}\n"
            f"💰 Ваша ставка: <b>{amount} 🪙</b>{outbid_msg}\n\n"
            f"💡 Вы можете повысить ставку в любое время до окончания аукциона.",
            parse_mode="HTML"
        )
        # Уведомляем перебитого участника
        if result.get("outbid_user_id") and result["outbid_user_id"] != uid:
            try:
                a = await get_auction_detail(auction_id, chat_id)
                item_name = a["item_name"] if a else f"Лот #{auction_id}"
                outbid_uid = result["outbid_user_id"]
                next_min = result["new_price"] + 1
                await message.bot.send_message(
                    chat_id,
                    f"⚡ <a href='tg://user?id={outbid_uid}'>Предвестник</a>, "
                    f"вашу ставку на <b>{esc(item_name)}</b> перебили! "
                    f"Новая цена: <b>{amount} 🪙</b>. "
                    f"Используйте <code>бот ставка {auction_id} {next_min}</code>",
                    parse_mode="HTML"
                )
            except Exception:
                pass
    except ValueError as e:
        await message.answer(f"❌ {e}")


# ─── Команда: мгновенный выкуп ───────────────────────────────────────────────

@router.message(BotCommand("выкупить"))
async def cmd_buyout(message: Message, cmd_args: str):
    uid     = message.from_user.id
    chat_id = message.chat.id

    if not cmd_args.strip().isdigit():
        await message.answer(
            "💥 Использование: <code>бот выкупить &lt;id_лота&gt;</code>",
            parse_mode="HTML"
        )
        return

    auction_id = int(cmd_args.strip())
    from api.auction import buyout_auction
    try:
        result = await buyout_auction(uid, chat_id, auction_id)
        await message.answer(
            f"💥 <b>Выкуп выполнен!</b>\n\n"
            f"📦 <b>{esc(result['item_name'])}</b>\n"
            f"💰 Уплачено: <b>{result['price_paid']} 🪙</b>\n"
            f"✅ Предмет добавлен в ваш инвентарь",
            parse_mode="HTML"
        )
    except ValueError as e:
        await message.answer(f"❌ {e}")


# ─── Команда: мои лоты ───────────────────────────────────────────────────────

@router.message(BotCommand("мои лоты", "мой аукцион"))
async def cmd_my_auction(message: Message, cmd_args: str):
    uid     = message.from_user.id
    chat_id = message.chat.id

    from api.auction import get_user_auctions
    data = await get_user_auctions(uid, chat_id)

    lines = ["📋 <b>Мои аукционы</b>\n"]

    if data["my_lots"]:
        lines.append("<b>🏷 Мои лоты:</b>")
        for a in data["my_lots"][:5]:
            status = {"active": "✅", "sold": "🔨", "expired": "⏰", "cancelled": "❌"}.get(a["status"], "?")
            lines.append(f"  {status} #{a['id']} <b>{esc(a['item_name'])}</b> — {a['current_price']} 🪙 ({a['bid_count']} ставок)")
    else:
        lines.append("<i>Нет активных лотов</i>")

    if data["my_bids"]:
        lines.append("\n<b>💸 Мои ставки:</b>")
        for a in data["my_bids"][:5]:
            is_winning = a.get("highest_bidder_id") == uid
            win_str = " 🏆 лидер" if is_winning else ""
            lines.append(f"  #{a['id']} <b>{esc(a['item_name'])}</b> — моя ставка: {a.get('my_bid','?')} 🪙{win_str}")
    else:
        lines.append("\n<i>Нет активных ставок</i>")

    lines.append(
        "\n<code>бот аукцион</code> — все лоты\n"
        "<code>бот продать &lt;id&gt; &lt;цена&gt;</code> — выставить предмет\n"
        "<code>бот ставка &lt;id&gt; &lt;сумма&gt;</code> — сделать ставку\n"
        "<code>бот отмена лот &lt;id&gt;</code> — отменить лот"
    )

    await message.answer("\n".join(lines), parse_mode="HTML")


# ─── Команда: отменить лот ───────────────────────────────────────────────────

@router.message(BotCommand("отмена лот"))
async def cmd_cancel_lot(message: Message, cmd_args: str):
    uid     = message.from_user.id
    chat_id = message.chat.id

    if not cmd_args.strip().isdigit():
        await message.answer(
            "❌ Использование: <code>бот отмена лот &lt;id_лота&gt;</code>",
            parse_mode="HTML"
        )
        return

    auction_id = int(cmd_args.strip())
    from api.auction import cancel_auction
    try:
        result = await cancel_auction(uid, chat_id, auction_id)
        msg = f"✅ Лот #{auction_id} отменён. Предмет <b>{esc(result['item_name'])}</b> возвращён в инвентарь."
        if result.get("refunded_bidder_id"):
            msg += f"\n💸 Ставка {result['refunded_amount']} 🪙 возвращена участнику.\n⚠️ Штраф 5% списан."
        await message.answer(msg, parse_mode="HTML")
    except ValueError as e:
        await message.answer(f"❌ {e}")
