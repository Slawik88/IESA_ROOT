"""Casino v1: chip wallet, daily gift, Мора → chips, rounds. Every write is one transaction and replays by action id."""
from __future__ import annotations

import secrets
from uuid import uuid4

from core import casino_v1 as rules
from core.economy_contract import InsufficientBalance
from infrastructure.repositories import casino_v1 as repo
from infrastructure.repositories import economy_ledger, public_profiles_v1
from services import leaderboards_v1


class CasinoError(Exception):
    pass


def _action(value: object) -> str:
    text = str(value or "").strip()
    if not 8 <= len(text) <= 96 or any(ord(ch) < 33 for ch in text):
        raise CasinoError("Повторите действие.")
    return text


def _wallet_view(row: dict | None, today) -> dict:
    row = row or {}
    bought = int(row.get("bought_today") or 0) if row.get("buy_day") == today else 0
    return {"chips": int(row.get("chips") or 0), "gift_ready": row.get("gift_day") != today,
            "buy_left": max(0, rules.DAILY_BUY_CAP_CHIPS - bought)}


def _round_view(row: dict) -> dict:
    return {"game": row["game"], "stake": int(row["stake"]), "mult": int(row["mult"]), "payout": int(row["payout"]),
            "detail": row["detail"]}


async def overview(db, user_id: int) -> dict:
    wallet, today = await repo.wallet(db, user_id), await repo.today(db)
    rows = await repo.week_wins(db)
    players = await public_profiles_v1.player_projection(db, user_ids=[int(r["user_id"]) for r in rows])
    board = {"top": [{"place": i + 1, "player": players.get(int(r["user_id"])), "game": r["game"], "mult": int(r["mult"]),
                      "payout": int(r["payout"])} for i, r in enumerate(rows) if players.get(int(r["user_id"]))]}
    await leaderboards_v1.decorate_game_board(db, board, user_id)
    return {"wallet": _wallet_view(wallet, today), "rules": rules.public_rules(),
            "recent": [_round_view(r) for r in await repo.recent_rounds(db, user_id)], "luck": board["top"]}


async def claim_gift(db, user_id: int) -> dict:
    async with db.connection.transaction():
        row = await repo.lock_wallet(db, user_id)
        if row["gift_day"] == row["today"]:
            raise CasinoError("Подарок уже получен сегодня. Новый — завтра.")
        await repo.claim_gift(db, user_id, rules.DAILY_GIFT)
        row = await repo.lock_wallet(db, user_id)
        return {"wallet": _wallet_view(row, row["today"]), "gift": rules.DAILY_GIFT}


async def buy_chips(db, user_id: int, *, mora: int, action_id: str) -> dict:
    """Мора → chips at the fixed rate, one way, within the daily cap; the Мора debit is a ledger operation."""
    action_id = _action(action_id)
    if isinstance(mora, bool) or mora not in rules.MORA_PACKS:
        raise CasinoError("Выберите пакет жетонов.")
    chips = mora * rules.CHIPS_PER_MORA
    async with db.connection.transaction():
        row = await repo.lock_wallet(db, user_id)
        replay = await repo.find_purchase(db, user_id, action_id)
        if replay:
            if int(replay["mora"]) != mora:
                raise CasinoError("Этот запрос уже использован для другой покупки.")
            return {"wallet": _wallet_view(row, row["today"]), "chips": int(replay["chips"]), "replayed": True}
        view = _wallet_view(row, row["today"])
        if chips > view["buy_left"]:
            raise CasinoError(f"Сегодня можно купить ещё {view['buy_left']} жетонов. Лимит обновится завтра.")
        purchase_id = uuid4().hex
        try:
            mutation = await economy_ledger.apply_balance_change(
                db, int(user_id), {"mora": -mora}, reason_code="casino_chips", idempotency_key=f"casino-chips:{purchase_id}",
                source_type="casino_v1", reference_type="casino_chips", reference_id=purchase_id,
                metadata={"policy_version": rules.POLICY_VERSION, "chips": chips, "mora": mora}, note=f"Жетоны казино: {chips}",
            )
        except InsufficientBalance as exc:
            raise CasinoError("Не хватает Моры.") from exc
        await repo.add_bought(db, user_id, chips)
        await repo.insert_purchase(db, purchase_id=purchase_id, user_id=user_id, action_id=action_id, mora=mora, chips=chips,
                                   operation_id=str(mutation.operation_id))
        row = await repo.lock_wallet(db, user_id)
        return {"wallet": _wallet_view(row, row["today"]), "chips": chips, "replayed": False}


async def play(db, user_id: int, *, game: str, stake: int, params: dict, action_id: str) -> dict:
    """One round: the server draws, debits the stake and credits the win atomically. A retry returns the same round."""
    action_id = _action(action_id)
    async with db.connection.transaction():
        row = await repo.lock_wallet(db, user_id)
        replay = await repo.find_round(db, user_id, action_id)
        if replay:
            if replay["game"] != game or int(replay["stake"]) != stake:
                raise CasinoError("Этот запрос уже использован для другой ставки.")
            return {"round": _round_view(replay), "wallet": _wallet_view(row, row["today"]), "replayed": True}
        try:
            outcome = rules.play(game, stake, params, secrets.randbelow)
        except rules.CasinoRuleError as exc:
            raise CasinoError(str(exc)) from exc
        chips_after = await repo.settle_round(db, user_id, stake, outcome.payout)
        if chips_after < 0:
            raise CasinoError("Не хватает жетонов. Заберите подарок дня или купите жетоны за Мору.")
        await repo.insert_round(db, round_id=uuid4().hex, user_id=user_id, action_id=action_id, game=game, stake=stake,
                                mult=outcome.mult, payout=outcome.payout, detail=outcome.detail, chips_after=chips_after,
                                policy_version=rules.POLICY_VERSION)
        row = await repo.lock_wallet(db, user_id)
        return {"round": {"game": game, "stake": stake, "mult": outcome.mult, "payout": outcome.payout, "detail": outcome.detail},
                "wallet": _wallet_view(row, row["today"]), "replayed": False}
