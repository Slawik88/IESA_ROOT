"""
Казино — азартные игры на Мору.

  бот монетка N           — подбросить монетку: 50/50, выиграть x2 или потерять N Мора
  бот кубик @user N       — бросить кубик против @user на N Мора (цель должна принять)
  бот купить лотерею      — купить лотерейный билет на эту неделю (10 Мора)
  бот мои билеты          — сколько билетов у тебя на эту неделю
"""
import html
import random
from datetime import date, datetime

from aiogram import F, Router
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from database.db import (
    add_mora,
    buy_lottery_ticket,
    create_duel,
    deduct_mora,
    get_duel,
    get_lottery_tickets,
    get_mora,
    get_pending_duels_for_chat,
    get_user,
    set_duel_status,
)
from filters.bot_command import BotCommand
from utils.helpers import resolve_target, user_mention

router = Router()

LOTTERY_PRICE   = 10    # Мора за билет
COIN_MAX_BET    = 5000  # максимальная ставка на монетку
DICE_MAX_BET    = 5000  # максимальная ставка на кубик
DUEL_EXPIRE_SEC = 300   # 5 минут для принятия дуэли


def _week_key() -> str:
    """Ключ текущей недели в формате ISO year-week, напр. '2025-W03'."""
    today = date.today()
    iso   = today.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


# ─── бот монетка N ────────────────────────────────────────────────────────────

@router.message(BotCommand("монетка", "coin", "flip", "монета"))
async def cmd_coin(message: Message, cmd_args: str):
    if message.chat.type not in ("group", "supergroup"):
        await message.answer("❌ Казино доступно только в группах.")
        return

    arg = (cmd_args or "").strip()
    if not arg.isdigit() or int(arg) <= 0:
        await message.answer(
            "🪙 <b>Монетка</b>\n\n"
            "Поставь Мору — 50/50 шанс удвоить или потерять.\n\n"
            "Использование: <code>бот монетка N</code>",
            parse_mode="HTML",
        )
        return

    bet = int(arg)
    if bet > COIN_MAX_BET:
        await message.answer(f"❌ Максимальная ставка: <b>{COIN_MAX_BET} 🪙</b>", parse_mode="HTML")
        return

    uid = message.from_user.id
    chat_id = message.chat.id
    mora = await get_mora(uid, chat_id)
    bal  = mora["balance"] if mora else 0

    if bal < bet:
        await message.answer(f"❌ Недостаточно Моры. У тебя: <b>{bal} 🪙</b>", parse_mode="HTML")
        return

    ok, _ = await deduct_mora(uid, chat_id, bet)
    if not ok:
        await message.answer("❌ Не удалось принять ставку.")
        return

    win = random.random() < 0.5
    if win:
        new_bal = await add_mora(uid, chat_id, bet * 2)
        result_emoji = "🟡"
        result_text  = f"<b>Орёл!</b> Ты выиграл <b>+{bet} 🪙</b>! 🎉"
    else:
        new_bal = bal - bet
        result_emoji = "⚫"
        result_text  = f"<b>Решка!</b> Ты потерял <b>-{bet} 🪙</b>. 😢"

    name = html.escape(message.from_user.full_name)
    await message.answer(
        f"{result_emoji} {user_mention(uid, name)} подбросил монетку!\n\n"
        f"Ставка: <b>{bet} 🪙</b>\n"
        f"{result_text}\n"
        f"Баланс: <b>{new_bal} 🪙</b>",
        parse_mode="HTML",
    )


# ─── бот кубик @user N ────────────────────────────────────────────────────────

