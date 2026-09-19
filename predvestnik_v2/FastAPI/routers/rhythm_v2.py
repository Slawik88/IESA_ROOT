"""HTTP adapter for the new standalone endless Rune Rhythm."""
from __future__ import annotations

from typing import Literal

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from FastAPI.deps import get_db, require_tab_enabled, require_tg_user
from services import rhythm_v2 as game
from infrastructure.database import create_pool, get_pool
from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories import users as users_repo
from services.roles import DEVELOPER_GLOBAL_RANK


# The transport and fraud gate are intentionally unfinished; no authenticated
# user should be able to reach a world leaderboard merely by guessing its URL.
# A browser WebSocket cannot attach the HTTP-only x-init-data header.  Its
# first frame instead contains our short, one-use server ticket.  Keep feature
# + Telegram/session authentication on every HTTP writer/reader that issues
# that ticket; never apply that HTTP dependency to the ticket-authenticated WS.
router = APIRouter(prefix="/rhythm-v2", tags=["rhythm-v2"])
_feature_gate = Depends(require_tab_enabled("game_rhythm_v2"))


class StartBody(BaseModel):
    mode: Literal["normal", "augments"]


class SelectBody(BaseModel):
    positive: list[str] = Field(min_length=2, max_length=2)
    negative: list[str] = Field(min_length=2, max_length=2)


class TapBody(BaseModel):
    signal_no: int = Field(ge=1)
    rune: Literal["left", "center", "right"]
    action_id: str = Field(min_length=1, max_length=96)


class OfflineAction(BaseModel):
    signal_no: int = Field(ge=1)
    rune: Literal["left", "center", "right"] | None = None
    elapsed_ms: int = Field(ge=0, le=60_000)


class OfflineFinalizeBody(BaseModel):
    finalize_id: str = Field(min_length=1, max_length=96)
    actions: list[OfflineAction] = Field(min_length=1, max_length=game.OFFLINE_PACKET_SIGNALS)


class ReviewBody(BaseModel):
    review_id: str = Field(min_length=1, max_length=96)
    decision: Literal["clear", "quarantined"]
    reason: str = Field(min_length=8, max_length=500)


async def _require_integrity_reviewer(db, user_id: int) -> None:
    if int(await users_repo.get_global_rank(db, int(user_id)) or 0) < DEVELOPER_GLOBAL_RANK:
        raise HTTPException(403, "Только разработчик может проверять результаты Rhythm.")


def _raise(exc: game.RhythmError) -> None:
    status = 409 if isinstance(exc, game.RhythmConflict) else 400
    raise HTTPException(status, str(exc)) from exc


def _public(state: dict) -> dict:
    state = dict(state)
    state["rune"] = None
    return state


@router.post("/runs", dependencies=[_feature_gate])
async def start(body: StartBody, db=Depends(get_db), user=Depends(require_tg_user)):
    try:
        return _public(await game.start_run(db, user_id=int(user["id"]), mode=body.mode))
    except game.RhythmError as exc:
        _raise(exc)


@router.post("/runs/{run_id}/augmentations", dependencies=[_feature_gate])
async def select_augmentations(run_id: str, body: SelectBody, db=Depends(get_db), user=Depends(require_tg_user)):
    try:
        return _public(await game.choose_augmentations(db, user_id=int(user["id"]), run_id=run_id,
                                                       positive=body.positive, negative=body.negative))
    except game.RhythmError as exc:
        _raise(exc)


@router.post("/runs/{run_id}/cancel", dependencies=[_feature_gate])
async def cancel(run_id: str, db=Depends(get_db), user=Depends(require_tg_user)):
    try:
        return _public(await game.cancel_run(db, user_id=int(user["id"]), run_id=run_id))
    except game.RhythmError as exc:
        _raise(exc)


@router.get("/runs/{run_id}", dependencies=[_feature_gate])
async def current(run_id: str, db=Depends(get_db), user=Depends(require_tg_user)):
    try:
        return _public(await game.current_run(db, user_id=int(user["id"]), run_id=run_id))
    except game.RhythmError as exc:
        _raise(exc)


@router.post("/runs/{run_id}/offline-packet", dependencies=[_feature_gate])
async def offline_packet(run_id: str, db=Depends(get_db), user=Depends(require_tg_user)):
    try:
        return await game.offline_packet(db, user_id=int(user["id"]), run_id=run_id)
    except game.RhythmError as exc:
        _raise(exc)


