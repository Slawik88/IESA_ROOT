"""League Rhythm: one level is played on the phone and checked by the server in the pause after it.

The phone receives the runes of this level only, plays them locally (no network, no stalls) and sends
the journal when the level ends.  The server replays the journal with the authoritative rules.  It
rejects only what an honest phone cannot produce (a broken journal, a level returned faster than it
can be played); statistical oddities only mark the result for a human look and never cost points.
"""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import hmac
import statistics

from core import league_v1 as rules
from core import rhythm_v2 as rhythm

FAST_TAP_MS = 120          # nobody reacts to one of three random runes this fast; such taps are guesses
FAST_TAPS_TO_REVIEW = 8    # an honest guesser is right 1 time in 3; 8+ fast taps right 80% of the time is not luck
STEADY_TAPS_TO_REVIEW = 25
STEADY_SPREAD_MS = 12      # human reactions vary by far more than this
CLOCK_TOLERANCE_MS = 2_000


def runes(seed: bytes, count: int) -> list[str]:
    return [rhythm.RUNES[hmac.new(seed, f"league-rune:{i}".encode(), hashlib.sha256).digest()[0] % 3]
            for i in range(1, count + 1)]


def packet(*, season: str, level: int, seed: bytes) -> dict:
    """Everything the phone needs for one level: no other level and no seed."""
    spec = rules.rhythm_level(level)
    windows = [spec.base_window_ms * 100 // rules.rhythm_pace(spec, i, rhythm.new_perks()) for i in range(1, spec.signals + 1)]
    return {
        "level": spec.level, "signals": spec.signals, "hearts": spec.hearts, "base_window_ms": spec.base_window_ms,
        "growth_pct": spec.growth_pct, "floor_ms": rules.RHYTHM_FLOOR_MS, "chunk": rules.RHYTHM_CHUNK,
        "max_bonus_pct": rules.MAX_SCORE_BONUS_PCT, "runes": runes(seed, spec.signals), "plain_windows_ms": windows,
        "drafts": [list(rules.gift_plan(season, level, n)) for n in range(1, rules.rhythm_drafts(spec) + 1)],
        "reference": rules.rhythm_reference(spec), "star_pct": list(spec.star_pct),
        "catalog": [asdict(item) for item in rhythm.PERKS if not item.filler], "max_health": rhythm.MAX_HEALTH,
    }


def _new_state(spec: rules.RhythmLevel) -> dict:
    return {"health": spec.hearts, "perks": rhythm.new_perks(), "score": 0, "combo": 0, "streak": 0,
            "correct": 0, "mistakes": 0, "signal": 1, "selected": [], "taps": []}


def _pick(state: dict, action: dict, offered: list[str]) -> None:
    choice = action.get("perk_id")
    if action.get("kind") != "pick":
        raise rules.LeagueRuleError("Сначала выбери дар или пропусти его.")
    state["selected"].append(choice)
    if choice is None:
        return
    if choice not in offered or not rules.gift_allowed(choice, health=state["health"], perks=state["perks"]):
        raise rules.LeagueRuleError("Этот дар сейчас взять нельзя.")
    state["health"], state["perks"] = rhythm.apply_perk(choice, health=state["health"], perks=state["perks"])


def _tap(spec: rules.RhythmLevel, state: dict, action: dict, expected: str) -> None:
    rune, elapsed = action.get("rune"), action.get("elapsed_ms")
    if (action.get("kind") != "tap" or action.get("signal_no") != state["signal"] or type(elapsed) is not int
            or not 0 <= elapsed <= 60_000 or rune not in (*rhythm.RUNES, None)):
        raise rules.LeagueRuleError("Журнал уровня повреждён.")
    window = rules.rhythm_window(spec, state["signal"], state["perks"])
    correct = rune == expected and elapsed <= window
    state["taps"].append((elapsed, correct, rune is not None))
    if correct:
        state["score"] += rules.rhythm_score(elapsed_ms=elapsed, window_ms=window, combo_before=state["combo"],
                                             perks=state["perks"], health=state["health"])
        state["combo"] += 1
        state["streak"] += 1
        state["correct"] += 1
        state["health"], state["perks"] = rhythm.after_correct(state["perks"], health=state["health"],
                                                               streak_after=state["streak"])
    else:
        state["health"], state["perks"] = rhythm.after_error(health=state["health"], perks=state["perks"],
                                                             timed_out=rune is None or elapsed > window)
        state["combo"] = state["streak"] = 0
        state["mistakes"] += 1
    state["signal"] += 1


def replay(*, season: str, level: int, seed: bytes, actions: list[dict]) -> dict:
    """Authoritative result of one level journal; raises LeagueRuleError on anything an honest phone cannot send."""
    spec = rules.rhythm_level(level)
    order, plan = runes(seed, spec.signals), packet(season=season, level=level, seed=seed)["drafts"]
    state = _new_state(spec)
    pending = list(actions)
    while pending:
        if state["health"] <= 0 or state["signal"] > spec.signals:
            raise rules.LeagueRuleError("Журнал продолжается после конца уровня.")
        draft = (state["signal"] - 1) // rules.RHYTHM_CHUNK
        if draft > len(state["selected"]):
            _pick(state, pending.pop(0), plan[draft - 1])
            continue
        _tap(spec, state, pending.pop(0), order[state["signal"] - 1])
    alive = state["health"] > 0
    if alive and state["signal"] <= spec.signals:
        raise rules.LeagueRuleError("Уровень ещё не доигран.")
    stars = rules.rhythm_stars(spec, alive=alive, score=state["score"])
    return {"score": state["score"], "alive": alive, "stars": stars, "hearts": max(0, state["health"]),
            "correct": state["correct"], "mistakes": state["mistakes"], "selected": state["selected"],
            "reference": rules.rhythm_reference(spec), "_taps": state["taps"]}


def played_ms(result: dict) -> int:
    """Least wall-clock time the journal can have taken: every signal waited for its tap."""
    return sum(elapsed for elapsed, _, _ in result["_taps"])


def review_marks(result: dict) -> list[str]:
    """Reasons for a human look.  Never a penalty: an honest player keeps the result either way."""
    marks = []
    fast = [correct for elapsed, correct, tapped in result["_taps"] if tapped and elapsed < FAST_TAP_MS]
    if len(fast) >= FAST_TAPS_TO_REVIEW and sum(fast) >= 0.8 * len(fast):
        marks.append("fast_correct_taps")
    steady = [elapsed for elapsed, correct, _ in result["_taps"] if correct]
    if len(steady) >= STEADY_TAPS_TO_REVIEW and statistics.pstdev(steady) < STEADY_SPREAD_MS:
        marks.append("machine_steady_timing")
    return marks
