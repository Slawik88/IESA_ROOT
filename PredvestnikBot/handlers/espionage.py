"""
Шпионаж и Облигации.

бот шпионить @user   — разведка баланса (50 🪙, 30% провал)
бот облигации        — просмотр и торговля облигациями
бот купить обл [key] [n] — купить N облигаций
бот продать обл [key] [n] — продать N облигаций
"""

import html
import random

from aiogram import Router
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from database.db import (
    deduct_mora, add_mora, get_mora, get_user,
    log_espionage, get_espionage_cooldown,
    get_bond_prices, get_user_bonds, buy_bonds, sell_bonds,
    BOND_DEFAULTS,
)
from filters.bot_command import BotCommand
from utils.helpers import resolve_target, user_mention

router = Router()

_SPY_COST = 50


# ─── Шпионаж ──────────────────────────────────────────────────────────────────

@router.message(BotCommand("шпионить", "spy", "разведка"))
async def cmd_spy(message: Message, cmd_args: str):
    if message.chat.type not in ("group", "supergroup"):
        await message.answer("❌ Команда работает только в группах.")
        return

    uid = message.from_user.id
    chat_id = message.chat.id

    if not cmd_args:
        await message.answer(
            "🕵️ <b>Шпионаж</b>\n\n"
            "Разведай баланс другого участника.\n"
            f"Стоимость: <b>{_SPY_COST} 🪙</b>  |  Шанс провала: 30%\n\n"
            "Пример: <code>бот шпионить @username</code>",
            parse_mode="HTML",
        )
        return

    target_id, target_name, _ = await resolve_target(message, cmd_args)
    if target_id is None:
        await message.answer(target_name)
        return

    if target_id == uid:
        await message.answer("🤦 Зачем шпионить за самим собой?")
        return

    # Кулдаун: нельзя следить за одним человеком чаще раза в час
    cd = await get_espionage_cooldown(uid, target_id, chat_id)
    if cd > 0:
        mins = cd // 60
        secs = cd % 60
        await message.answer(f"⏳ Подожди {mins} мин. {secs} сек. — ты недавно уже следил за этим человеком.")
        return

    # Списать мору
    mora = await get_mora(uid, chat_id)
    bal = (mora["balance"] or 0) if mora else 0
    if bal < _SPY_COST:
        await message.answer(f"❌ Недостаточно Моры. Нужно {_SPY_COST} 🪙, у тебя {bal} 🪙.")
        return

    ok, _ = await deduct_mora(uid, chat_id, _SPY_COST)
    if not ok:
        await message.answer("❌ Не удалось списать Мору.")
        return

    # Проверка: цель существует
    target_user = await get_user(target_id)
    if not target_user:
        await message.answer("❌ Пользователь не найден в базе.")
        await add_mora(uid, chat_id, _SPY_COST)
        return

    # Бросок провала 30%
    failed = random.random() < 0.30
    await log_espionage(uid, target_id, chat_id, success=not failed)

    t_name = html.escape(target_user["full_name"])
    t_uname = f" (@{target_user['username']})" if target_user.get("username") else ""
    t_mention = user_mention(target_id, t_name)

    if failed:
        # Уведомить жертву
        try:
            spy_name = html.escape(message.from_user.full_name or "")
            spy_mention = user_mention(uid, spy_name)
            await message.bot.send_message(
                chat_id,
                f"⚠️ {t_mention}, за тобой следят!\n"
                f"Агент {spy_mention} пытался разведать твой баланс, но <b>провалился</b>.",
                parse_mode="HTML",
            )
        except Exception:
            pass
        await message.answer(
            f"💥 <b>Провал!</b> Агент обнаружен.\n"
            f"Жертва уведомлена. -{_SPY_COST} 🪙 потрачено.",
            parse_mode="HTML",
        )
        return

    # Успех — показываем разведданные
    t_mora = await get_mora(target_id, chat_id)
    t_bal = (t_mora["balance"] or 0) if t_mora else 0
    t_vip = bool(t_mora and t_mora.get("vip"))
    vip_line = "\n💎 VIP статус активен" if t_vip else ""

    # Показываем облигации цели
    t_bonds = await get_user_bonds(target_id, chat_id)
    bond_prices = await get_bond_prices(chat_id)
    bond_lines = []
    for b in t_bonds:
        bkey = b["bond_key"]
        bname = BOND_DEFAULTS.get(bkey, {}).get("name", bkey)
        cur_price = bond_prices.get(bkey, 0)
        cur_value = b["amount"] * cur_price
        bond_lines.append(f"  {bname}: {b['amount']} шт. (~{cur_value} 🪙)")
    bonds_section = "\n📊 Облигации:\n" + "\n".join(bond_lines) if bond_lines else ""

    await message.answer(
        f"🕵️ <b>Разведданные</b>{vip_line}\n"
        f"Цель: {t_mention}{t_uname}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 Мора: <b>{t_bal} 🪙</b>"
        f"{bonds_section}",
        parse_mode="HTML",
    )


