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
    WebAppInfo,
)

from config import (
    ANON_MSG_PRICE,
    BANK_PLANS,
    GACHA_MULTI_PRICE,
    GACHA_SINGLE_PRICE,
    LOTTERY_TICKET_PRICE,
    MARRIAGE_GIFTS,
    MINI_APP_TG_URL,
    PET_ADOPT_PRICE,
    PET_MORA_SKIP_PRICE,
    PET_RENAME_PRICE,
    QUEST_REROLL_PRICE,
    SECRET_MSG_PRICE,
    SHOP_ITEMS,
    VIP_PRICE,
)
from database.db import (
    buy_shop_item,
    get_family_wallet,
    get_marriage,
    get_mora,
    has_shop_item,
    set_pet_color,
    set_pet_emoji_status,
    set_custom_title_in_chat,
)
from filters.bot_command import BotCommand
from handlers.economy import TOP_FRAMES, XP_BOOST_OPTIONS, deduct_wallet

from filters.chat_mode import MainChatOnly
router = Router()
router.message.filter(MainChatOnly())


_PET_COLORS = {
    "red":    "🔴 Красный",
    "blue":   "🔵 Синий",
    "green":  "🟢 Зелёный",
    "purple": "🟣 Фиолетовый",
    "gold":   "🟡 Золотой",
    "cyan":   "🩵 Бирюзовый",
}

_SHOP_SECTIONS = {
    "all": "🧾 Всё",
    "economy": "🪙 Экономика",
    "pets": "🐾 Питомцы",
    "gacha": "🎲 Молитвы",
    "bank": "🏦 Банк",
    "gifts": "🎁 Подарки",
    "casino": "🎰 Казино",
    "cosmetics": "🎨 Косметика",
}


