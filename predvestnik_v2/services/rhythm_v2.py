"""Server-owned execution of the approved endless Rune Rhythm."""
from __future__ import annotations

from datetime import datetime, timedelta
import copy
import hashlib
import secrets
from uuid import uuid4

from asyncpg.exceptions import UniqueViolationError

from core import rhythm_v2 as rules
from core import seasons as season_rules
from infrastructure.repositories import rhythm_v2 as repo
from services import achievements_v1 as achievements
from services import game_seasons
from services import quests_v1 as quests


OFFLINE_PACKET_SIGNALS = 2_048


class RhythmError(Exception):
    pass


class RhythmConflict(RhythmError):
    pass


async def _record_completed_quest(db, *, user_id: int, run_id: str, mode: str, score: int,
                                  integrity_status: str, picks: int = 0) -> None:
    """Only independently timed terminal runs may advance progression."""
    if integrity_status != "clear":
        return
    event_id = f"rhythm:{run_id}"
    sources = await quests.available_sources(db, user_id=user_id)
    metrics = ["game_completed", "rhythm_completed", f"rhythm_{mode}_completed"]
    if picks > 0:
        # Quest id/metric keep their historical "augments" name so players'
        # already assigned quests stay valid; the gift draft is what counts now.
        metrics.append("rhythm_augments_completed")
    for metric in metrics:
        await quests.record_metric(db, user_id=user_id, metric=metric, event_id=event_id,
                                   vip_active=False, sources=sources)
    if int(score) >= 500:
        await quests.record_metric(db, user_id=user_id, metric="rhythm_score_500", event_id=event_id,
                                   vip_active=False, sources=sources)
    await achievements.record_terminal(
        db, user_id=user_id, metric="rhythm_completed", source_event_id=run_id,
        source_snapshot={"run_id": run_id},
    )


async def _settle_finished_run(db, *, row: dict, state: dict, user_id: int,
                              integrity_status: str, integrity_reason: str,
                              integrity_evidence: dict) -> str:
    """Set integrity before every leaderboard or progression writer."""
    await repo.set_integrity(
        db, run_id=row["run_id"], status=integrity_status,
        reason=integrity_reason, evidence=integrity_evidence,
    )
    verdict = await repo.integrity_status(db, run_id=row["run_id"])
    row["integrity_status"] = verdict
    row["integrity_reason"] = integrity_reason
    if verdict == "clear":
        await repo.upsert_leaderboard(
            db, run_id=row["run_id"], user_id=user_id, mode=row["mode"],
            ruleset_version=row["ruleset_version"], score=state["score"],
        )
    await _record_completed_quest(
        db, user_id=user_id, run_id=row["run_id"], mode=str(row["mode"]), score=int(state["score"]),
        integrity_status=verdict, picks=len(state["selected"]),
    )
    return verdict


def _state(row: dict) -> dict:
    return {
        "status": row["status"], "selected": list(repo.load(row["selected_json"]) or []),
        "perks": rules.normalize_perks(repo.load(row.get("perk_state_json"))),
        "health": int(row["health"]), "score": int(row["score"]), "combo": int(row["combo"]),
        "correct_streak": int(row["correct_streak"]), "correct_taps": int(row["correct_taps"]),
        "mistakes": int(row["mistakes"]), "next_signal_no": int(row["next_signal_no"]),
        "signal_opened_at": row["signal_opened_at"], "finished_at": row["finished_at"],
    }


def _draft_pending(state: dict) -> bool:
    return state["status"] == "active" and rules.draft_pending(
        next_signal_no=state["next_signal_no"], picks=len(state["selected"]),
    )


def _draft(row: dict, state: dict) -> dict | None:
    """The gifts on offer while the run is paused between two chunks."""
    if not _draft_pending(state):
        return None
    number = len(state["selected"]) + 1
    offers = rules.perk_offers(bytes(row["seed"]), number, health=state["health"], perks=state["perks"])
    return {"number": number, "offers": [
        {"id": item.id, "kind": item.kind, "name": item.name, "bonus": item.bonus, "cost": item.cost}
        for item in map(rules.perk, offers)
    ]}


def _hold_for_draft(state: dict) -> None:
    """The clock never runs while a gift is owed: reconnects cannot start it."""
    if _draft_pending(state):
        state["signal_opened_at"] = None


