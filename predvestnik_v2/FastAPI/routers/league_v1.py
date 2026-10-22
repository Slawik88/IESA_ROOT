"""League demo (early access only): the page /league-demo and its API under /league-demo/api.

The page shell is public (Telegram passes initData to JavaScript, not to the first navigation);
every API call requires a signed-in player whose global role is at or above the creator's threshold
for «Ранний доступ к контенту» (admin «Права»).  Rewards in the demo are fake.
"""
from __future__ import annotations

import os
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field

from FastAPI.deps import get_db, require_tg_user
from FastAPI.static_assets import asset_version
from services import early_access, league_v1 as league

router = APIRouter(tags=["league-demo"])
_STATIC = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
_ASSETS = {"league-demo.css": "text/css", "league-demo.js": "application/javascript",
           "league-mines.js": "application/javascript", "league-rhythm.js": "application/javascript"}
_VER = asset_version(_STATIC, ("league-demo.html", *_ASSETS))
_BASE = os.getenv("ROOT_PATH", "").rstrip("/")


def _read(name: str) -> str:
    with open(os.path.join(_STATIC, name), encoding="utf-8") as handle:
        return handle.read()


_HTML = _read("league-demo.html").replace("{{BASE}}", _BASE).replace("{{VER}}", _VER)


async def _early(user=Depends(require_tg_user), db=Depends(get_db)) -> dict:
    if not await early_access.allowed(db, int(user["id"])):
        raise HTTPException(403, "Ранний доступ к этому режиму закрыт.")
    return user


def _fail(exc: league.LeagueError):
    raise HTTPException(409, str(exc)) from exc


class StartBody(BaseModel):
    game: Literal["minesweeper", "rhythm"]
    level: int = Field(ge=1, le=1000)


class MineBody(BaseModel):
    revision: int = Field(ge=0)
    kind: Literal["open", "flag"]
    cell: int = Field(ge=0, le=12 * 16 - 1)


class RhythmBody(BaseModel):
    actions: list[dict] = Field(max_length=200)


@router.get("/league-demo", response_class=HTMLResponse)
async def page():
    return HTMLResponse(_HTML, headers={"Cache-Control": "no-cache"})


@router.get("/static/league-demo/{name}")
async def asset(name: str):
    if name not in _ASSETS:
        raise HTTPException(404, "not found")
    return Response(_read(name), media_type=f"{_ASSETS[name]}; charset=utf-8", headers={"Cache-Control": "no-cache"})


@router.get("/league-demo/api/access")
async def access(user=Depends(require_tg_user), db=Depends(get_db)) -> dict:
    return {"allowed": await early_access.allowed(db, int(user["id"]))}


@router.get("/league-demo/api/me")
async def me(user=Depends(_early), db=Depends(get_db)) -> dict:
    return await league.overview(db, user_id=int(user["id"]))


@router.post("/league-demo/api/runs")
async def start(body: StartBody, user=Depends(_early), db=Depends(get_db)) -> dict:
    try:
        return await league.start(db, user_id=int(user["id"]), game=body.game, level=body.level)
    except league.LeagueError as exc:
        _fail(exc)


@router.post("/league-demo/api/runs/{run_id}/mines")
async def mines(run_id: str, body: MineBody, user=Depends(_early), db=Depends(get_db)) -> dict:
    try:
        return await league.mines_act(db, user_id=int(user["id"]), run_id=run_id, revision=body.revision,
                                      kind=body.kind, cell=body.cell)
    except league.LeagueError as exc:
        _fail(exc)


@router.post("/league-demo/api/runs/{run_id}/rhythm")
async def rhythm(run_id: str, body: RhythmBody, user=Depends(_early), db=Depends(get_db)) -> dict:
    try:
        return await league.rhythm_finish(db, user_id=int(user["id"]), run_id=run_id, actions=body.actions)
    except league.LeagueError as exc:
        _fail(exc)


@router.post("/league-demo/api/reset")
async def reset(user=Depends(_early), db=Depends(get_db)) -> dict:
    await league.reset(db, user_id=int(user["id"]))
    return {"ok": True}
