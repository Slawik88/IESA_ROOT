# services/skill_games.py — R7: интеллектуальные мини-игры (GDD_REBUILD_PLAN.md).
#
# «Теневой Сапёр» (5×5, 3 мины, cashout в любой момент) и «Взлом сейфа»
# (Mastermind: 4 цифры 0-9 с повторами, 6 попыток). Server-authoritative:
# раскладка/секрет живут в minigame_sessions.state_json, клиент их не видит
# до конца сессии. Экономика — тот же паттерн, что казино (services/games.py):
# всё внутри eco.atomic(), дневной кап выигрыша ОБЩИЙ с казино
# (get/add_daily_winnings + GAMBLE_DAILY_CAP), победы кормят ачивку gamble_wins.
import random
from datetime import datetime, timezone

from core.constants import (
    GAMBLE_DAILY_CAP,
    SKILL_GAME_COOLDOWN_MIN,
    SAPPER_GRID, SAPPER_MINES, SAPPER_MIN_BET, SAPPER_MAX_BET, SAPPER_EDGE,
    SAFE_MIN_BET, SAFE_MAX_BET, SAFE_ATTEMPTS, SAFE_WIN_MULT,
    ALCHEMY_MIN_BET, ALCHEMY_MAX_BET,
)
from infrastructure.repositories import economy as eco_repo
from infrastructure.repositories import minigames as mg_repo
from infrastructure.repositories.games import get_daily_winnings, add_daily_winnings
from services import alchemy as alch


def _today_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


# ── Сапёр: математика множителя ───────────────────────────────────────────────

def sapper_multiplier(k: int) -> float:
    """Множитель после k безопасно открытых клеток: fair-гипергеометрия × эдж.
    fair(k) = Π_{i=0..k-1} (GRID−i) / (GRID−MINES−i) — обратная вероятность
    открыть k клеток подряд без мины."""
    if k <= 0:
        return 0.0
    fair = 1.0
    for i in range(k):
        fair *= (SAPPER_GRID - i) / (SAPPER_GRID - SAPPER_MINES - i)
    return round(fair * SAPPER_EDGE, 2)


def sapper_ladder() -> list[float]:
    """Лестница множителей для UI (1..GRID−MINES открытий)."""
    return [sapper_multiplier(k) for k in range(1, SAPPER_GRID - SAPPER_MINES + 1)]


async def _check_cooldown(db, user_id: int) -> str | None:
    since = await mg_repo.seconds_since_last_start(db, user_id)
    cd = SKILL_GAME_COOLDOWN_MIN * 60
    if since is not None and since < cd:
        left = cd - since
        return f"⏳ Кулдаун между играми: ещё {left // 60}м {left % 60:02d}с."
    return None


def _validate_stake(stake: float, lo: float, hi: float) -> str | None:
    if not (lo <= stake <= hi):
        return f"Ставка от {lo:.0f} до {hi:.0f} 🪙."
    return None


async def _payout_with_cap(db, user_id: int, gross: float, source: str) -> float:
    """Начислить выигрыш с учётом ОБЩЕГО дневного капа казино+скилл-игр.
    Возвращает фактически начисленное (может быть срезано капом до 0)."""
    today = _today_utc()
    already = await get_daily_winnings(db, user_id, today)
    if already + gross > GAMBLE_DAILY_CAP:
        gross = max(0.0, GAMBLE_DAILY_CAP - already)
    if gross > 0:
        await eco_repo.add_balance(db, user_id, mora=gross, commit=False, source=source)
        await add_daily_winnings(db, user_id, today, gross)
    return gross


# ── Теневой Сапёр ─────────────────────────────────────────────────────────────

async def sapper_start(db, user_id: int, stake: float) -> dict:
    active = await mg_repo.get_active(db, user_id, "sapper")
    if active:
        return {"ok": True, "resumed": True, **_sapper_public(active)}
    err = _validate_stake(stake, SAPPER_MIN_BET, SAPPER_MAX_BET) or await _check_cooldown(db, user_id)
    if err:
        return {"ok": False, "error": err}

    async with eco_repo.atomic(db, user_id):
        bal = await eco_repo.get_balance(db, user_id)
        if float(bal["user_balance_mora"] or 0) < stake:
            return {"ok": False, "error": "Недостаточно Моры."}
        await eco_repo.add_balance(db, user_id, mora=-stake, commit=False,
                                   source="gamble_loss", note="Сапёр: ставка")
        mines = random.sample(range(SAPPER_GRID), SAPPER_MINES)
        await mg_repo.create_session(db, user_id, "sapper", stake,
                                     {"mines": mines, "opened": []})
    session = await mg_repo.get_active(db, user_id, "sapper")
    return {"ok": True, "resumed": False, **_sapper_public(session)}


