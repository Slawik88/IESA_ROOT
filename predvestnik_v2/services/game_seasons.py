"""Season settlement for the paying game boards.

A finished season is settled in three resumable steps, driven by the scheduler
(never by a player opening a leaderboard):

1. Wait ``SETTLEMENT_DELAY`` after the season ends so integrity verdicts settle.
2. Freeze each paying board once: only players who met the participation terms
   and whose account was in the bot for ``account_age.MIN_ACCOUNT_AGE`` by the
   season's end are ranked (new accounts neither take a place nor count towards
   the podium thresholds), each with the reward of their place (one transaction, one
   ``game_season_settlements`` marker per board).
3. Pay every player once, for the best reward over all paying boards.  Mora and
   Essence move in one transaction per player, so a failure rolls back that
   player only and the next tick retries it; ledger idempotency keys make a
   replay harmless.  The season closes when nobody is left unpaid.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable, Mapping

from loguru import logger

from core import account_age
from core import seasons as rules
from infrastructure.repositories import account_age as account_age_repo
from infrastructure.repositories import economy_ledger
from infrastructure.repositories import game_seasons as repo
from services import skins_v3 as skins_service

# Rows carry user_id, place (rank among everyone with a ranked result), runs and
# days (participation) plus any display fields of the board.
Standings = Callable[[object, datetime, datetime], Awaitable[list[dict]]]
BoardKey = tuple[str, str]
PAY_BATCH = 200
# One scheduler pass pays at most this many players, so a huge season never holds
# the maintenance loop for long; the rest continue on the next pass.
MAX_PAYOUTS_PER_PASS = 500


def _dumps(value) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)


def qualified_places(rows: list[dict]) -> list[dict]:
    """Rank only the players who met the participation terms; ties keep their tie."""
    ranked = sorted((row for row in rows if rules.qualifies(row["runs"], row["days"])),
                    key=lambda row: (int(row["place"]), int(row["user_id"])))
    previous_raw, previous_place = None, 0
    for index, row in enumerate(ranked, start=1):
        if int(row["place"]) != previous_raw:
            previous_raw, previous_place = int(row["place"]), index
        row["place_among_qualified"] = previous_place
    return ranked


async def _snapshot_board(db, *, season: int, game: str, board: str, standings: Standings) -> bool:
    """Freeze one board's places; False when it was already frozen."""
    if await repo.is_settled(db, game=game, board=board, season=season):
        return False
    start, end = rules.season_bounds(season)
    # The Rhythm standings first promote reviewed runs (idempotent writes); if that
    # raises, nothing is frozen yet and the next pass retries the whole snapshot.
    rows = await standings(db, start, end)
    seen = await account_age_repo.first_seen(db, (row["user_id"] for row in rows))
    allowed = account_age.eligible_ids(seen, (row["user_id"] for row in rows), end)
    ranked = qualified_places([row for row in rows if int(row["user_id"]) in allowed])
    if len(allowed) < len(rows):
        logger.info("Season {} {}/{}: {} new accounts left out of the ranking", season, game, board,
                    len(rows) - len(allowed))
    size = len(ranked)
    async with db.connection.transaction():
        if await repo.is_settled(db, game=game, board=board, season=season):
            return False
        for row in ranked:
            place = int(row["place_among_qualified"])
            mora, essence = rules.payout(place, board_size=size, runs=row["runs"], days=row["days"])
            result = {key: value for key, value in row.items()
                      if key not in {"user_id", "place", "place_among_qualified"}}
            result.update(raw_place=int(row["place"]), board_size=size, reward_essence=essence)
            await repo.insert_result(db, game=game, board=board, season=season, user_id=int(row["user_id"]),
                                     place=place, result_json=_dumps(result), reward_mora=mora)
        await repo.mark_settled(db, game=game, board=board, season=season, players=size)
    return True


