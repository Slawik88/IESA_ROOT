#!/usr/bin/env python3
"""League demo rules without a database: logic solver, level boards, stars, Rhythm journals, cheat marks.

Run: PYTHONPATH=. python3 tools/test_league_v1_rules.py
"""
from __future__ import annotations

from itertools import combinations
import math
import random

from core import league_mines, league_v1 as rules, mines_logic as logic, rhythm_v2 as rhythm
from services import league_rhythm as lr


def brute_no_guess(width: int, height: int, mines: frozenset[int], start: int) -> bool:
    """Reference: clear the board only by cells that are safe in EVERY layout consistent with what is visible."""
    total, count = width * height, len(mines)
    adjacent = logic.adjacency(width, height, mines)
    revealed = logic.flood(width, height, mines, adjacent, set(), start)
    while len(revealed) < total - count:
        closed = [c for c in range(total) if c not in revealed]
        layouts = [set(m) for m in combinations(closed, count)
                   if all(sum(n in m for n in logic.neighbours(width, height, c)) == adjacent[c] for c in revealed)]
        safe = [c for c in closed if all(c not in m for m in layouts)]
        if not safe:
            return False
        for cell in safe:
            revealed |= logic.flood(width, height, mines, adjacent, revealed, cell)
    return True


def test_solver_matches_brute_force() -> None:
    rng = random.Random(11)
    checked = solvable = 0
    for _ in range(260):
        width, height, count = rng.choice(((4, 4, 3), (4, 4, 4), (5, 4, 4), (5, 5, 4)))
        mines = frozenset(rng.sample(range(width * height), count))
        safe = [c for c in range(width * height) if c not in mines]
        start = rng.choice(safe)
        mine_says = logic.analyse(width, height, mines, [start]).solvable
        assert mine_says == brute_no_guess(width, height, mines, start), (width, height, sorted(mines), start)
        checked += 1
        solvable += mine_says
    assert 0 < solvable < checked, (solvable, checked)


def test_level_boards() -> None:
    for level in (1, 2, 3, 6, 12, 21, 40, 70):
        spec = rules.mines_level(level)
        seed = random.Random(level).randbytes(32)
        board = league_mines.generate(seed, spec)
        again = league_mines.generate(seed, spec)
        assert board == again, "a board must be reproducible from its seed"
        assert board.start not in board.mines and len(board.mines) == spec.mines
        result = logic.analyse(spec.width, spec.height, board.mines, [board.start])
        assert result.solvable and result.tier == board.tier == spec.tier, (level, result, board.tier)
        assert result.tier >= 1, "the start must never clear the board by itself"
    assert rules.mines_level(1).width == 3 and rules.mines_level(81).width == 12 and rules.mines_level(1000).height == 16


def test_stars_and_xp() -> None:
    assert rules.mines_stars(won=False, wrong_flags=0, elapsed_ms=1, par_s=60) == 0
    assert rules.mines_stars(won=True, wrong_flags=1, elapsed_ms=1, par_s=60) == 1
    assert rules.mines_stars(won=True, wrong_flags=0, elapsed_ms=61_000, par_s=60) == 2
    assert rules.mines_stars(won=True, wrong_flags=0, elapsed_ms=60_000, par_s=60) == 3
    spec = rules.rhythm_level(10)
    reference = rules.rhythm_reference(spec)
    assert rules.rhythm_stars(spec, alive=False, score=10 ** 9) == 0
    assert rules.rhythm_stars(spec, alive=True, score=0) == 1
    assert rules.rhythm_stars(spec, alive=True, score=math.ceil(reference * 0.7)) == 2
    assert rules.rhythm_stars(spec, alive=True, score=math.ceil(reference * 0.9)) == 3
    assert rules.xp_gain(0, 1) == 60 and rules.xp_gain(1, 3) == 40 and rules.xp_gain(3, 2) == 0 and rules.xp_gain(2, 0) == 0
    assert rules.mines_par_seconds(rules.mines_level(40), 20) >= 30 + 20 * 4, "the third-star time stays generous"


def test_gift_plan_is_shared() -> None:
    plan = rules.gift_plan("s", 7, 1)
    assert plan == rules.gift_plan("s", 7, 1) and len(set(plan)) == 3
    assert any(rhythm.perk(g).kind == "safe" for g in plan)
    assert rules.gift_plan("s", 7, 2) != plan or rules.gift_plan("s", 8, 1) != plan


def test_gift_pool_of_a_level_is_kept() -> None:
    """A level started before the series gifts keeps offering the old gifts; a new one may offer the new ones."""
    series = {item.id for item in rhythm.PERKS if item.since >= 8}
    assert series and rules.GIFT_POOL_BEFORE_SERIES < rules.GIFT_POOL_NOW
    for level in range(1, 120):
        for draft in (1, 2):
            assert not series & set(rules.gift_plan("s", level, draft, rules.GIFT_POOL_BEFORE_SERIES))
            assert len(set(rules.gift_plan("s", level, draft))) == 3
    assert any(series & set(rules.gift_plan("s", level, 1)) for level in range(1, 120))
    rng, rejected = random.Random(9), 0
    for level in range(5, 60):
        seed = rng.randbytes(32)
        old = honest_journal(level, seed, rng, gifts=True, pool_number=rules.GIFT_POOL_BEFORE_SERIES)
        assert lr.replay(season="t", level=level, seed=seed, actions=old, pool_number=rules.GIFT_POOL_BEFORE_SERIES)["score"] >= 0
        try:
            lr.replay(season="t", level=level, seed=seed, actions=old)   # the new plan, same journal
        except rules.LeagueRuleError:
            rejected += 1
    assert rejected, "the pool marker is what lets an old level finish: without it some old journals are refused"


