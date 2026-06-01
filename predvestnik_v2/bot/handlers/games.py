from aiogram import Router, types, F
from aiogram.filters.callback_data import CallbackData
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.filters.text_commands import TextCmd
from core.constants import GAMES, GAMBLE_DAILY_CAP
from infrastructure.repositories.games import get_daily_winnings
from services.games import play_dice, play_coin, play_number, play_roulette
from services.utils import format_currency

router = Router(name="games_router")
from bot.middlewares.module_check_mw import ModuleCheckMiddleware
router.message.middleware(ModuleCheckMiddleware("module_games"))

_GAME_LABELS = {
    "dice": "🎲 Кости",
    "coin": "🪙 Монетка",
    "number": "🔢 Угадай число",
    "roulette": "🎰 Рулетка",
}


class GameCB(CallbackData, prefix="game"):
    action: str    # menu | dice | coin | number | roulette | coin_choice | roul_type
    v: str = ""    # bet / choice
    v2: str = ""   # second param


def _stake_kb(action: str, extra: str = "") -> types.InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    cfg = GAMES.get(action.replace("_", "") if "_" in action else action, {})
    min_b = int(cfg.get("min_bet", 50))
    max_b = int(cfg.get("max_bet", 1000))
    presets = [50, 100, 200, 500, 1000, 2000]
    for stake in presets:
        if min_b <= stake <= max_b:
            b.button(text=f"{stake} 🪙",
                     callback_data=GameCB(action=action, v=str(stake), v2=extra))
    b.button(text="⬅️ Назад", callback_data=GameCB(action="menu"))
    b.adjust(3, 3, 1)
    return b.as_markup()


def _result_text(result: dict, game: str) -> str:
    if result.get("error"):
        return f"❌ {result['error']}"

    icon = "✅" if result["win"] else "❌"
    if result.get("capped"):
        icon = "⚠️"

    bet = result["bet"]
    win_str = f"+{format_currency(result['net_win'])} 🪙" if result["win"] else f"−{format_currency(bet)} 🪙"

    if game == "dice":
        detail = f"Вы: 🎲{result['player_roll']} vs Бот: 🎲{result['bot_roll']}"
    elif game == "coin":
        landed = "🦅 Орёл" if result["landed"] == "орёл" else "💿 Решка"
        detail = f"Выпало: {landed}"
    elif game == "number":
        detail = f"Загадано: {result['drawn']}, вы: {result['guess']}"
    elif game == "roulette":
        detail = f"Рулетка: {result['color']} {result['number']}"
    else:
        detail = ""

    if result.get("capped"):
        return f"⚠️ {detail}\n<i>Дневной кап достигнут — выигрыш не засчитан.</i>"
    return f"{icon} {detail}\n{win_str}"


# ── Menu ───────────────────────────────────────────────────────────────────────

@router.message(TextCmd(["игры", "казино", "азарт"]))
async def cmd_games_menu(message: types.Message, db):
    if message.chat.type == "private":
        return
    from datetime import datetime
    today = datetime.utcnow().strftime("%Y-%m-%d")
    won = await get_daily_winnings(db, message.from_user.id, today)
    remaining = max(0, GAMBLE_DAILY_CAP - won)

    b = InlineKeyboardBuilder()
    for game_id, label in _GAME_LABELS.items():
        b.button(text=label, callback_data=GameCB(action=game_id))
    b.adjust(2, 2)

    await message.answer(
        f"🎲 <b>МИНИ-ИГРЫ</b>\n\n"
        f"└ Осталось до кап-лимита: <code>{format_currency(remaining)} 🪙</code> из {int(GAMBLE_DAILY_CAP)}\n\n"
        f"Выберите игру:",
        reply_markup=b.as_markup(),
        parse_mode="HTML",
    )


@router.callback_query(GameCB.filter(F.action == "menu"))
async def cb_games_menu(query: types.CallbackQuery, db):
    await query.answer()
    await cmd_games_menu(query.message, db)


# ── Dice ───────────────────────────────────────────────────────────────────────

@router.message(TextCmd(["кости"]))
async def cmd_dice(message: types.Message, db, text_args: str = None):
    if message.chat.type == "private":
        return
    if not text_args:
        await message.answer(
            f"🎲 <b>КОСТИ</b>\n"
            f"<i>1d6 против бота — выше выигрывает. ×{GAMES['dice']['multiplier']}</i>",
            reply_markup=_stake_kb("dice"),
            parse_mode="HTML",
        )
        return
    try:
        bet = float(text_args.strip())
    except ValueError:
        return await message.answer("❌ Укажите ставку числом.", parse_mode="HTML")
    result = await play_dice(db, message.from_user.id, bet, message.chat.id)
    await message.answer(_result_text(result, "dice"), parse_mode="HTML")


