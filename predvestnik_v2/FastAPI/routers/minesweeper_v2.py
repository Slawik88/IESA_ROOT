"""Authenticated HTTP surface for the standalone Mini App Minesweeper."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from FastAPI.deps import get_db, require_tab_enabled, require_tg_user
from services import minesweeper_v2 as game


router = APIRouter(prefix="/minesweeper-v2", tags=["minesweeper-v2"])
_feature_gate = Depends(require_tab_enabled("game_minesweeper_v2"))


class StartBody(BaseModel):
    difficulty: Literal["easy", "normal", "hard"]


class ActionBody(BaseModel):
    action_id: str = Field(min_length=1, max_length=96)
    expected_revision: int = Field(ge=0)
    kind: Literal["open", "toggle_flag"]
    cell: int = Field(ge=0, le=143)


def _raise(exc: game.MinesweeperError) -> None:
    raise HTTPException(409 if isinstance(exc, game.MinesweeperConflict) else 400, str(exc)) from exc


@router.post("/runs", dependencies=[_feature_gate])
async def start(body: StartBody, db=Depends(get_db), user=Depends(require_tg_user)):
    try:
        return await game.start_run(db, user_id=int(user["id"]), difficulty=body.difficulty)
    except game.MinesweeperError as exc:
        _raise(exc)


@router.get("/runs/{run_id}", dependencies=[_feature_gate])
async def current(run_id: str, db=Depends(get_db), user=Depends(require_tg_user)):
    try:
        return await game.current_run(db, user_id=int(user["id"]), run_id=run_id)
    except game.MinesweeperError as exc:
        _raise(exc)


@router.post("/runs/{run_id}/actions", dependencies=[_feature_gate])
async def action(run_id: str, body: ActionBody, db=Depends(get_db), user=Depends(require_tg_user)):
    try:
        return await game.act(db, user_id=int(user["id"]), run_id=run_id, action_id=body.action_id,
                              expected_revision=body.expected_revision, kind=body.kind, cell=body.cell)
    except game.MinesweeperError as exc:
        _raise(exc)


@router.get("/leaderboard/{difficulty}", dependencies=[_feature_gate])
async def leaderboard(difficulty: Literal["easy", "normal", "hard"], db=Depends(get_db), user=Depends(require_tg_user)):
    try:
        return await game.rankings(db, user_id=int(user["id"]), difficulty=difficulty)
    except game.MinesweeperError as exc:
        _raise(exc)
