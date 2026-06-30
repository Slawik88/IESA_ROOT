"""FastAPI/routers/games.py — мини-игры: кости, монетка, угадай число, рулетка.
Тонкий адаптер над services/games.py — вся логика там.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from FastAPI.deps import get_db, require_tg_user, require_module
from core.constants import GAMES, GAMBLE_DAILY_CAP
from infrastructure.repositories.games import get_cooldown, get_daily_winnings
from services.games import play_dice, play_coin, play_number, play_roulette
from services.formatting import parse_dt

from datetime import datetime

router = APIRouter(prefix="/games", tags=["games"], dependencies=[Depends(require_module("module_games"))])


@router.get("/status")
async def games_status(db=Depends(get_db), user=Depends(require_tg_user)):
    """Текущий статус: дневной кап и кулдауны по каждой игре."""
    user_id = user["id"]
    today = datetime.utcnow().strftime("%Y-%m-%d")
    won_today = await get_daily_winnings(db, user_id, today)
    remaining_cap = max(0.0, GAMBLE_DAILY_CAP - won_today)

    cooldowns = {}
    now = datetime.utcnow()
    for game, cfg in GAMES.items():
        last_raw = await get_cooldown(db, user_id, game)
        ready_in = 0
        if last_raw:
            try:
                last_dt = parse_dt(last_raw) if not isinstance(last_raw, datetime) else last_raw
                elapsed_min = (now - last_dt).total_seconds() / 60
                cd_min = cfg["cooldown_min"]
                if elapsed_min < cd_min:
                    ready_in = max(0, int(cd_min - elapsed_min) + 1)
            except Exception:
                pass
        cooldowns[game] = {
            "ready": ready_in == 0,
            "ready_in_min": ready_in,
            "min_bet": cfg["min_bet"],
            "max_bet": cfg["max_bet"],
            "multiplier": cfg["multiplier"],
            "cooldown_min": cfg["cooldown_min"],
        }

    return {
        "won_today": won_today,
        "daily_cap": GAMBLE_DAILY_CAP,
        "remaining_cap": remaining_cap,
        "cooldowns": cooldowns,
    }


class PlayRequest(BaseModel):
    game: str        # "dice" | "coin" | "number" | "roulette"
    bet: float
    choice: str = ""  # монетка: "орёл"/"решка"; число: "1"-"10"; рулетка: "red"/"black"/...


@router.post("/play")
async def play_game(body: PlayRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    """Сыграть в мини-игру. Вся логика в services/games.py — идентично боту."""
    user_id = user["id"]

    if body.game == "dice":
        result = await play_dice(db, user_id, body.bet)

    elif body.game == "coin":
        if body.choice.lower().strip() not in ("орёл", "решка"):
            raise HTTPException(400, "Для монетки укажите choice: 'орёл' или 'решка'.")
        result = await play_coin(db, user_id, body.bet, body.choice)

    elif body.game == "number":
        try:
            guess = int(body.choice)
        except (ValueError, TypeError):
            raise HTTPException(400, "Для 'угадай число' укажите choice: целое число от 1 до 10.")
        result = await play_number(db, user_id, body.bet, guess)

    elif body.game == "roulette":
        valid_types = {"red", "black", "even", "odd", "low", "high"}
        if body.choice.lower().strip() not in valid_types:
            raise HTTPException(400, f"Для рулетки укажите choice из: {', '.join(sorted(valid_types))}.")
        result = await play_roulette(db, user_id, body.bet, body.choice)

    else:
        raise HTTPException(400, "Неизвестная игра. Доступны: dice, coin, number, roulette.")

    if result.get("error"):
        raise HTTPException(400, result["error"])

    return result
