#!/usr/bin/env python3
"""The phone engine of League Rhythm (FastAPI/static/league-rhythm.js) must score a level exactly like the server.

An honest player is never rejected or under-scored only if both sides agree on windows, hearts, gifts
and score for every journal.  Generates journals in Python, replays them in the real JS file under
node:vm, compares with services.league_rhythm.replay.
Run: PYTHONPATH=. python3 tools/test_league_v1_parity.py   (needs node)
"""
from __future__ import annotations

import json
import os
import random
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

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


if __name__ == "__main__":
    main()
