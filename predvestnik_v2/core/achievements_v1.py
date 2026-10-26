"""Pure, long-horizon achievement rules for the approved activity set."""
from __future__ import annotations

from math import ceil
from typing import Final


POLICY_VERSION: Final = "achievements-v1-2026-10-19-life"
MAX_LEVEL: Final = 40
MAX_ACTIVE_WEEKS: Final = 156
GAME_HISTORY_BATCH: Final = 200

# These are deliberately terminal server metrics, never page views, messages,
# client scores, quest progress or historical counters.
FAMILIES: Final = {
    "rhythm": {"title": "Пульс", "icon": "ᚱ", "category": "games", "metric": "rhythm_completed", "cap_events": 2400,
               "source_kind": "rhythm_v2_terminal", "help": "Завершай забеги в Ритме: в обычном режиме или рейтинге.", "action_label": "Открыть Ритм"},
    "minesweeper": {"title": "Контур", "icon": "▦", "category": "games", "metric": "minesweeper_completed", "cap_events": 1600,
                      "source_kind": "minesweeper_v2_terminal", "help": "Завершай партии в Сапёре: в обычном режиме или рейтинге.", "action_label": "Открыть Сапёр"},
    "mafia": {"title": "Свидетель", "icon": "◐", "category": "games", "metric": "mafia_completed", "cap_events": 360,
               "source_kind": "mafia_v1_terminal", "help": "Завершай матчи в Мафии.", "action_label": "История Мафии"},
    "chests": {"title": "Искатель", "icon": "✦", "category": "collection", "metric": "chest_revealed", "cap_events": 1200,
               "source_kind": "chest_v1_terminal", "help": "Раскрывай сундуки бесплатными или купленными ключами.", "action_label": "К сундукам"},
    "pets": {"title": "Следопыт", "icon": "🐾", "category": "collection", "metric": "pet_activity_completed", "cap_events": 520,
             "source_kind": "pet_v1_terminal", "help": "Завершай походы и экспедиции с питомцами.", "action_label": "К питомцам"},
}

# Finite achievements use concrete milestones, without the legacy weekly gate.
FAMILIES.update({
    'care': {'title':'Заботливый', 'icon':'♡', 'category':'progression', 'metric':'pet_care_day', 'source_kind':'pet_feed_day',
             'thresholds':(1,3,7,14,30,60,120,365), 'measure':('день заботы','дня заботы','дней заботы'),
             'help':'Корми питомцев в разные дни. Несколько питомцев за день считаются одним днём заботы.', 'action_label':'К питомцам'},
    'builder': {'title':'Мастер лагеря', 'icon':'⌂', 'category':'progression', 'metric':'camp_upgrade_started', 'source_kind':'pet_camp_paid_upgrade',
                'thresholds':(1,3,6,10,15), 'measure':('улучшение','улучшения','улучшений'),
                'help':'Начинай улучшения построек лагеря. Засчитывается подтверждённая оплата каждого уровня, включая прошлые улучшения.', 'action_label':'К питомцам'},
    'stylist': {'title':'Мастер образов', 'icon':'✧', 'category':'progression', 'metric':'skin_tier_upgraded', 'source_kind':'skin_v3_paid_upgrade',
                'thresholds':(1,3,6,12,24,48,96), 'measure':('тир образа','тира образов','тиров образов'),
                'help':'Повышай тиры разных образов. Каждая пара образ + новый тир учитывается один раз; подтверждённые прошлые улучшения тоже засчитываются.', 'action_label':'К образам'},
    'quester': {'title':'Дело дня', 'icon':'✓', 'category':'progression', 'metric':'daily_quest_bundle_claimed', 'source_kind':'quest_v1_daily_reward',
                'thresholds':(1,3,7,14,30,60,120,365), 'measure':('дневной комплект','дневных комплекта','дневных комплектов'),
                'help':'Забирай награду за выполненные дневные квесты. Одна награда за день; недельная и общая награды не дублируют прогресс.', 'action_label':'К заданиям'},
})


def max_level(family: str) -> int:
    return len(FAMILIES[family]['thresholds']) if 'thresholds' in FAMILIES[family] else MAX_LEVEL


def required_weeks(family: str, level: int) -> int:
    return 0 if 'thresholds' in FAMILIES[family] else week_threshold(level)


def milestones(family: str) -> tuple[int, ...]:
    return tuple(range(1, max_level(family)+1)) if 'thresholds' in FAMILIES[family] else MILESTONE_LEVELS


MILESTONE_LEVELS: Final = (1, 5, 10, 20, 30, 40)


class AchievementPolicyError(ValueError):
    """Raised when a terminal source cannot advance the achievement contract."""


def family_for_metric(metric: str) -> str:
    for family, definition in FAMILIES.items():
        if definition["metric"] == metric:
            return family
    raise AchievementPolicyError("Unknown achievement terminal metric.")


def event_threshold(family: str, level: int) -> int:
    definition = FAMILIES.get(family)
    if not definition or not 1 <= int(level) <= max_level(family):
        raise AchievementPolicyError("Unknown achievement level.")
    if "thresholds" in definition:
        return definition["thresholds"][int(level)-1]
    return max(int(level), ceil(int(definition["cap_events"]) * (int(level) / MAX_LEVEL) ** 2.25))


def week_threshold(level: int) -> int:
    if not 1 <= int(level) <= MAX_LEVEL:
        raise AchievementPolicyError("Unknown achievement level.")
    return max(int(level), ceil(MAX_ACTIVE_WEEKS * (int(level) / MAX_LEVEL) ** 1.6))


def unlocked_level(family: str, *, completed_events: int, active_weeks: int) -> int:
    if family not in FAMILIES or completed_events < 0 or active_weeks < 0:
        raise AchievementPolicyError("Invalid achievement progress.")
    return max((level for level in range(1, max_level(family) + 1)
                if completed_events >= event_threshold(family, level) and active_weeks >= required_weeks(family, level)), default=0)


def reward_mora(level: int) -> int:
    if not 1 <= int(level) <= MAX_LEVEL:
        raise AchievementPolicyError("Unknown achievement reward level.")
    if level <= 10:
        return 5
    if level <= 20:
        return 8
    if level <= 30:
        return 12
    if level <= 35:
        return 18
    if level <= 39:
        return 25
    return 75


def lifetime_mora() -> int:
    return sum(reward_mora(level) for level in range(1, MAX_LEVEL + 1))


def validate() -> None:
    if len(FAMILIES) != 9 or lifetime_mora() != 515:
        raise AchievementPolicyError("Achievement reward policy changed unexpectedly.")
    for family, definition in FAMILIES.items():
        if definition.get("category") not in {"games", "collection", "progression"} or not definition.get("icon"):
            raise AchievementPolicyError("Achievement family presentation metadata is incomplete.")
        cap = definition.get("cap_events", definition.get("thresholds", (0,))[-1])
        if unlocked_level(family, completed_events=int(cap), active_weeks=MAX_ACTIVE_WEEKS) != max_level(family):
            raise AchievementPolicyError("Level 40 must remain reachable at its stated cap.")