@router.message(BotCommand("кубик", "dice", "дуэль", "duel"))
async def cmd_dice(message: Message, cmd_args: str, bot):
    if message.chat.type not in ("group", "supergroup"):
        await message.answer("❌ Казино доступно только в группах.")
        return

    args = (cmd_args or "").strip().split()
    if len(args) < 2:
        await message.answer(
            "🎲 <b>Дуэль на кубике</b>\n\n"
            "Брось кубик против другого участника на Мору.\n"
            "Цель должна принять вызов нажав кнопку.\n\n"
            "Использование: <code>бот кубик @user N</code>",
            parse_mode="HTML",
        )
        return

    target_str = args[0]
    bet_str    = args[-1]

    if not bet_str.isdigit() or int(bet_str) <= 0:
        await message.answer("❌ Укажи ставку числом.\nПример: <code>бот кубик @user 50</code>", parse_mode="HTML")
        return

    bet = int(bet_str)
    if bet > DICE_MAX_BET:
        await message.answer(f"❌ Максимальная ставка: <b>{DICE_MAX_BET} 🪙</b>", parse_mode="HTML")
        return

    uid = message.from_user.id
    chat_id = message.chat.id

    target_uid, target_name, _ = await resolve_target(message, target_str)
    if target_uid is None:
        await message.answer(f"❌ Пользователь не найден: {target_str}")
        return
    if target_uid == uid:
        await message.answer("❌ Нельзя бросить кубик против самого себя.")
        return

    # Проверяем, нет ли уже ожидающей дуэли от этого пользователя
    pending = await get_pending_duels_for_chat(chat_id, uid)
    if pending:
        await message.answer("❌ У тебя уже есть ожидающий вызов. Дождись его завершения.")
        return

    mora = await get_mora(uid, chat_id)
    bal  = mora["balance"] if mora else 0
    if bal < bet:
        await message.answer(f"❌ Недостаточно Моры. У тебя: <b>{bal} 🪙</b>", parse_mode="HTML")
        return

    ok, _ = await deduct_mora(uid, chat_id, bet)
    if not ok:
        await message.answer("❌ Не удалось принять ставку.")
        return

    target_user = await get_user(target_uid)
    target_display = html.escape(target_user["full_name"]) if target_user else html.escape(target_name)
    my_display = html.escape(message.from_user.full_name)

    # Создаём временного дуэль (msg_id=0 сначала, обновим после)
    duel_id = await create_duel(chat_id, uid, target_uid, bet, 0)

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text=f"🎲 Принять вызов ({bet} 🪙)",
            callback_data=f"duel_accept:{duel_id}:{target_uid}",
        ),
        InlineKeyboardButton(
            text="❌ Отказать",
            callback_data=f"duel_decline:{duel_id}:{target_uid}",
        ),
    ]])

    sent = await message.answer(
        f"🎲 <b>Вызов на дуэль!</b>\n\n"
        f"{user_mention(uid, my_display)} вызывает {user_mention(target_uid, target_display)}\n"
        f"Ставка: <b>{bet} 🪙</b>\n\n"
        f"⏳ {user_mention(target_uid, target_display)}, у тебя 5 минут чтобы принять.",
        parse_mode="HTML",
        reply_markup=kb,
    )

    # Обновляем msg_id в дуэли
    from database.sql_compat import aiosqlite_compat as aiosqlite
    from config import DATABASE_PATH
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "UPDATE casino_duels SET msg_id=? WHERE id=?",
            (sent.message_id, duel_id),
        )
        await db.commit()


@router.callback_query(F.data.startswith("duel_accept:"))
async def cb_duel_accept(callback: CallbackQuery):
    parts     = callback.data.split(":")
    duel_id   = int(parts[1])
    target_id = int(parts[2])

    if callback.from_user.id != target_id:
        await callback.answer("🚫 Этот вызов предназначен не тебе!", show_alert=True)
        return

    duel = await get_duel(duel_id)
    if not duel or duel["status"] != "pending":
        await callback.answer("⌛ Вызов устарел или уже завершён.", show_alert=True)
        return

    chat_id      = duel["chat_id"]
    challenger_id = duel["challenger_id"]
    bet          = duel["bet"]

    # Цель должна заплатить тоже
    mora = await get_mora(target_id, chat_id)
    bal  = mora["balance"] if mora else 0
    if bal < bet:
        await callback.answer(
            f"❌ У тебя недостаточно Моры! ({bal} / {bet} 🪙)",
            show_alert=True,
        )
        return

    ok, _ = await deduct_mora(target_id, chat_id, bet)
    if not ok:
        await callback.answer("❌ Не удалось принять ставку. Попробуй ещё раз.", show_alert=True)
        return

    await set_duel_status(duel_id, "accepted")

    # Броски кубика
    challenger_roll = random.randint(1, 6)
    target_roll     = random.randint(1, 6)

    # Перебросить при ничьей
    while challenger_roll == target_roll:
        challenger_roll = random.randint(1, 6)
        target_roll     = random.randint(1, 6)

    total_pot = bet * 2
    challenger_user = await get_user(challenger_id)
    target_user     = await get_user(target_id)
    challenger_name = html.escape(challenger_user["full_name"]) if challenger_user else str(challenger_id)
    target_name     = html.escape(target_user["full_name"]) if target_user else str(target_id)

    _DICE_FACE = ["", "1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣"]

    if challenger_roll > target_roll:
        winner_id   = challenger_id
        loser_id    = target_id
        winner_name = challenger_name
        winner_roll = challenger_roll
        loser_roll  = target_roll
    else:
        winner_id   = target_id
        loser_id    = challenger_id
        winner_name = target_name
        winner_roll = target_roll
        loser_roll  = challenger_roll

    new_bal = await add_mora(winner_id, chat_id, total_pot)

    result_text = (
        f"🎲 <b>Дуэль завершена!</b>\n\n"
        f"{user_mention(challenger_id, challenger_name)}: {_DICE_FACE[challenger_roll]} {challenger_roll}\n"
        f"{user_mention(target_id, target_name)}: {_DICE_FACE[target_roll]} {target_roll}\n\n"
        f"🏆 Победитель: {user_mention(winner_id, winner_name)}!\n"
        f"Приз: <b>+{bet} 🪙</b>  (банк: {total_pot} 🪙)\n"
        f"Баланс победителя: <b>{new_bal} 🪙</b>"
    )
    try:
        await callback.message.edit_text(result_text, parse_mode="HTML")
    except Exception:
        await callback.message.answer(result_text, parse_mode="HTML")
    await callback.answer("🎲 Дуэль!")


