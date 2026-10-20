"""Cross-language replay parity, including every gift and first-open halo."""
import copy
from dataclasses import asdict
import json
from pathlib import Path
import subprocess

from core import rhythm_v2 as r, minesweeper_v2 as m
from services import local_games

seed = bytes(range(32))


def state():
    return dict(status="active", selected=[], perks=r.new_perks(), health=5, score=0,
                combo=0, correct_streak=0, correct_taps=0, mistakes=0, next_signal_no=1,
                signal_opened_at=None, finished_at=None, analysis=None)


def packet(s):
    return dict(state=s, seed=seed.hex(), catalog=[asdict(p) for p in r.PERKS],
                legacy=False, run_id="test", ruleset_version=r.RULESET_VERSION)


tests, expected = [], []
for gift in (None, *r.PERKS):
    for signal in (1, 21, 301, 801):
        for timing in (0, 1, 2, 3):
            s = state()
            s.update(health=4, combo=14, correct_streak=14, next_signal_no=signal)
            if gift:
                s["perks"]["owned"][gift.id] = 1
                s["perks"].update(shield=gift.shield, ebb=gift.ebb, bloody=gift.bloody, miss_debt=1, recovery=2)
            # Avoid owed drafts while testing all combinations of gift effects.
            s["selected"] = ["test"] * ((signal-1)//20)
            w = r.window_ms(signal, s["perks"])
            elapsed = (0, w//2, w, w+1)[timing]
            rune = r.expected_rune(seed, signal) if timing < 3 else None
            action = dict(kind="tap", signal_no=signal, rune=rune, elapsed_ms=elapsed)
            # Replay requires a terminal journal; pure rules below provide each
            # intermediate expected state without depending on service writers.
            result = copy.deepcopy(s)
            if timing < 3:
                result["score"] += r.score_for_correct(elapsed_ms=elapsed,allowed_window_ms=w,combo_before=14,perks=s["perks"],health=4)
                result["combo"] += 1; result["correct_streak"] += 1; result["correct_taps"] += 1
                result["health"],result["perks"] = r.after_correct(s["perks"],health=4,streak_after=15)
            else:
                result["combo"]=result["correct_streak"]=0;result["mistakes"]+=1
                result["health"],result["perks"] = r.after_error(health=4,perks=s["perks"],timed_out=True)
            result["next_signal_no"] += 1
            if result["health"] == 0: result["status"]="finished"
            tests.append(dict(game="rhythm",packet=packet(s),actions=[action]));expected.append(result)

# Gifts are offered with exactly the same HMAC order and eligibility filters.
for health in (1, 2, 4, 7):
    s=state();s.update(health=health,next_signal_no=21)
    tests.append(dict(game="rhythm",packet=packet(s),actions=[]));expected.append(copy.deepcopy(s))

rhythm_count=len(tests)
for spec in m.DIFFICULTIES.values():
    layouts={str(c):sorted(m.board(seed,spec,c)["mines"]) for c in range(spec.size**2)}
    for first in range(spec.size**2):
        layout=m.board(seed,spec,first)
        assert not ({first,*m.neighbours(spec.size,first)} & layout["mines"])
        s=dict(run_id="mine",status="awaiting_first_open",size=spec.size,mine_count=spec.mines,
               difficulty=spec.id,revision=0,opened_actions=0,revealed=[],flags=[],changed=[],mines=[],elapsed_ms=0)
        p=dict(state=s,first_cell=None,layouts=layouts,seed=seed.hex())
        actions=[dict(kind="open",cell=first,elapsed_ms=0),dict(kind="open",cell=next(iter(layout["mines"])),elapsed_ms=1234)]
        tests.append(dict(game="minesweeper",packet=p,actions=actions));expected.append(local_games.replay_mine(p,actions))

fresh_start=len(tests)
for difficulty in ('easy','normal','hard'):
    tests.append(dict(game='fresh',target='minesweeper',difficulty=difficulty,packet=p));expected.append(None)
tests.append(dict(game='fresh',target='rhythm',packet=packet(state())));expected.append(None)

result=subprocess.run(['node',str(Path(__file__).with_name('local_games_probe.cjs'))],input=json.dumps(tests),text=True,encoding='utf-8',capture_output=True,check=True)
results=json.loads(result.stdout)
for index,(test,want,got) in enumerate(zip(tests,expected,results)):
    if index>=fresh_start:
        seed_new=bytes.fromhex(got['seed'])
        if test['target']=='minesweeper':
            spec=m.difficulty(test['difficulty'])
            assert got['state']['size']==spec.size
            for first in range(spec.size**2):assert got['layouts'][str(first)]==sorted(m.board(seed_new,spec,first)['mines'])
        else:assert got['state']==state()
    elif index<rhythm_count:
        assert got['state']==want,(index,got['state'],want)
        assert got['initial']['window_ms']==r.window_ms(test['packet']['state']['next_signal_no'],test['packet']['state']['perks'])
        draft=got['initial']['draft']
        if draft:
            s=test['packet']['state']
            assert [p['id'] for p in draft['offers']]==list(r.perk_offers(seed,1,health=s['health'],perks=s['perks']))
    else:
        assert got['status']==want['status'] and got['elapsed_ms']==want['elapsed_ms']
        assert set(got['revealed'])==set(want['revealed_json'])
        assert got['opened_actions']==want['opened_actions']
print(f'OK: {rhythm_count} Rhythm effect/timing cases, 198 first-open layouts, durable lost-reply recovery and account isolation')
