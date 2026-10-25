#!/usr/bin/env python3
"""The phone engine of League Rhythm (FastAPI/static/league-rhythm.js) must score a level exactly like the server.

An honest player is never rejected or under-scored only if both sides agree on windows, hearts, gifts
and score for every journal.  Generates journals in Python, replays them in the real JS file under
node:vm, compares with services.league_rhythm.replay.
Run: PYTHONPATH=. python3 tools/test_league_v1_parity.py   (needs node)
"""
from __future__ import annotations

import json
import math
import os
import random
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core import league_v1 as rules  # noqa: E402
from core import rhythm_v2 as rhythm  # noqa: E402
from services import league_rhythm as lr  # noqa: E402
from test_league_v1_rules import honest_journal  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODE = r"""
const fs = require('fs'), vm = require('vm');
const ctx = {window: {}, document: {addEventListener() {}}, performance: {now: () => 0}, requestAnimationFrame() {}, setTimeout() {}, clearTimeout() {}, BigInt, Math, Object, Number};
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(process.argv[1], 'utf8'), ctx);
const Engine = ctx.window.LeagueRhythmEngine;
const cases = JSON.parse(fs.readFileSync(0, 'utf8'));
const out = cases.map(({packet, actions}) => {
  const e = new Engine(packet);
  for (const a of actions) {
    if (a.kind === 'pick') {
      const due = e.draftDue();
      if (!due) throw new Error('pick without a draft');
      if (a.perk_id !== null && !e.allowed(a.perk_id)) throw new Error('engine forbids a gift the server allows');
      e.pick(a.perk_id);
    } else e.tap(a.rune, a.elapsed_ms);
  }
  return {score: e.s.score, health: Math.max(0, e.s.health), over: e.over()};
});
process.stdout.write(JSON.stringify(out));
"""


SERIES = ("hot_streak", "anchor", "recharge", "phoenix", "trade")   # gifts of rules-8; the random journals meet each only now and then


def forced_gift_journal(level: int, seed: bytes, rng: random.Random, gift: str, rt: float, slip: float) -> tuple[dict, list[dict], dict]:
    """A journal that takes `gift` at the first gift choice (it replaces the first offer) and plays on with the given skill."""
    packet = lr.packet(season="parity", level=level, seed=seed)
    packet["drafts"] = [[gift, *packet["drafts"][0][:2]], *packet["drafts"][1:]]
    spec = rules.rhythm_level(level)
    state, actions = lr._new_state(spec), []
    while state["health"] > 0 and state["signal"] <= spec.signals:
        draft = (state["signal"] - 1) // rules.RHYTHM_CHUNK
        if draft > len(state["selected"]):
            offers = [g for g in packet["drafts"][draft - 1] if rules.gift_allowed(g, health=state["health"], perks=state["perks"])]
            action = {"kind": "pick", "perk_id": gift if draft == 1 and gift in offers else (rng.choice(offers) if offers else None)}
            lr._pick(state, action, packet["drafts"][draft - 1])
        else:
            window, expected = rules.rhythm_window(spec, state["signal"], state["perks"]), packet["runes"][state["signal"] - 1]
            elapsed = int(rng.lognormvariate(math.log(rt), 0.22))
            rune = expected if rng.random() > slip else rng.choice([r for r in rhythm.RUNES if r != expected])
            if elapsed > window:
                rune, elapsed = None, window + 1
            action = {"kind": "tap", "signal_no": state["signal"], "rune": rune, "elapsed_ms": elapsed}
            lr._tap(spec, state, action, expected)
        actions.append(action)
    return packet, actions, state


def forced_gift_cases(rng: random.Random) -> tuple[list[dict], list[tuple[int, int]], dict]:
    """Every series gift, taken at levels long enough for a 40-tap series, with sloppy and clean players alike."""
    cases, expected, reached = [], [], {gift: 0 for gift in SERIES}
    for gift in SERIES:
        for _ in range(120):
            level = rng.randrange(36, 100)
            slip = rng.choice((0.0, 0.004, 0.02, 0.06, 0.15))
            packet, actions, state = forced_gift_journal(level, rng.randbytes(32), rng, gift, rng.choice((380, 450, 560)), slip)
            cases.append({"packet": packet, "actions": actions})
            expected.append((state["score"], max(0, state["health"])))
            reached[gift] += gift in state["perks"]["owned"]
    return cases, expected, reached


def main() -> None:
    rng = random.Random(21)
    cases, expected = [], []
    for _ in range(400):
        level = rng.randrange(1, 120)
        seed = rng.randbytes(32)
        profile = rng.choice(((640, 0.05, 0.05), (520, 0.03, 0.03), (420, 0.015, 0.02), (360, 0.01, 0.0)))
        actions = honest_journal(level, seed, rng, *profile, season="parity")
        cases.append({"packet": lr.packet(season="parity", level=level, seed=seed), "actions": actions})
        expected.append(lr.replay(season="parity", level=level, seed=seed, actions=actions))
    script = os.path.join(ROOT, "FastAPI", "static", "league-rhythm.js")
    done = subprocess.run(["node", "-e", NODE, script], input=json.dumps(cases), capture_output=True, text=True, check=True)
    got = json.loads(done.stdout)
    gifts = sum(any(a["kind"] == "pick" and a["perk_id"] for a in c["actions"]) for c in cases)
    for case, mine, theirs in zip(cases, got, expected):
        assert mine["over"], "the journal must end the level on the phone too"
        assert (mine["score"], mine["health"]) == (theirs["score"], theirs["hearts"]), (case["packet"]["level"], mine, theirs)
    assert gifts > 100, gifts
    print(f"PASS {len(cases)} levels ({gifts} with gifts): phone engine == server replay")
    forced, forced_expected, reached = forced_gift_cases(random.Random(5))
    done = subprocess.run(["node", "-e", NODE, script], input=json.dumps(forced), capture_output=True, text=True, check=True)
    for case, mine, want in zip(forced, json.loads(done.stdout), forced_expected):
        assert (mine["score"], mine["health"]) == want, (case["packet"]["level"], mine, want)
    assert all(count > 40 for count in reached.values()), reached
    print(f"PASS {len(forced)} levels with a forced series gift {dict(reached)}: phone engine == rules")


if __name__ == "__main__":
    main()