def _sapper_public(s: dict) -> dict:
    """Публичное состояние сессии — БЕЗ раскладки мин."""
    opened = s["state"].get("opened", [])
    k = len(opened)
    return {
        "session_id": s["id"],
        "stake": float(s["stake"]),
        "opened": opened,
        "k": k,
        "multiplier": sapper_multiplier(k),
        "next_multiplier": sapper_multiplier(k + 1),
        "cashout_value": round(float(s["stake"]) * sapper_multiplier(k), 2) if k else 0.0,
        "grid": SAPPER_GRID,
        "mines_count": SAPPER_MINES,
    }


async def sapper_open(db, user_id: int, cell: int) -> dict:
    s = await mg_repo.get_active(db, user_id, "sapper")
    if not s:
        return {"ok": False, "error": "Нет активной игры — начни новую."}
    if not (0 <= cell < SAPPER_GRID):
        return {"ok": False, "error": "Нет такой клетки."}
    state = s["state"]
    if cell in state["opened"]:
        return {"ok": False, "error": "Клетка уже открыта."}

    if cell in state["mines"]:
        await mg_repo.finish(db, s["id"], "lost")
        await db.commit()
        return {"ok": True, "boom": True, "cell": cell,
                "mines": state["mines"], "stake": float(s["stake"])}

    state["opened"].append(cell)
    k = len(state["opened"])
    # Все безопасные клетки открыты — принудительный кэшаут (масштаба поля хватит)
    if k >= SAPPER_GRID - SAPPER_MINES:
        return await sapper_cashout(db, user_id, _preloaded=s, _state=state)
    await mg_repo.update_state(db, s["id"], state)
    await db.commit()
    return {"ok": True, "boom": False, "cell": cell, "k": k,
            "multiplier": sapper_multiplier(k),
            "next_multiplier": sapper_multiplier(k + 1),
            "cashout_value": round(float(s["stake"]) * sapper_multiplier(k), 2)}


async def sapper_cashout(db, user_id: int, _preloaded: dict | None = None,
                         _state: dict | None = None) -> dict:
    s = _preloaded or await mg_repo.get_active(db, user_id, "sapper")
    if not s:
        return {"ok": False, "error": "Нет активной игры."}
    state = _state or s["state"]
    k = len(state.get("opened", []))
    if k == 0:
        return {"ok": False, "error": "Открой хотя бы одну клетку."}

    stake = float(s["stake"])
    gross = round(stake * sapper_multiplier(k), 2)
    async with eco_repo.atomic(db, user_id):
        paid = await _payout_with_cap(db, user_id, gross, "gamble_win")
        await mg_repo.finish(db, s["id"], "cashed", paid)
    if paid > stake:
        try:
            from services.achievements import increment_metric as _ach
            await _ach(db, user_id, "gamble_wins", delta=1.0)
            await db.commit()
        except Exception:
            pass
    return {"ok": True, "cashed": True, "k": k, "multiplier": sapper_multiplier(k),
            "payout": paid, "capped": paid < gross, "mines": state["mines"]}


# ── Взлом сейфа (Mastermind: быки/коровы) ─────────────────────────────────────

def _score_guess(secret: list[int], guess: list[int]) -> tuple[int, int]:
    """(быки, коровы) с поддержкой повторов: быки — позиционные совпадения,
    коровы — мультисет-пересечение минус быки."""
    bulls = sum(1 for a, b in zip(secret, guess) if a == b)
    common = 0
    for d in range(10):
        common += min(secret.count(d), guess.count(d))
    return bulls, common - bulls


async def safe_start(db, user_id: int, stake: float) -> dict:
    active = await mg_repo.get_active(db, user_id, "safe")
    if active:
        return {"ok": True, "resumed": True, **_safe_public(active)}
    err = _validate_stake(stake, SAFE_MIN_BET, SAFE_MAX_BET) or await _check_cooldown(db, user_id)
    if err:
        return {"ok": False, "error": err}

    async with eco_repo.atomic(db, user_id):
        bal = await eco_repo.get_balance(db, user_id)
        if float(bal["user_balance_mora"] or 0) < stake:
            return {"ok": False, "error": "Недостаточно Моры."}
        await eco_repo.add_balance(db, user_id, mora=-stake, commit=False,
                                   source="gamble_loss", note="Взлом сейфа: ставка")
        secret = [random.randint(0, 9) for _ in range(4)]
        await mg_repo.create_session(db, user_id, "safe", stake,
                                     {"secret": secret, "guesses": []})
    session = await mg_repo.get_active(db, user_id, "safe")
    return {"ok": True, "resumed": False, **_safe_public(session)}


def _safe_public(s: dict) -> dict:
    guesses = s["state"].get("guesses", [])
    return {
        "session_id": s["id"],
        "stake": float(s["stake"]),
        "guesses": guesses,                    # [{digits, bulls, cows}]
        "attempts_left": SAFE_ATTEMPTS - len(guesses),
        "win_mult": SAFE_WIN_MULT,
    }


