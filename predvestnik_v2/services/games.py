"""
services/games.py
Pure gambling logic. No bot imports.

Аудит C1: каждая ставка целиком выполняется внутри `eco.atomic(db, user_id)`
(транзакция + FOR UPDATE на строке игрока). Это сериализует параллельные ставки
одного игрока → КД, дневной лимит и баланс проверяются под локом, поэтому больше
нельзя спамом параллельных запросов обойти кулдаун/кэп или уйти в минус.
"""
import random
from datetime import datetime, timedelta
from services.formatting import parse_dt

from core.constants import GAMES, GAMBLE_DAILY_CAP, ROULETTE_RED_NUMBERS
from infrastructure.repositories import economy as eco_repo
from infrastructure.repositories.games import (
    get_cooldown, set_cooldown, get_daily_winnings, add_daily_winnings,
)


def _today_utc() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d")


async def _check_cooldown(db, user_id: int, game: str) -> str | None:
    """Returns None if OK, or a human-readable error string."""
    last = await get_cooldown(db, user_id, game)
    if not last:
        return None
    cooldown_min = GAMES[game]["cooldown_min"]
    try:
        last_dt = parse_dt(last)
        elapsed = (datetime.utcnow() - last_dt).total_seconds() / 60
        if elapsed < cooldown_min:
            remaining = int(cooldown_min - elapsed) + 1
            return f"КД: ещё {remaining} мин."
    except ValueError:
        pass
    return None


async def _settle(
    db,
    user_id: int,
    game: str,
    bet: float,
    win: bool,
    multiplier: float,
    chat_id: int | None = None,
) -> dict:
    """Deduct bet, add winnings if win. Returns result dict.
    БЕЗ commit — вызывается ВНУТРИ eco.atomic(), который коммитит на выходе."""
    today = _today_utc()
    already_won = await get_daily_winnings(db, user_id, today)

    await eco_repo.add_balance(db, user_id, mora=-bet, commit=False,
                               source="gamble_loss", chat_id=chat_id)
    net_win = 0.0
    if win:
        gross = bet * multiplier
        if already_won + gross > GAMBLE_DAILY_CAP:
            gross = max(0.0, GAMBLE_DAILY_CAP - already_won)
        net_win = gross
        if gross > 0:
            await eco_repo.add_balance(db, user_id, mora=gross, commit=False,
                                       source="gamble_win", chat_id=chat_id)
            await add_daily_winnings(db, user_id, today, gross)

    await set_cooldown(db, user_id, game)

    return {
        "win": win and net_win > 0,
        "capped": win and net_win == 0,
        "net_win": net_win,
        "bet": bet,
        "multiplier": multiplier,
    }


def _validate_bet(game: str, bet: float) -> str | None:
    cfg = GAMES[game]
    if not cfg["min_bet"] <= bet <= cfg["max_bet"]:
        return f"Ставка: {int(cfg['min_bet'])}–{int(cfg['max_bet'])} 🪙."
    return None


async def play_dice(db, user_id: int, bet: float, chat_id: int | None = None) -> dict:
    if err := _validate_bet("dice", bet):
        return {"error": err}
    cfg = GAMES["dice"]
    player = random.randint(1, 6)
    bot_roll = random.randint(1, 6)
    win = player > bot_roll

    async with eco_repo.atomic(db, user_id):
        if err := await _check_cooldown(db, user_id, "dice"):
            return {"error": err}
        if (await eco_repo.get_balance(db, user_id))["user_balance_mora"] < bet:
            return {"error": "Недостаточно Моры."}
        result = await _settle(db, user_id, "dice", bet, win, cfg["multiplier"], chat_id)

    result["player_roll"] = player
    result["bot_roll"] = bot_roll
    return result


async def play_coin(
    db, user_id: int, bet: float, choice: str, chat_id: int | None = None
) -> dict:
    if err := _validate_bet("coin", bet):
        return {"error": err}
    cfg = GAMES["coin"]
    landed = random.choice(["орёл", "решка"])
    win = landed == choice.lower().strip()

    async with eco_repo.atomic(db, user_id):
        if err := await _check_cooldown(db, user_id, "coin"):
            return {"error": err}
        if (await eco_repo.get_balance(db, user_id))["user_balance_mora"] < bet:
            return {"error": "Недостаточно Моры."}
        result = await _settle(db, user_id, "coin", bet, win, cfg["multiplier"], chat_id)

    result["landed"] = landed
    result["choice"] = choice
    return result


async def play_number(
    db, user_id: int, bet: float, guess: int, chat_id: int | None = None
) -> dict:
    if err := _validate_bet("number", bet):
        return {"error": err}
    if not 1 <= guess <= 10:
        return {"error": "Загадайте число от 1 до 10."}
    cfg = GAMES["number"]
    drawn = random.randint(1, 10)
    win = drawn == guess

    async with eco_repo.atomic(db, user_id):
        if err := await _check_cooldown(db, user_id, "number"):
            return {"error": err}
        if (await eco_repo.get_balance(db, user_id))["user_balance_mora"] < bet:
            return {"error": "Недостаточно Моры."}
        result = await _settle(db, user_id, "number", bet, win, cfg["multiplier"], chat_id)

    result["drawn"] = drawn
    result["guess"] = guess
    return result


async def play_roulette(
    db, user_id: int, bet: float, bet_type: str, chat_id: int | None = None
) -> dict:
    """bet_type: 'red' | 'black' | 'even' | 'odd' | 'low' | 'high'"""
    if err := _validate_bet("roulette", bet):
        return {"error": err}
    cfg = GAMES["roulette"]
    number = random.randint(0, 36)
    bet_type = bet_type.lower().strip()
    win = False
    if number == 0:
        win = False
    elif bet_type == "red":
        win = number in ROULETTE_RED_NUMBERS
    elif bet_type == "black":
        win = number not in ROULETTE_RED_NUMBERS
    elif bet_type == "even":
        win = number % 2 == 0
    elif bet_type == "odd":
        win = number % 2 != 0
    elif bet_type == "low":
        win = 1 <= number <= 18
    elif bet_type == "high":
        win = 19 <= number <= 36

    async with eco_repo.atomic(db, user_id):
        if err := await _check_cooldown(db, user_id, "roulette"):
            return {"error": err}
        if (await eco_repo.get_balance(db, user_id))["user_balance_mora"] < bet:
            return {"error": "Недостаточно Моры."}
        result = await _settle(db, user_id, "roulette", bet, win, cfg["multiplier"], chat_id)

    result["number"] = number
    result["color"] = "🟢 0" if number == 0 else ("🔴" if number in ROULETTE_RED_NUMBERS else "⚫")
    result["bet_type"] = bet_type
    return result
