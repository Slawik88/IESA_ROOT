#!/usr/bin/env python3
"""Real PostgreSQL proof for Rune Rhythm state, replay and leaderboard rules."""
from __future__ import annotations

import argparse
import asyncio
from urllib.parse import urlparse

import asyncpg

from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories import achievements_v1 as achievements_repo
from infrastructure.repositories import economy_ledger
from services import rhythm_v2 as rhythm


def local_dsn(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"postgres", "postgresql"} or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise argparse.ArgumentTypeError("only a loopback PostgreSQL DSN is allowed")
    return value


def wrong_rune(expected: str) -> str:
    return next(rune for rune in ("left", "center", "right") if rune != expected)


async def run(dsn: str) -> None:
    connection = await asyncpg.connect(dsn)
    db = PGAdapter(connection)
    await achievements_repo.ensure_tables(db)
    await economy_ledger.ensure_tables(db)
    transaction = connection.transaction()
    await transaction.start()
    try:
        normal = await rhythm.start_run(db, user_id=975001, mode="normal")
        assert normal["status"] == "active" and normal["rune"] is None
        replacement = await rhythm.start_run(db, user_id=975001, mode="normal")
        assert replacement["run_id"] != normal["run_id"] and replacement["status"] == "active"
        abandoned = await rhythm.current_run(db, user_id=975001, run_id=normal["run_id"])
        assert abandoned["status"] == "cancelled"
        normal = replacement

        normal_ticket = await rhythm.issue_transport_ticket(db, user_id=975001, run_id=normal["run_id"])
        _, normal_lease, normal = await rhythm.connect_transport(db, run_id=normal["run_id"], ticket=normal_ticket["ticket"])
        assert normal["rune"] in {"left", "center", "right"}
        first_rune = normal["rune"]
        first = await rhythm.transport_tap(db, user_id=975001, run_id=normal["run_id"], lease=normal_lease, signal_no=1,
                                 rune=first_rune, action_id="first-tap")
        assert first["next_signal_no"] == 2, first
        # A transport reconnect must continue the same server-owned run;
        # releasing its old lease may never reset time, sequence or score.
        await rhythm.release_transport(db, user_id=975001, run_id=normal["run_id"], lease=normal_lease)
        reconnect_ticket = await rhythm.issue_transport_ticket(db, user_id=975001, run_id=normal["run_id"])
        _, normal_lease, normal = await rhythm.connect_transport(db, run_id=normal["run_id"], ticket=reconnect_ticket["ticket"])
        assert normal["next_signal_no"] == first["next_signal_no"] and normal["score"] == first["score"]
        replay = await rhythm.transport_tap(db, user_id=975001, run_id=normal["run_id"], lease=normal_lease, signal_no=1,
                                  rune=first_rune, action_id="first-tap")
        assert replay["idempotent_replay"] and replay["score"] == first["score"]
        try:
            await rhythm.transport_tap(db, user_id=975001, run_id=normal["run_id"], lease=normal_lease, signal_no=2,
                             rune="left", action_id="first-tap")
        except rhythm.RhythmConflict:
            pass
        else:
            raise AssertionError("same action id with a different tap must fail")

        state = first
        for attempt in range(rhythm.rules.initial_health()):
            state = await rhythm.transport_tap(db, user_id=975001, run_id=normal["run_id"], lease=normal_lease,
                                     signal_no=state["next_signal_no"], rune=wrong_rune(state["rune"]),
                                     action_id=f"wrong-{attempt}")
            if state["status"] == "finished":
                break
        assert state["status"] == "finished" and state["health"] == 0
        assert state["integrity_status"] == "clear"
        async with db.execute("SELECT COUNT(*) FROM quest_v1_metric_receipts WHERE user_id=? AND metric='rhythm_completed' AND event_id=?", (975001, f"rhythm:{normal['run_id']}")) as cursor:
            assert (await cursor.fetchone())[0] == 1, "trusted transport must advance quests"
        async with db.execute("SELECT COUNT(*) FROM achievement_v1_metric_receipts WHERE user_id=? AND source_event_id=?", (975001, normal["run_id"])) as cursor:
            assert (await cursor.fetchone())[0] == 1, "trusted transport must advance achievements"
        async with db.execute("SELECT metric FROM quest_v1_metric_receipts WHERE user_id=? AND event_id=? ORDER BY metric", (975001, f"rhythm:{normal['run_id']}")) as cursor:
            assert [row[0] for row in await cursor.fetchall()] == ['game_completed', 'rhythm_completed', 'rhythm_normal_completed']
        ranking = await rhythm.rankings(db, user_id=975001, mode="normal")
        assert ranking["personal"] and ranking["personal"]["best_score"] == first["score"]
        assert all("user_id" not in row for row in ranking["top"]), "public leaderboard DTO must not expose raw user ids"

        scorer = await rhythm.start_run(db, user_id=975008, mode="normal")
        scorer_ticket = await rhythm.issue_transport_ticket(db, user_id=975008, run_id=scorer["run_id"])
        _, scorer_lease, scorer = await rhythm.connect_transport(db, run_id=scorer["run_id"], ticket=scorer_ticket["ticket"])
        for number in range(5):
            scorer = await rhythm.transport_tap(
                db, user_id=975008, run_id=scorer["run_id"], lease=scorer_lease,
                signal_no=scorer["next_signal_no"], rune=scorer["rune"], action_id=f"score-correct-{number}",
            )
        for number in range(rhythm.rules.initial_health()):
            scorer = await rhythm.transport_tap(
                db, user_id=975008, run_id=scorer["run_id"], lease=scorer_lease,
                signal_no=scorer["next_signal_no"], rune=wrong_rune(scorer["rune"]), action_id=f"score-wrong-{number}",
            )
            if scorer["status"] == "finished":
                break
        assert scorer["score"] >= 500 and scorer["status"] == "finished"
        async with db.execute("SELECT COUNT(*) FROM quest_v1_metric_receipts WHERE user_id=? AND metric='rhythm_score_500' AND event_id=?", (975008, f"rhythm:{scorer['run_id']}")) as cursor:
            assert (await cursor.fetchone())[0] == 1

        zero = await rhythm.start_run(db, user_id=975004, mode="normal")
        zero_ticket = await rhythm.issue_transport_ticket(db, user_id=975004, run_id=zero["run_id"])
        _, zero_lease, zero = await rhythm.connect_transport(db, run_id=zero["run_id"], ticket=zero_ticket["ticket"])
        for attempt in range(rhythm.rules.initial_health()):
            zero = await rhythm.transport_tap(db, user_id=975004, run_id=zero["run_id"], lease=zero_lease,
                                              signal_no=zero["next_signal_no"], rune=wrong_rune(zero["rune"]),
                                              action_id=f"zero-{attempt}")
            if zero["status"] == "finished":
                break
        assert zero["status"] == "finished" and zero["score"] == 0
        assert zero["integrity_status"] == "clear"
        assert (await rhythm.rankings(db, user_id=975004, mode="normal"))["personal"] is None

        offline = await rhythm.start_run(db, user_id=975005, mode="normal")
        packet = await rhythm.offline_packet(db, user_id=975005, run_id=offline["run_id"])
        assert len(packet["runes"]) == rhythm.OFFLINE_PACKET_SIGNALS and packet["windows_ms"][0] == rhythm.rules.BASE_WINDOW_MS
        try:
            await rhythm.issue_transport_ticket(db, user_id=975005, run_id=offline["run_id"])
        except rhythm.RhythmConflict:
            pass
        else:
            raise AssertionError("an offline-exposed run must not switch into trusted transport")
        try:
            await rhythm.offline_packet(db, user_id=975003, run_id=offline["run_id"])
        except rhythm.RhythmConflict:
            pass
        else:
            raise AssertionError("foreign user must not read an offline packet")
        incomplete = [{"signal_no": 1, "rune": wrong_rune(packet["runes"][0]), "elapsed_ms": 10}]
        try:
            await rhythm.finalize_offline_run(db, user_id=975005, run_id=offline["run_id"], actions=incomplete, finalize_id="offline-incomplete")
        except rhythm.RhythmConflict:
            pass
        else:
            raise AssertionError("offline result must not finish before defeat")
        journal = [
            {"signal_no": number, "rune": wrong_rune(packet["runes"][number - 1]), "elapsed_ms": 10}
            for number in range(1, rhythm.rules.initial_health() + 1)
        ]
        offline_final = await rhythm.finalize_offline_run(db, user_id=975005, run_id=offline["run_id"], actions=journal, finalize_id="offline-finalize")
        assert offline_final["status"] == "finished" and offline_final["score"] == 0
        offline_replay = await rhythm.finalize_offline_run(db, user_id=975005, run_id=offline["run_id"], actions=journal, finalize_id="offline-finalize")
        assert offline_replay["idempotent_replay"]
        try:
            await rhythm.finalize_offline_run(db, user_id=975005, run_id=offline["run_id"], actions=journal[:-1] + [dict(journal[-1], elapsed_ms=11)], finalize_id="offline-finalize")
        except rhythm.RhythmConflict:
            pass
        else:
            raise AssertionError("offline finalize id must bind its journal")

        overlong = await rhythm.start_run(db, user_id=975006, mode="normal")
        overlong_packet = await rhythm.offline_packet(db, user_id=975006, run_id=overlong["run_id"])
        impossible_journal = [
            {"signal_no": number, "rune": wrong_rune(overlong_packet["runes"][number - 1]), "elapsed_ms": 10}
            for number in range(1, rhythm.rules.initial_health() + 2)
        ]
        try:
            await rhythm.finalize_offline_run(db, user_id=975006, run_id=overlong["run_id"], actions=impossible_journal, finalize_id="offline-after-death")
        except rhythm.RhythmError:
            pass
        else:
            raise AssertionError("offline journal must not continue after defeat")

        # A modified local client knows the complete packet and may fabricate
        # perfect timing. Preserve the personal score, but never rank or reward it.
        quarantined = await rhythm.start_run(db, user_id=975007, mode="normal")
        quarantined_packet = await rhythm.offline_packet(db, user_id=975007, run_id=quarantined["run_id"])
        forged = [
            {"signal_no": number, "rune": quarantined_packet["runes"][number - 1], "elapsed_ms": 0}
            for number in range(1, 9)
        ] + [
            {"signal_no": number, "rune": wrong_rune(quarantined_packet["runes"][number - 1]), "elapsed_ms": 1}
            for number in range(9, 14)
        ]
        quarantined_final = await rhythm.finalize_offline_run(
            db, user_id=975007, run_id=quarantined["run_id"], actions=forged, finalize_id="offline-forged-perfect",
        )
        assert quarantined_final["status"] == "finished" and quarantined_final["score"] > 0
        assert quarantined_final["integrity_status"] == "quarantined"
        assert (await rhythm.rankings(db, user_id=975007, mode="normal"))["personal"] is None
        # A stale pre-integrity summary row with a huge untrusted score must
        # not poison the current table or hide a later lower trusted result.
        await db.execute(
            "UPDATE rhythm_v2_leaderboard SET best_score=?,best_run_id=? "
            "WHERE user_id=? AND mode='normal' AND ruleset_version=?",
            (999999, quarantined["run_id"], 975001, rhythm.rules.RULESET_VERSION),
        )
        repaired_view = await rhythm.rankings(db, user_id=975001, mode="normal")
        assert repaired_view["personal"] and repaired_view["personal"]["best_score"] == first["score"]
        assert all(row["best_score"] != 999999 for row in repaired_view["top"])
        async with db.execute("SELECT COUNT(*) FROM quest_v1_metric_receipts WHERE user_id=? AND event_id=?", (975007, f"rhythm:{quarantined['run_id']}")) as cursor:
            assert (await cursor.fetchone())[0] == 0
        async with db.execute("SELECT COUNT(*) FROM achievement_v1_metric_receipts WHERE user_id=? AND source_event_id=?", (975007, quarantined["run_id"])) as cursor:
            assert (await cursor.fetchone())[0] == 0

        augmented = await rhythm.start_run(db, user_id=975001, mode="augments")
        assert augmented["status"] == "choosing" and len(augmented["offers"]["positive"]) == 3
        try:
            await rhythm.choose_augmentations(db, user_id=975001, run_id=augmented["run_id"],
                                              positive=["forged", "also_forged"],
                                              negative=augmented["offers"]["negative"][:2])
        except rhythm.rules.RhythmRuleError:
            pass
        else:
            raise AssertionError("unoffered augmentation must fail")
        chosen = await rhythm.choose_augmentations(db, user_id=975001, run_id=augmented["run_id"],
                                                   positive=augmented["offers"]["positive"][:2],
                                                   negative=augmented["offers"]["negative"][:2])
        assert chosen["status"] == "active" and len(chosen["selected_augmentations"]) == 4
        ticket = await rhythm.issue_transport_ticket(db, user_id=975001, run_id=augmented["run_id"])
        live_user, lease, live = await rhythm.connect_transport(db, run_id=augmented["run_id"], ticket=ticket["ticket"])
        assert live_user == 975001 and live["rune"] in {"left", "center", "right"}, live
        try:
            await rhythm.connect_transport(db, run_id=augmented["run_id"], ticket=ticket["ticket"])
        except rhythm.RhythmConflict:
            pass
        else:
            raise AssertionError("one-use live ticket must reject replay")
        await rhythm.release_transport(db, user_id=live_user, run_id=augmented["run_id"], lease=lease)
        cancelled = await rhythm.cancel_run(db, user_id=975001, run_id=augmented["run_id"])
        assert cancelled["status"] == "cancelled"
        try:
            await rhythm.cancel_run(db, user_id=975003, run_id=augmented["run_id"])
        except rhythm.RhythmConflict:
            pass
        else:
            raise AssertionError("foreign user must not cancel a Rhythm run")

        augmented_terminal = await rhythm.start_run(db, user_id=975009, mode="augments")
        augmented_terminal = await rhythm.choose_augmentations(
            db, user_id=975009, run_id=augmented_terminal["run_id"],
            positive=augmented_terminal["offers"]["positive"][:2],
            negative=augmented_terminal["offers"]["negative"][:2],
        )
        augmented_ticket = await rhythm.issue_transport_ticket(db, user_id=975009, run_id=augmented_terminal["run_id"])
        _, augmented_lease, augmented_terminal = await rhythm.connect_transport(
            db, run_id=augmented_terminal["run_id"], ticket=augmented_ticket["ticket"],
        )
        for attempt in range(20):
            augmented_terminal = await rhythm.transport_tap(
                db, user_id=975009, run_id=augmented_terminal["run_id"], lease=augmented_lease,
                signal_no=augmented_terminal["next_signal_no"], rune=wrong_rune(augmented_terminal["rune"]),
                action_id=f"augmented-wrong-{attempt}",
            )
            if augmented_terminal["status"] == "finished":
                break
        assert augmented_terminal["status"] == "finished"
        async with db.execute("SELECT COUNT(*) FROM quest_v1_metric_receipts WHERE user_id=? AND event_id=?", (975009, f"rhythm:{augmented_terminal['run_id']}")) as cursor:
            assert (await cursor.fetchone())[0] == 3
        async with db.execute("SELECT metric FROM quest_v1_metric_receipts WHERE user_id=? AND event_id=? ORDER BY metric", (975009, f"rhythm:{augmented_terminal['run_id']}")) as cursor:
            assert [row[0] for row in await cursor.fetchall()] == [
                'game_completed', 'rhythm_augments_completed', 'rhythm_completed',
            ]
    finally:
        await transaction.rollback()
        await connection.close()

    # A real concurrent delivery needs committed visibility between two
    # connections, so it is deliberately isolated and cleans only its exact
    # generated rows afterwards.
    first_connection = await asyncpg.connect(dsn)
    second_connection = await asyncpg.connect(dsn)
    first_db, second_db = PGAdapter(first_connection), PGAdapter(second_connection)
    run_id = None
    try:
        # Exact synthetic test identity cleanup makes an interrupted previous
        # proof rerunnable without touching any real player row.
        await first_connection.execute("DELETE FROM rhythm_v2_leaderboard WHERE user_id=$1", 975002)
        await first_connection.execute("DELETE FROM rhythm_v2_actions WHERE run_id IN (SELECT run_id FROM rhythm_v2_runs WHERE user_id=$1)", 975002)
        await first_connection.execute("DELETE FROM rhythm_v2_transport_tickets WHERE run_id IN (SELECT run_id FROM rhythm_v2_runs WHERE user_id=$1)", 975002)
        await first_connection.execute("DELETE FROM rhythm_v2_runs WHERE user_id=$1", 975002)
        concurrent = await rhythm.start_run(first_db, user_id=975002, mode="normal")
        run_id = concurrent["run_id"]
        ticket = await rhythm.issue_transport_ticket(first_db, user_id=975002, run_id=run_id)
        _, concurrent_lease, concurrent = await rhythm.connect_transport(first_db, run_id=run_id, ticket=ticket["ticket"])
        async def submit(db):
            return await rhythm.transport_tap(db, user_id=975002, run_id=run_id, lease=concurrent_lease,
                                              signal_no=1, rune=concurrent["rune"], action_id="same-network-retry")
        left, right = await asyncio.gather(submit(first_db), submit(second_db))
        assert left["score"] == right["score"]
        assert bool(left.get("idempotent_replay")) != bool(right.get("idempotent_replay"))
        try:
            await rhythm.current_run(first_db, user_id=975003, run_id=run_id)
        except rhythm.RhythmConflict:
            pass
        else:
            raise AssertionError("foreign user must not read a Rhythm run")
    finally:
        if run_id:
            await first_connection.execute("DELETE FROM rhythm_v2_leaderboard WHERE best_run_id=$1", run_id)
            await first_connection.execute("DELETE FROM rhythm_v2_actions WHERE run_id=$1", run_id)
            await first_connection.execute("DELETE FROM rhythm_v2_transport_tickets WHERE run_id=$1", run_id)
            await first_connection.execute("DELETE FROM rhythm_v2_runs WHERE run_id=$1", run_id)
        await first_connection.close()
        await second_connection.close()


parser = argparse.ArgumentParser()
parser.add_argument("--dsn", required=True, type=local_dsn)
args = parser.parse_args()
asyncio.run(run(args.dsn))
print("Rhythm v2: PostgreSQL replay/seed/finish/leaderboard proof OK")