# ─── Облигации ────────────────────────────────────────────────────────────────

@router.message(BotCommand("облигации", "bonds", "обл"))
async def cmd_bonds(message: Message, cmd_args: str):
    if message.chat.type not in ("group", "supergroup"):
        await message.answer("❌ Команда работает только в группах.")
        return

    uid = message.from_user.id
    chat_id = message.chat.id

    prices = await get_bond_prices(chat_id)
    my_bonds = {b["bond_key"]: b for b in await get_user_bonds(uid, chat_id)}
    mora = await get_mora(uid, chat_id)
    balance = (mora["balance"] or 0) if mora else 0

    lines = [
        "📊 <b>Облигации Тейвата</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        "Цены обновляются каждые 6 часов.\n",
    ]
    for key, info in BOND_DEFAULTS.items():
        price = prices.get(key, info["base_price"])
        base = info["base_price"]
        pct_diff = (price - base) / base * 100
        trend = f"({pct_diff:+.0f}% к базе)"
        lines.append(f"{info['name']}")
        lines.append(f"  Цена: <b>{price} 🪙</b> {trend}")

        if key in my_bonds:
            b = my_bonds[key]
            cur_val = b["amount"] * price
            profit = cur_val - b["invested"]
            profit_str = f"+{profit}" if profit >= 0 else str(profit)
            lines.append(
                f"  Твои: {b['amount']} шт. | Вложено: {b['invested']} 🪙 | "
                f"Сейчас: {cur_val} 🪙 (<b>{profit_str}</b>)"
            )
    lines += [
        "",
        f"💰 Твой баланс: <b>{balance} 🪙</b>",
        "",
        "🛒 <code>бот купить обл [mondstadt/inazuma] [кол-во]</code>",
        "💵 <code>бот продать обл [mondstadt/inazuma] [кол-во]</code>",
    ]
    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(BotCommand("купить обл", "купить облигацию", "buy bond"))
async def cmd_buy_bond(message: Message, cmd_args: str):
    if message.chat.type not in ("group", "supergroup"):
        await message.answer("❌ Команда работает только в группах.")
        return

    args = (cmd_args or "").strip().split()
    if len(args) < 2:
        await message.answer(
            "Пример: <code>бот купить обл mondstadt 5</code>",
            parse_mode="HTML",
        )
        return

    bond_key = args[0].lower()
    if bond_key not in BOND_DEFAULTS:
        keys = ", ".join(BOND_DEFAULTS.keys())
        await message.answer(f"❌ Неизвестная облигация. Доступные: {keys}")
        return

    try:
        amount = int(args[1])
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Кол-во должно быть положительным числом.")
        return

    uid = message.from_user.id
    chat_id = message.chat.id
    prices = await get_bond_prices(chat_id)
    price_per = prices.get(bond_key, BOND_DEFAULTS[bond_key]["base_price"])
    total_cost = price_per * amount
    bname = BOND_DEFAULTS[bond_key]["name"]

    # Wallet choice
    mora = await get_mora(uid, chat_id)
    pers_bal = (mora["balance"] or 0) if mora else 0
    try:
        from database.db import get_family_wallet
        fam_bal = await get_family_wallet(chat_id, uid)
    except Exception:
        fam_bal = 0

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text=f"💳 Личный ({pers_bal} 🪙)",
            callback_data=f"bond_buy:personal:{uid}:{chat_id}:{bond_key}:{amount}",
        ),
        InlineKeyboardButton(
            text=f"👨‍👩‍👧 Семейный ({fam_bal} 🪙)",
            callback_data=f"bond_buy:family:{uid}:{chat_id}:{bond_key}:{amount}",
        ),
    ]])
    await message.answer(
        f"🛒 <b>Купить облигации</b>\n"
        f"{bname}: <b>{amount} шт.</b>\n"
        f"Итого: <b>{total_cost} 🪙</b> ({price_per} за шт.)\n\n"
        f"Выбери кошелёк:",
        parse_mode="HTML",
        reply_markup=kb,
    )


