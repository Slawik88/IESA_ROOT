#!/usr/bin/env python3
"""Season 2 fairness study of Minesweeper on the shipped generator (core.minesweeper_v2).

Commands (PYTHONPATH=. python3 tools/season2_mines_sim.py <command> [boards]):
  luck     perfect-logic solver per difficulty: win rate, share of boards that need
           no guess, guesses per board, 3BV (minimum clicks, the board-complexity measure)
  noguess  cost of generating boards that are solvable without guessing from the first click

The solver enumerates the frontier exactly, flags certain mines, opens certain
safe cells and otherwise opens the cell with the lowest exact mine probability.
"""
from __future__ import annotations

import hashlib
import random
import statistics
import sys
import time
from math import comb
from multiprocessing import Pool

from core import minesweeper_v2 as M


def three_bv(spec, layout):
    size, mines, adj = spec.size, layout["mines"], layout["adjacent"]
    seen, bv = set(), 0
    for c in range(size * size):
        if c in mines or c in seen or adj[c] != 0:
            continue
        bv += 1
        stack = [c]
        while stack:
            x = stack.pop()
            if x in seen:
                continue
            seen.add(x)
            if adj[x] == 0:
                stack.extend(n for n in M.neighbours(size, x) if n not in mines)
    bv += sum(1 for c in range(size * size) if c not in mines and c not in seen)
    return bv


def enumerate_frontier(cells, constraints):
    """counts[k] = #assignments with k mines; per[cell][k] = #with cell mined."""
    index = {c: i for i, c in enumerate(cells)}
    cons = [([index[c] for c in cs], n) for cs, n in constraints]
    by_cell = [[] for _ in cells]
    for ci, (cs, _) in enumerate(cons):
        for i in cs:
            by_cell[i].append(ci)
    assign = [None] * len(cells)
    mined_in = [0] * len(cons)
    open_in = [len(cs) for cs, _ in cons]
    counts = {}
    per = [dict() for _ in cells]

    def rec(i, k):
        if i == len(cells):
            counts[k] = counts.get(k, 0) + 1
            for j, v in enumerate(assign):
                if v:
                    per[j][k] = per[j].get(k, 0) + 1
            return
        for v in (0, 1):
            ok = True
            for ci in by_cell[i]:
                need = cons[ci][1]
                m = mined_in[ci] + v
                rest = open_in[ci] - 1
                if m > need or m + rest < need:
                    ok = False
                    break
            if not ok:
                continue
            assign[i] = v
            for ci in by_cell[i]:
                mined_in[ci] += v
                open_in[ci] -= 1
            rec(i + 1, k + v)
            for ci in by_cell[i]:
                mined_in[ci] -= v
                open_in[ci] += 1
            assign[i] = None

    rec(0, 0)
    return counts, per


def components(cells, constraints):
    parent = {c: c for c in cells}
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for cs, _ in constraints:
        cs = list(cs)
        for c in cs[1:]:
            parent[find(c)] = find(cs[0])
    groups = {}
    for c in cells:
        groups.setdefault(find(c), []).append(c)
    out = []
    for g in groups.values():
        gs = set(g)
        out.append((g, [(cs, n) for cs, n in constraints if set(cs) & gs]))
    return out


def solve(spec, layout, first, rng):
    size, total = spec.size, spec.size * spec.size
    revealed, flags = set(), set()
    revealed, flags, status, _ = M.apply_action(spec=spec, layout=layout, revealed=revealed, flags=flags, kind="open", cell=first)
    guesses, guess_risk, clicks = 0, [], 1
    adj = layout["adjacent"]
    while status == "active":
        unknown = [c for c in range(total) if c not in revealed and c not in flags]
        constraints, frontier = [], set()
        for c in revealed:
            if adj[c] == 0:
                continue
            nb = [n for n in M.neighbours(size, c) if n not in revealed and n not in flags]
            if not nb:
                continue
            need = adj[c] - sum(1 for n in M.neighbours(size, c) if n in flags)
            constraints.append((tuple(sorted(nb)), need))
            frontier.update(nb)
        # dedupe constraints
        constraints = list(dict.fromkeys(constraints))
        frontier = sorted(frontier)
        others = [c for c in unknown if c not in frontier]
        remaining = spec.mines - len(flags)
        comps = components(frontier, constraints)
        comp_results = [enumerate_frontier(sorted(g, key=lambda x: x), cons) + (sorted(g),) for g, cons in comps]
        # convolve component mine-count distributions
        dist = {0: 1}
        for counts, _, _ in comp_results:
            nd = {}
            for a, wa in dist.items():
                for b, wb in counts.items():
                    nd[a + b] = nd.get(a + b, 0) + wa * wb
            dist = nd
        def weight(k):
            r = remaining - k
            return comb(len(others), r) if 0 <= r <= len(others) else 0
        total_w = sum(w * weight(k) for k, w in dist.items())
        prob = {}
        for ci, (counts, per, cells) in enumerate(comp_results):
            # distribution of the other components
            rest = {0: 1}
            for cj, (cc, _, _) in enumerate(comp_results):
                if cj == ci:
                    continue
                nd = {}
                for a, wa in rest.items():
                    for b, wb in cc.items():
                        nd[a + b] = nd.get(a + b, 0) + wa * wb
                rest = nd
            for j, cell in enumerate(cells):
                num = 0
                for k, wk in per[j].items():
                    for kr, wr in rest.items():
                        num += wk * wr * weight(k + kr)
                prob[cell] = num / total_w
        if others:
            exp_front = sum(w * weight(k) * k for k, w in dist.items()) / total_w
            p_other = (remaining - exp_front) / len(others)
            for c in others:
                prob[c] = p_other
        safe = [c for c in unknown if prob[c] < 1e-12]
        mined = [c for c in unknown if prob[c] > 1 - 1e-12]
        for c in mined:
            flags.add(c)
        if safe:
            for c in safe:
                if status != "active":
                    break
                revealed, flags, status, _ = M.apply_action(spec=spec, layout=layout, revealed=revealed, flags=flags, kind="open", cell=c)
                clicks += 1
            continue
        if mined:
            continue
        best = min(prob[c] for c in unknown)
        cands = [c for c in unknown if prob[c] <= best + 1e-12]
        cell = rng.choice(cands)
        guesses += 1
        guess_risk.append(best)
        revealed, flags, status, _ = M.apply_action(spec=spec, layout=layout, revealed=revealed, flags=flags, kind="open", cell=cell)
        clicks += 1
    return status == "won", guesses, guess_risk


