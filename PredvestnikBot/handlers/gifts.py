"""
Подарки для партнёра (брак) — витрина с баффами.

Команды:
  бот подарки / бот витрина / бот gifts  — каталог подарков
  бот подарить <подарок>                  — подарить партнёру

Элитные подарки (trip/crown/castle) дают баффы к добыче моры.
"""

import html

from aiogram import Router
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from config import MARRIAGE_GIFTS
from database.db import (
    add_buff,
    deduct_mora,
    get_marriage,
    get_mora,
    give_gift,
    get_gifts_summary,
)
from filters.bot_command import BotCommand

router = Router()


# ─── бот подарки ──────────────────────────────────────────────────────────────

@router.message(BotCommand("подарки", "витрина", "gifts", "подарок"))
async def cmd_gifts(message: Message, cmd_args: str):
    if message.chat.type == "private":
        await message.answer("❌ Подарки доступны только в группах.")
        return

    uid = message.from_user.id
    chat_id = message.chat.id

    marriage = await get_marriage(uid, chat_id)
    if not marriage:
        await message.answer(
            "❌ Ты не в браке!\n"
            "Подарки можно дарить только партнёру.\n"
            "Используй: <code>бот предложение @ник</code>",
            parse_mode="HTML",
        )
        return

    mora = await get_mora(uid, chat_id)
    bal = mora["balance"] if mora else 0

    lines = [
        "🎁 <b>Витрина подарков</b>\n",
        f"💰 Баланс: <b>{bal} 🪙</b>\n",
    ]
    buttons = []
    for key, gift in MARRIAGE_GIFTS.items():
        buff_info = ""
        if gift.get("buff"):
            buff = gift["buff"]
            pct = buff["type"].replace("mora_boost_", "")
            buff_info = f" | 🔥 +{pct}% мора на {buff['hours']}ч"
        lines.append(f"  {gift['name']} — <b>{gift['price']} 🪙</b>{buff_info}")
        buttons.append([InlineKeyboardButton(
            text=f"{gift['name']} — {gift['price']} 🪙",
            callback_data=f"gift:{uid}:{key}",
        )])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=kb)


# ─── Callback: подарить ──────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data and c.data.startswith("gift:"))
async def cb_gift(callback: CallbackQuery):
    parts = callback.data.split(":")
    owner = int(parts[1])
    gift_key = parts[2]

    if callback.from_user.id != owner:
        await callback.answer("❌ Это не для тебя!", show_alert=True)
        return

    gift_info = MARRIAGE_GIFTS.get(gift_key)
    if not gift_info:
        await callback.answer("❌ Подарок не найден.", show_alert=True)
        return

    uid = owner
    chat_id = callback.message.chat.id

    # Проверяем брак
    marriage = await get_marriage(uid, chat_id)
    if not marriage:
        await callback.answer("❌ Ты не в браке!", show_alert=True)
        return

    partner_id = marriage["partner_id"]
    price = gift_info["price"]

    ok, new_bal = await deduct_mora(uid, chat_id, price)
    if not ok:
        mora = await get_mora(uid, chat_id)
        bal = mora["balance"] if mora else 0
        await callback.answer(f"❌ Недостаточно Моры ({bal} / {price})", show_alert=True)
        return

    # Записываем подарок
    await give_gift(uid, partner_id, chat_id, gift_key, gift_info["name"], price)

    # Если есть бафф — активируем для обоих
    buff = gift_info.get("buff")
    buff_text = ""
    if buff:
        await add_buff(uid, chat_id, buff["type"], buff["hours"], f"gift:{gift_key}")
        await add_buff(partner_id, chat_id, buff["type"], buff["hours"], f"gift:{gift_key}")
        pct = buff["type"].replace("mora_boost_", "")
        buff_text = f"\n🔥 <b>Бафф +{pct}% к добыче моры на {buff['hours']}ч</b> для вас обоих!"

    # Получаем общую статистику
    count, total = await get_gifts_summary(uid, partner_id, chat_id)

    try:
        await callback.message.edit_text(
            f"🎁 <b>Подарок отправлен!</b>\n\n"
            f"{gift_info['name']} → партнёру"
            f"{buff_text}\n\n"
            f"💰 Баланс: {new_bal} 🪙\n"
            f"📊 Всего подарков паре: {count} (на {total} 🪙)",
            parse_mode="HTML",
        )
    except Exception:
        pass
    await callback.answer("🎁 Подарок отправлен!")

    # Quest tick: gift
    try:
        from utils.helpers import bot_today
        from database.db import get_user_quest, quest_tick, mark_quest_rewarded, add_xp_in_chat, add_mora
        today = bot_today()
        quest = await get_user_quest(uid, chat_id, today)
        if quest["type"] == "gift":
            new_p, goal, just_done = await quest_tick(uid, chat_id, today, quest["type"], quest["goal"])
            if just_done:
                _mr = quest.get("mora", 5)
                await add_xp_in_chat(uid, chat_id, quest["xp"])
                await add_mora(uid, chat_id, _mr)
                await mark_quest_rewarded(uid, chat_id, today)
                try:
                    name = html.escape(callback.from_user.full_name)
                    await callback.message.answer(
                        f"🎉 {name} выполнил ежедневное задание! "
                        f"<b>+{quest['xp']} XP</b>  <b>+{_mr} Моры</b> 🪙",
                        parse_mode="HTML",
                    )
                except Exception:
                    pass
    except Exception:
        pass