def honest_journal(level: int, seed: bytes, rng: random.Random, rt: float = 520, slip: float = 0.03,
                   guess: float = 0.02, gifts: bool = True, season: str = "t", pool_number: int = rules.GIFT_POOL_NOW) -> list[dict]:
    """A human: log-normal reaction, a few wrong runes, a few anticipations (guesses before the rune is seen)."""
    packet = lr.packet(season=season, level=level, seed=seed, pool_number=pool_number)
    spec = rules.rhythm_level(level)
    state, actions = lr._new_state(spec), []
    while state["health"] > 0 and state["signal"] <= spec.signals:
        draft = (state["signal"] - 1) // rules.RHYTHM_CHUNK
        if draft > len(state["selected"]):
            offers = [g for g in packet["drafts"][draft - 1] if rules.gift_allowed(g, health=state["health"], perks=state["perks"])]
            action = {"kind": "pick", "perk_id": rng.choice(offers) if gifts and offers and rng.random() < 0.7 else None}
            lr._pick(state, action, packet["drafts"][draft - 1])
        else:
            window, expected = rules.rhythm_window(spec, state["signal"], state["perks"]), packet["runes"][state["signal"] - 1]
            if rng.random() < guess:
                elapsed, rune = rng.randrange(40, 120), rng.choice(rhythm.RUNES)
            else:
                elapsed = int(rng.lognormvariate(math.log(rt), 0.22))
                rune = expected if rng.random() > slip else rng.choice([r for r in rhythm.RUNES if r != expected])
            if elapsed > window:
                rune, elapsed = None, window + 1
            action = {"kind": "tap", "signal_no": state["signal"], "rune": rune, "elapsed_ms": elapsed}
            lr._tap(spec, state, action, expected)
        actions.append(action)
    return actions


def test_journal_replay_and_rejections() -> None:
    rng, seed = random.Random(3), bytes(range(32))
    actions = honest_journal(5, seed, rng)
    result = lr.replay(season="t", level=5, seed=seed, actions=actions)
    assert result["stars"] >= 0 and result["correct"] + result["mistakes"] == sum(a["kind"] == "tap" for a in actions)
    for broken in (actions[:-1] if result["alive"] else None, actions + [actions[-1]],
                   [{**a, "signal_no": 99} if i == 0 else a for i, a in enumerate(actions)]):
        if broken is None:
            continue
        try:
            lr.replay(season="t", level=5, seed=seed, actions=broken)
        except rules.LeagueRuleError:
            continue
        raise AssertionError("a broken journal must be rejected")
    level = 30   # 44 signals: a gift choice after signal 20
    actions = honest_journal(level, seed, random.Random(4), rt=380, slip=0, guess=0)
    picks = [i for i, a in enumerate(actions) if a["kind"] == "pick"]
    assert picks, "level 30 has a gift choice"
    foreign = [g.id for g in rhythm.PERKS if not g.filler and g.id not in lr.packet(season="t", level=level, seed=seed)["drafts"][0]][0]
    try:
        lr.replay(season="t", level=level, seed=seed, actions=[{**a, "perk_id": foreign} if i == picks[0] else a for i, a in enumerate(actions)])
    except rules.LeagueRuleError:
        pass
    else:
        raise AssertionError("a gift outside the level plan must be rejected")


def test_cheat_marks_spare_honest_players() -> None:
    rng, marked = random.Random(8), 0
    runs = 1500
    for i in range(runs):
        level = rng.randrange(1, 90)
        profile = rng.choice(((640, 0.05, 0.05), (520, 0.03, 0.03), (430, 0.015, 0.02), (380, 0.01, 0.08)))
        seed = rng.randbytes(32)
        result = lr.replay(season="t", level=level, seed=seed, actions=honest_journal(level, seed, rng, *profile))
        marked += bool(lr.review_marks(result))
    assert marked == 0, f"{marked} honest levels were marked for review"
    seed = bytes(32)
    packet = lr.packet(season="t", level=20, seed=seed)
    bot = []
    state = lr._new_state(rules.rhythm_level(20))
    for n, rune in enumerate(packet["runes"], start=1):
        if (n - 1) // 20 > len(state["selected"]):
            bot.append({"kind": "pick", "perk_id": None})
            state["selected"].append(None)
        bot.append({"kind": "tap", "signal_no": n, "rune": rune, "elapsed_ms": 30})
    result = lr.replay(season="t", level=20, seed=seed, actions=bot)
    assert set(lr.review_marks(result)) == {"fast_correct_taps", "machine_steady_timing"}, lr.review_marks(result)


def main() -> None:
    for name, test in list(globals().items()):
        if name.startswith("test_"):
            test()
            print("PASS", name)


if __name__ == "__main__":
    main()
