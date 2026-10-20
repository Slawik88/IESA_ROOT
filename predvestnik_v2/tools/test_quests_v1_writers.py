"""Every quest metric must still have a terminal server writer.

No database needed: reads the service layer and proves that each metric a quest
can request is named by a writer (or by one of the explicit dynamic families).
Run from predvestnik_v2/:  python tools/test_quests_v1_writers.py
"""
from __future__ import annotations

import pathlib

from core.quests_v1 import QUESTS

ROOT = pathlib.Path(__file__).resolve().parent.parent
SERVICES = ROOT / 'services'

# Dynamic metric families: the writer builds the name from a validated value.
DYNAMIC = {
    'rhythm_normal_completed': 'rhythm_{mode}_completed',
    'minesweeper_easy_win': 'minesweeper_{difficulty}_win',
    'minesweeper_normal_win': 'minesweeper_{difficulty}_win',
    'minesweeper_hard_win': 'minesweeper_{difficulty}_win',
}


def main() -> None:
    corpus = '\n'.join(path.read_text(encoding='utf-8') for path in SERVICES.rglob('*.py'))
    missing = []
    for quest in QUESTS:
        metric = quest['metric']
        token = DYNAMIC.get(metric, metric)
        if f'"{token}"' not in corpus and f"'{token}'" not in corpus:
            missing.append(f"{quest['id']} -> {metric}")
    assert not missing, 'quests without a terminal writer: ' + ', '.join(missing)

    # The dynamic families must stay tied to a closed vocabulary.
    assert 'mode, state, offers = "normal"' in (SERVICES / 'rhythm_v2.py').read_text(encoding='utf-8'), \
        'all Rhythm runs must be stored as mode="normal"'
    from core.minesweeper_v2 import DIFFICULTIES
    difficulties = {q['metric'].removeprefix('minesweeper_').removesuffix('_win')
                    for q in QUESTS
                    if q['metric'].startswith('minesweeper_') and q['metric'].endswith('_win')
                    and q['metric'].count('_') == 2}
    assert difficulties == set(DIFFICULTIES), (difficulties, set(DIFFICULTIES))
    assert 'minesweeper_{difficulty}_win' in corpus

    print(f'OK: {len(QUESTS)} quests, every metric has a terminal writer')


if __name__ == '__main__':
    main()