def _view(row: dict, state: dict, *, now: datetime) -> dict:
    selected = state["selected"]
    signal_no = state["next_signal_no"]
    active = state["status"] == "active"
    window_ms = rules.window_ms(signal_no, state["perks"])
    opened_at = state["signal_opened_at"]
    remaining_ms = window_ms
    starts_in_ms = 0
    if active and opened_at is not None:
        # A signal may be scheduled slightly ahead (breathing room after a gift).
        starts_in_ms = max(0, int((opened_at - now).total_seconds() * 1000))
        remaining_ms = max(0, window_ms - max(0, int((now - opened_at).total_seconds() * 1000)))
    return {
        "run_id": row["run_id"], "mode": row["mode"], "ruleset_version": row["ruleset_version"],
        "status": state["status"], "health": state["health"], "score": state["score"],
        "combo": state["combo"], "correct_taps": state["correct_taps"], "mistakes": state["mistakes"],
        "next_signal_no": signal_no, "chunk": rules.chunk_for_signal(signal_no),
        "speed_percent": rules.speed_percent(signal_no, state["perks"]),
        "window_ms": window_ms, "remaining_ms": remaining_ms,
        # The expected rune is delivered only for the current signal.  The seed
        # and all future sequence values stay server-side.
        "rune": rules.expected_rune(bytes(row["seed"]), signal_no) if active and opened_at and not _draft_pending(state) else None,
        "draft": _draft(row, state),
        "perks": state["perks"], "selected_perks": selected, "gifts": rules.owned_gifts(state["perks"]),
        "starts_in_ms": starts_in_ms,
        "integrity_status": str(row.get("integrity_status") or "legacy_unverified"),
        "server_time": now.isoformat(),
    }


def _finish(row: dict, state: dict, now: datetime) -> None:
    state["status"] = "finished"
    state["finished_at"] = now
    state["signal_opened_at"] = None


def _cancel(state: dict, now: datetime) -> None:
    """An abandoned run has no score, leaderboard entry or economic result."""
    state["status"] = "cancelled"
    state["finished_at"] = now
    state["signal_opened_at"] = None


def _resolve_error(row: dict, state: dict, *, now: datetime, timed_out: bool) -> None:
    state["health"], state["perks"] = rules.after_error(
        health=state["health"], perks=state["perks"], timed_out=timed_out,
    )
    state["combo"] = 0
    state["mistakes"] += 1
    state["correct_streak"] = 0
    state["next_signal_no"] += 1
    if state["health"] == 0:
        _finish(row, state, now)


def _advance_expired(row: dict, state: dict, *, now: datetime) -> None:
    """A disconnected client cannot freeze a run's difficulty indefinitely."""
    while state["status"] == "active":
        _hold_for_draft(state)
        opened = state["signal_opened_at"]
        # A run exists before its first ticketed live connection.  There is no
        # deadline to advance until the server has opened that first signal.
        if opened is None:
            return
        window = rules.window_ms(state["next_signal_no"], state["perks"])
        deadline = opened + timedelta(milliseconds=window)
        if now <= deadline:
            return
        # Preserve the real schedule rather than resetting it to reconnect time.
        _resolve_error(row, state, now=now, timed_out=True)
        if state["status"] == "active":
            state["signal_opened_at"] = deadline + timedelta(milliseconds=rules.NEXT_SIGNAL_LEAD_MS)


