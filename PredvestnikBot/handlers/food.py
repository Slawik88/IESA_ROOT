"""
🍖 Магазин еды для питомцев.

Команды:
  бот еда               — показать ассортимент еды + текущая усталость питомца
  бот купить еду [блюдо] — купить еду и сразу накормить питомца
"""

import html

from aiogram import Router
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from database.db import (
    get_mora,
    get_pet,
    get_pet_fatigue,
    reduce_pet_fatigue,
)
from filters.bot_command import BotCommand
from config import MINI_APP_TG_URL
from utils.helpers import user_mention

from filters.chat_mode import MainChatOnly
import logging
_log = logging.getLogger(__name__)
router = Router()
router.message.filter(MainChatOnly())


# ─── Каталог еды ──────────────────────────────────────────────────────────────
FOOD_CATALOG: dict[str, dict] = {
    "краб": {
        "name":    "Золотой краб",
        "emoji":   "🦀",
        "price":   50,
        "fatigue": 40,
        "desc":    "Изысканное морское блюдо. Сильно восстанавливает силы.",
    },
    "лапша": {
        "name":    "Лапша путника",
        "emoji":   "🍜",
        "price":   25,
        "fatigue": 20,
        "desc":    "Простая, но сытная еда. Умеренно снижает усталость.",
    },
}


def _catalog_kb() -> InlineKeyboardMarkup:
    buttons = []
    for key, item in FOOD_CATALOG.items():
        label = f"{item['emoji']} {item['name']} | -{item['fatigue']}😴 | {item['price']}🪙"
        buttons.append([InlineKeyboardButton(
            text=label,
            callback_data=f"buy_food:{key}",
        )])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ─── бот еда ──────────────────────────────────────────────────────────────────

