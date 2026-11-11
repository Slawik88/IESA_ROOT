"""Игры вдвоём в личной переписке (S29a): приглашение, «Принять», ходы, итог, возврат ставок.

Правила ходов — core/pair_games.py. Здесь — кто может нажимать и деньги. Каждое действие идёт под блокировкой строки
партии, поэтому двойное нажатие и одновременные нажатия двоих не дают двойного списания или выплаты:
- ставка списывается у обоих только при «Принять» (нажимает собеседник), в одной транзакции; не хватило одному —
  не списывается ни у кого;
- итог выплачивается один раз (settled), ничья и отмена возвращают ставки;
- жетоны берутся из одного фонда (бесплатные или купленные) и туда же возвращаются: бесплатные в купленные не превращаются;
- купленные жетоны стоят Мору, поэтому на них действуют правила переводов: игра на них закрыта, когда Мора не переводится,
  и с игроком, который удаляет аккаунт;
- в крестиках-ноликах затянуть проигранную партию нельзя: через сутки без хода проигрывает тот, чей ход.
"""
from __future__ import annotations

import secrets

from loguru import logger

from core import pair_games as rules
from infrastructure.repositories import casino_v1 as chips_repo
from infrastructure.repositories import pair_games as repo

MoveError = rules.MoveError


async def ensure_schema(db) -> None:
    await repo.ensure_schema(db)


async def chip_balance(db, user_id: int) -> dict[str, int]:
    """Сколько жетонов у игрока в каждом фонде (кошелька ещё нет — нули)."""
    found = await chips_repo.wallet(db, user_id)
    if not found:
        return {"bonus": 0, "redeemable": 0}
    total, real = int(found.get("chips") or 0), int(found.get("available_redeemable") or 0)
    return {"bonus": total - real, "redeemable": real}


async def invite(db, *, connection_id: str, chat_id: int, owner_id: int, partner_id: int, kind: str, stake: int,
                 funds: str | None, names: dict, mora_transferable: bool = True) -> dict:
    """Создать приглашение. Жетоны ещё не списываются — только проверяется, что у владельца их хватает."""
    if kind not in rules.KINDS:
        raise MoveError("Такой игры нет.")
    if stake:
        if funds not in rules.FUND_TITLES or stake not in rules.STAKES:
            raise MoveError("Выбери ставку кнопкой.")
        await check_money_rules(db, funds, owner_id, partner_id, mora_transferable=mora_transferable)
        if (await chip_balance(db, owner_id))[funds] < stake:
            raise MoveError(f"Не хватает {rules.FUND_TITLES[funds]}: нужно {stake}.")
    else:
        funds = None
    game_id = await repo.create(db, kind=kind, connection_id=connection_id, chat_id=chat_id, owner_id=owner_id,
                                partner_id=partner_id, stake=stake, funds=funds, state={}, names=names)
    return await repo.get(db, game_id)


async def attach_message(db, game_id: int, message_id: int) -> None:
    await repo.set_message(db, game_id, message_id)


async def check_money_rules(db, funds: str, *user_ids: int, mora_transferable: bool) -> None:
    """Купленные жетоны меняются на Мору, поэтому игра на них подчиняется тем же правилам, что перевод Моры.
    mora_transferable — переводится ли сейчас Мора (настройка «бот перевод»; её читает вызывающий бот)."""
    from infrastructure.repositories import business as business_repo
    if funds == "redeemable" and not mora_transferable:
        raise MoveError("Игры на купленные жетоны сейчас закрыты: переводы Моры выключены. Можно на бесплатные.")
    for uid in user_ids:
        found = await business_repo.known_player(db, uid)
        if found and found["deleting"]:
            raise MoveError("Один из игроков удаляет аккаунт: на жетоны с ним играть нельзя.")


def side_of(game: dict, user_id: int) -> str | None:
    return "owner" if int(user_id) == game["owner_id"] else "partner" if int(user_id) == game["partner_id"] else None


async def get(db, game_id: int) -> dict | None:
    return await repo.get(db, game_id)


async def _lock_wallets(db, *user_ids: int) -> None:
    for uid in sorted(set(int(u) for u in user_ids)):   # всегда в одном порядке: встречные партии не ждут друг друга
        await chips_repo.lock_wallet(db, uid)


async def accept(db, game_id: int, user_id: int, *, mora_transferable: bool = True) -> dict:
    async with db.connection.transaction():
        game = await repo.get(db, game_id, lock=True)
        if game is None:
            raise MoveError("Эта игра уже недоступна.")
        if game["status"] != "invited":
            raise MoveError("Игра уже началась или закрыта.")
        if int(user_id) != game["partner_id"]:
            raise MoveError("Принять может только тот, кого позвали.")
        if game["stake"]:
            await check_money_rules(db, game["funds"], game["owner_id"], game["partner_id"], mora_transferable=mora_transferable)
            await _lock_wallets(db, game["owner_id"], game["partner_id"])
            for side, uid in (("owner", game["owner_id"]), ("partner", game["partner_id"])):
                if await chips_repo.move_chips(db, uid, -game["stake"], game["funds"]) < 0:
                    who = "У тебя" if side == "partner" else "У того, кто позвал,"
                    raise MoveError(f"{who} не хватает {rules.FUND_TITLES[game['funds']]}: нужно {game['stake']}.")
        state = rules.new_state(game["kind"], secrets.choice(rules.SIDES))
        await repo.save(db, game_id, status="playing", state=state, held=bool(game["stake"]))
    logger.info(f"pair game {game_id} accepted (stake {game['stake']} {game['funds']})")
    return await repo.get(db, game_id)


