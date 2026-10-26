"""Bridge verified casual/ranked game terminals into one achievement family."""
from datetime import datetime

from core import league_v1 as league_rules
from core.achievements_v1 import GAME_HISTORY_BATCH
from infrastructure.repositories import achievements_v1 as repo
from services import achievements_v1 as achievements



async def ranked_terminal(db, *, user_id: int, run_id: str, game: str, at: datetime) -> dict:
    if game not in {"rhythm","minesweeper"}:
        raise ValueError("unsupported ranked achievement game")
    await repo.ensure_tables(db)
    return await achievements.record_terminal(db,user_id=user_id,metric=f"{game}_completed",
        source_event_id=f"league:{run_id}",source_kind="league_v1_terminal",
        source_snapshot={"run_id":run_id,"game":game,"mode":"ranked"},now=at)


async def record_ranked(db, row: dict) -> None:
    if league_rules.is_demo(row["season"]):
        return
    await ranked_terminal(db,user_id=int(row["user_id"]),run_id=str(row["run_id"]),game=row["game"],at=row["server_now"])


async def reconcile(db, *, user_id: int) -> dict:
    async with db.connection.transaction():
        await repo.lock_user(db,user_id)
        terminals = await repo.missing_game_terminals(db,user_id,GAME_HISTORY_BATCH)
        for row in terminals:
            if row["mode"]=="ranked":
                await ranked_terminal(db,user_id=user_id,run_id=row["run_id"],game=row["game"],at=row["finished_at"])
            else:
                await achievements.record_terminal(db,user_id=user_id,metric=f"{row['game']}_completed",
                    source_event_id=row["run_id"],source_snapshot={"run_id":row["run_id"]},now=row["finished_at"])
    return {"games_restored":len(terminals),"games_pending":len(terminals)==GAME_HISTORY_BATCH}
