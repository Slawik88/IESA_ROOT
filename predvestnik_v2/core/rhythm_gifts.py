"""Catalog of the rune gifts ("рун-дары") of Rune Rhythm.

Every gift carries a bonus AND a price.  The numbers here are the single source of truth for the casual
endless run and for the ranked League; the phone receives this catalog in its packet and mirrors only the
arithmetic (FastAPI/static/local-games-v1.js, league-rhythm.js).  Rules that combine them: core/rhythm_v2.py.

``since`` is the first ruleset number that offers a gift.  A run keeps the pool of its own ruleset, so a gift
added later never changes the offers of a run that is already in progress.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

PerkKind = Literal["safe", "boost", "risk"]
FIRST_POOL: Final = 5          # rules-5: the original fourteen gifts
POOL_WITH_NEW_THREE: Final = 6  # + Метроном, Последняя искра, Второе дыхание
POOL_WITH_SERIES: Final = 8     # + Горячая серия, Якорь, Зарядка щита, Феникс, Размен


@dataclass(frozen=True)
class Perk:
    id: str
    kind: PerkKind
    name: str
    bonus: str
    cost: str
    max_stack: int = 2
    filler: bool = False        # only offered when fewer than three real gifts remain
    since: int = FIRST_POOL     # first ruleset number that offers the gift
    # Permanent per-copy effects (summed over copies):
    window_pct: int = 0
    score_pct: int = 0
    pace_pct: int = 0
    damage_extra: int = 0       # extra hearts lost by every mistake
    wrong_extra: int = 0        # extra hearts lost by a wrong rune only
    combo_step: int = 0         # extra score per combo step (base 4)
    combo_cap: int = 0          # extra combo bonus cap (base 80)
    regen_every: int = 0        # +1 heart every N correct taps in a row
    timeout_free: bool = False  # every second missed signal costs no heart
    sharp_eye: bool = False     # exact taps pay more, slow taps pay less
    cadence_every: int = 0     # periodic scoring within an unbroken combo
    cadence_bonus_pct: int = 0
    low_health_bonus_pct: int = 0
    recovery_signals: int = 0  # wider windows after paid health loss, not shields
    sacrifice: int = 0        # hearts paid immediately on selection
    streak_bonus_from: int = 0  # the score bonus below applies from this many correct taps in a row
    streak_bonus_pct: int = 0
    combo_keep_pct: int = 0   # share of the series that survives a mistake (0 = it drops to zero)
    shield_every: int = 0     # +1 shield every N correct taps in a row ...
    shield_cap: int = 0       # ... while fewer than this many shields are held
    # One-off effects applied when the gift is taken:
    heal: int = 0
    shield: int = 0
    revive: int = 0             # hearts the run continues with, once, instead of ending
    ebb: int = 0                # signals with a wider window
    bloody: int = 0             # taps with triple score
    cap_health: int = 0         # health is cut to this value (0 = no cut)


# Every gift changes authoritative fields and always carries a price.
PERKS: Final[tuple[Perk, ...]] = (
    Perk("iron_heart", "safe", "Железное сердце", "+2 сердца сразу", "время на нажатие меньше на 10%", window_pct=-10, heal=2),
    Perk("stone_shield", "safe", "Каменный щит", "щит: он принимает одну ошибку, сердце не теряется", "очки ниже на 12%", score_pct=-12, shield=1),
    Perk("tailwind", "safe", "Попутный ветер", "время на нажатие больше на 18%", "очки ниже на 18%", window_pct=18, score_pct=-18),
    Perk("vampire", "safe", "Вампир", "+1 сердце за каждые 15 верных нажатий подряд", "очки ниже на 10%", score_pct=-10, regen_every=15),
    Perk("ebb_tide", "safe", "Отлив", "на следующие 12 нажатий времени больше на 40%", "скорость выше на 8% до конца забега", pace_pct=8, ebb=12),
    Perk("gold_vein", "boost", "Золотая жила", "очки выше на 35%", "каждая ошибка отнимает на сердце больше", score_pct=35, damage_extra=1),
    Perk("sprint", "boost", "Спринт", "очки выше на 30%", "скорость выше на 12%", score_pct=30, pace_pct=12),
    Perk("echo_chain", "boost", "Цепь эха", "серия растёт вдвое быстрее и даёт больше очков", "время на нажатие меньше на 8%", window_pct=-8, combo_step=4, combo_cap=80),
    Perk("steady_hand", "boost", "Твёрдая рука", "пропущенное нажатие вдвое реже отнимает сердце", "неверная руна отнимает ещё одно сердце", max_stack=1, timeout_free=True, wrong_extra=1),
    Perk("sharp_eye", "boost", "Меткий глаз", "точные нажатия дают в 1,5 раза больше очков", "медленные нажатия дают вдвое меньше", max_stack=1, sharp_eye=True),
    Perk("gambit", "risk", "Ставка", "очки выше на 30%", "время на нажатие меньше на 12%", score_pct=30, window_pct=-12),
    Perk("blood_price", "risk", "Цена крови", "следующие 20 верных нажатий дают втрое больше очков", "сразу теряешь сердце", max_stack=1, bloody=20),
    Perk("metronome", "boost", "Метроном", "в серии каждое 4-е нажатие даёт на 115% больше очков", "остальные нажатия дают на 15% меньше", max_stack=1, since=POOL_WITH_NEW_THREE, score_pct=-15, cadence_every=4, cadence_bonus_pct=130),
    Perk("last_spark", "risk", "Последняя искра", "когда осталось 1–2 сердца, очки выше на 25%", "сразу теряешь сердце; при 3 и более сердцах очки ниже на 8%", max_stack=1, since=POOL_WITH_NEW_THREE, score_pct=-8, low_health_bonus_pct=33, sacrifice=1),
    Perk("second_wind", "safe", "Второе дыхание", "после потери сердца 3 нажатия даётся на 25% больше времени", "очки ниже на 12%", max_stack=1, since=POOL_WITH_NEW_THREE, score_pct=-12, recovery_signals=3),
    Perk("breather", "safe", "Передышка", "+1 сердце", "скорость выше на 5%", max_stack=99, pace_pct=5, heal=1, filler=True),
    Perk("glass_cannon", "risk", "Стеклянная пушка", "очки выше на 60%", "сразу остаётся не больше 2 сердец", max_stack=1, score_pct=60, cap_health=2),
    # ── Серия 2026-10-25: награда за чистую игру и страховка от случайной ошибки (docs/audits/RHYTHM_SERIES_GIFTS_2026-10-25.md) ──
    Perk("hot_streak", "boost", "Горячая серия", "после 10 верных нажатий подряд очки выше на 15%", "пока серия короче 10, очки ниже на 25%", max_stack=1, since=POOL_WITH_SERIES, score_pct=-25, streak_bonus_from=10, streak_bonus_pct=40),
    Perk("anchor", "boost", "Якорь", "ошибка сбрасывает серию лишь наполовину", "время на нажатие меньше на 8%", max_stack=1, since=POOL_WITH_SERIES, window_pct=-8, combo_keep_pct=50),
    Perk("recharge", "safe", "Зарядка щита", "каждые 20 верных подряд — щит, который принимает ошибку (про запас один)", "очки ниже на 10%", max_stack=1, since=POOL_WITH_SERIES, score_pct=-10, shield_every=20, shield_cap=1),
    Perk("phoenix", "safe", "Феникс", "когда сердца кончатся, забег продолжится с 2 сердцами (один раз)", "очки ниже на 10%", max_stack=1, since=POOL_WITH_SERIES, score_pct=-10, revive=2),
    Perk("trade", "risk", "Размен", "очки выше на 30%", "сразу теряешь сердце", max_stack=1, since=POOL_WITH_SERIES, score_pct=30, sacrifice=1),
)
PERK_BY_ID: Final = {item.id: item for item in PERKS}
assert len(PERK_BY_ID) == len(PERKS) == 22