def _section_keyboard(uid: int, active: str, owned_keys: set[str] | None = None) -> InlineKeyboardMarkup:
    buttons = []
    row = []
    for key in ("all", "economy", "pets", "gacha", "bank", "gifts", "casino", "cosmetics"):
        label = _SHOP_SECTIONS[key]
        text = f"· {label} ·" if key == active else label
        row.append(InlineKeyboardButton(text=text, callback_data=f"shop_nav:{uid}:{key}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    if active == "cosmetics":
        owned = owned_keys or set()
        for key, item in SHOP_ITEMS.items():
            if key in owned:
                buttons.append([InlineKeyboardButton(
                    text=f"✅ {item['name']} (куплено)",
                    callback_data=f"shop_buy:{uid}:{key}:personal",
                )])
            else:
                buttons.append([
                    InlineKeyboardButton(
                        text=f"💰 {item['name']} — {item['price']} 🪙",
                        callback_data=f"shop_buy:{uid}:{key}:personal",
                    ),
                    InlineKeyboardButton(
                        text="👨‍👩‍👧",
                        callback_data=f"shop_buy:{uid}:{key}:family",
                    ),
                ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _shop_text(section: str, bal: int) -> str:
    from shared_prices import CLEANUP_PASS_PRICE
    boost_prices = " · ".join(f"{label}={price} 🪙" for _key, _hours, price, label in XP_BOOST_OPTIONS)
    frame_lines = "\n".join(
        f"  • {emoji} <b>{name}</b> — {price} 🪙"
        for _key, emoji, name, price, _desc in TOP_FRAMES
        if price > 0
    )
    bank_lines = "\n".join(
        f"  • <b>{entry['label']}</b>"
        for entry in BANK_PLANS.values()
    )
    gift_lines = "\n".join(
        f"  • {gift['name']} — <b>{gift['price']} 🪙</b>"
        for gift in MARRIAGE_GIFTS.values()
    )
    cosmetics_lines = "\n".join(
        f"  • {item['name']} — <b>{item['price']} 🪙</b>\n    <i>{item['desc']}</i>"
        for item in SHOP_ITEMS.values()
    )

    sections = {
        "all": (
            "🛍 <b>Единый магазин Предвестника</b>\n\n"
            f"💰 Твой баланс: <b>{bal} 🪙</b>\n\n"
            "🪙 <b>Экономика</b>\n"
            f"  • VIP — <b>{VIP_PRICE} 🪙</b> · <code>бот купить вип</code>\n"
            f"  • Откуп от чистки — <b>{CLEANUP_PASS_PRICE} 🪙</b> · КД: 12 дн. · <code>бот откуп</code>\n"
            f"  • Буст XP ×2 — {boost_prices} · <code>бот купить буст</code>\n"
            "  • Рамки профиля — <code>бот рамки</code> / <code>бот купить рамку</code>\n"
            f"  • Анонимка — <b>{ANON_MSG_PRICE} 🪙</b> · <code>бот анонимка текст</code>\n"
            f"  • Секретное сообщение — <b>{SECRET_MSG_PRICE} 🪙</b> · <code>бот секрет @user текст</code>\n"
            f"  • Переброс задания — <b>{QUEST_REROLL_PRICE} 🪙</b> · <code>бот перебросить задание</code>\n\n"
            "🐾 <b>Питомцы</b>\n"
            f"  • Завести питомца — <b>{PET_ADOPT_PRICE} 🪙</b> · <code>бот завести питомца</code>\n"
            f"  • Пропуск ожидания брака — <b>{PET_MORA_SKIP_PRICE} 🪙</b> · <code>бот питомец</code>\n"
            f"  • Переименование — <b>{PET_RENAME_PRICE} 🪙</b> · <code>бот назвать питомца Имя</code>\n"
            "  • Экспедиции — <code>бот экспедиция</code>\n\n"
            "🎲 <b>Молитвы</b>\n"
            f"  • Крутка x1 — <b>{GACHA_SINGLE_PRICE} 🪙</b>\n"
            f"  • Крутка x10 — <b>{GACHA_MULTI_PRICE} 🪙</b>\n"
            "  • Инвентарь / продажа мусора — <code>бот инвентарь</code>, <code>бот продать мусор</code>\n\n"
            "🏦 <b>Банк</b>\n"
            f"{bank_lines}\n"
            "  • Открыть вклад — <code>бот банк</code>\n\n"
            "🎁 <b>Пара и подарки</b>\n"
            f"{gift_lines}\n"
            "  • Купить/подарить — <code>бот подарки</code>\n\n"
            "🎨 <b>Косметика</b>\n"
            f"{cosmetics_lines}\n\n"
            "🎰 <b>Казино</b>\n"
            f"  • Лотерейный билет — <b>{LOTTERY_TICKET_PRICE} 🪙</b> · <code>бот купить лотерею</code>\n\n"
            "<i>Переключай категории кнопками ниже.</i>"
        ),
        "economy": (
            "🪙 <b>Магазин</b> › <b>Экономика</b>\n\n"
            f"💰 Баланс: <b>{bal} 🪙</b>\n\n"
            f"💎 VIP — <b>{VIP_PRICE} 🪙</b>\n  <code>бот купить вип</code>\n\n"
            f"🎫 Откуп от чистки — <b>{CLEANUP_PASS_PRICE} 🪙</b> · КД: 12 дн.\n  <code>бот откуп</code>\n\n"
            f"⚡ Буст XP ×2\n  {boost_prices}\n  <code>бот купить буст</code>\n\n"
            "🖼 Рамки профиля\n"
            f"{frame_lines}\n"
            "  <code>бот рамки</code> · <code>бот купить рамку название</code>\n\n"
            f"📨 Анонимка — <b>{ANON_MSG_PRICE} 🪙</b>\n  <code>бот анонимка текст</code>\n\n"
            f"🔐 Секретное сообщение — <b>{SECRET_MSG_PRICE} 🪙</b>\n  <code>бот секрет @user текст</code>\n\n"
            f"🎯 Переброс задания — <b>{QUEST_REROLL_PRICE} 🪙</b>\n  <code>бот перебросить задание</code>"
        ),
        "pets": (
            "🐾 <b>Магазин</b> › <b>Питомцы</b>\n\n"
            f"💰 Баланс: <b>{bal} 🪙</b>\n\n"
            f"🐱 Завести питомца — <b>{PET_ADOPT_PRICE} 🪙</b>\n"
            "  <code>бот завести питомца</code>\n\n"
            f"⏩ Пропуск ожидания брака — <b>{PET_MORA_SKIP_PRICE} 🪙</b>\n"
            "  <code>бот питомец</code>\n\n"
            f"✏️ Переименование питомца — <b>{PET_RENAME_PRICE} 🪙</b>\n"
            "  <code>бот назвать питомца Имя</code>\n\n"
            "🗺 Экспедиции питомца\n"
            "  <code>бот экспедиция</code>"
        ),
        "gacha": (
            "🎲 <b>Магазин</b> › <b>Молитвы</b>\n\n"
            f"💰 Баланс: <b>{bal} 🪙</b>\n\n"
            f"🙏 Одна молитва — <b>{GACHA_SINGLE_PRICE} 🪙</b>\n"
            f"🙏 Десять молитв — <b>{GACHA_MULTI_PRICE} 🪙</b>\n\n"
            "📦 Сопутствующие команды\n"
            "  <code>бот молитва</code>\n"
            "  <code>бот инвентарь</code>\n"
            "  <code>бот продать мусор</code>\n"
            "  <code>бот экипировать #ID</code>"
        ),
        "bank": (
            "🏦 <b>Магазин</b> › <b>Банк</b>\n\n"
            f"💰 Баланс: <b>{bal} 🪙</b>\n\n"
            "Вклады доступны через <code>бот банк</code>.\n\n"
            f"{bank_lines}\n\n"
            "<i>Досрочное снятие уменьшает выплату.</i>"
        ),
        "gifts": (
            "🎁 <b>Магазин</b> › <b>Подарки партнёру</b>\n\n"
            f"💰 Баланс: <b>{bal} 🪙</b>\n\n"
            f"{gift_lines}\n\n"
            "Купить и отправить: <code>бот подарки</code>\n"
            "Подарки с баффами усиливают добычу моры для пары."
        ),
        "casino": (
            "🎰 <b>Магазин</b> › <b>Казино</b>\n\n"
            f"💰 Баланс: <b>{bal} 🪙</b>\n\n"
            f"🎟 Лотерейный билет — <b>{LOTTERY_TICKET_PRICE} 🪙</b>\n"
            "  <code>бот купить лотерею</code>\n\n"
            "Монетка и кубик не продаются заранее — там ставка списывается в момент игры."
        ),
        "cosmetics": (
            "🎨 <b>Магазин</b> › <b>Косметика</b>\n\n"
            f"💰 Баланс: <b>{bal} 🪙</b>\n\n"
            f"{cosmetics_lines}\n\n"
            "Для покупки используй кнопки ниже."
        ),
    }
    return sections.get(section, sections["all"])


async def _get_owned_keys(uid: int, chat_id: int) -> set[str]:
    """Return set of SHOP_ITEMS keys the user already purchased."""
    owned = set()
    for key in SHOP_ITEMS:
        if await has_shop_item(uid, chat_id, key):
            owned.add(key)
    return owned


# ─── бот магазин ──────────────────────────────────────────────────────────────

@router.message(BotCommand("магазин", "лавка", "shop", "store", "маркет", "каталог покупок"))
async def cmd_shop(message: Message, cmd_args: str):
    if message.chat.type == "private":
        await message.answer("❌ Магазин доступен только в группах.")
        return

    uid = message.from_user.id
    chat_id = message.chat.id
    mora = await get_mora(uid, chat_id)
    bal = mora["balance"] if mora else 0

    arg = (cmd_args or "").strip().lower()
    section = "all"
    arg_map = {
        "все": "all",
        "всё": "all",
        "экономика": "economy",
        "питомцы": "pets",
        "молитвы": "gacha",
        "гача": "gacha",
        "банк": "bank",
        "подарки": "gifts",
        "казино": "casino",
        "косметика": "cosmetics",
    }
    if arg in arg_map:
        section = arg_map[arg]

    owned = await _get_owned_keys(uid, chat_id) if section == "cosmetics" else None
    kb = _section_keyboard(uid, section, owned)
    # Use t.me Mini App link with startapp=abs(chat_id) so the app knows which chat context
    abs_cid = abs(message.chat.id)
    kb.inline_keyboard.append([
        InlineKeyboardButton(
            text="📱 Открыть в Mini App",
            url=f"{MINI_APP_TG_URL}?startapp={abs_cid}_shop",
        )
    ])
    await message.answer(
        _shop_text(section, bal),
        parse_mode="HTML",
        reply_markup=kb,
    )


@router.callback_query(lambda c: c.data and c.data.startswith("shop_nav:"))
async def cb_shop_nav(callback: CallbackQuery):
    _prefix, owner_str, section = callback.data.split(":", 2)
    owner = int(owner_str)

    if callback.from_user.id != owner:
        await callback.answer("❌ Это не твой магазин!", show_alert=True)
        return

    chat_id = callback.message.chat.id
    mora = await get_mora(owner, chat_id)
    bal = mora["balance"] if mora else 0
    owned = await _get_owned_keys(owner, chat_id) if section == "cosmetics" else None

    try:
        await callback.message.edit_text(
            _shop_text(section, bal),
            parse_mode="HTML",
            reply_markup=_section_keyboard(owner, section, owned),
        )
    except Exception:
        pass
    await callback.answer()


# ─── Покупка ──────────────────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data and c.data.startswith("shop_buy:"))
async def cb_shop_buy(callback: CallbackQuery):
    parts = callback.data.split(":")
    owner = int(parts[1])
    item_key = parts[2]
    wallet = parts[3] if len(parts) > 3 else "personal"

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

    already_owned = await has_shop_item(uid, chat_id, item_key)
    if already_owned:
        await callback.answer("✅ У тебя уже есть этот товар!", show_alert=True)
        return

    ok, new_bal = await deduct_wallet(uid, chat_id, price, wallet)
    if not ok:
        await callback.answer(f"❌ Недостаточно Моры ({new_bal} / {price})", show_alert=True)
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

        # Block 4: Add season XP for shop purchase
        try:
            from database.db import add_season_xp
            await add_season_xp(uid, 1)  # +1 season XP
        except Exception:
            pass

    elif item_key == "pet_color":
        await buy_shop_item(uid, chat_id, "pet_color", "pending")
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

    else:
        # Неизвестный товар — возвращаем деньги
        from database.db import add_mora
        await add_mora(uid, chat_id, price)
        await callback.answer("❌ Ошибка: товар не обработан.", show_alert=True)
        return

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


# ─── Пропуск чистки ──────────────────────────────────────────────────────────

@router.message(BotCommand("откуп", "пропуск чистки", "cleanup_pass"))
async def cmd_buy_cleanup_pass(message: Message, bot, cmd_args: str):
    """Купить откуп от 1 чистки (макс. 1 активный). Требует одобрения владельца."""
    if message.chat.type == "private":
        await message.answer("❌ Команда работает только в чате.")
        return

    uid = message.from_user.id
    chat_id = message.chat.id
    from shared_prices import CLEANUP_PASS_PRICE
    from database.db import buy_cleanup_pass, get_mora as _gm
    from handlers.economy import deduct_wallet as _dw

    mora = await _gm(uid, chat_id)
    bal = mora["balance"] if mora else 0
    if bal < CLEANUP_PASS_PRICE:
        await message.answer(
            f"❌ Недостаточно Моры. Нужно <b>{CLEANUP_PASS_PRICE} 🪙</b>, у тебя <b>{bal} 🪙</b>.",
            parse_mode="HTML",
        )
        return

    try:
        ok, new_bal = await _dw(uid, chat_id, CLEANUP_PASS_PRICE)
        if not ok:
            await message.answer("❌ Не удалось списать Мору.")
            return
        pass_id = await buy_cleanup_pass(uid, chat_id, CLEANUP_PASS_PRICE)
    except ValueError as ve:
        await message.answer(f"❌ {ve}")
        return

    # Log to wallet ledger
    try:
        from api.economy import log_wallet_tx
        import asyncio
        await log_wallet_tx(uid, chat_id, "expense", CLEANUP_PASS_PRICE, "cleanup_pass",
                            "Откуп от чистки")
    except Exception:
        pass

    user_name = html.escape(message.from_user.full_name)
    chat_title = html.escape(message.chat.title or "чат")

    await message.answer(
        f"✅ Заявка на пропуск чистки отправлена!\n"
        f"Списано: <b>{CLEANUP_PASS_PRICE} 🪙</b>\n"
        f"Ожидай одобрения от владельца/разработчика.",
        parse_mode="HTML",
    )

    # Уведомление владельцу и разработчику
    from config import DEVELOPER_ID
    from database.db import get_staff_in_chat

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Одобрить", callback_data=f"cpass:approve:{pass_id}:{uid}:{chat_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"cpass:reject:{pass_id}:{uid}:{chat_id}"),
        ]
    ])
    notify_text = (
        f"🎫 <b>Заявка на пропуск чистки</b>\n\n"
        f"👤 {user_name} (<code>{uid}</code>)\n"
        f"💬 {chat_title}\n"
        f"💰 Оплачено: <b>{CLEANUP_PASS_PRICE} 🪙</b>\n"
        f"📋 Заявка #{pass_id}"
    )

    # Уведомить владельцев чата + разработчика
    notified = set()
    staff = await get_staff_in_chat(chat_id)
    for s in staff:
        if s["rank"] in ("owner", "developer"):
            try:
                await bot.send_message(s["user_id"], notify_text, parse_mode="HTML", reply_markup=kb)
                notified.add(s["user_id"])
            except Exception:
                pass
    if DEVELOPER_ID and DEVELOPER_ID not in notified:
        try:
            await bot.send_message(DEVELOPER_ID, notify_text, parse_mode="HTML", reply_markup=kb)
        except Exception:
            pass


@router.callback_query(lambda c: c.data and c.data.startswith("cpass:"))
async def cb_cleanup_pass(callback: CallbackQuery):
    """Обработка одобрения/отклонения пропуска чистки."""
    from database.db import resolve_cleanup_pass, add_mora as _am
    from utils.ranks import is_developer as _is_dev

    parts = callback.data.split(":")
    if len(parts) < 5:
        await callback.answer("❌ Некорректные данные", show_alert=True)
        return

    action = parts[1]  # approve / reject
    pass_id = int(parts[2])
    buyer_uid = int(parts[3])
    chat_id = int(parts[4])

    admin_uid = callback.from_user.id

    # Проверяем права: только owner или developer
    from database.db import get_user_stats
    stats = await get_user_stats(admin_uid, chat_id)
    admin_rank = stats["rank"] if stats else None
    if admin_rank not in ("owner", "co_owner") and not _is_dev(admin_uid):
        await callback.answer("❌ Только владелец или разработчик может решать.", show_alert=True)
        return

    result = await resolve_cleanup_pass(pass_id, "approve" if action == "approve" else "reject", admin_uid)
    if not result:
        await callback.answer("⚠️ Заявка уже обработана или не найдена.", show_alert=True)
        return

    if action == "approve":
        try:
            await callback.message.edit_text(
                callback.message.text + "\n\n✅ <b>Одобрено</b>",
                parse_mode="HTML",
            )
        except Exception:
            pass
        # Уведомить покупателя
        try:
            await callback.bot.send_message(
                buyer_uid,
                f"✅ Твоя заявка на пропуск чистки <b>одобрена</b>!\n"
                f"При следующей чистке ты будешь защищён.",
                parse_mode="HTML",
            )
        except Exception:
            pass
        await callback.answer("✅ Пропуск одобрен!", show_alert=True)
    else:
        # Вернуть деньги
        price = result["price"]
        await _am(buyer_uid, chat_id, price)
        # Log refund
        try:
            from api.economy import log_wallet_tx
            await log_wallet_tx(buyer_uid, chat_id, "income", price, "cleanup_pass_refund",
                                "Возврат за отклонённый пропуск чистки")
        except Exception:
            pass
        try:
            await callback.message.edit_text(
                callback.message.text + "\n\n❌ <b>Отклонено</b> (деньги возвращены)",
                parse_mode="HTML",
            )
        except Exception:
            pass
        # Уведомить покупателя
        try:
            await callback.bot.send_message(
                buyer_uid,
                f"❌ Заявка на пропуск чистки <b>отклонена</b>.\n"
                f"Возврат: <b>{price} 🪙</b>",
                parse_mode="HTML",
            )
        except Exception:
            pass
        await callback.answer("❌ Заявка отклонена, деньги возвращены.", show_alert=True)
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
    if not await has_shop_item(uid, chat_id, "custom_title"):
        await message.answer(
            "❌ Сначала купи кастомный титул в магазине: <code>бот магазин</code>",
            parse_mode="HTML",
        )
        return
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
    if not await has_shop_item(uid, chat_id, "pet_emoji_status"):
        await message.answer(
            "❌ Сначала купи эмодзи-статус в магазине: <code>бот магазин</code>",
            parse_mode="HTML",
        )
        return
    await set_pet_emoji_status(uid, chat_id, emoji)
    await message.answer(f"✅ Эмодзи-статус питомца: {html.escape(emoji)}", parse_mode="HTML")