async def start_run(db, *, user_id: int, mode: rules.Mode) -> dict:
    if mode not in ("normal", "augments"):
        raise RhythmError("unknown rhythm mode")
    await repo.ensure_tables(db)
    run_id, seed = str(uuid4()), secrets.token_bytes(32)
    # One ranked mode.  "augments" survives only so that an already open
    # Mini App tab can still start a run; gifts now come during the run.
    mode, state, offers = "normal", "active", {}
    health = rules.initial_health()
    try:
        # The nested transaction is a savepoint when a caller already owns a
        # transaction.  A duplicate-open-run race therefore fails closed
        # without aborting unrelated work on that connection.
        async with db.connection.transaction():
            async with db.execute(
                "SELECT *,CLOCK_TIMESTAMP() AS server_now FROM rhythm_v2_runs "
                "WHERE user_id=? AND status IN ('choosing','active') FOR UPDATE",
                (int(user_id),),
            ) as cursor:
                existing = await cursor.fetchone()
            if existing:
                # A deliberate new start abandons the earlier open run.  It is
                # not a loss and is never written to the leaderboard.
                row = dict(existing)
                existing_state = _state(row)
                _cancel(existing_state, row["server_now"])
                await repo.update_run(db, run_id=row["run_id"], state=existing_state)
            await db.execute(
                "INSERT INTO rhythm_v2_runs(run_id,user_id,mode,ruleset_version,seed,offers_json,status,health,signal_opened_at) "
                "VALUES (?,?,?,?,?,?::jsonb,?,?,NULL)",
                (run_id, int(user_id), mode, rules.RULESET_VERSION, seed, repo.dumps(offers), state, health),
            )
    except UniqueViolationError as exc:
        # The partial unique index is intentional: a player must resume/finish
        # the same server run, not open parallel tabs until a favourable seed.
        raise RhythmConflict("finish or resume the current Rhythm run first") from exc
    async with db.execute("SELECT *,CLOCK_TIMESTAMP() AS server_now FROM rhythm_v2_runs WHERE run_id=?", (run_id,)) as cursor:
        row = dict(await cursor.fetchone())
    return _view(row, _state(row), now=row["server_now"])


async def cancel_run(db, *, user_id: int, run_id: str) -> dict:
    """Cancel only the caller's open run; cancelled runs never settle rewards."""
    async with db.connection.transaction():
        row = await repo.lock_owned_run(db, run_id=run_id, user_id=user_id)
        if not row:
            raise RhythmConflict("Rhythm run was not found")
        state = _state(row)
        if state["status"] in {"active", "choosing"}:
            _cancel(state, row["server_now"])
            await repo.update_run(db, run_id=run_id, state=state)
        return _view(row, state, now=row["server_now"])


async def pick_perk(db, *, user_id: int, run_id: str, perk_id: str, action_id: str) -> dict:
    """Take one of the three offered rune gifts and restart the paused clock."""
    if not action_id or len(action_id) > 96:
        raise RhythmError("invalid rune gift pick")
    request = {"perk": str(perk_id)}
    async with db.connection.transaction():
        row = await repo.lock_owned_run(db, run_id=run_id, user_id=user_id)
        if not row:
            raise RhythmConflict("Rhythm run was not found")
        recorded = await repo.get_action(db, run_id=run_id, action_id=action_id)
        if recorded:
            if repo.load(recorded["request_json"]) != request:
                raise RhythmConflict("action id was already used with another pick")
            response = repo.load(recorded["result_json"])
            response["idempotent_replay"] = True
            return response
        state, now = _state(row), row["server_now"]
        # No expiry here: while a gift is owed the clock is paused, so there is
        # nothing to expire and the pick can never finish (and so strand) a run.
        draft = _draft(row, state)
        if not draft:
            raise RhythmConflict("no rune gift is on offer")
        if perk_id not in {item["id"] for item in draft["offers"]}:
            raise RhythmConflict("this rune gift was not offered")
        state["health"], state["perks"] = rules.apply_perk(perk_id, health=state["health"], perks=state["perks"])
        state["selected"].append(perk_id)
        # Breathing room: the next signal opens a few seconds from now.
        state["signal_opened_at"] = now + timedelta(milliseconds=rules.RESUME_LEAD_MS)
        _hold_for_draft(state)  # a second gift may be owed after a very long pause
        await repo.update_run(db, run_id=run_id, state=state)
        response = _view(row, state, now=now)
        await repo.insert_action(db, run_id=run_id, action_id=action_id, request=request, result=response)
        return response


async def offline_packet(db, *, user_id: int, run_id: str) -> dict:
    """Give the Mini App a buffered, server-derived signal sequence.

    Gameplay remains completely local until the player loses.  Delivering the
    complete packet marks the run as client-timed, so it can never later enter
    a trusted ranking or progression path.
    """
    async with db.connection.transaction():
        row = await repo.lock_owned_run(db, run_id=run_id, user_id=user_id)
        if not row or row["status"] != "active":
            raise RhythmConflict("only an active Rhythm run can load a packet")
        state = _state(row)
        if state["next_signal_no"] != 1 or state["signal_opened_at"] is not None:
            raise RhythmConflict("this Rhythm run is not an offline run")
        await repo.set_integrity(
            db, run_id=row["run_id"], status="offline_exposed",
            reason="client_timed_journal", evidence={"packet_signals": OFFLINE_PACKET_SIGNALS},
        )
        start = 1
        end = start + OFFLINE_PACKET_SIGNALS
        seed = bytes(row["seed"])
        return {
            "run_id": row["run_id"], "ruleset_version": row["ruleset_version"],
            "start_signal_no": start,
            "runes": [rules.expected_rune(seed, number) for number in range(start, end)],
            "windows_ms": [rules.window_ms(number, state["perks"]) for number in range(start, end)],
            "speed_percent": [rules.speed_percent(number) for number in range(start, end)],
            # Rune gifts need the live server clock, so an offline run has none.
            "rules": {"initial_health": rules.initial_health()},
        }