async def _pay_one(db, *, season: int, row: dict) -> bool:
    """Pay one player's best reward; Mora and Essence succeed or fail together."""
    user_id, mora, essence = int(row["user_id"]), int(row["reward_mora"]), int(row["reward_essence"])
    if not await repo.insert_payout(db, season=season, user_id=user_id, game=row["game"], board=row["board"],
                                    place=int(row["place"]), mora=mora, essence=essence):
        return False
    await economy_ledger.apply_balance_change(
        db, user_id, {"mora": mora}, reason_code="season_reward",
        idempotency_key=f"season:{season}:{user_id}",
        source_type="season", reference_type="game_season", reference_id=str(season),
        metadata={"season": season, "game": row["game"], "board": row["board"],
                  "place": int(row["place"]), "mora": mora, "essence": essence},
        note=f"Сезон {season}: место #{int(row['place'])}",
    )
    if essence:
        await skins_service.grant_essence_in_transaction(
            db, user_id, essence, reason="season_reward", reference=f"{season}:{user_id}")
    return True


async def _pay_season(db, *, season: int, batch: int = PAY_BATCH,
                      max_payouts: int = MAX_PAYOUTS_PER_PASS) -> tuple[int, int]:
    paid = failed = 0
    cursor_user = 0
    while paid + failed < max_payouts:
        rows = await repo.unpaid_batch(db, season=season, after_user_id=cursor_user,
                                       limit=min(batch, max_payouts - paid - failed))
        if not rows:
            break
        for row in rows:
            cursor_user = int(row["user_id"])
            try:
                async with db.connection.transaction():
                    if await _pay_one(db, season=season, row=row):
                        paid += 1
            except Exception:
                failed += 1
                logger.exception("Season {} payout failed for user {}; it is retried on the next pass",
                                 season, cursor_user)
    return paid, failed


async def settle_due(db, *, boards: Mapping[BoardKey, Standings], now: datetime | None = None,
                     batch: int = PAY_BATCH, max_payouts: int = MAX_PAYOUTS_PER_PASS) -> dict:
    """One resumable settlement pass over every finished, not yet closed season."""
    missing = [key for key in rules.PAYING_BOARDS if key not in boards]
    if missing:
        raise rules.SeasonRuleError(f"no standings provided for paying boards: {missing}")
    now = now or datetime.now(timezone.utc)
    summary = {"snapshots": 0, "paid": 0, "failed": 0, "closed": 0}
    await repo.ensure_tables(db)
    for season in range(1, rules.season_number(now)):
        if now < rules.season_bounds(season)[1] + rules.SETTLEMENT_DELAY:
            continue
        if await repo.is_closed(db, season=season):
            continue
        if not await repo.try_lock_season(db, season=season):
            if now > rules.season_bounds(season)[1] + rules.SETTLEMENT_DELAY + timedelta(days=1):
                logger.warning("Season {} is overdue and its settlement lock is held elsewhere", season)
            continue
        try:
            for game, board in rules.PAYING_BOARDS:
                if await _snapshot_board(db, season=season, game=game, board=board,
                                         standings=boards[(game, board)]):
                    summary["snapshots"] += 1
            paid, failed = await _pay_season(db, season=season, batch=batch, max_payouts=max_payouts)
            summary["paid"] += paid
            summary["failed"] += failed
            if not failed and await repo.unpaid_count(db, season=season) == 0:
                await repo.close_season(db, season=season)
                summary["closed"] += 1
        finally:
            await repo.unlock_season(db, season=season)
    return summary


def season_view(now: datetime | None = None, *, game: str | None = None, board: str | None = None) -> dict:
    """Current season for a leaderboard; ``paying`` and ``terms`` describe its payout."""
    view = rules.current_season(now)
    if game is not None:
        view["paying"] = rules.is_paying(game, board or "")
        if view["paying"]:
            view["terms"] = rules.terms()
        else:
            view["rewards"] = []
    return view


async def last_result(db, *, game: str, board: str, user_id: int) -> dict | None:
    row = await repo.last_result(db, game=game, board=board, user_id=user_id)
    if not row:
        return None
    result = row["result_json"]
    result = (json.loads(result) if isinstance(result, str) else result) or {}
    return {"season": int(row["season"]), "place": int(row["place"]),
            "reward_mora": int(row["reward_mora"]),
            "reward_essence": int(result.get("reward_essence", 0)), "result": result}