@router.callback_query(GameCB.filter(F.action == "dice"))
async def cb_dice_stake(query: types.CallbackQuery, callback_data: GameCB, db):
    if not callback_data.v:
        await query.message.edit_text(
            f"🎲 <b>КОСТИ</b> — Выберите ставку:",
            reply_markup=_stake_kb("dice"),
            parse_mode="HTML",
        )
        await query.answer()
        return
    bet = float(callback_data.v)
    result = await play_dice(db, query.from_user.id, bet, query.message.chat.id)
    await query.answer(_result_text(result, "dice")[:200], show_alert=False)
    b = InlineKeyboardBuilder()
    b.button(text="🔁 Ещё раз", callback_data=GameCB(action="dice"))
    b.button(text="⬅️ Меню", callback_data=GameCB(action="menu"))
    b.adjust(2)
    await query.message.edit_text(_result_text(result, "dice"),
                                   reply_markup=b.as_markup(), parse_mode="HTML")


# ── Coin ───────────────────────────────────────────────────────────────────────

@router.message(TextCmd(["монетка"]))
async def cmd_coin(message: types.Message, db, text_args: str = None):
    if message.chat.type == "private":
        return
    if not text_args:
        b = InlineKeyboardBuilder()
        b.button(text="🦅 Орёл", callback_data=GameCB(action="coin_choice", v="орёл"))
        b.button(text="💿 Решка", callback_data=GameCB(action="coin_choice", v="решка"))
        b.button(text="⬅️ Назад", callback_data=GameCB(action="menu"))
        b.adjust(2, 1)
        await message.answer(
            f"🪙 <b>МОНЕТКА</b> — 50/50, ×{GAMES['coin']['multiplier']}. Сначала выберите сторону:",
            reply_markup=b.as_markup(),
            parse_mode="HTML",
        )
        return
    parts = text_args.strip().split(",")
    if len(parts) < 2:
        return await message.answer(
            "ℹ️ <code>бот монетка, [ставка], [орёл/решка]</code>", parse_mode="HTML"
        )
    try:
        bet, choice = float(parts[0]), parts[1].strip()
    except ValueError:
        return
    result = await play_coin(db, message.from_user.id, bet, choice, message.chat.id)
    await message.answer(_result_text(result, "coin"), parse_mode="HTML")


@router.callback_query(GameCB.filter(F.action == "coin_choice"))
async def cb_coin_choice(query: types.CallbackQuery, callback_data: GameCB):
    choice = callback_data.v
    await query.message.edit_text(
        f"🪙 <b>МОНЕТКА</b> — {choice.upper()} — Выберите ставку:",
        reply_markup=_stake_kb("coin", extra=choice),
        parse_mode="HTML",
    )
    await query.answer()


@router.callback_query(GameCB.filter(F.action == "coin"))
async def cb_coin_bet(query: types.CallbackQuery, callback_data: GameCB, db):
    if not callback_data.v:
        b = InlineKeyboardBuilder()
        b.button(text="🦅 Орёл", callback_data=GameCB(action="coin_choice", v="орёл"))
        b.button(text="💿 Решка", callback_data=GameCB(action="coin_choice", v="решка"))
        b.adjust(2)
        await query.message.edit_text("🪙 <b>МОНЕТКА</b> — выберите сторону:",
                                       reply_markup=b.as_markup(), parse_mode="HTML")
        await query.answer()
        return
    bet = float(callback_data.v)
    choice = callback_data.v2 or "орёл"
    result = await play_coin(db, query.from_user.id, bet, choice, query.message.chat.id)
    await query.answer(_result_text(result, "coin")[:200], show_alert=False)
    b = InlineKeyboardBuilder()
    b.button(text="🔁 Ещё раз", callback_data=GameCB(action="coin_choice", v=choice))
    b.button(text="⬅️ Меню", callback_data=GameCB(action="menu"))
    b.adjust(2)
    await query.message.edit_text(_result_text(result, "coin"),
                                   reply_markup=b.as_markup(), parse_mode="HTML")


# ── Number ─────────────────────────────────────────────────────────────────────

@router.message(TextCmd(["числа", "угадай число"]))
async def cmd_number(message: types.Message, db, text_args: str = None):
    if message.chat.type == "private":
        return
    if not text_args:
        b = InlineKeyboardBuilder()
        for n in range(1, 11):
            b.button(text=str(n), callback_data=GameCB(action="number", v2=str(n)))
        b.button(text="⬅️ Назад", callback_data=GameCB(action="menu"))
        b.adjust(5, 5, 1)
        await message.answer(
            f"🔢 <b>УГАДАЙ ЧИСЛО</b> 1–10, ×{GAMES['number']['multiplier']}.\nВыберите число:",
            reply_markup=b.as_markup(), parse_mode="HTML",
        )
        return
    parts = text_args.strip().split(",")
    if len(parts) < 2:
        return await message.answer(
            "ℹ️ <code>бот числа, [ставка], [1-10]</code>", parse_mode="HTML"
        )
    try:
        bet, guess = float(parts[0]), int(parts[1])
    except ValueError:
        return
    result = await play_number(db, message.from_user.id, bet, guess, message.chat.id)
    await message.answer(_result_text(result, "number"), parse_mode="HTML")