async def finalize_offline_run(db, *, user_id: int, run_id: str, actions: list[dict], finalize_id: str) -> dict:
    """Atomically replay the local action journal; client totals are ignored."""
    if not finalize_id or len(finalize_id) > 96 or not actions or len(actions) > OFFLINE_PACKET_SIGNALS:
        raise RhythmError("invalid offline Rhythm result")
    normalized: list[dict] = []
    for number, action in enumerate(actions, start=1):
        rune = action.get("rune")
        elapsed = action.get("elapsed_ms")
        if action.get("signal_no") != number or rune not in {*rules.RUNES, None} or not isinstance(elapsed, int) or elapsed < 0 or elapsed > 60_000:
            raise RhythmError("invalid offline Rhythm action")
        normalized.append({"signal_no": number, "rune": rune, "elapsed_ms": elapsed})
    request = {"actions": normalized}
    async with db.connection.transaction():
        row = await repo.lock_owned_run(db, run_id=run_id, user_id=user_id)
        if not row:
            raise RhythmConflict("Rhythm run was not found")
        recorded = await repo.get_action(db, run_id=run_id, action_id=finalize_id)
        if recorded:
            if repo.load(recorded["request_json"]) != request:
                raise RhythmConflict("finalize id was already used with another result")
            response = repo.load(recorded["result_json"]); response["idempotent_replay"] = True
            return response
        state, now = _state(row), row["server_now"]
        if state["status"] != "active" or state["next_signal_no"] != 1 or state["signal_opened_at"] is not None:
            raise RhythmConflict("this Rhythm run cannot accept an offline result")
        for action in normalized:
            expected = rules.expected_rune(bytes(row["seed"]), state["next_signal_no"])
            window = rules.window_ms(state["next_signal_no"], state["perks"])
            if action["rune"] == expected and action["elapsed_ms"] <= window:
                state["score"] += rules.score_for_correct(elapsed_ms=action["elapsed_ms"], allowed_window_ms=window, combo_before=state["combo"], perks=state["perks"])
                state["combo"] += 1; state["correct_streak"] += 1; state["correct_taps"] += 1; state["next_signal_no"] += 1
            else:
                _resolve_error(row, state, now=now, timed_out=action["rune"] is None or action["elapsed_ms"] > window)
            if state["status"] == "finished":
                if action is not normalized[-1]:
                    raise RhythmError("offline Rhythm journal continues after defeat")
                break
        if state["status"] != "finished":
            raise RhythmConflict("offline Rhythm result must end after defeat")
        await repo.update_run(db, run_id=run_id, state=state)
        integrity = await _settle_finished_run(
            db, row=row, state=state, user_id=user_id,
            integrity_status="quarantined", integrity_reason="client_timed_journal",
            integrity_evidence={"journal_actions": len(normalized), "packet_signals": OFFLINE_PACKET_SIGNALS},
        )
        response = _view(row, state, now=now)
        response["integrity_status"] = integrity
        await repo.insert_action(db, run_id=run_id, action_id=finalize_id, request=request, result=response)
        return response


