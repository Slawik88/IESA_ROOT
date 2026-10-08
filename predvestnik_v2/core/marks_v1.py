"""Player marks («метки»): short status tags shown in a profile hero and, for the most important one, next to a name in lists.

Three kinds, and the kind decides who may give a mark (nobody can award themselves anything):

* staff    : follows the global rank of the bot (helper, senior helper, developer). Never stored: promote or demote the rank and the
             mark follows. The only way to wear one is to hold the rank.
* granted  : given by hand by a developer through the console (permission `marks_manage`), with a reason and a log entry; can be taken back.
* earned   : computed from the player's own data every time it is shown (a streak, years with the project, a collection, a season skin).
             Nothing is stored, so it can never go stale and never needs a migration.

Display: weight decides the order (staff first), a hero shows the first three and a count of the rest, a list row shows one glyph.
Everything here is pure; storage is infrastructure/repositories/marks_v1.py, composition is services/marks_v1.py.
"""
from __future__ import annotations

from typing import Final

KINDS: Final = ("staff", "granted", "earned")
# CSS tone of the chip (marks-v3.css); staff tones are fixed colours so that staff are recognisable on any skin
TONES: Final = ("dev", "staff", "gold", "green", "pink", "orange", "violet", "acc")
HERO_LIMIT: Final = 3

# id: (title, glyph, kind, tone, weight, what it means, how it is obtained)
_ROWS: Final = {
    # staff: from users.global_rank (3 is also the developer id)
    "developer":     ("Разработчик", "🌌", "staff", "dev", 1000, "Создаёт и ведёт Предвестника.", "Выдаётся автоматически главному разработчику."),
    "senior_helper": ("Старший хелпер", "⚔️", "staff", "staff", 900, "Следит за порядком во всех чатах бота.", "Выдаётся автоматически вместе с рангом старшего хелпера."),
    "helper":        ("Хелпер", "🛡", "staff", "staff", 800, "Помогает игрокам и следит за порядком.", "Выдаётся автоматически вместе с рангом хелпера."),
    # granted by hand
    "founder":  ("Основатель", "👑", "granted", "gold", 700, "Был с проектом с самого начала.", "Выдают разработчики."),
    "partner":  ("Партнёр", "🤝", "granted", "pink", 650, "Ведёт сообщество или делает контент вместе с проектом.", "Выдают разработчики."),
    "patron":   ("Меценат", "💎", "granted", "orange", 640, "Поддержал проект сверх обычного.", "Выдают разработчики."),
    "champion": ("Чемпион", "🏆", "granted", "gold", 620, "Победил в турнире или событии Предвестника.", "Выдают разработчики после события."),
    "tester":   ("Тестер", "🧪", "granted", "green", 600, "Помогал проверять Предвестника до выхода.", "Выдают разработчики."),
    # earned
    "tier_master": ("Мастер тиров", "⭐", "earned", "violet", 360, "Три образа доведены до своего потолка.", "Прокачайте три образа до максимума."),
    "collector":   ("Коллекционер", "🗂", "earned", "violet", 340, "Собрано десять постоянных образов.", "Соберите десять постоянных образов."),
    "streak30":    ("Серия 30", "🔥", "earned", "orange", 320, "Тридцать дней подряд с проектом.", "Заходите тридцать дней подряд."),
    "veteran":     ("Ветеран", "🎖", "earned", "acc", 300, "С проектом больше года.", "Оставайтесь с проектом год."),
    "chatter":     ("Душа чата", "💬", "earned", "acc", 280, "Больше десяти тысяч сообщений.", "Напишите десять тысяч сообщений в чатах бота."),
    "halloween":   ("Ночь Тыкв", "🎃", "earned", "orange", 200, "Взял образ из сезона «Ночь Тыкв».", "Купите образ из сезона «Ночь Тыкв»."),
    "new_year":    ("Новогодняя Ночь", "🎄", "earned", "green", 190, "Взял образ из сезона «Новогодняя Ночь».", "Купите образ из сезона «Новогодняя Ночь»."),
}
MARKS: Final = {key: {"id": key, "title": r[0], "glyph": r[1], "kind": r[2], "tone": r[3], "weight": r[4], "desc": r[5], "how": r[6]} for key, r in _ROWS.items()}

# earned rule: id -> (fact, need). `seasons` is a set of season ids the player owns a skin from.
EARNED_RULES: Final = {
    "tier_master": ("maxed", 3), "collector": ("owned_permanent", 10), "streak30": ("streak", 30), "veteran": ("joined_days", 365),
    "chatter": ("messages", 10_000), "halloween": ("season:halloween", 1), "new_year": ("season:new_year", 1),
}
GRANTABLE: Final = tuple(k for k, m in MARKS.items() if m["kind"] == "granted")


def staff_mark(global_rank: int, *, is_developer: bool = False) -> str | None:
    """Mark id for a bot role, or None for an ordinary player."""
    if is_developer or int(global_rank or 0) >= 3:
        return "developer"
    return {2: "senior_helper", 1: "helper"}.get(int(global_rank or 0))


def _have(facts: dict, fact: str) -> int:
    if fact.startswith("season:"):
        return 1 if fact.split(":", 1)[1] in (facts.get("seasons") or ()) else 0
    return max(0, int(facts.get(fact) or 0))


def earned_state(facts: dict) -> list[dict]:
    """Every earned mark with its progress: {id, done, have, need}. Progress never exceeds the need."""
    out = []
    for mark_id, (fact, need) in EARNED_RULES.items():
        have = _have(facts, fact)
        out.append({"id": mark_id, "done": have >= need, "have": min(have, need), "need": need})
    return out


def public(mark_id: str) -> dict:
    """What a client may see of a mark (no weight, no internal fields)."""
    m = MARKS[mark_id]
    return {"id": m["id"], "title": m["title"], "glyph": m["glyph"], "kind": m["kind"], "tone": m["tone"], "desc": m["desc"]}


def ordered(ids) -> list[dict]:
    """Unique mark ids, heaviest first, as public dicts. Unknown ids (a mark retired from the catalog) are skipped."""
    seen = dict.fromkeys(i for i in ids if i in MARKS)
    return [public(i) for i in sorted(seen, key=lambda i: -MARKS[i]["weight"])]


def compose(*, global_rank: int, is_developer: bool, granted_ids, facts: dict) -> list[dict]:
    ids: list[str] = []
    staff = staff_mark(global_rank, is_developer=is_developer)
    if staff:
        ids.append(staff)
    ids.extend(i for i in granted_ids if i in MARKS and MARKS[i]["kind"] == "granted")
    ids.extend(s["id"] for s in earned_state(facts) if s["done"])
    return ordered(ids)