@router.post("/runs/{run_id}/finalize", dependencies=[_feature_gate])
async def finalize_offline(run_id: str, body: OfflineFinalizeBody, db=Depends(get_db), user=Depends(require_tg_user)):
    try:
        return _public(await game.finalize_offline_run(
            db, user_id=int(user["id"]), run_id=run_id,
            actions=[item.model_dump() for item in body.actions], finalize_id=body.finalize_id,
        ))
    except game.RhythmError as exc:
        _raise(exc)


@router.post("/runs/{run_id}/transport-ticket", dependencies=[_feature_gate])
async def transport_ticket(run_id: str, db=Depends(get_db), user=Depends(require_tg_user)):
    try:
        return await game.issue_transport_ticket(db, user_id=int(user["id"]), run_id=run_id)
    except game.RhythmError as exc:
        _raise(exc)


@router.get("/leaderboard/{mode}", dependencies=[_feature_gate])
async def leaderboard(mode: Literal["normal", "augments"], db=Depends(get_db), user=Depends(require_tg_user)):
    try:
        return await game.rankings(db, user_id=int(user["id"]), mode=mode)
    except game.RhythmError as exc:
        _raise(exc)


@router.get("/integrity/reviews")
async def integrity_reviews(limit: int = 50, db=Depends(get_db), user=Depends(require_tg_user)):
    await _require_integrity_reviewer(db, int(user["id"]))
    try:
        return {"items": await game.pending_reviews(db, limit=limit)}
    except game.RhythmError as exc:
        _raise(exc)


@router.post("/integrity/reviews/{run_id}")
async def decide_integrity_review(
    run_id: str, body: ReviewBody, db=Depends(get_db), user=Depends(require_tg_user),
):
    await _require_integrity_reviewer(db, int(user["id"]))
    try:
        return await game.review_run(
            db, reviewer_id=int(user["id"]), run_id=run_id,
            review_id=body.review_id, decision=body.decision, reason=body.reason,
        )
    except game.RhythmError as exc:
        _raise(exc)


@router.websocket("/runs/{run_id}/live")
async def live_run(websocket: WebSocket, run_id: str):
    """Dedicated, ticket-authenticated channel; never accepts Telegram auth in URL."""
    await websocket.accept()
    user_id = lease = None
    try:
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=10)
        hello = json.loads(raw)
        if not isinstance(hello, dict) or hello.get("type") != "authenticate":
            raise game.RhythmConflict("Rhythm live connection needs a transport ticket")
        await create_pool()
        async with get_pool().acquire() as connection:
            db = PGAdapter(connection)
            user_id, lease, state = await game.connect_transport(db, run_id=run_id, ticket=str(hello.get("ticket", "")))
        await websocket.send_json({"type": "state", "state": state})
        while True:
            # A timeout re-evaluates server deadlines, so a disconnect/silent
            # client cannot pause a run.
            try:
                raw = await asyncio.wait_for(websocket.receive_text(), timeout=1.0)
            except asyncio.TimeoutError:
                await create_pool()
                async with get_pool().acquire() as connection:
                    state = await game.transport_state(PGAdapter(connection), user_id=user_id, run_id=run_id, lease=lease)
                await websocket.send_json({"type": "state", "state": state})
                if state["status"] != "active":
                    return
                continue
            if len(raw) > 512:
                raise game.RhythmConflict("Rhythm live payload is too large")
            event = json.loads(raw)
            if not isinstance(event, dict) or event.get("type") != "tap":
                raise game.RhythmConflict("unsupported Rhythm live action")
            await create_pool()
            async with get_pool().acquire() as connection:
                state = await game.transport_tap(PGAdapter(connection), user_id=user_id, run_id=run_id, lease=lease,
                                                 signal_no=int(event.get("signal_no", 0)), rune=str(event.get("rune", "")),
                                                 action_id=str(event.get("action_id", "")))
            await websocket.send_json({"type": "state", "state": state})
            if state["status"] != "active":
                return
    except (game.RhythmError, ValueError, json.JSONDecodeError):
        await websocket.close(code=1008)
    except WebSocketDisconnect:
        pass
    finally:
        if user_id is not None and lease:
            try:
                await create_pool()
                async with get_pool().acquire() as connection:
                    await game.release_transport(PGAdapter(connection), user_id=user_id, run_id=run_id, lease=lease)
            except Exception:
                pass
