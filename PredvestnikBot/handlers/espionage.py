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
    add_mora, get_mora, get_user,
    log_espionage, get_espionage_cooldown,
    get_bond_prices, get_bond_price_history, get_user_bonds, buy_bonds, sell_bonds,
    BOND_DEFAULTS,
)
from filters.bot_command import BotCommand
from utils.helpers import resolve_target, user_mention

from filters.chat_mode import MainChatOnly
router = Router()
router.message.filter(MainChatOnly())


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

    from database.postgres import connect as postgres_connect
    async with postgres_connect() as db:
        cursor = await db.execute(
            "UPDATE users SET balance=balance-? WHERE user_id=? AND COALESCE(balance,0)>=?",
            (_SPY_COST, uid, _SPY_COST),
        )
        if cursor.rowcount == 0:
            await message.answer("❌ Не удалось списать Мору.")
            return
        await db.commit()

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
        "Цены обновляются каждые 3 часа.\n",
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
            cur_val  = b["amount"] * price
            invested = b["invested"]
            avg_entry = round(invested / b["amount"], 1) if b["amount"] > 0 else 0
            profit    = cur_val - invested
            pct       = round(profit / invested * 100, 1) if invested > 0 else 0
            sign      = "+" if profit >= 0 else ""
            pnl_emoji = "📈" if profit >= 0 else "📉"
            lines.append(
                f"  📄 {b['amount']} шт. | Ср. цена: <b>{avg_entry} 🪙</b> | Сейчас: {cur_val} 🪙"
            )
            lines.append(
                f"  {pnl_emoji} П/У: <b>{sign}{profit} 🪙</b> ({sign}{pct}%)"
            )
    lines += [
        "",
        f"💰 Твой баланс: <b>{balance} 🪙</b>",
        "",
        "🛒 <code>бот купить обл [key] [кол-во]</code>",
        "💵 <code>бот продать обл [key] [кол-во]</code>",
        "💸 <code>бот купить акции [key] [сумма Моры]</code>",
        "📊 <code>бот акции</code> — график цен",
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
        from database.db import get_total_family_balance
        fam_bal, _, _ = await get_total_family_balance(chat_id, uid)
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


# ─── Акции: график цен ────────────────────────────────────────────────────────

@router.message(BotCommand("акции", "биржа", "charts"))
async def cmd_bonds_chart(message: Message, cmd_args: str):
    """бот акции — сгенерировать matplotlib-график цен облигаций для чата."""
    if message.chat.type not in ("group", "supergroup"):
        await message.answer("❌ Команда работает только в группах.")
        return

    chat_id = message.chat.id
    prices = await get_bond_prices(chat_id)

    try:
        import io
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.ticker as mticker
    except ImportError:
        await message.answer("⚠️ Модуль matplotlib не установлен.")
        return

    bond_keys = list(BOND_DEFAULTS.keys())
    n = len(bond_keys)
    fig, axes = plt.subplots(1, n, figsize=(5 * n, 3))
    if n == 1:
        axes = [axes]
    fig.patch.set_facecolor("#0f1117")

    for ax, key in zip(axes, bond_keys):
        info = BOND_DEFAULTS[key]
        hist = await get_bond_price_history(chat_id, key, limit=30)
        cur_price = prices.get(key, info["base_price"])
        pct = (cur_price - info["base_price"]) / info["base_price"] * 100

        ax.set_facecolor("#1a1d2e")
        for spine in ax.spines.values():
            spine.set_color("#2d3151")
        ax.tick_params(colors="#94a3b8", labelsize=8)

        if hist and len(hist) >= 2:
            ys = [h["price"] for h in hist]
            xs = list(range(len(ys)))
            color = "#22c55e" if ys[-1] >= ys[0] else "#ef4444"
            ax.plot(xs, ys, color=color, linewidth=2)
            ax.fill_between(xs, ys, alpha=0.15, color=color)
            ax.yaxis.set_major_formatter(mticker.FormatStrFormatter('%d'))
            ax.set_xticks([])
        else:
            ax.text(0.5, 0.5, "Нет данных", ha="center", va="center",
                    transform=ax.transAxes, color="#94a3b8", fontsize=10)
            ax.set_xticks([])
            ax.set_yticks([])

        sign = "+" if pct >= 0 else ""
        ax.set_title(
            f"{info['name']}\n{cur_price} 🪙  ({sign}{pct:.0f}% к базе)",
            color="#e2e8f0", fontsize=9, pad=5,
        )

    fig.tight_layout(pad=1.2)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)

    from aiogram.types import BufferedInputFile
    await message.answer_photo(
        BufferedInputFile(buf.read(), filename="bonds.png"),
        caption="📊 <b>Биржа Тейвата</b> — динамика цен",
        parse_mode="HTML",
    )


# ─── Купить акции на сумму Моры ───────────────────────────────────────────────

@router.message(BotCommand("купить акции", "вложить"))
async def cmd_buy_bonds_mora(message: Message, cmd_args: str):
    """бот купить акции [ключ] [сумма] — купить облигации на указанную сумму Моры."""
    if message.chat.type not in ("group", "supergroup"):
        await message.answer("❌ Команда работает только в группах.")
        return

    args = (cmd_args or "").strip().split()
    if len(args) < 2:
        await message.answer(
            "Пример: <code>бот купить акции mondstadt 500</code>\n"
            "Мора конвертируется в максимальное кол-во облигаций.",
            parse_mode="HTML",
        )
        return

    bond_key = args[0].lower()
    if bond_key not in BOND_DEFAULTS:
        keys = ", ".join(BOND_DEFAULTS.keys())
        await message.answer(f"❌ Неизвестная облигация. Доступные: {keys}")
        return

    try:
        mora_amount = int(args[1])
        if mora_amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Сумма Моры должна быть положительным числом.")
        return

    uid = message.from_user.id
    chat_id = message.chat.id

    prices = await get_bond_prices(chat_id)
    price_per = prices.get(bond_key, BOND_DEFAULTS[bond_key]["base_price"])
    shares = mora_amount // price_per

    if shares <= 0:
        await message.answer(
            f"❌ Недостаточно для покупки 1 облигации.\n"
            f"Текущая цена: <b>{price_per} 🪙</b>",
            parse_mode="HTML",
        )
        return

    total_cost = shares * price_per
    bname = BOND_DEFAULTS[bond_key]["name"]

    mora = await get_mora(uid, chat_id)
    pers_bal = (mora["balance"] or 0) if mora else 0
    try:
        from database.db import get_total_family_balance
        fam_bal, _, _ = await get_total_family_balance(chat_id, uid)
    except Exception:
        fam_bal = 0

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text=f"💳 Личный ({pers_bal} 🪙)",
            callback_data=f"bond_buy:personal:{uid}:{chat_id}:{bond_key}:{shares}",
        ),
        InlineKeyboardButton(
            text=f"👨‍👩‍👧 Семейный ({fam_bal} 🪙)",
            callback_data=f"bond_buy:family:{uid}:{chat_id}:{bond_key}:{shares}",
        ),
    ]])
    await message.answer(
        f"💸 <b>Купить на Мору</b>\n"
        f"{bname}: <b>{shares} шт.</b>\n"
        f"Итого: <b>{total_cost} 🪙</b> ({price_per} за шт.)\n\n"
        f"Выбери кошелёк:",
        parse_mode="HTML",
        reply_markup=kb,
    )

