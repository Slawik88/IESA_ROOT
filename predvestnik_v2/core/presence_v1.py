"""Presence V1: what other players may know about when a player was last around.

Three levels, chosen by the player (default: approximate):
  everyone  exact: "в сети" / "был(а) 12 минут назад"
  approx    only a coarse bucket: "недавно", "на этой неделе", "в этом месяце", "давно"; "в сети" is never shown
  nobody    nothing at all
Reciprocity, the same as in messengers: a player who hides their own time (nobody) sees other players' time only coarsely.
The server turns a timestamp into a label; a hidden or coarse owner never has an exact time leave the API.
"""
from __future__ import annotations

from datetime import datetime, timedelta

LEVELS = ("everyone", "approx", "nobody")
DEFAULT_LEVEL = "approx"
ONLINE_WINDOW = timedelta(minutes=3)


def _plural(n: int, one: str, few: str, many: str) -> str:
    m, d = n % 100, n % 10
    return many if 10 < m < 20 else one if d == 1 else few if 1 < d < 5 else many


def normalize(level: str | None) -> str:
    return level if level in LEVELS else DEFAULT_LEVEL


def visible_detail(owner_level: str, viewer_level: str) -> str:
    """'exact', 'approx' or 'none': how much of the owner's time this viewer may see."""
    owner, viewer = normalize(owner_level), normalize(viewer_level)
    if owner == "nobody":
        return "none"
    if owner == "approx" or viewer == "nobody":
        return "approx"
    return "exact"


def approx_label(age: timedelta) -> str:
    days = age.total_seconds() / 86400
    return "был(а) недавно" if days <= 3 else "был(а) на этой неделе" if days <= 7 else "был(а) в этом месяце" if days <= 30 else "был(а) давно"


def exact_label(age: timedelta, last_seen: datetime) -> tuple[str, str]:
    """(state, label) for the exact level."""
    if age <= ONLINE_WINDOW:
        return "online", "в сети"
    minutes = int(age.total_seconds() // 60)
    if minutes < 60:
        return "ago", f"был(а) {minutes} {_plural(minutes, 'минуту', 'минуты', 'минут')} назад"
    hours = minutes // 60
    if hours < 24:
        return "ago", f"был(а) {hours} {_plural(hours, 'час', 'часа', 'часов')} назад"
    days = hours // 24
    if days == 1:
        return "ago", "был(а) вчера"
    if days <= 30:
        return "ago", f"был(а) {days} {_plural(days, 'день', 'дня', 'дней')} назад"
    return "ago", f"был(а) {last_seen:%d.%m.%Y}"


def describe(last_seen: datetime | None, owner_level: str, viewer_level: str, now: datetime) -> dict | None:
    """What a viewer sees: None (hide the line) or {state, label}. Never carries a timestamp."""
    detail = visible_detail(owner_level, viewer_level)
    if detail == "none" or last_seen is None:
        return None
    age = max(timedelta(0), now - last_seen)
    if detail == "approx":
        return {"state": "recent", "label": approx_label(age)}
    state, label = exact_label(age, last_seen)
    return {"state": state, "label": label}
