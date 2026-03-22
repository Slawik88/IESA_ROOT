"""
Магазин Предвестника — покупка эксклюзивных товаров за мору.

Команды:
  бот магазин / бот лавка / бот shop  — каталог товаров
"""

import html

from aiogram import Router
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from config import SHOP_ITEMS
from database.db import (
    buy_shop_item,
    deduct_mora,
    get_mora,
    set_pet_color,
    set_pet_emoji_status,
    set_custom_title_in_chat,
)
from filters.bot_command import BotCommand

router = Router()

_PET_COLORS = {
    "red":    "🔴 Красный",
    "blue":   "🔵 Синий",
    "green":  "🟢 Зелёный",
    "purple": "🟣 Фиолетовый",
    "gold":   "🟡 Золотой",
    "cyan":   "🩵 Бирюзовый",
}


# ─── бот магазин ──────────────────────────────────────────────────────────────

@router.message(BotCommand("магазин", "лавка", "shop", "store"))
async def cmd_shop(message: Message, cmd_args: str):
    if message.chat.type == "private":
        await message.answer("❌ Магазин доступен только в группах.")
        return

    uid = message.from_user.id
    chat_id = message.chat.id
    mora = await get_mora(uid, chat_id)
    bal = mora["balance"] if mora else 0

    lines = [
        "🛍 <b>Магазин Предвестника</b>\n",
        f"💰 Баланс: <b>{bal} 🪙</b>\n",
    ]
    buttons = []
    for key, item in SHOP_ITEMS.items():
        lines.append(f"  • {item['name']} — <b>{item['price']} 🪙</b>\n    <i>{item['desc']}</i>")
        buttons.append([InlineKeyboardButton(
            text=f"{item['name']} — {item['price']} 🪙",
            callback_data=f"shop_buy:{uid}:{key}",
        )])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=kb)


# ─── Покупка ──────────────────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data and c.data.startswith("shop_buy:"))
async def cb_shop_buy(callback: CallbackQuery):
    parts = callback.data.split(":")
    owner = int(parts[1])
    item_key = parts[2]

    if callback.from_user.id != owner:
        await callback.answer("❌ Это не твой магазин!", show_alert=True)
        return

    item = SHOP_ITEMS.get(item_key)
    if not item:
        await callback.answer("❌ Товар не найден.", show_alert=True)
        return

    uid = owner
    chat_id = callback.message.chat.id
    price = item["price"]

    ok, new_bal = await deduct_mora(uid, chat_id, price)
    if not ok:
        mora = await get_mora(uid, chat_id)
        bal = mora["balance"] if mora else 0
        await callback.answer(f"❌ Недостаточно Моры ({bal} / {price})", show_alert=True)
        return

    # Для каждого товара — свой flow
    if item_key == "custom_title":
        await buy_shop_item(uid, chat_id, "custom_title", "pending")
        try:
            await callback.message.edit_text(
                f"✅ <b>Кастомный титул куплен!</b>\n\n"
                f"Теперь напиши: <code>бот титул &lt;текст&gt;</code>\n"
                f"💰 Баланс: {new_bal} 🪙",
                parse_mode="HTML",
            )
        except Exception:
            pass

    elif item_key == "pet_color":
        # Предлагаем выбрать цвет
        buttons = []
        row = []
        for ckey, cname in _PET_COLORS.items():
            row.append(InlineKeyboardButton(
                text=cname,
                callback_data=f"shop_color:{uid}:{ckey}",
            ))
            if len(row) == 2:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)
        kb = InlineKeyboardMarkup(inline_keyboard=buttons)
        try:
            await callback.message.edit_text(
                "🎨 <b>Выбери цвет имени питомца:</b>",
                parse_mode="HTML",
                reply_markup=kb,
            )
        except Exception:
            pass

    elif item_key == "pet_emoji_status":
        await buy_shop_item(uid, chat_id, "pet_emoji_status", "pending")
        try:
            await callback.message.edit_text(
                f"✅ <b>Эмодзи-статус питомца куплен!</b>\n\n"
                f"Теперь напиши: <code>бот эмодзи-статус 🐾</code>\n"
                f"(Укажи один эмодзи)\n"
                f"💰 Баланс: {new_bal} 🪙",
                parse_mode="HTML",
            )
        except Exception:
            pass

    await callback.answer("✅ Покупка совершена!")


# ─── Выбор цвета питомца ─────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data and c.data.startswith("shop_color:"))
async def cb_shop_color(callback: CallbackQuery):
    parts = callback.data.split(":")
    owner = int(parts[1])
    color = parts[2]

    if callback.from_user.id != owner:
        await callback.answer("❌ Не для тебя!", show_alert=True)
        return

    if color not in _PET_COLORS:
        await callback.answer("❌ Неизвестный цвет.", show_alert=True)
        return

    uid = owner
    chat_id = callback.message.chat.id

    await set_pet_color(uid, chat_id, color)
    await buy_shop_item(uid, chat_id, "pet_color", color)

    try:
        await callback.message.edit_text(
            f"✅ Цвет имени питомца изменён на {_PET_COLORS[color]}!",
            parse_mode="HTML",
        )
    except Exception:
        pass
    await callback.answer()


# ─── бот титул (установка кастомного титула) ──────────────────────────────────

@router.message(BotCommand("титул", "title"))
async def cmd_set_title(message: Message, cmd_args: str):
    if message.chat.type == "private":
        return

    title = (cmd_args or "").strip()
    if not title:
        await message.answer(
            "❌ Укажи текст титула.\nПример: <code>бот титул Архонт Мудрости</code>",
            parse_mode="HTML",
        )
        return
    if len(title) > 30:
        await message.answer("❌ Титул слишком длинный (макс. 30 символов).")
        return

    uid = message.from_user.id
    chat_id = message.chat.id
    await set_custom_title_in_chat(uid, chat_id, title)
    await message.answer(f"✅ Титул установлен: <b>{html.escape(title)}</b>", parse_mode="HTML")


# ─── бот эмодзи-статус (установка эмодзи питомца) ────────────────────────────

@router.message(BotCommand("эмодзи-статус", "emoji-status", "эмодзи статус"))
async def cmd_set_emoji_status(message: Message, cmd_args: str):
    if message.chat.type == "private":
        return

    emoji = (cmd_args or "").strip()
    if not emoji or len(emoji) > 4:
        await message.answer(
            "❌ Укажи один эмодзи.\nПример: <code>бот эмодзи-статус 🐾</code>",
            parse_mode="HTML",
        )
        return

    uid = message.from_user.id
    chat_id = message.chat.id
    await set_pet_emoji_status(uid, chat_id, emoji)
    await message.answer(f"✅ Эмодзи-статус питомца: {html.escape(emoji)}", parse_mode="HTML")