@router.message(BotCommand("еда", "food", "кормить", "кормить питомца"))
async def cmd_food_shop(message: Message):
    if message.chat.type not in ("group", "supergroup"):
        await message.answer("❌ Магазин еды доступен только в группах.")
        return

    # PHASE 3: Pet food → Mini App in groups
    abs_cid = abs(message.chat.id)
    btn = InlineKeyboardButton(
        text="🍖 Кормить в Mini App",
        url=f"{MINI_APP_TG_URL}?startapp={abs_cid}_union",
    )
    await message.answer(
        "🍖 <b>Кормление питомца переехало в Mini App!</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[btn]]),
    )
    return

    uid     = message.from_user.id  # noqa: unreachable (Phase 3 — superseded by Mini App)
    chat_id = message.chat.id

    pet = await get_pet(uid, chat_id)
    if not pet:
        await message.answer(
            "❌ У тебя нет питомца! Сначала заведи его: <code>бот завести питомца</code>",
            parse_mode="HTML",
        )
        return

    fatigue = pet.get("fatigue") or await get_pet_fatigue(uid, chat_id)
    mora    = await get_mora(uid, chat_id)
    balance = mora["balance"] if mora else 0
    pet_emoji = {"cat": "🐱", "dog": "🐶"}.get(pet["pet_type"], "🐾")
    pet_name  = html.escape(pet["name"]) if pet.get("name") else "безымянный"

    fatigue_bar = "❤️" * (fatigue // 20) + "🖤" * (5 - fatigue // 20)
    fatigue_label = (
        "🟢 Бодрый" if fatigue < 40 else
        "🟡 Устал"  if fatigue < 70 else
        "🔴 Измотан"
    )

    lines = [
        f"🍽️ <b>Магазин еды для питомцев</b>\n",
        f"{pet_emoji} <b>{pet_name}</b>",
        f"😴 Усталость: <b>{fatigue}/100</b>  {fatigue_bar}  <i>{fatigue_label}</i>",
        f"💰 Твой баланс: <b>{balance} 🪙</b>\n",
        "📋 <b>Меню:</b>",
    ]
    for item in FOOD_CATALOG.values():
        lines.append(
            f"\n{item['emoji']} <b>{item['name']}</b> — {item['price']} 🪙\n"
            f"   -{item['fatigue']} усталости · {item['desc']}"
        )
    lines.append("\n👇 Нажми кнопку чтобы купить:")

    await message.answer(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=_catalog_kb(),
    )


# ─── Callback: купить еду ────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data and c.data.startswith("buy_food:"))
async def cb_buy_food(callback: CallbackQuery):
    key = callback.data.split(":")[1]
    item = FOOD_CATALOG.get(key)
    if not item:
        await callback.answer("❌ Неизвестная еда.", show_alert=True)
        return

    uid     = callback.from_user.id
    chat_id = callback.message.chat.id

    pet = await get_pet(uid, chat_id)
    if not pet:
        await callback.answer("❌ У тебя нет питомца!", show_alert=True)
        return

    mora    = await get_mora(uid, chat_id)
    balance = mora["balance"] if mora else 0
    if balance < item["price"]:
        await callback.answer(
            f"❌ Недостаточно Моры! У тебя {balance}/{item['price']} 🪙",
            show_alert=True,
        )
        return

    from database.postgres import connect as postgres_connect
    async with postgres_connect() as db:
        cursor = await db.execute(
            "UPDATE users SET balance=balance-? WHERE user_id=? AND COALESCE(balance,0)>=?",
            (item["price"], uid, item["price"]),
        )
        if cursor.rowcount == 0:
            await callback.answer("❌ Не удалось списать Мору.", show_alert=True)
            return
        await db.commit()

    await reduce_pet_fatigue(uid, chat_id, item["fatigue"])
    new_fatigue = max(0, (pet.get("fatigue") or await get_pet_fatigue(uid, chat_id)) - item["fatigue"])

    pet_emoji = {"cat": "🐱", "dog": "🐶"}.get(pet["pet_type"], "🐾")
    pet_name  = html.escape(pet["name"]) if pet.get("name") else "безымянный"

    await callback.answer(
        f"✅ {pet_emoji} {pet_name} съел «{item['name']}»! Усталость -{item['fatigue']}",
        show_alert=True,
    )
    try:
        await callback.message.edit_text(
            f"🍽️ <b>Питомец покормлен!</b>\n\n"
            f"{item['emoji']} {pet_emoji} <b>{pet_name}</b> съел <b>{item['name']}</b>.\n"
            f"😴 Усталость: <b>{new_fatigue}/100</b>  (−{item['fatigue']})\n"
            f"💸 Потрачено: <b>{item['price']} 🪙</b>",
            parse_mode="HTML",
        )
    except Exception:
        pass


# ─── CMD: бот купить еду [блюдо] (текстовый алиас) ──────────────────────────

@router.message(BotCommand("купить еду", "накормить"))
async def cmd_buy_food_text(message: Message, cmd_args: str):
    arg = (cmd_args or "").strip().lower()
    # Нормализуем: "краб" / "лапша" / "золотой краб" / "лапша путника"
    key = None
    for k, item in FOOD_CATALOG.items():
        if k in arg or item["name"].lower() in arg:
            key = k
            break

    if not key:
        lines = ["🍖 Укажи что купить:\n"]
        for k, item in FOOD_CATALOG.items():
            lines.append(f"  <code>бот купить еду {k}</code> — {item['name']} ({item['price']} 🪙)")
        await message.answer("\n".join(lines), parse_mode="HTML")
        return

    # Имитируем callback
    item    = FOOD_CATALOG[key]
    uid     = message.from_user.id
    chat_id = message.chat.id

    pet = await get_pet(uid, chat_id)
    if not pet:
        await message.answer("❌ У тебя нет питомца!", parse_mode="HTML")
        return

    mora    = await get_mora(uid, chat_id)
    balance = mora["balance"] if mora else 0
    if balance < item["price"]:
        await message.answer(
            f"❌ Недостаточно Моры! У тебя {balance}/{item['price']} 🪙",
            parse_mode="HTML",
        )
        return

    from database.postgres import connect as postgres_connect
    async with postgres_connect() as db:
        cursor = await db.execute(
            "UPDATE users SET balance=balance-? WHERE user_id=? AND COALESCE(balance,0)>=?",
            (item["price"], uid, item["price"]),
        )
        if cursor.rowcount == 0:
            await message.answer("❌ Не удалось списать Мору.", parse_mode="HTML")
            return
        await db.commit()

    await reduce_pet_fatigue(uid, chat_id, item["fatigue"])

    pet_emoji = {"cat": "🐱", "dog": "🐶"}.get(pet["pet_type"], "🐾")
    pet_name  = html.escape(pet["name"]) if pet.get("name") else "безымянный"
    old_fatigue = pet.get("fatigue") or await get_pet_fatigue(uid, chat_id)
    new_fatigue = max(0, old_fatigue - item["fatigue"])

    await message.answer(
        f"🍽️ <b>Питомец покормлен!</b>\n\n"
        f"{item['emoji']} {pet_emoji} <b>{pet_name}</b> съел <b>{item['name']}</b>.\n"
        f"😴 Усталость: <b>{new_fatigue}/100</b>  (−{item['fatigue']})\n"
        f"💸 Потрачено: <b>{item['price']} 🪙</b>",
        parse_mode="HTML",
    )