async def decline(db, game_id: int, user_id: int) -> dict:
    """Собеседник отказался или владелец передумал, пока игру не приняли. Жетоны ещё не списаны."""
    async with db.connection.transaction():
        game = await repo.get(db, game_id, lock=True)
        if game is None or game["status"] != "invited":
            raise MoveError("Игра уже началась или закрыта.")
        side = side_of(game, user_id)
        if side is None:
            raise MoveError("Это не твоя игра.")
        await repo.save(db, game_id, status="declined" if side == "partner" else "cancelled", state=game["state"])
    return await repo.get(db, game_id)


async def play(db, game_id: int, user_id: int, value: str) -> tuple[dict, str | None]:
    """Ход. Возвращает (партия, итог): итог None — игра идёт, иначе 'owner' / 'partner' / 'draw' (партия закрыта и оплачена)."""
    async with db.connection.transaction():
        game = await repo.get(db, game_id, lock=True)
        if game is None or game["status"] != "playing":
            raise MoveError("Игра уже закрыта.")
        side = side_of(game, user_id)
        if side is None:
            raise MoveError("Это не твоя игра.")
        roll = secrets.randbelow(6) + 1 if game["kind"] == "dice" else None
        state, result = rules.move(game["kind"], game["state"], side, value, roll=roll)
        if result is None:
            await repo.save(db, game_id, status="playing", state=state)
        else:
            await _pay(db, game, result)
            await repo.save(db, game_id, status="finished", state=state, winner=result, settled=True)
    game = await repo.get(db, game_id)
    if result is not None:
        await _reward(db, game)
    return game, result


async def _pay(db, game: dict, result: str) -> None:
    if not (game["held"] and game["stake"]) or game["settled"]:
        return
    await _lock_wallets(db, game["owner_id"], game["partner_id"])
    for side, amount in rules.settle(game["stake"], result).items():
        if amount:
            await chips_repo.move_chips(db, game["owner_id"] if side == "owner" else game["partner_id"], amount, game["funds"])


async def _reward(db, game: dict) -> None:
    """Опыт Пропуска обоим игрокам за сыгранную партию: один раз на партию, в общем дневном пределе обычных игр."""
    from infrastructure.repositories import business as business_repo
    from services import league_pass
    for uid in (game["owner_id"], game["partner_id"]):
        if await business_repo.known_player(db, uid) is None:
            continue
        await league_pass.add_xp(db, user_id=uid, source="pair_game", event_id=str(game["id"]), xp=rules.XP, casual=True)


async def cancel(db, game_id: int, status: str = "expired", *, owner_forfeits: bool = False) -> dict | None:
    """Закрыть партию без итога (давно нет ходов или бота отключили) и вернуть ставки. Повтор ничего не меняет.
    Исключение — начатые крестики-нолики: через сутки без хода проигрывает тот, чей ход (иначе проигрывающий просто молчал бы);
    если владелец отключил бота посреди партии (owner_forfeits), проигрывает он — иначе отключение было бы выходом из проигрыша."""
    async with db.connection.transaction():
        game = await repo.get(db, game_id, lock=True)
        if game is None or game["status"] not in ("invited", "playing"):
            return None
        forfeit = None
        if game["status"] == "playing" and rules.forfeit(game["kind"], game["state"]):
            forfeit = "partner" if owner_forfeits else rules.forfeit(game["kind"], game["state"]) if status == "expired" else None
        if forfeit:
            await _pay(db, game, forfeit)
            await repo.save(db, game_id, status="finished", state={**game["state"], "forfeit": True}, winner=forfeit, settled=bool(game["held"]))
        else:
            await _pay(db, game, "draw")
            await repo.save(db, game_id, status=status, state=game["state"], settled=bool(game["held"]))
    return await repo.get(db, game_id)


async def expire_due(db) -> list[dict]:
    closed = []
    for game_id in await repo.stale_ids(db, rules.EXPIRE_HOURS):
        game = await cancel(db, game_id, "expired")
        if game:
            closed.append(game)
    await repo.forget_finished(db)
    return closed


async def cancel_for_connection(db, connection_id: str) -> list[dict]:
    closed = []
    for game_id in await repo.open_ids_for_connection(db, connection_id):
        game = await cancel(db, game_id, "cancelled", owner_forfeits=True)
        if game:
            closed.append(game)
    return closed