async def tap(db, *, user_id: int, run_id: str, signal_no: int, rune: str,
              action_id: str, trusted_transport: bool = False) -> dict:
    if rune not in rules.RUNES or signal_no < 1 or not action_id or len(action_id) > 96:
        raise RhythmError("invalid rhythm tap")
    request = {"signal_no": int(signal_no), "rune": rune}
    async with db.connection.transaction():
        row = await repo.lock_owned_run(db, run_id=run_id, user_id=user_id)
        if not row:
            raise RhythmConflict("Rhythm run was not found")
        recorded = await repo.get_action(db, run_id=run_id, action_id=action_id)
        if recorded:
            if repo.load(recorded["request_json"]) != request:
                raise RhythmConflict("action id was already used with another tap")
            response = repo.load(recorded["result_json"])
            response["idempotent_replay"] = True
            return response
        state, now = _state(row), row["server_now"]
        if state["status"] != "active":
            raise RhythmConflict("Rhythm run is not active")
        _advance_expired(row, state, now=now)
        if state["status"] == "finished":
            await repo.update_run(db, run_id=run_id, state=state)
            integrity = await _settle_finished_run(
                db, row=row, state=state, user_id=user_id,
                integrity_status="clear" if trusted_transport else "review_required",
                integrity_reason="server_timed_transport" if trusted_transport else "server_timed_transport_pending_review",
                integrity_evidence={"terminal_signal": state["next_signal_no"], "mistakes": state["mistakes"], "transport_authenticated": trusted_transport},
            )
            response = _view(row, state, now=now)
            response["integrity_status"] = integrity
            await repo.insert_action(db, run_id=run_id, action_id=action_id, request=request, result=response)
            return response
        if _draft_pending(state):
            await repo.update_run(db, run_id=run_id, state=state)
            raise RhythmConflict("choose a rune gift before the next signal")
        if signal_no != state["next_signal_no"]:
            raise RhythmConflict("stale or future rhythm signal")
        if state["signal_opened_at"] is not None and now < state["signal_opened_at"]:
            raise RhythmConflict("the next signal has not opened yet")
        elapsed_ms = max(0, int((now - state["signal_opened_at"]).total_seconds() * 1000))
        window = rules.window_ms(signal_no, state["perks"])
        correct = rune == rules.expected_rune(bytes(row["seed"]), signal_no) and elapsed_ms <= window
        if correct:
            state["score"] += rules.score_for_correct(elapsed_ms=elapsed_ms, allowed_window_ms=window, combo_before=state["combo"], perks=state["perks"])
            state["combo"] += 1
            state["correct_streak"] += 1
            state["health"], state["perks"] = rules.after_correct(
                state["perks"], health=state["health"], streak_after=state["correct_streak"])
            state["correct_taps"] += 1
            state["next_signal_no"] += 1
        else:
            _resolve_error(row, state, now=now, timed_out=rune == rules.expected_rune(bytes(row["seed"]), signal_no))
        if state["status"] == "active":
            # The window opens slightly ahead so the answer's network trip and the
            # DB write do not eat the player's reaction time.
            state["signal_opened_at"] = now + timedelta(milliseconds=rules.NEXT_SIGNAL_LEAD_MS)
            _hold_for_draft(state)
        else:
            await repo.update_run(db, run_id=run_id, state=state)
            integrity = await _settle_finished_run(
                db, row=row, state=state, user_id=user_id,
                integrity_status="clear" if trusted_transport else "review_required",
                integrity_reason="server_timed_transport" if trusted_transport else "server_timed_transport_pending_review",
                integrity_evidence={"terminal_signal": state["next_signal_no"], "mistakes": state["mistakes"], "transport_authenticated": trusted_transport},
            )
        await repo.update_run(db, run_id=run_id, state=state)
        response = _view(row, state, now=now)
        response["server_elapsed_ms"] = elapsed_ms
        if state["status"] == "finished":
            response["integrity_status"] = integrity
        await repo.insert_action(db, run_id=run_id, action_id=action_id, request=request, result=response)
        return response


async def current_run(db, *, user_id: int, run_id: str) -> dict:
    async with db.connection.transaction():
        row = await repo.lock_owned_run(db, run_id=run_id, user_id=user_id)
        if not row:
            raise RhythmConflict("Rhythm run was not found")
        state, now = _state(row), row["server_now"]
        if state["status"] == "active":
            before = dict(state, selected=list(state["selected"]), perks=copy.deepcopy(state["perks"]))
            _advance_expired(row, state, now=now)
            if state["status"] == "finished":
                await repo.update_run(db, run_id=run_id, state=state)
                await _settle_finished_run(
                    db, row=row, state=state, user_id=user_id,
                    integrity_status="review_required", integrity_reason="server_timed_transport_pending_review",
                    integrity_evidence={"terminal_signal": state["next_signal_no"], "mistakes": state["mistakes"]},
                )
            if state != before:  # an idle tick must not lock-write the row under the player's next tap
                await repo.update_run(db, run_id=run_id, state=state)
        return _view(row, state, now=now)