@router.callback_query(F.data.startswith("duel_decline:"))
async def cb_duel_decline(callback: CallbackQuery):
    parts     = callback.data.split(":")
    duel_id   = int(parts[1])
    target_id = int(parts[2])

    if callback.from_user.id != target_id:
        await callback.answer("🚫 Этот вызов предназначен не тебе!", show_alert=True)
        return

    duel = await get_duel(duel_id)
    if not duel or duel["status"] != "pending":
        await callback.answer("⌛ Вызов уже завершён.", show_alert=True)
        return

    await set_duel_status(duel_id, "declined")

    # Вернуть Мору вызывающему
    challenger_id = duel["challenger_id"]
    await add_mora(challenger_id, duel["chat_id"], duel["bet"])

    challenger_user = await get_user(challenger_id)
    challenger_name = html.escape(challenger_user["full_name"]) if challenger_user else str(challenger_id)

    try:
        await callback.message.edit_text(
            f"❌ {user_mention(target_id, html.escape(callback.from_user.full_name))} "
            f"отказался от дуэли.\n"
            f"Ставка возвращена {user_mention(challenger_id, challenger_name)}.",
            parse_mode="HTML",
        )
    except Exception:
        pass
    await callback.answer("Ты отказался от дуэли.")


# ─── бот купить лотерею ───────────────────────────────────────────────────────

@router.message(BotCommand("купить лотерею", "лотерея", "lottery", "билет"))
async def cmd_lottery(message: Message, cmd_args: str):
    if message.chat.type not in ("group", "supergroup"):
        await message.answer("❌ Казино доступно только в группах.")
        return

    uid     = message.from_user.id
    chat_id = message.chat.id
    week    = _week_key()

    existing = await get_lottery_tickets(chat_id, uid, week)
    mora     = await get_mora(uid, chat_id)
    bal      = mora["balance"] if mora else 0

    if bal < LOTTERY_PRICE:
        await message.answer(
            f"🎰 <b>Лотерея недели</b>\n\n"
            f"Цена билета: <b>{LOTTERY_PRICE} 🪙</b>\n"
            f"У тебя: <b>{bal} 🪙</b> — недостаточно.\n\n"
            f"<i>Розыгрыш каждое воскресенье! ~20% шанс выиграть 20–50 Моры.</i>",
            parse_mode="HTML",
        )
        return

    ok, _ = await deduct_mora(uid, chat_id, LOTTERY_PRICE)
    if not ok:
        await message.answer("❌ Не удалось купить билет.")
        return

    new_count = await buy_lottery_ticket(chat_id, uid, week)
    mora_after = await get_mora(uid, chat_id)
    bal_after  = mora_after["balance"] if mora_after else 0

    name = html.escape(message.from_user.full_name)
    await message.answer(
        f"🎰 {user_mention(uid, name)} купил лотерейный билет!\n\n"
        f"Неделя: <b>{week}</b>\n"
        f"Твоих билетов: <b>{new_count}</b> 🎟\n"
        f"Баланс: <b>{bal_after} 🪙</b>\n\n"
        f"<i>Розыгрыш в воскресенье. Удачи!</i>",
        parse_mode="HTML",
    )


@router.message(BotCommand("мои билеты", "мои лотерейные билеты", "lottery tickets"))
async def cmd_my_tickets(message: Message, cmd_args: str):
    if message.chat.type not in ("group", "supergroup"):
        return

    uid   = message.from_user.id
    chat_id = message.chat.id
    week  = _week_key()
    count = await get_lottery_tickets(chat_id, uid, week)

    if count:
        await message.answer(
            f"🎟 У тебя <b>{count}</b> билет(ов) на эту неделю ({week}).\n"
            f"<i>Розыгрыш в воскресенье!</i>",
            parse_mode="HTML",
        )
    else:
        await message.answer(
            f"🎰 У тебя нет лотерейных билетов на эту неделю.\n"
            f"Купить: <code>бот купить лотерею</code>  <i>({LOTTERY_PRICE} 🪙)</i>",
            parse_mode="HTML",
        )