async def safe_guess(db, user_id: int, digits: list[int]) -> dict:
    s = await mg_repo.get_active(db, user_id, "safe")
    if not s:
        return {"ok": False, "error": "Нет активной игры — начни новую."}
    if len(digits) != 4 or any(not (0 <= d <= 9) for d in digits):
        return {"ok": False, "error": "Нужно ровно 4 цифры (0–9)."}

    state = s["state"]
    bulls, cows = _score_guess(state["secret"], digits)
    state["guesses"].append({"digits": digits, "bulls": bulls, "cows": cows})
    n = len(state["guesses"])

    if bulls == 4:
        stake = float(s["stake"])
        gross = round(stake * SAFE_WIN_MULT, 2)
        async with eco_repo.atomic(db, user_id):
            paid = await _payout_with_cap(db, user_id, gross, "gamble_win")
            await mg_repo.finish(db, s["id"], "won", paid)
        try:
            from services.achievements import increment_metric as _ach
            await _ach(db, user_id, "gamble_wins", delta=1.0)
            await db.commit()
        except Exception:
            pass
        return {"ok": True, "cracked": True, "bulls": bulls, "cows": cows,
                "guesses": state["guesses"], "payout": paid,
                "capped": paid < gross, "secret": state["secret"]}

    if n >= SAFE_ATTEMPTS:
        await mg_repo.finish(db, s["id"], "lost")
        await db.commit()
        return {"ok": True, "cracked": False, "failed": True,
                "bulls": bulls, "cows": cows, "guesses": state["guesses"],
                "secret": state["secret"], "stake": float(s["stake"])}

    await mg_repo.update_state(db, s["id"], state)
    await db.commit()
    return {"ok": True, "cracked": False, "failed": False,
            "bulls": bulls, "cows": cows, "guesses": state["guesses"],
            "attempts_left": SAFE_ATTEMPTS - n}


# ── Алхимия (merge-2048, server-authoritative replay) ─────────────────────────

def _alchemy_public(s: dict) -> dict:
    seed = s["state"]["seed"]
    return {
        "session_id": s["id"],
        "stake": float(s["stake"]),
        "seed": seed,
        "time_limit_sec": alch.TIME_LIMIT_SEC,
    }


async def alchemy_start(db, user_id: int, stake: float) -> dict:
    active = await mg_repo.get_active(db, user_id, "alchemy")
    if active:
        return {"ok": True, "resumed": True, **_alchemy_public(active)}
    err = _validate_stake(stake, ALCHEMY_MIN_BET, ALCHEMY_MAX_BET) or await _check_cooldown(db, user_id)
    if err:
        return {"ok": False, "error": err}

    async with eco_repo.atomic(db, user_id):
        bal = await eco_repo.get_balance(db, user_id)
        if float(bal["user_balance_mora"] or 0) < stake:
            return {"ok": False, "error": "Недостаточно Моры."}
        await eco_repo.add_balance(db, user_id, mora=-stake, commit=False,
                                   source="gamble_loss", note="Алхимия: ставка")
        seed = random.randint(1, 2**32 - 1)
        await mg_repo.create_session(db, user_id, "alchemy", stake, {"seed": seed})
    session = await mg_repo.get_active(db, user_id, "alchemy")
    return {"ok": True, "resumed": False, **_alchemy_public(session)}


async def alchemy_submit(db, user_id: int, session_id: int, moves: list[str]) -> dict:
    s = await mg_repo.get_active(db, user_id, "alchemy")
    if not s or s["id"] != session_id:
        return {"ok": False, "error": "Нет активной игры — начни новую."}

    elapsed = await mg_repo.seconds_since_created(db, s["id"])
    if elapsed > alch.TIME_LIMIT_SEC + alch.SUBMIT_GRACE_SEC:
        await mg_repo.finish(db, s["id"], "lost")
        await db.commit()
        return {"ok": False, "error": "Время вышло — сессия закрыта."}

    result = alch.replay(s["state"]["seed"], moves)
    score = result["score"]
    mult = alch.payout_mult(score)
    stake = float(s["stake"])
    gross = round(stake * mult, 2)

    async with eco_repo.atomic(db, user_id):
        paid = await _payout_with_cap(db, user_id, gross, "gamble_win")
        await mg_repo.finish(db, s["id"], "done", paid)
    if paid > stake:
        try:
            from services.achievements import increment_metric as _ach
            await _ach(db, user_id, "gamble_wins", delta=1.0)
            await db.commit()
        except Exception:
            pass
    return {"ok": True, "score": score, "mult": mult, "payout": paid,
            "capped": paid < gross, "board": result["board"]}