async def rankings(db, *, user_id: int, mode: rules.Mode) -> dict:
    if mode not in ("normal", "augments"):
        raise RhythmError("unknown rhythm mode")
    await repo.ensure_tables(db)
    promoted = await repo.promote_authenticated_transport_reviews(db)
    for row in promoted:
        await repo.upsert_leaderboard(
            db, run_id=row["run_id"], user_id=int(row["user_id"]), mode=str(row["mode"]),
            ruleset_version=str(row["ruleset_version"]), score=int(row["score"]),
        )
        await _record_completed_quest(
            db, user_id=int(row["user_id"]), run_id=str(row["run_id"]),
            mode=str(row["mode"]), score=int(row["score"]), integrity_status="clear",
            picks=len(repo.load(row.get("selected_json")) or []),
        )
    # One ranked board; "augments" is only a legacy alias of it.
    mode = "normal"

    async def standings(db_, start, end):
        return await repo.season_standings(db_, mode=mode, starts_at=start, ends_at=end)

    await game_seasons.settle_due(db, game="rhythm", board=mode, standings=standings)
    season = game_seasons.season_view()
    start, end = season_rules.season_bounds(season["number"])
    board = await repo.leaderboard(db, user_id=user_id, mode=mode, starts_at=start, ends_at=end)
    board["season"] = season
    board["last_season"] = await game_seasons.last_result(db, game="rhythm", board=mode, user_id=user_id)
    return board


def _ticket_hash(ticket: str) -> str:
    return hashlib.sha256(ticket.encode()).hexdigest()


async def issue_transport_ticket(db, *, user_id: int, run_id: str) -> dict:
    """REST auth mints a short opaque ticket; no long-lived auth enters WS URLs."""
    async with db.connection.transaction():
        row = await repo.lock_owned_run(db, run_id=run_id, user_id=user_id)
        if not row or row["status"] != "active":
            raise RhythmConflict("only an active owned Rhythm run can connect")
        if str(row.get("integrity_status") or "legacy_unverified") != "pending":
            raise RhythmConflict("a client-timed Rhythm run cannot enter the trusted transport")
        ticket = secrets.token_urlsafe(32)
        await repo.store_transport_ticket(db, ticket_hash=_ticket_hash(ticket), run_id=run_id, user_id=user_id)
    return {"ticket": ticket, "expires_in_seconds": 60}


async def connect_transport(db, *, run_id: str, ticket: str) -> tuple[int, str, dict]:
    if not ticket or len(ticket) > 128:
        raise RhythmConflict("invalid Rhythm transport ticket")
    lease = secrets.token_urlsafe(24)
    row = await repo.consume_transport_ticket(db, ticket_hash=_ticket_hash(ticket), run_id=run_id, lease=lease)
    if not row:
        raise RhythmConflict("expired, replayed or competing Rhythm transport ticket")
    user_id = int(row["user_id"])
    # The current rune is intentionally returned only after the ticket is used.
    view = await transport_state(db, user_id=user_id, run_id=run_id, lease=lease)
    return user_id, lease, view


async def transport_state(db, *, user_id: int, run_id: str, lease: str) -> dict:
    async with db.connection.transaction():
        row = await repo.lock_owned_run(db, run_id=run_id, user_id=user_id)
        if not row or not await repo.extend_transport_lease(db, run_id=run_id, user_id=user_id, lease=lease):
            raise RhythmConflict("Rhythm live connection is no longer valid")
        state, now = _state(row), row["server_now"]
        if state["status"] == "active":
            before = dict(state, selected=list(state["selected"]), perks=copy.deepcopy(state["perks"]))
            _advance_expired(row, state, now=now)
            if state["status"] == "finished":
                await repo.update_run(db, run_id=run_id, state=state)
                await _settle_finished_run(
                    db, row=row, state=state, user_id=user_id,
                    integrity_status="clear", integrity_reason="server_timed_transport",
                    integrity_evidence={"terminal_signal": state["next_signal_no"], "mistakes": state["mistakes"], "transport_authenticated": True},
                )
            if state != before:  # an idle tick must not lock-write the row under the player's next tap
                await repo.update_run(db, run_id=run_id, state=state)
        return _view(row, state, now=now)


