"""The League: the page /league (alias /league-demo) and its API under /league-demo/api.

The page shell is public (Telegram passes initData to JavaScript, not to the first navigation).  Before
season 2 every League call needs «Ранний доступ к контенту» (admin «Права») and plays a fake demo; from
season 2 the League is open to every signed-in player.  The season pass API serves everyone.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Path
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field

from FastAPI import game_shell
from FastAPI.deps import get_db, require_tg_user
from FastAPI.static_assets import asset_version
from core import league_v1 as league_rules
from services import early_access, league_pass, league_v1 as league

router = APIRouter(tags=["league-demo"])
_STATIC = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
_JS, _CSS = "application/javascript", "text/css"
_ASSETS = {"league-demo.css": _CSS, "league-games.css": _CSS, "league-pass.css": _CSS, "casual-games-v3.css": _CSS,
           "league-art.js": _JS, "league-fx.js": _JS, "league-demo.js": _JS, "league-ladder.js": _JS, "league-result.js": _JS,
           "league-mines.js": _JS, "league-rhythm-fx.js": _JS, "league-rhythm.js": _JS, "league-pass.js": _JS, "league-help.js": _JS, "game-mode-v3.js": _JS,
           "game-shell-v3.js": _JS, "skin-runtime-v3.js": _JS}   # палитра надетого образа (--v3-acc), как в играх
_VER = asset_version(_STATIC, ("league-demo.html", "game-shell-v3.html", "page-transitions.js", *_ASSETS))
# What the pages of the casual mode (Rhythm, Minesweeper) load from here: their look, the shared header and the mode switch
CASUAL_PAGE_ASSETS = ("league-demo.css", "league-games.css", "casual-games-v3.css", "league-art.js", "league-fx.js", "game-mode-v3.js", "game-shell-v3.js")
ASSET_VERSION = _VER   # страницы обычного режима грузят общие файлы Лиги по этой версии (FastAPI/main.py)
_BASE = os.getenv("ROOT_PATH", "").rstrip("/")


def _read(name: str) -> str:
    with open(os.path.join(_STATIC, name), encoding="utf-8") as handle:
        return handle.read()


_HTML = game_shell.render(_read("league-demo.html"), base=_BASE, version=_VER, eyebrow="Сезон", title="Рейтинг")


async def _open_for(db, user_id: int) -> bool:
    return league_rules.is_public(datetime.now(timezone.utc)) or await early_access.allowed(db, user_id)


async def _early(user=Depends(require_tg_user), db=Depends(get_db)) -> dict:
    if not await _open_for(db, int(user["id"])):
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


class ClaimBody(BaseModel):
    season: int = Field(ge=2, le=10_000)


@router.get("/league", response_class=HTMLResponse)
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
    public = league_rules.is_public(datetime.now(timezone.utc))
    return {"allowed": public or await early_access.allowed(db, int(user["id"])), "public": public}


@router.get("/league-demo/api/pass")
async def pass_status(user=Depends(require_tg_user), db=Depends(get_db)) -> dict:
    return await league_pass.status(db, user_id=int(user["id"]))


# Опыт Пропуска за одну обычную игру (строка на экране итога Ритма и Сапёра); только чтение своих записей
@router.get("/league-demo/api/pass/casual/{source}/{event_id}")
async def pass_casual(source: Literal["rhythm", "minesweeper"], event_id: str = Path(max_length=80),
                      user=Depends(require_tg_user), db=Depends(get_db)) -> dict:
    return await league_pass.casual_receipt(db, user_id=int(user["id"]), source=source, event_id=event_id)


@router.post("/league-demo/api/pass/claim")
async def pass_claim(body: ClaimBody, user=Depends(require_tg_user), db=Depends(get_db)) -> dict:
    try:
        return await league_pass.claim(db, user_id=int(user["id"]), season=body.season)
    except league_pass.PassError as exc:
        raise HTTPException(409, str(exc)) from exc


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
    try:
        await league.reset(db, user_id=int(user["id"]))
    except league.LeagueError as exc:
        _fail(exc)
    return {"ok": True}