@router.callback_query(lambda c: c.data and c.data.startswith("bond_buy:"))
async def cb_bond_buy(callback: CallbackQuery):
    parts = callback.data.split(":")
    if len(parts) < 6:
        await callback.answer()
        return
    _, wallet, owner_str, chat_str, bond_key, amount_str = parts[:6]
    owner = int(owner_str)
    chat_id = int(chat_str)
    amount = int(amount_str)

    if callback.from_user.id != owner:
        await callback.answer("❌ Не твоя кнопка.", show_alert=True)
        return

    if bond_key not in BOND_DEFAULTS:
        await callback.answer("❌ Неверный ключ облигации.", show_alert=True)
        return

    prices = await get_bond_prices(chat_id)
    price_per = prices.get(bond_key, BOND_DEFAULTS[bond_key]["base_price"])
    total_cost = price_per * amount

    # Deduct from chosen wallet
    from handlers.economy import deduct_wallet
    ok, new_bal = await deduct_wallet(owner, chat_id, total_cost, wallet)
    if not ok:
        await callback.answer(
            f"❌ Недостаточно Моры в {'семейном' if wallet == 'family' else 'личном'} кошельке.",
            show_alert=True,
        )
        return

    await buy_bonds(owner, chat_id, bond_key, amount, price_per)
    bname = BOND_DEFAULTS[bond_key]["name"]
    wallet_label = "Семейный" if wallet == "family" else "Личный"
    try:
        await callback.message.edit_text(
            f"✅ Куплено <b>{amount}</b> облигаций «{bname}»\n"
            f"Потрачено: <b>{total_cost} 🪙</b> ({price_per} за шт.)\n"
            f"💳 Кошелёк: {wallet_label} | Остаток: {new_bal} 🪙",
            parse_mode="HTML",
        )
    except Exception:
        pass
    await callback.answer("✅ Куплено!")


@router.message(BotCommand("продать обл", "продать облигацию", "sell bond"))
async def cmd_sell_bond(message: Message, cmd_args: str):
    if message.chat.type not in ("group", "supergroup"):
        await message.answer("❌ Команда работает только в группах.")
        return

    args = (cmd_args or "").strip().split()
    if len(args) < 2:
        await message.answer(
            "Пример: <code>бот продать обл mondstadt 5</code>",
            parse_mode="HTML",
        )
        return

    bond_key = args[0].lower()
    if bond_key not in BOND_DEFAULTS:
        keys = ", ".join(BOND_DEFAULTS.keys())
        await message.answer(f"❌ Неизвестная облигация. Доступные: {keys}")
        return

    try:
        amount = int(args[1])
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Кол-во должно быть положительным числом.")
        return

    uid = message.from_user.id
    chat_id = message.chat.id

    prices = await get_bond_prices(chat_id)
    price_per = prices.get(bond_key, BOND_DEFAULTS[bond_key]["base_price"])

    ok, sold = await sell_bonds(uid, chat_id, bond_key, amount)
    if not ok:
        user_b = {b["bond_key"]: b["amount"] for b in await get_user_bonds(uid, chat_id)}
        have = user_b.get(bond_key, 0)
        await message.answer(
            f"❌ У тебя только {have} облигаций «{BOND_DEFAULTS[bond_key]['name']}».",
        )
        return

    revenue = sold * price_per
    await add_mora(uid, chat_id, revenue)
    bname = BOND_DEFAULTS[bond_key]["name"]
    await message.answer(
        f"✅ Продано <b>{sold}</b> облигаций «{bname}»\n"
        f"Получено: <b>{revenue} 🪙</b> ({price_per} за шт.)",
        parse_mode="HTML",
    )