def _job(args):
    diff, start, n, version = args
    spec = M.difficulty(diff)
    rng = random.Random(f"{diff}:{start}")
    rows = []
    for i in range(start, start + n):
        seed = random.Random(f"seed:{diff}:{i}").randbytes(32)
        first = rng.randrange(spec.size * spec.size)
        layout = M.board(seed, spec, first, ruleset_version=version)
        won, g, risk = solve(spec, layout, first, rng)
        rows.append((won, g, three_bv(spec, layout), sum(risk), max(risk) if risk else 0.0))
    return rows


def cmd_luck(pool, n):
    print(f"{n} boards per difficulty, first click at a random cell, ruleset v2 (shipped)")
    print(f"{'diff':>6} {'grid':>6} {'density':>7} | {'win perfect':>11} {'no-guess':>8} {'guesses avg':>11} {'loss if guess':>13} | {'3BV med (p10-p90)':>18}")
    for diff in ("easy", "normal", "hard"):
        spec = M.difficulty(diff)
        rows = []
        for part in pool.map(_job, [(diff, k * (n // 4), n // 4, M.RULESET_VERSION) for k in range(4)]):
            rows.extend(part)
        wins = sum(r[0] for r in rows) / len(rows)
        noguess = sum(r[1] == 0 for r in rows) / len(rows)
        g = statistics.mean(r[1] for r in rows)
        guessed = [r for r in rows if r[1] > 0]
        loss_g = 1 - sum(r[0] for r in guessed) / len(guessed) if guessed else 0
        bv = sorted(r[2] for r in rows)
        print(f"{diff:>6} {spec.size}x{spec.size:<3} {spec.mines / spec.size ** 2:>7.1%} | {wins:>11.1%} {noguess:>8.1%} {g:>11.2f} {loss_g:>13.1%} | "
              f"{statistics.median(bv):>6.0f} ({bv[len(bv) // 10]}-{bv[len(bv) * 9 // 10]})")


def no_guess_board(base: bytes, spec, first: int, attempts: int = 200):
    """First derived seed whose board the solver clears without a guess; (layout, attempts used)."""
    for attempt in range(attempts):
        seed = hashlib.sha256(base + attempt.to_bytes(4, "big")).digest()
        layout = M.board(seed, spec, first)
        won, guesses, _ = solve(spec, layout, first, random.Random(0))
        if won and guesses == 0:
            return layout, attempt + 1
    raise RuntimeError("no no-guess board within the attempt budget")


def cmd_noguess(n: int) -> None:
    for diff in ("easy", "normal", "hard"):
        spec, used, bvs = M.difficulty(diff), [], []
        started = time.time()
        for i in range(n):
            first = random.Random(i).randrange(spec.size * spec.size)
            layout, tries = no_guess_board(random.Random(f"ng:{diff}:{i}").randbytes(32), spec, first)
            used.append(tries)
            bvs.append(three_bv(spec, layout))
        ms = (time.time() - started) / n * 1000
        bvs.sort()
        print(f"{diff:6s} no-guess: attempts mean {statistics.mean(used):.1f}, worst {max(used)}; {ms:.0f} ms per board; "
              f"3BV median {statistics.median(bvs):.0f} (p10 {bvs[n // 10]} - p90 {bvs[n * 9 // 10]})")


def main() -> None:
    command = sys.argv[1] if len(sys.argv) > 1 else "luck"
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 2000
    if command == "noguess":
        cmd_noguess(n)
        return
    with Pool(4) as pool:
        cmd_luck(pool, n)


if __name__ == "__main__":
    main()
