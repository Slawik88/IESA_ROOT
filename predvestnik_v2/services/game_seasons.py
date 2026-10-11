"""Season settlement shared by Rhythm and Minesweeper.

Settlement is lazy and idempotent: the first leaderboard view after a season
ends records every player's final place and credits the Mora reward once
(guarded by a ledger idempotency key and the result table's primary key).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Awaitable, Callable

from core import seasons as rules
from infrastructure.repositories import economy_ledger
from infrastructure.repositories import game_seasons as repo
from services import skins_v3 as skins_service

Standings = Callable[[object, datetime, datetime], Awaitable[list[dict]]]


def _dumps(value) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)


async def settle_due(db, *, game: str, board: str, standings: Standings,
                     now: datetime | None = None) -> int:
    """Settle every finished, not yet settled season of one board; returns how many."""
    now = now or datetime.now(timezone.utc)
    current = rules.season_number(now)
    settled = 0
    await repo.ensure_tables(db)
    for season in range(1, current):
        if await repo.is_settled(db, game=game, board=board, season=season):
            continue
        async with db.connection.transaction():
            if not await repo.try_lock_board(db, game=game, board=board):
                return settled
            if await repo.is_settled(db, game=game, board=board, season=season):
                continue
            start, end = rules.season_bounds(season)
            rows = await standings(db, start, end)
            for row in rows:
                place, user_id = int(row["place"]), int(row["user_id"])
                reward, essence = rules.reward(place)
                result = {key: value for key, value in row.items() if key not in {"user_id", "place"}}
                result["reward_essence"] = essence
                await repo.insert_result(db, game=game, board=board, season=season, user_id=user_id,
                                         place=place, result_json=_dumps(result), reward_mora=reward)
                await economy_ledger.apply_balance_change(
                    db, user_id, {"mora": reward}, reason_code="season_reward",
                    idempotency_key=f"season:{game}:{board}:{season}:{user_id}",
                    source_type="season", reference_type="game_season",
                    reference_id=f"{game}:{board}:{season}",
                    metadata={"game": game, "board": board, "season": season, "place": place, "mora": reward},
                    note=f"Сезон {season}: место #{place}",
                )
                # Essence is idempotent per (reason, reference); a skins-table
                # hiccup must never take the Mora payout down with it.
                try:
                    async with db.connection.transaction():
                        await skins_service.grant_essence_in_transaction(
                            db, user_id, essence, reason="season_reward",
                            reference=f"{game}:{board}:{season}:{user_id}")
                except Exception:
                    pass
            await repo.mark_settled(db, game=game, board=board, season=season, players=len(rows))
            settled += 1
    return settled


def season_view(now: datetime | None = None) -> dict:
    return rules.current_season(now)


async def last_result(db, *, game: str, board: str, user_id: int) -> dict | None:
    row = await repo.last_result(db, game=game, board=board, user_id=user_id)
    if not row:
        return None
    result = row["result_json"]
    result = (json.loads(result) if isinstance(result, str) else result) or {}
    return {"season": int(row["season"]), "place": int(row["place"]),
            "reward_mora": int(row["reward_mora"]),
            "reward_essence": int(result.get("reward_essence", 0)), "result": result}