@router.callback_query(GameCB.filter(F.action == "number"))
async def cb_number_pick(query: types.CallbackQuery, callback_data: GameCB, db):
    if not callback_data.v:
        # No bet yet — show number picker or stake picker
        if callback_data.v2:
            # Has number, needs stake
            await query.message.edit_text(
                f"🔢 Число: <b>{callback_data.v2}</b> — выберите ставку:",
                reply_markup=_stake_kb("number", extra=callback_data.v2),
                parse_mode="HTML",
            )
        else:
            # Needs number first
            b = InlineKeyboardBuilder()
            for n in range(1, 11):
                b.button(text=str(n), callback_data=GameCB(action="number", v2=str(n)))
            b.button(text="⬅️ Назад", callback_data=GameCB(action="menu"))
            b.adjust(5, 5, 1)
            await query.message.edit_text(
                f"🔢 <b>УГАДАЙ ЧИСЛО</b> 1–10\nВыберите число:",
                reply_markup=b.as_markup(),
                parse_mode="HTML",
            )
        await query.answer()
        return
    # Have both bet and number
    bet = float(callback_data.v)
    guess = int(callback_data.v2)
    result = await play_number(db, query.from_user.id, bet, guess, query.message.chat.id)
    await query.answer(_result_text(result, "number")[:200], show_alert=False)
    b = InlineKeyboardBuilder()
    b.button(text="🔁 Ещё раз", callback_data=GameCB(action="number", v2=str(guess)))
    b.button(text="⬅️ Меню", callback_data=GameCB(action="menu"))
    b.adjust(2)
    await query.message.edit_text(_result_text(result, "number"),
                                   reply_markup=b.as_markup(), parse_mode="HTML")


# ── Roulette ───────────────────────────────────────────────────────────────────

@router.message(TextCmd(["рулетка"]))
async def cmd_roulette(message: types.Message, db):
    if message.chat.type == "private":
        return
    b = InlineKeyboardBuilder()
    for bet_type, label in [("red","🔴 Красное"), ("black","⚫ Чёрное"),
                              ("even","2️⃣ Чётное"), ("odd","1️⃣ Нечётное"),
                              ("low","📉 1-18"), ("high","📈 19-36")]:
        b.button(text=label, callback_data=GameCB(action="roul_type", v=bet_type))
    b.button(text="⬅️ Назад", callback_data=GameCB(action="menu"))
    b.adjust(2, 2, 2, 1)
    await message.answer(
        f"🎰 <b>РУЛЕТКА</b> (0-36) · ×{GAMES['roulette']['multiplier']}\nВыберите ставку:",
        reply_markup=b.as_markup(), parse_mode="HTML",
    )


async def cb_roulette_menu(query: types.CallbackQuery):
    b = InlineKeyboardBuilder()
    for bt, label in [("red","🔴"), ("black","⚫"), ("even","2️⃣"), ("odd","1️⃣"),
                       ("low","📉"), ("high","📈")]:
        b.button(text=label, callback_data=GameCB(action="roul_type", v=bt))
    b.button(text="⬅️ Назад", callback_data=GameCB(action="menu"))
    b.adjust(3, 3, 1)
    await query.message.edit_text("🎰 <b>РУЛЕТКА</b> — выберите тип:",
                                   reply_markup=b.as_markup(), parse_mode="HTML")
    await query.answer()


@router.callback_query(GameCB.filter(F.action == "roul_type"))
async def cb_roul_type(query: types.CallbackQuery, callback_data: GameCB):
    await query.message.edit_text(
        f"🎰 <b>РУЛЕТКА</b> — {callback_data.v.upper()} — Ставка:",
        reply_markup=_stake_kb("roulette", extra=callback_data.v),
        parse_mode="HTML",
    )
    await query.answer()


@router.callback_query(GameCB.filter(F.action == "roulette"))
async def cb_roulette_bet(query: types.CallbackQuery, callback_data: GameCB, db):
    if not callback_data.v or not callback_data.v2:
        await cb_roulette_menu(query)
        return
    bet = float(callback_data.v)
    bet_type = callback_data.v2
    result = await play_roulette(db, query.from_user.id, bet, bet_type, query.message.chat.id)
    await query.answer(_result_text(result, "roulette")[:200], show_alert=False)
    b = InlineKeyboardBuilder()
    b.button(text="🔁 Ещё раз", callback_data=GameCB(action="roul_type", v=bet_type))
    b.button(text="⬅️ Меню", callback_data=GameCB(action="menu"))
    b.adjust(2)
    await query.message.edit_text(_result_text(result, "roulette"),
                                   reply_markup=b.as_markup(), parse_mode="HTML")

    # Wire achievement
    if result.get("win"):
        from services.achievements import increment_metric
        await increment_metric(db, query.from_user.id, "gamble_wins", delta=1.0)
        await db.commit()