async def release_transport(db, *, user_id: int, run_id: str, lease: str) -> None:
    await repo.release_transport_lease(db, run_id=run_id, user_id=user_id, lease=lease)


async def transport_tap(db, *, user_id: int, run_id: str, lease: str, signal_no: int,
                        rune: str, action_id: str) -> dict:
    if not await repo.extend_transport_lease(db, run_id=run_id, user_id=user_id, lease=lease):
        raise RhythmConflict("Rhythm live connection is no longer valid")
    return await tap(db, user_id=user_id, run_id=run_id, signal_no=signal_no, rune=rune, action_id=action_id, trusted_transport=True)


async def transport_pick(db, *, user_id: int, run_id: str, lease: str, perk_id: str, action_id: str) -> dict:
    if not await repo.extend_transport_lease(db, run_id=run_id, user_id=user_id, lease=lease):
        raise RhythmConflict("Rhythm live connection is no longer valid")
    return await pick_perk(db, user_id=user_id, run_id=run_id, perk_id=perk_id, action_id=action_id)


async def pending_reviews(db, *, limit: int = 50) -> list[dict]:
    if not 1 <= int(limit) <= 100:
        raise RhythmError("invalid review page size")
    await repo.ensure_tables(db)
    rows = await repo.pending_integrity_reviews(db, limit=int(limit))
    for row in rows:
        row["timing_ms"] = list(repo.load(row.get("timing_ms")) or [])
        row["integrity_evidence"] = dict(repo.load(row.get("integrity_evidence")) or {})
    return rows


async def review_run(db, *, reviewer_id: int, run_id: str, review_id: str,
                     decision: str, reason: str) -> dict:
    """One audited reviewer decision unlocks or quarantines a terminal run."""
    review_id, reason = str(review_id or "").strip(), str(reason or "").strip()
    if decision not in {"clear", "quarantined"} or not review_id or len(review_id) > 96:
        raise RhythmError("invalid Rhythm integrity review")
    if len(reason) < 8 or len(reason) > 500:
        raise RhythmError("review reason must contain 8-500 characters")
    await repo.ensure_tables(db)
    request = {"run_id": str(run_id), "decision": decision, "reason": reason}
    async with db.connection.transaction():
        # The review id is global. Serialize on it before the replay lookup so
        # identical concurrent retries become a replay and cross-run reuse is
        # a controlled conflict, never a unique-constraint HTTP 500.
        await repo.lock_integrity_review_id(db, review_id=review_id)
        replay = await repo.integrity_review(db, review_id=review_id)
        if replay:
            recorded = {
                "run_id": str(replay["run_id"]),
                "decision": str(replay["decision"]),
                "reason": str(replay["reason"]),
            }
            if recorded != request or int(replay["reviewer_id"]) != int(reviewer_id):
                raise RhythmConflict("review_id is already bound to another decision")
            row = await repo.lock_run(db, run_id=run_id)
            return {**_view(row, _state(row), now=row["server_now"]), "idempotent_replay": True}
        row = await repo.lock_run(db, run_id=run_id)
        if not row or row["status"] != "finished" or row["integrity_status"] != "review_required":
            raise RhythmConflict("Rhythm run is not awaiting review")
        evidence = {
            "score": int(row["score"]), "correct_taps": int(row["correct_taps"]),
            "mistakes": int(row["mistakes"]), "previous_reason": str(row.get("integrity_reason") or ""),
        }
        await repo.insert_integrity_review(
            db, review_id=review_id, run_id=run_id, reviewer_id=reviewer_id,
            decision=decision, reason=reason, evidence=evidence,
        )
        if not await repo.apply_integrity_review(db, run_id=run_id, decision=decision, reason=reason):
            raise RhythmConflict("Rhythm review lost its state race")
        row["integrity_status"] = decision
        row["integrity_reason"] = f"manual_review:{reason}"
        if decision == "clear":
            await repo.upsert_leaderboard(
                db, run_id=run_id, user_id=int(row["user_id"]), mode=str(row["mode"]),
                ruleset_version=str(row["ruleset_version"]), score=int(row["score"]),
            )
            await _record_completed_quest(
                db, user_id=int(row["user_id"]), run_id=run_id, mode=str(row["mode"]),
                score=int(row["score"]), integrity_status="clear",
                picks=len(repo.load(row.get("selected_json")) or []),
            )
        return _view(row, _state(row), now=row["server_now"])
