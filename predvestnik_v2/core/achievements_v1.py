"""Pure, long-horizon achievement rules for the approved activity set."""
from __future__ import annotations

from math import ceil
from typing import Final


POLICY_VERSION: Final = "achievements-v1-2026-09-13-2"
MAX_LEVEL: Final = 40
MAX_ACTIVE_WEEKS: Final = 156

# These are deliberately terminal server metrics, never page views, messages,
# client scores, quest progress or historical counters.
FAMILIES: Final = {
    "rhythm": {"title": "Пульс", "icon": "ᚱ", "category": "games", "metric": "rhythm_completed", "cap_events": 2400,
               "source_kind": "rhythm_v2_terminal", "help": "Завершай забеги в Ритме.", "action_label": "Открыть Ритм"},
    "minesweeper": {"title": "Контур", "icon": "▦", "category": "games", "metric": "minesweeper_completed", "cap_events": 1600,
                      "source_kind": "minesweeper_v2_terminal", "help": "Завершай партии в Сапёре.", "action_label": "Открыть Сапёр"},
    "mafia": {"title": "Свидетель", "icon": "◐", "category": "games", "metric": "mafia_completed", "cap_events": 360,
               "source_kind": "mafia_v1_terminal", "help": "Завершай матчи в Мафии.", "action_label": "История Мафии"},
    "chests": {"title": "Искатель", "icon": "✦", "category": "collection", "metric": "chest_revealed", "cap_events": 1200,
               "source_kind": "chest_v1_terminal", "help": "Раскрывай сундуки бесплатными или купленными ключами.", "action_label": "К сундукам"},
    "pets": {"title": "Следопыт", "icon": "🐾", "category": "collection", "metric": "pet_activity_completed", "cap_events": 520,
             "source_kind": "pet_v1_terminal", "help": "Завершай походы и экспедиции с питомцами.", "action_label": "К питомцам"},
}

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
    if not definition or not 1 <= int(level) <= MAX_LEVEL:
        raise AchievementPolicyError("Unknown achievement level.")
    return max(int(level), ceil(int(definition["cap_events"]) * (int(level) / MAX_LEVEL) ** 2.25))


def week_threshold(level: int) -> int:
    if not 1 <= int(level) <= MAX_LEVEL:
        raise AchievementPolicyError("Unknown achievement level.")
    return max(int(level), ceil(MAX_ACTIVE_WEEKS * (int(level) / MAX_LEVEL) ** 1.6))


def unlocked_level(family: str, *, completed_events: int, active_weeks: int) -> int:
    if family not in FAMILIES or completed_events < 0 or active_weeks < 0:
        raise AchievementPolicyError("Invalid achievement progress.")
    return max((level for level in range(1, MAX_LEVEL + 1)
                if completed_events >= event_threshold(family, level) and active_weeks >= week_threshold(level)), default=0)


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
    if len(FAMILIES) != 5 or lifetime_mora() != 515:
        raise AchievementPolicyError("Achievement reward policy changed unexpectedly.")
    for family, definition in FAMILIES.items():
        if definition.get("category") not in {"games", "collection"} or not definition.get("icon"):
            raise AchievementPolicyError("Achievement family presentation metadata is incomplete.")
        if unlocked_level(family, completed_events=int(definition["cap_events"]), active_weeks=MAX_ACTIVE_WEEKS) != MAX_LEVEL:
            raise AchievementPolicyError("Level 40 must remain reachable at its stated cap.")
